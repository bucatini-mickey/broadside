# Life aboard: watches, sleep, meals, the weather on your back - the day
# a sailor actually lives, rather than the minute of action he is in.
#
# A ship's company is divided into two watches, starboard and larboard, and
# the day into four-hour watches (engine/clock.py). The watch on deck works
# the ship; the watch below sleeps, eats, mends clothes and grumbles. So:
#
#   * every man belongs to a watch, and the watch below really does go
#     below - off the weather deck, out of the view, out of the way - and
#     comes up again when his watch is called;
#   * at night, men below sleep, and sleeping is how fatigue is paid off;
#   * meals are served at the proper hours and eat real provisions out of
#     real casks, so a hungry ship is a ship whose stores have run down;
#   * rain and squalls wet the men on deck, which tires them and sours them.
#
# Beating to quarters overrides all of it: every man turns out, whatever
# the hour, which is why night actions ruined a crew for days.
#
# See docs/design/18_life_aboard.md.

from __future__ import annotations

import random
from dataclasses import dataclass

from broadside.engine.clock import watch_and_bells
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.people import components as pc
from broadside.sim.people.psyche import appraise

# Which four-hour watch each ship's watch (0 starboard, 1 larboard) has on
# deck. The dog watches are deliberately uneven so the rotation shifts each
# day - the reason they existed.
WATCH_ON_DECK = {
    "Middle Watch": 1,
    "Morning Watch": 0,
    "Forenoon Watch": 1,
    "Afternoon Watch": 0,
    "First Dog Watch": 1,
    "Last Dog Watch": 0,
    "First Watch": 1,
}

MEALS = {
    8.0: ("breakfast", {"oatmeal": 0.43, "ship's biscuit": 0.33}),
    12.0: ("dinner", {"salt beef": 0.57, "dried peas": 0.29, "ship's biscuit": 0.34}),
    17.0: ("supper", {"ship's biscuit": 0.33, "cheese": 0.14, "butter": 0.14}),
}
MEAL_RELIEF = 0.55
DRINK_RELIEF = 0.75
SLEEP_FATIGUE_PER_HOUR = -0.42  # a watch below pays off a watch on deck twice over
WORK_FATIGUE_PER_HOUR = 0.07
WET_FATIGUE_PER_HOUR = 0.05
NIGHT_LIGHT = 0.3


@dataclass
class Watch:
    """Which watch a man keeps. -1 for the idlers - the cook, the carpenter,
    the surgeon and the officers who are not in the watch bill but turn out
    when wanted."""

    side: int = 0


@dataclass
class Asleep:
    since_s: float = 0.0


IDLER_ROLES = {"Captain", "Surgeon", "Cook's Mate", "Carpenter's Mate", "Sailmaker's Mate", "Loblolly Boy", "Marine", "Lookout"}


def assign_watches(world, ship: int, rng: random.Random) -> None:
    """Draw up the watch bill: every hand into one watch or the other, the
    idlers left out of it."""
    i = 0
    for ent, crew in world.get_component(c.CrewMember):
        if crew.ship != ship:
            continue
        if world.has_component(ent, Watch):
            continue
        role = world.try_component(ent, c.Role)
        title = role.title if role is not None else ""
        if title in IDLER_ROLES:
            world.add_component(ent, Watch(side=-1))
            continue
        world.add_component(ent, Watch(side=i % 2))
        i += 1


def _hour(state) -> float:
    return (state.start_hour + state.now_s / 3600.0) % 24.0


def _free_tile(layout, taken: set, rng: random.Random):
    tiles = layout.walkable_tiles()
    for _ in range(24):
        t = tiles[rng.randrange(len(tiles))]
        if t not in taken:
            return t
    return tiles[0] if tiles else (0, 0)


def send_below(world, ent: int, deck: str = "berth") -> None:
    if world.has_component(ent, c.DeckPosition):
        world.remove_component(ent, c.DeckPosition)
    if not world.has_component(ent, c.Below):
        world.add_component(ent, c.Below(deck=deck))
    task = world.try_component(ent, c.CrewTask)
    if task is not None:
        task.kind, task.station, task.station_kind, task.path = "idle", None, "", []


def bring_up(world, ent: int, layout, taken: set, rng: random.Random) -> None:
    if world.has_component(ent, c.Below):
        world.remove_component(ent, c.Below)
    if world.has_component(ent, Asleep):
        world.remove_component(ent, Asleep)
    if not world.has_component(ent, c.DeckPosition):
        x, y = _free_tile(layout, taken, rng)
        world.add_component(ent, c.DeckPosition(x=x, y=y))
        taken.add((x, y))
    if not world.has_component(ent, c.CrewTask):
        world.add_component(ent, c.CrewTask(cooldown_ticks=rng.randint(0, 30)))


def serve_meal(state, ship: int, goods: dict, mouths: int) -> float:
    """Eat a meal out of the ship's stores. Returns the share of the ration
    actually served, 0..1 - a ship can only feed her people what she has."""
    from broadside.sim.items import Contents, Item, Stowed

    world = state.world
    served = []
    for commodity, per_man in goods.items():
        want = per_man * mouths
        got = 0.0
        for _e, (item, stw, cont) in world.get_components(Item, Stowed, Contents):
            if stw.ship != ship or commodity not in cont.goods:
                continue
            take = min(cont.goods[commodity], want - got)
            if take <= 0:
                continue
            cont.goods[commodity] = round(cont.goods[commodity] - take, 2)
            got += take
            if got >= want - 1e-6:
                break
        served.append(0.0 if want <= 0 else got / want)
    return sum(served) / max(1, len(served))


def life_system(state, dt: float) -> None:
    """Watches, sleep and meals. Runs a few times a minute, not every tick."""
    world = state.world
    rng = state.rng.stream("life")
    hour = _hour(state)
    prev = getattr(state, "_life_last_hour", None)
    state._life_last_hour = hour
    watch_name, _bells = watch_and_bells(hour)
    on_deck_side = WATCH_ON_DECK.get(watch_name, 0)
    night = state.atmosphere.light < NIGHT_LIGHT
    wet = state.atmosphere.rain > 0.2

    def crossed(h: float) -> bool:
        if prev is None:
            return False
        return (prev < h <= hour) or (prev > hour and (h > prev or h <= hour))

    for ship, (body, orders) in world.get_components(c.ShipBody, c.ShipOrders):
        layout = body.layout
        company = []
        for ent, crew in world.get_component(c.CrewMember):
            if crew.ship == ship:
                company.append(ent)
        if not company:
            continue
        if not world.has_component(company[0], Watch):
            assign_watches(world, ship, rng)

        taken = {
            (p.x, p.y)
            for _e, (cm, p) in world.get_components(c.CrewMember, c.DeckPosition)
            if cm.ship == ship
        }
        # --- the watch on deck -------------------------------------------
        for ent in company:
            pbody = world.try_component(ent, pc.Body)
            if pbody is not None and not pbody.alive:
                continue
            watch = world.try_component(ent, Watch)
            if watch is None:
                continue
            wanted_up = orders.quarters or watch.side == -1 or watch.side == on_deck_side
            below = world.has_component(ent, c.Below)
            if wanted_up and below:
                bring_up(world, ent, layout, taken, rng)
            elif not wanted_up and not below and not world.has_component(ent, c.Aloft):
                send_below(world, ent)

            needs = world.try_component(ent, c.Needs)
            if needs is None:
                continue
            asleep = world.has_component(ent, Asleep)
            if below and not orders.quarters:
                # Below in the night, a man turns in; by day he rests, mends
                # his clothes and spins yarns.
                if night and not asleep and needs.fatigue > 0.1:
                    world.add_component(ent, Asleep(since_s=state.now_s))
                    asleep = True
                rate = SLEEP_FATIGUE_PER_HOUR if asleep else SLEEP_FATIGUE_PER_HOUR * 0.35
            else:
                if asleep:
                    world.remove_component(ent, Asleep)
                rate = WORK_FATIGUE_PER_HOUR + (WET_FATIGUE_PER_HOUR if wet else 0.0)
            needs.fatigue = max(0.0, min(1.0, needs.fatigue + rate * dt / 3600.0))
            if asleep and needs.fatigue <= 0.02:
                world.remove_component(ent, Asleep)
                appraise(state, ent, "rested")
            elif wet and not below:
                appraise(state, ent, "soaked", dt / 600.0)

        # --- meals ---------------------------------------------------------
        for meal_hour, (name, goods) in MEALS.items():
            if not crossed(meal_hour):
                continue
            alive = [e for e in company if (world.try_component(e, pc.Body) is None or world.component_for_entity(e, pc.Body).alive)]
            share = serve_meal(state, ship, goods, len(alive))
            for ent in alive:
                needs = world.try_component(ent, c.Needs)
                if needs is not None:
                    needs.hunger = max(0.0, needs.hunger - MEAL_RELIEF * share)
                    needs.thirst = max(0.0, needs.thirst - DRINK_RELIEF * share)
                psy = world.try_component(ent, pc.Psyche)
                if psy is not None:
                    if share > 0.8:
                        appraise(state, ent, "fed")
                    elif share < 0.4:
                        psy.grievance = min(1.0, psy.grievance + 0.03)
                        appraise(state, ent, "short_commons")
            if ship == state.player_ship:
                if share > 0.8:
                    state.say(f"Hands to {name}.", "info")
                elif share > 0.05:
                    state.say(f"Short commons at {name}: the ship cannot feed her people properly.", "alert")
                else:
                    state.say(f"No {name} today - the stores are out.", "alert")
