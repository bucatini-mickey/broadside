# Actions: what a person can do to the things around him.
#
# Any person - the player's captain included - can perform an action on an
# object he's standing next to. An action has a duration; while it runs he
# is busy (can't walk away), and when it completes its effect happens. The
# same functions serve the player (walk mode in the terminal app) and
# scripts (scenarios, and later the crew's own task system), so the player
# is just one more person acting in the world, like the AI.
#
# For now the objects are a ship's guns - worked through the period drill,
# one order at a time, from the same table of steps the gun crews use
# (sim/gundrill.py) - and the items stowed on deck (shot garlands, powder
# cartridge boxes, provision casks, the scuttlebutt). Loading takes a
# cartridge from a box and a ball from the garland: items are consumed, not
# conjured, and a job takes as long as the man doing it needs. The captain
# working a 24-pounder single-handed will find running her out very slow
# indeed, which is the point.

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.items import Contents, Item, Stowed


@dataclass
class Activity:
    """What a person is busy doing right now."""

    label: str
    remaining_s: float
    total_s: float
    effect: Callable = None  # called with state on completion


@dataclass
class Action:
    label: str
    duration_s: float
    effect: Callable  # (state) -> None
    note: str = ""


def _near(ax: int, ay: int, bx: int, by: int, r: int = 1) -> bool:
    return abs(ax - bx) <= r and abs(ay - by) <= r


def _nearby_goods(world, ship: int, x: int, y: int, commodity: str):
    """(entity, Contents) of the nearest stowed container holding `commodity`
    within reach, or (None, None)."""
    best = None
    for ent, (item, st, cont) in world.get_components(Item, Stowed, Contents):
        if st.ship != ship or st.x is None or not _near(st.x, st.y, x, y):
            continue
        if cont.goods.get(commodity, 0) > 0:
            d = abs(st.x - x) + abs(st.y - y)
            if best is None or d < best[0]:
                best = (d, ent, cont)
    return (best[1], best[2]) if best else (None, None)


def _shot_kind(cont: Contents) -> Optional[str]:
    for k, q in cont.goods.items():
        if "shot" in k and q > 0:
            return k
    return None


def available_actions(state, actor: int) -> list:
    """Every action `actor` could start where he stands."""
    world = state.world
    crew = world.component_for_entity(actor, c.CrewMember)
    pos = world.try_component(actor, c.DeckPosition)
    if pos is None:
        return []
    ship = crew.ship
    body = world.component_for_entity(ship, c.ShipBody)
    battery = world.try_component(ship, c.Battery)
    out: list[Action] = []
    if battery is not None:
        for gs in battery.guns:
            spec = body.layout.guns[gs.index]
            if not spec.on_deck or not _near(pos.x, pos.y, spec.x, spec.y):
                continue
            out.extend(_gun_actions(state, actor, ship, spec, gs))
    for ent, (item, st) in world.get_components(Item, Stowed):
        if st.ship == ship and st.x is not None and _near(pos.x, pos.y, st.x, st.y):
            cont = world.try_component(ent, Contents)
            goods = ", ".join(f"{q:g} {cont.unit} {k}" for k, q in cont.goods.items()) if cont else ""
            out.append(Action(f"Inspect the {item.kind} ({goods})", 1.0, lambda st_, k=item.kind, g=goods: st_.say(f"The {k}: {g}.", "info")))
            if item.kind == "scuttlebutt" and cont and cont.goods.get("fresh water", 0) > 0.5:
                out.append(Action("Drink from the scuttlebutt", 4.0, lambda st_, cont_=cont, a=actor: _drink(st_, a, cont_)))
            if item.kind == "signal locker":
                out.extend(_signal_actions(state, actor, ship))
    return out


# Signals a captain sends most: the rest of the book is read from the locker.
COMMON_SIGNALS = (1, 4, 7, 11, 12)


def _signal_actions(state, actor: int, ship: int) -> list:
    """Sending a signal is a job for a midshipman at the locker: the flags
    have to be bent on and hoisted before anyone can read them."""
    from broadside.sim.systems.signals import SIGNAL_BOOK, Signals, haul_down, hoist, hoist_time

    world = state.world
    skill = _skill(world, actor, "seamanship")
    out = [Action("Read the signal book", 2.0, lambda st: st.say("Signal book: " + "; ".join(f"No. {n} {t}" for n, t in sorted(SIGNAL_BOOK.items())), "info"))]
    sig = world.try_component(ship, Signals)
    if sig is not None and sig.hoisted:
        out.append(Action(f"Haul down signal No. {sig.hoisted}", 6.0, lambda st: haul_down(st, ship)))
    for n in COMMON_SIGNALS:
        out.append(Action(f"Hoist signal No. {n}: {SIGNAL_BOOK[n]}", hoist_time(skill), lambda st, n_=n: hoist(st, ship, n_)))
    return out


def _gun_actions(state, actor, ship, spec, gs) -> list:
    """The gun's drill, one order at a time, plus laying her by hand."""
    from broadside.sim import gundrill as gd

    world = state.world
    acts: list[Action] = []
    step = gd.next_step(gs)
    if step is not None:
        hands = 1 + sum(1 for m in gd.crew_at_guns(state, ship).get(gs.index, []) if m[0] != actor)
        shot_kg, _d, _v = gundrill_ballistics(spec.kind)
        secs = gd.step_time(
            step,
            skill=_skill(world, actor, step.skill),
            fatigue=_fatigue(world, actor),
            physique_=gd.physique(world, actor),
            shot_kg=shot_kg,
            gun_kg=gd.gun_mass_kg(spec.kind),
            hands=hands,
            own_station=True,
        )
        if step.takes and not _store_within_reach(state, ship, spec, step.takes):
            want = "powder cartridge" if step.takes == "powder cartridge" else "round shot"
            acts.append(Action(f"(no {want} within reach)", 0.0, lambda st: None, note="unavailable"))
        else:
            label = f"{step.label} ({spec.kind})"
            acts.append(Action(label, secs, _drill_effect(ship, spec, gs, step, actor), note=step.key))
    acts.append(Action("Train the gun forward 0.5 deg", 1.5, _aim(gs, train=+0.5)))
    acts.append(Action("Train the gun aft 0.5 deg", 1.5, _aim(gs, train=-0.5)))
    acts.append(Action("Elevate 0.5 deg (quoin out)", 1.5, _aim(gs, elev=+0.5)))
    acts.append(Action("Depress 0.5 deg (quoin in)", 1.5, _aim(gs, elev=-0.5)))
    if gd.ready(gs):
        acts.append(Action("FIRE!", 0.5, lambda st: _fire(st, ship, gs)))
    return acts


def gundrill_ballistics(kind: str):
    from broadside.sim.systems.ballistics import gun_ballistics

    return gun_ballistics(kind)


def _skill(world, ent: int, skill: str) -> float:
    from broadside.sim.people import components as pc

    sk = world.try_component(ent, pc.Skills)
    return sk.get(skill) if sk is not None else 0.4


def _fatigue(world, ent: int) -> float:
    needs = world.try_component(ent, c.Needs)
    return needs.fatigue if needs is not None else 0.0


def _store_within_reach(state, ship: int, spec, what: str) -> bool:
    world = state.world
    for _ent, (item, st, cont) in world.get_components(Item, Stowed, Contents):
        if st.ship != ship or st.x is None or abs(st.x - spec.x) > 2 or abs(st.y - spec.y) > 2:
            continue
        for kind, qty in cont.goods.items():
            if qty > 0 and ((what == "shot" and "shot" in kind) or kind == what):
                return True
    return False


def _drill_effect(ship, spec, gs, step, actor):
    """Completing a step by hand does exactly what a crew doing it does."""
    from broadside.sim import gundrill as gd

    def effect(state):
        if step.takes and not gd.take_store(state, ship, spec.x, spec.y, step.takes):
            state.say("Nothing left to hand.", "gun")
            return
        if step.key == "laid":
            gd.lay_gun(state, ship, spec, gs, _skill(state.world, actor, "gunlaying"))
        else:
            setattr(gs, step.key, step.want)
        gs.loaded = gd.ready(gs)
        needs = state.world.try_component(actor, c.Needs)
        if needs is not None:
            needs.fatigue = min(1.0, needs.fatigue + gd.fatigue_cost(step))
        state.say(_drill_says.get(step.key, step.label + "."), "gun")

    return effect


_drill_says = {
    "needs_sponge": "Sponged out - clear of embers.",
    "charged": "Cartridge in the muzzle.",
    "charge_rammed": "Cartridge rammed home.",
    "wadded": "Wad on the charge.",
    "shotted": "Shot in the muzzle.",
    "rammed": "Shot rammed home.",
    "run_out": "Run out - the muzzle is through the port.",
    "primed": "Primed. She wants only laying and the word.",
    "laid": "Laid on the mark.",
}


def _aim(gs, train: float = 0.0, elev: float = 0.0):
    """Laying her yourself, by handspike and quoin, counts as laying her."""
    from broadside.sim import gundrill as gd

    def effect(state):
        if train:
            gs.train_deg = max(-gd.MAX_TRAIN_DEG, min(gd.MAX_TRAIN_DEG, gs.train_deg + train))
        if elev:
            gs.elevation_deg = max(gd.MIN_ELEVATION_DEG, min(gd.MAX_ELEVATION_DEG, gs.elevation_deg + elev))
        gs.laid = True
        gs.loaded = gd.ready(gs)

    return effect


def _set(obj, **kw) -> None:
    for k, v in kw.items():
        setattr(obj, k, v)


def _fire(state, ship, gs) -> None:
    from broadside.sim.systems.gunnery import discharge

    elev, train = gs.elevation_deg, gs.train_deg
    discharge(state, ship, gs.index, gs)
    state.say(f"FIRE! (elevation {elev:+.1f} deg, trained {train:+.1f} deg)", "gun")


def _drink(state, actor, cont: Contents) -> None:
    cont.goods["fresh water"] = round(cont.goods["fresh water"] - 0.5, 1)
    needs = state.world.try_component(actor, c.Needs)
    if needs is not None:
        needs.thirst = max(0.0, needs.thirst - 0.4)


def start_action(state, actor: int, action: Action) -> bool:
    world = state.world
    if action.note == "unavailable" or world.has_component(actor, Activity):
        return False
    if action.duration_s <= 0:
        action.effect(state)
        return True
    world.add_component(actor, Activity(action.label, action.duration_s, action.duration_s, action.effect))
    return True


def perform(state, actor: int, prefix: str) -> bool:
    """Start the first available action whose label starts with `prefix`
    (case-insensitive). Used by scripts; the player picks from the menu."""
    for a in available_actions(state, actor):
        if a.label.lower().startswith(prefix.lower()) and a.note != "unavailable":
            return start_action(state, actor, a)
    return False


def activity_system(state, dt: float) -> None:
    world = state.world
    for ent, act in list(world.get_component(Activity)):
        act.remaining_s -= dt
        if act.remaining_s <= 0:
            world.remove_component(ent, Activity)
            if act.effect is not None:
                act.effect(state)


def step_actor(state, actor: int, dx: int, dy: int) -> bool:
    """Move a person one tile if the deck allows (and he isn't busy)."""
    world = state.world
    if world.has_component(actor, Activity):
        return False
    crew = world.component_for_entity(actor, c.CrewMember)
    pos = world.component_for_entity(actor, c.DeckPosition)
    layout = world.component_for_entity(crew.ship, c.ShipBody).layout
    nx, ny = pos.x + dx, pos.y + dy
    if layout.tile(nx, ny) not in sl.WALKABLE:
        return False
    if dx and dy and not (layout.tile(pos.x + dx, pos.y) in sl.WALKABLE and layout.tile(pos.x, pos.y + dy) in sl.WALKABLE):
        return False
    pos.x, pos.y = nx, ny
    task = world.try_component(actor, c.CrewTask)
    if task is not None and task.station_kind == "post":
        task.station = (nx, ny)  # he stays where he walked to
        task.path = []
    return True


def walk_to(state, actor: int, tile: tuple) -> None:
    """Send a person walking (along a deck path) to a tile."""
    task = state.world.component_for_entity(actor, c.CrewTask)
    task.kind, task.station, task.path = "station", tuple(tile), []
    if not task.station_kind:
        task.station_kind = "post"
