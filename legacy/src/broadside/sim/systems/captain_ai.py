# A captain's mind.
#
# Until now there was none: an enemy ship followed waypoints laid down by
# the scenario and fired if the scenario told her to. Now every ship that is
# not yours can have a captain, and he is a person like the rest - with
# skills and a character, and no more knowledge of the world than his own
# ship's lookouts have given him (`Contacts`: knowledge, not truth).
#
# He is deliberately simple, and deliberately *parameterised*, because the
# parameters are the point:
#
#   skill         how well he handles his ship - the station he keeps, the
#                 range he chooses, whether he takes the weather gage
#   intelligence  how quickly he takes a situation in: his whole thinking
#                 loop runs slower when he is dull, so a stupid captain is
#                 always a few seconds behind the action
#   aggression    how readily he closes, and how close
#   caution       when he breaks off: damage, casualties, odds
#   discipline    whether he obeys a signal he dislikes, or claps on more
#                 sail and does what he thinks best
#
# What he decides is a *mission*; the mission is then executed by setting
# the same orders a player sets (helm, sail, quarters, fire), so nothing
# here can do anything the player could not do.
#
# See docs/design/19_fleet_and_captains.md.

from __future__ import annotations

import math
from dataclasses import dataclass, field

from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.units import angle_delta, bearing_degrees

# Missions a captain can be on.
HOLD = "hold"  # keep the course he has
STATION = "station"  # keep station on his leader
ENGAGE = "engage"  # fight the ship he has chosen
CHASE = "chase"  # run her down
WITHDRAW = "withdraw"  # haul off out of it
CLOSE = "close"  # come within hail and stay there
HEAVE_TO = "heave_to"  # lie quiet

PREFERRED_RANGE_M = (420.0, 90.0)  # cautious ... yardarm to yardarm
THINK_BASE_S = 3.0
THINK_DULL_S = 14.0
BREAK_OFF_HULL = 0.55
BREAK_OFF_DEAD_SHARE = 0.3


@dataclass
class ShipCaptainAI:
    """The captain of a ship that is not yours, and what he is like."""

    skill: float = 0.5
    intelligence: float = 0.5
    aggression: float = 0.5
    caution: float = 0.5
    discipline: float = 0.6
    mission: str = HOLD
    leader: int = -1  # whose motions he conforms to
    station_bearing: float = 180.0  # relative to the leader's head
    station_m: float = 220.0
    target: int = -1
    signal_pending: int = 0  # a signal read but not yet acted on
    signal_from: int = -1  # whose signal it was: his admiral, for this order
    signal_at_s: float = -1.0
    # An order from his admiral holds him to it, for as long as a man of his
    # discipline holds an order: without this he simply reverts to his own
    # judgement at the next thought, and signalling is pointless.
    ordered_mission: str = ""
    ordered_until_s: float = -1.0
    last_think_s: float = -1e9
    said: list = field(default_factory=list)

    @property
    def think_interval_s(self) -> float:
        return THINK_BASE_S + THINK_DULL_S * (1.0 - self.intelligence)

    @property
    def wants_range_m(self) -> float:
        far, near = PREFERRED_RANGE_M
        return far + (near - far) * self.aggression


def from_person(person, rank: str = "captain") -> ShipCaptainAI:
    """Build a captain's mind from the person generated for him, so his
    tactics come from the same skills and character as everything else."""
    sk = person.skills
    pers = person.personality
    return ShipCaptainAI(
        skill=0.5 * sk.get("navigation") + 0.3 * sk.get("seamanship") + 0.2 * sk.get("gunlaying"),
        intelligence=0.45 * sk.get("leadership") + 0.3 * sk.get("navigation") + 0.25 * pers.discipline,
        aggression=0.6 * pers.bravery + 0.25 * pers.ambition + 0.15 * (1.0 - pers.resilience),
        caution=0.7 * (1.0 - pers.bravery) + 0.3 * (1.0 - pers.ambition),
        discipline=pers.discipline,
    )


# --- what he knows --------------------------------------------------------


def _known_enemies(state, ship: int) -> list:
    """(distance, entity, where he last saw her) for every hostile he knows
    of - from his own contact records, not from the world."""
    world = state.world
    mine = world.try_component(ship, c.Faction)
    pos = world.try_component(ship, c.WorldPosition)
    contacts = world.try_component(ship, c.Contacts)
    if mine is None or pos is None or contacts is None:
        return []
    out = []
    for ent, rec in contacts.records.items():
        theirs = world.try_component(ent, c.Faction)
        if theirs is None or theirs.name == mine.name or "neutral" in (mine.name, theirs.name):
            continue
        if rec.status not in ("hull", "topsails", "reported"):
            continue
        d = math.hypot(rec.x_m - pos.x_m, rec.y_m - pos.y_m)
        out.append((d, ent, (rec.x_m, rec.y_m)))
    out.sort()
    return out


def _strength(state, ship: int) -> float:
    """A rough count of what she can throw, for comparing odds."""
    battery = state.world.try_component(ship, c.Battery)
    hull = state.world.try_component(ship, c.Hull)
    if battery is None:
        return 0.0
    guns = len(battery.guns)
    return guns * (hull.integrity if hull is not None else 1.0)


def _hurt(state, ship: int) -> tuple:
    """(hull integrity, share of her people down, morale)."""
    world = state.world
    hull = world.try_component(ship, c.Hull)
    alive = dead = 0
    for ent, crew in world.get_component(c.CrewMember):
        if crew.ship != ship:
            continue
        body = world.try_component(ent, pc.Body)
        if body is None:
            alive += 1
        elif body.alive:
            alive += 1
        else:
            dead += 1
    share = dead / max(1, alive + dead)
    from broadside.sim.people.psyche import ShipMorale

    sm = world.try_component(ship, ShipMorale)
    return (hull.integrity if hull is not None else 1.0), share, (sm.morale if sm is not None else 0.2)


# --- deciding -------------------------------------------------------------


def decide(state, ship: int, ai: ShipCaptainAI) -> None:
    """Choose a mission. This is the whole of his tactical thinking, and it
    is meant to stay short: the character and the skills do the work."""
    integrity, lost, morale = _hurt(state, ship)
    enemies = _known_enemies(state, ship)

    # A signal he has read and not yet acted on - and whether he will.
    if ai.signal_pending:
        number = ai.signal_pending
        ai.signal_pending = 0
        obey_signal(state, ship, ai, number)
        return

    # Beaten about enough, and a cautious man hauls off.
    if integrity < BREAK_OFF_HULL + 0.25 * ai.caution - 0.15 * ai.aggression or lost > BREAK_OFF_DEAD_SHARE * (1.4 - ai.caution):
        ai.mission = WITHDRAW
        return
    if morale < -0.45 and ai.discipline < 0.7:
        ai.mission = WITHDRAW
        return

    # An order from the admiral stands until it runs out, or until he is in
    # no state to carry it out.
    if ai.ordered_mission and state.now_s < ai.ordered_until_s:
        ai.mission = ai.ordered_mission
        if ai.mission in (ENGAGE, CHASE) and ai.target < 0:
            enemies = _known_enemies(state, ship)
            if enemies:
                ai.target = enemies[0][1]
            else:
                ai.mission = STATION if ai.leader >= 0 else HOLD
        return

    if not enemies:
        ai.mission = STATION if ai.leader >= 0 else HOLD
        ai.target = -1
        return

    dist, ent, _where = enemies[0]
    ai.target = ent
    mine, theirs = _strength(state, ship), _strength(state, ent)
    odds = mine / max(0.2, theirs)
    # The odds he needs before he will fight: a bold man needs none.
    want = 0.75 + 0.5 * ai.caution - 0.5 * ai.aggression
    if odds < want and dist < 1200.0:
        ai.mission = WITHDRAW
    elif dist > 2500.0:
        ai.mission = CHASE if ai.aggression > 0.4 else (STATION if ai.leader >= 0 else HOLD)
    else:
        ai.mission = ENGAGE


# --- carrying it out ------------------------------------------------------


def _steer(state, ship: int, heading: float) -> None:
    helm = state.world.try_component(ship, c.Helm)
    if helm is not None:
        helm.waypoints = []
        helm.desired_heading = heading % 360.0


def _make_sail(state, ship: int, trim: float) -> None:
    sail = state.world.try_component(ship, c.SailPlan)
    if sail is not None:
        sail.ordered = max(0.0, min(1.0, trim))


def _quarters(state, ship: int, on: bool, fire: bool) -> None:
    orders = state.world.try_component(ship, c.ShipOrders)
    if orders is not None:
        orders.quarters = on
        orders.fire_at_will = fire and on


def _laying_course(state, ship: int, ai: ShipCaptainAI, tx: float, ty: float) -> float:
    """The course that brings his broadside to bear at the range he likes,
    on the weather side of her if he is good enough to think of it."""
    world = state.world
    pos = world.component_for_entity(ship, c.WorldPosition)
    dx, dy = tx - pos.x_m, ty - pos.y_m
    to_her = bearing_degrees(dx, dy)
    dist = math.hypot(dx, dy)
    want = ai.wants_range_m
    if dist > want * 1.25:
        # Close her, but on a slant so his guns will bear as he arrives.
        lead = 35.0 * (1.0 - 0.6 * ai.skill)
        wind_from = state.wind.current.direction_degrees
        weather_side = 1.0 if angle_delta(wind_from, to_her) >= 0 else -1.0
        if ai.skill > 0.45:
            return to_her + weather_side * lead
        return to_her
    if dist < want * 0.7:
        # Too close for his taste: edge away while keeping her abeam.
        return to_her + 115.0
    # At the range he wants: lie parallel, guns bearing.
    heading = world.component_for_entity(ship, c.Heading).degrees
    side = 90.0 if angle_delta(to_her, heading) >= 0 else -90.0
    return to_her - side


def execute(state, ship: int, ai: ShipCaptainAI) -> None:
    world = state.world
    pos = world.component_for_entity(ship, c.WorldPosition)
    if ai.mission == ENGAGE and ai.target >= 0:
        contacts = world.try_component(ship, c.Contacts)
        rec = contacts.records.get(ai.target) if contacts is not None else None
        if rec is None:
            ai.mission = HOLD
            return
        _steer(state, ship, _laying_course(state, ship, ai, rec.x_m, rec.y_m))
        _make_sail(state, ship, 0.45 + 0.2 * ai.aggression)  # fighting sail
        _quarters(state, ship, True, True)
        orders = world.try_component(ship, c.ShipOrders)
        if orders is not None and orders.gun_target != ai.target:
            orders.gun_target = ai.target
            orders.gun_target_since_s = state.now_s
    elif ai.mission == CHASE and ai.target >= 0:
        contacts = world.try_component(ship, c.Contacts)
        rec = contacts.records.get(ai.target) if contacts is not None else None
        if rec is not None:
            _steer(state, ship, bearing_degrees(rec.x_m - pos.x_m, rec.y_m - pos.y_m))
        _make_sail(state, ship, 1.0)
        _quarters(state, ship, True, False)
    elif ai.mission == WITHDRAW:
        enemies = _known_enemies(state, ship)
        if enemies:
            _d, _ent, (ex, ey) = enemies[0]
            away = bearing_degrees(pos.x_m - ex, pos.y_m - ey)
        else:
            away = world.component_for_entity(ship, c.Heading).degrees
        # Run off the wind if that is the faster way out of it.
        wind_from = state.wind.current.direction_degrees
        if abs(angle_delta(away, (wind_from + 180.0) % 360.0)) < 70.0:
            away = (wind_from + 180.0) % 360.0
        _steer(state, ship, away)
        _make_sail(state, ship, 1.0)
        _quarters(state, ship, True, True)
    elif ai.mission == STATION and ai.leader >= 0:
        lead_pos = world.try_component(ai.leader, c.WorldPosition)
        lead_head = world.try_component(ai.leader, c.Heading)
        if lead_pos is None or lead_head is None:
            ai.mission = HOLD
            return
        brg = (lead_head.degrees + ai.station_bearing) % 360.0
        want_x = lead_pos.x_m + math.sin(math.radians(brg)) * ai.station_m
        want_y = lead_pos.y_m + math.cos(math.radians(brg)) * ai.station_m
        dx, dy = want_x - pos.x_m, want_y - pos.y_m
        off = math.hypot(dx, dy)
        # A good captain holds his station; a poor one wanders about it.
        slack = 40.0 + 120.0 * (1.0 - ai.skill)
        if off > slack:
            _steer(state, ship, bearing_degrees(dx, dy))
            _make_sail(state, ship, min(1.0, 0.5 + off / 600.0))
        else:
            _steer(state, ship, lead_head.degrees)
            lead_speed = world.try_component(ai.leader, c.Speed)
            mine = world.try_component(ship, c.Speed)
            trim = world.try_component(ai.leader, c.SailPlan)
            base = trim.trim if trim is not None else 0.5
            if lead_speed is not None and mine is not None:
                base += 0.08 if mine.knots < lead_speed.knots - 0.3 else (-0.08 if mine.knots > lead_speed.knots + 0.3 else 0.0)
            _make_sail(state, ship, base)
    elif ai.mission == CLOSE and ai.target >= 0:
        contacts = world.try_component(ship, c.Contacts)
        rec = contacts.records.get(ai.target) if contacts is not None else None
        if rec is not None:
            d = math.hypot(rec.x_m - pos.x_m, rec.y_m - pos.y_m)
            _steer(state, ship, bearing_degrees(rec.x_m - pos.x_m, rec.y_m - pos.y_m))
            _make_sail(state, ship, 0.7 if d > 200.0 else 0.25)
    elif ai.mission == HEAVE_TO:
        _make_sail(state, ship, 0.0)
        _quarters(state, ship, False, False)


# --- signals as orders ----------------------------------------------------


def obey_signal(state, ship: int, ai: ShipCaptainAI, number: int) -> None:
    """A signal he has read. Whether he does as he is told depends on the
    man: a disciplined captain obeys, a bold one may decide the admiral
    cannot see what he can."""
    from broadside.sim.systems.signals import SIGNAL_BOOK, hoist

    world = state.world
    name = world.try_component(ship, c.Name)
    who = name.full if name is not None else "She"
    text = SIGNAL_BOOK.get(number, "")
    enemies = _known_enemies(state, ship)
    rng = state.rng.stream("captain_ai")

    willing = ai.discipline + 0.25 * (1.0 - ai.aggression)
    if number == 9 and willing < 0.75 and enemies and enemies[0][0] < 600.0:
        # "Discontinue the action" - and he is in the thick of it.
        state.say(f"{who} does not answer the signal to discontinue.", "alert")
        ai.mission = ENGAGE
        return
    if rng.random() > min(0.98, 0.45 + 0.6 * ai.discipline):
        state.say(f"{who} seems not to have understood the signal.", "sight")
        return

    def order(mission: str) -> None:
        ai.mission = mission
        ai.ordered_mission = mission
        # A disciplined captain holds his admiral's order; a wilful one
        # drifts back to his own ideas within a minute or two.
        ai.ordered_until_s = state.now_s + 60.0 + 300.0 * ai.discipline

    if number == 1:  # Engage the enemy more closely
        ai.aggression = min(1.0, ai.aggression + 0.25)
        if enemies:
            ai.target = enemies[0][1]
            order(ENGAGE)
    elif number == 2:  # Form line of battle
        # Whoever made the signal is the ship he takes his station from.
        if ai.leader < 0:
            ai.leader = ai.signal_from if ai.signal_from >= 0 else state.player_ship
        ai.station_bearing = 180.0
        ai.station_m = 200.0
        order(STATION)
    elif number == 3:  # Make all sail
        _make_sail(state, ship, 1.0)
    elif number == 4:  # Enemy in sight
        pass  # information: his own lookouts will find her
    elif number in (5, 6):  # Tack in succession / wear together
        heading = world.component_for_entity(ship, c.Heading).degrees
        wind_from = state.wind.current.direction_degrees
        side = 1.0 if angle_delta(heading, wind_from) >= 0 else -1.0
        _steer(state, ship, heading + side * (110.0 if number == 5 else -150.0))
    elif number == 7:  # Come within hail
        ai.target = ai.signal_from if ai.signal_from >= 0 else from_ship_of(state, ship)
        order(CLOSE)
    elif number == 8:  # Report your damage
        integrity, lost, morale = _hurt(state, ship)
        state.say(
            f"{who} answers: hull {integrity * 100:.0f} in a hundred, {lost * 100:.0f} in a hundred of her people down.",
            "sight",
        )
        hoist(state, ship, 12 if integrity > 0.8 else 8)
    elif number == 9:  # Discontinue the action
        order(WITHDRAW)
    elif number == 10:  # Anchor
        order(HEAVE_TO)
    elif number == 11:  # Prepare to board
        ai.aggression = min(1.0, ai.aggression + 0.3)
        orders = world.try_component(ship, c.ShipOrders)
        if orders is not None:
            orders.quarters = True
        if enemies:
            ai.target = enemies[0][1]
            order(ENGAGE)
    elif number == 12:  # Well done
        from broadside.sim.people.psyche import appraise_ship

        appraise_ship(state, ship, "prize_taken", 0.3)
    if text and number not in (4, 8):
        state.say(f"{who} acknowledges: '{text}'.", "sight")


def captain_ai_system(state, dt: float) -> None:
    """Every ship with a captain thinks, at the speed he thinks."""
    world = state.world
    for ship, ai in world.get_component(ShipCaptainAI):
        if ship == state.player_ship:
            continue
        helm = world.try_component(ship, c.Helm)
        if helm is not None and helm.aground:
            continue
        if state.now_s - ai.last_think_s < ai.think_interval_s and not ai.signal_pending:
            execute(state, ship, ai)
            continue
        ai.last_think_s = state.now_s
        decide(state, ship, ai)
        execute(state, ship, ai)


def from_ship_of(state, ship: int) -> int:
    """Whose signal he is answering: his leader if he has one, else the
    player's ship (the only one that signals, for now)."""
    world = state.world
    ai = world.try_component(ship, ShipCaptainAI)
    if ai is not None and ai.leader >= 0:
        return ai.leader
    return state.player_ship
