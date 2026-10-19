# Working a gun: the drill, step by step, by named men.
#
# Nobody stands beside a cannon while an invisible bar fills. A gun is
# fought by a crew with numbered stations, each with his own job, and every
# job is a real Activity that takes real time:
#
#   1 gun captain    primes the vent, lays the gun, gives the word to fire
#   2 rammer/sponger sponges out, rams the cartridge and the shot home
#   3 loader         cartridge from the box, wad, shot from the garland
#   4 tackle men     run the gun out on the side tackles after it recoils
#
# How long each step takes comes from the man doing it - his proficiency in
# the skill the job needs, how tired he is, whether he still has both hands
# - and from the physical facts: a 24-pounder ball weighs 10.9 kg to lift
# into the muzzle, and the gun with its carriage weighs two and a half
# tonnes to haul back out. Short-handed, the same men do each other's jobs,
# slower. That is where a ship's rate of fire comes from: three rounds in
# five minutes for a crack crew, half that for a green one, and nothing at
# all from a gun with two men left alive.
#
# The player works a gun through these identical steps (sim/actions.py),
# because they are defined once, here.
#
# See docs/design/16_observation_and_targeting.md.

from __future__ import annotations

import math
from dataclasses import dataclass

from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.systems.ballistics import AIR_DENSITY, DRAG_CD, G, gun_ballistics, re_pounds
from broadside.sim.units import bearing_degrees, heading_axes

MAX_TRAIN_DEG = 12.0
# How long it takes a gun captain to understand that the captain wants a
# different mark, and to shift his piece onto it.
COMPREHEND_BASE_S = 6.0
COMPREHEND_GREEN_S = 26.0
MAX_ELEVATION_DEG = 8.0
MIN_ELEVATION_DEG = -4.0
# A gun with nothing in her arc is laid level and left run out.
DEFAULT_ELEVATION_DEG = 0.5


@dataclass(frozen=True)
class Step:
    """One order in the drill. `key` is the GunState flag it completes."""

    key: str
    want: bool
    label: str
    station: int  # whose job it is: his number in the gun's crew
    skill: str
    base_s: float
    effort: float = 0.0  # 0 = deft work, 1 = heavy hauling
    mass: str = ""  # "shot" or "gun": what physical weight sets the pace
    takes: str = ""  # a store it consumes: "powder cartridge" | "shot"


# The period sequence for a gun that has just fired and lies recoiled inboard.
DRILL = (
    Step("needs_sponge", False, "Sponge out", 2, "gunnery", 5.0, 0.3),
    Step("charged", True, "Load a powder cartridge", 3, "gunnery", 4.0, 0.1, takes="powder cartridge"),
    Step("charge_rammed", True, "Ram the cartridge home", 2, "gunnery", 3.0, 0.4),
    Step("wadded", True, "Wad the charge", 3, "gunnery", 2.0, 0.1),
    Step("shotted", True, "Load round shot", 3, "gunnery", 3.5, 0.6, mass="shot", takes="shot"),
    Step("rammed", True, "Ram the shot home", 2, "gunnery", 3.5, 0.5, mass="shot"),
    Step("run_out", True, "Run the gun out", 4, "seamanship", 7.0, 1.0, mass="gun"),
    Step("primed", True, "Prime the vent", 1, "gunnery", 3.0, 0.0),
    Step("laid", True, "Lay the gun", 1, "gunlaying", 4.0, 0.2),
)
BY_KEY = {s.key: s for s in DRILL}


def next_step(gs):
    """The next thing that must be done to this gun, or None if she's ready."""
    for s in DRILL:
        if getattr(gs, s.key) != s.want:
            return s
    return None


def ready(gs) -> bool:
    return next_step(gs) is None


def reset_after_firing(gs) -> None:
    """She has fired, and recoiled inboard: everything must be done again.
    Train and elevation stay where they were, but the gun captain lays her
    afresh, which is where shot-to-shot dispersion comes from."""
    gs.needs_sponge = True
    gs.charged = gs.charge_rammed = gs.wadded = gs.shotted = gs.rammed = False
    gs.run_out = gs.primed = gs.laid = False
    gs.loaded = False
    gs.working = -1
    gs.working_key = ""


# --- how long a job takes --------------------------------------------------


def gun_mass_kg(kind: str) -> float:
    """Gun and carriage together. A long 24-pounder ran about 50 cwt for the
    piece, with a quarter as much again for the truck carriage; carronades,
    short and thin-walled, a fraction of that."""
    lb = re_pounds(kind)
    piece = 105.0 * lb  # kg per pound of shot: close for period long guns
    if "carronade" in kind.lower():
        piece *= 0.3
    return piece * 1.25


def physique(world, ent: int) -> float:
    """0..1: how much of the work at a gun a man can still do. Asked of the
    body itself (`Body.capability`), so a broken wrist, a cut tendon or a
    tourniquet all tell without the gun drill knowing what a tendon is."""
    body = world.try_component(ent, pc.Body)
    if body is None:
        return 1.0
    grip = body.capability("grip")
    reach = body.capability("reach")
    stand = body.capability("stand")
    return max(0.12, 0.45 * grip + 0.35 * reach + 0.2 * stand)


def step_time(
    step: Step,
    *,
    skill: float = 0.4,
    fatigue: float = 0.0,
    physique_: float = 1.0,
    shot_kg: float = 5.4,
    gun_kg: float = 1500.0,
    hands: int = 4,
    own_station: bool = True,
) -> float:
    """Seconds for one man of this ability to do this job, now."""
    t = step.base_s * (0.6 + 1.0 * (1.0 - max(0.0, min(1.0, skill))))
    if step.mass == "shot":
        t *= (shot_kg / 5.4) ** 0.4  # a 32-pounder ball is a two-man lift
    elif step.mass == "gun":
        # Everyone at the gun tails on to the side tackles; a tonne a man is
        # the difference between a gun run out briskly and one that crawls.
        t *= max(0.5, min(3.5, gun_kg / (max(1, hands) * 750.0)))
    t *= 1.0 + 0.6 * max(0.0, fatigue) * (0.3 + step.effort)
    t /= max(0.2, physique_ ** (0.3 + step.effort))
    if not own_station:
        t *= 1.2  # doing another man's job, in his way
    return max(0.8, t)


def fatigue_cost(step: Step) -> float:
    return 0.004 + 0.02 * step.effort


# --- laying the gun -------------------------------------------------------


def solve_elevation(kind: str, range_m: float, dz_m: float) -> float:
    """The elevation that puts this gun's ball `dz_m` above the muzzle at
    `range_m`, drag and all - found by bisection over the real trajectory,
    which is what a gun captain's eye and experience stand in for."""
    mass, diameter, v0 = gun_ballistics(kind)
    k = 0.5 * AIR_DENSITY * DRAG_CD * math.pi * (diameter / 2.0) ** 2 / mass

    def height_at(elev_deg: float) -> float:
        a = math.radians(elev_deg)
        x, z = 0.0, 0.0
        vx, vz = v0 * math.cos(a), v0 * math.sin(a)
        dt = 0.01
        for _ in range(4000):
            if x >= range_m:
                return z
            sp = math.hypot(vx, vz)
            vx -= k * sp * vx * dt
            vz -= (k * sp * vz + G) * dt
            x += vx * dt
            z += vz * dt
            if z < -300.0:
                break
        return z

    lo, hi = MIN_ELEVATION_DEG, MAX_ELEVATION_DEG
    if height_at(hi) < dz_m:
        return hi
    if height_at(lo) > dz_m:
        return lo
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        if height_at(mid) < dz_m:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def bears(train_deg: float) -> bool:
    return abs(train_deg) <= MAX_TRAIN_DEG + 1e-6


def train_for(hdg: float, side: int, from_x: float, from_y: float, tx: float, ty: float) -> float:
    """The training a gun needs (+ toward the bow) to point at a world
    point - whether or not that lies within her arc."""
    neutral = (hdg + side * 90.0) % 360.0
    want = bearing_degrees(tx - from_x, ty - from_y)
    off = ((neutral - want + 180.0) % 360.0) - 180.0
    return side * off


def gun_muzzle(world, ship: int, spec) -> tuple:
    """(x, y, z) of a gun's muzzle in world metres."""
    layout = world.component_for_entity(ship, c.ShipBody).layout
    pos = world.component_for_entity(ship, c.WorldPosition)
    hdg = world.component_for_entity(ship, c.Heading).degrees
    fx, fy, sx, sy = heading_axes(hdg)
    u, v = layout.local_m(spec.x, spec.y)
    v_out = v + spec.side * 1.2
    return pos.x_m + u * fx + v_out * sx, pos.y_m + u * fy + v_out * sy, layout.freeboard_m + 0.7


def _hostile(world, ship: int, other: int) -> bool:
    a = world.try_component(ship, c.Faction)
    b = world.try_component(other, c.Faction)
    if a is None or b is None:
        return False
    return a.name != b.name and "neutral" not in (a.name, b.name)


def understood_target(state, ship: int, skill: float) -> int:
    """The target the captain has named, if this gun captain has taken it in
    yet. Shifting a battery onto a new mark took repeating and pointing; a
    crack gun captain has it in a few seconds, a green one takes half a
    minute, and until then he goes on firing at what he was firing at."""
    orders = state.world.try_component(ship, c.ShipOrders)
    if orders is None or orders.gun_target < 0:
        return -1
    delay = COMPREHEND_BASE_S + COMPREHEND_GREEN_S * (1.0 - max(0.0, min(1.0, skill)))
    if state.now_s - orders.gun_target_since_s < delay:
        return -1
    return orders.gun_target


def choose_target(state, ship: int, spec, gs, prefer: int = -1) -> tuple:
    """What this gun can bear on: (entity, range_m, dz_m, train_deg), the
    entity -1 if nothing is in her arc. A structure is aimed at the foot of
    the wall - that is how a breach is made; a ship at her hull. A target
    the captain has named wins over a nearer one, if she can bear on it."""
    from broadside.sim.voxels import VoxelStructure

    world = state.world
    hdg = world.component_for_entity(ship, c.Heading).degrees
    mx, my, mz = gun_muzzle(world, ship, spec)
    best = (-1, 0.0, 0.0, 0.0, 1e18)
    for ent, (vs, pos) in world.get_components(VoxelStructure, c.WorldPosition):
        d = math.hypot(pos.x_m - mx, pos.y_m - my)
        t = train_for(hdg, spec.side, mx, my, pos.x_m, pos.y_m)
        if not bears(t) or d > 2000.0 or not vs.solid.any():
            continue
        score = d * (0.2 if ent == prefer else 1.0)
        if score < best[4]:
            best = (ent, d, vs.base_z_m + 0.8 - mz, t, score)
    for ent, (body, pos) in world.get_components(c.ShipBody, c.WorldPosition):
        if ent == ship or not _hostile(world, ship, ent):
            continue
        d = math.hypot(pos.x_m - mx, pos.y_m - my)
        t = train_for(hdg, spec.side, mx, my, pos.x_m, pos.y_m)
        if not bears(t) or d > 2000.0:
            continue
        score = d * (0.2 if ent == prefer else 1.0)
        if score < best[4]:
            best = (ent, d, body.layout.freeboard_m + 0.5 - mz, t, score)
    return best[:4]


def lay_gun(state, ship: int, spec, gs, skill: float) -> None:
    """The gun captain lays his piece: trains it round with handspikes and
    sets the quoin under the breech. He misjudges the range by however green
    he is, which is where shot-to-shot dispersion comes from."""
    ent, range_m, dz, train = choose_target(state, ship, spec, gs, prefer=understood_target(state, ship, skill))
    gs.target = ent
    if ent < 0:
        gs.train_deg = 0.0
        gs.elevation_deg = DEFAULT_ELEVATION_DEG
        gs.laid = True
        return
    rng = state.rng.stream("gunlaying")
    err = 1.0 - max(0.0, min(1.0, skill))
    guessed = max(20.0, range_m * (1.0 + rng.gauss(0.0, 0.05 * err + 0.01)))
    elev = solve_elevation(spec.kind, guessed, dz)
    gs.elevation_deg = max(MIN_ELEVATION_DEG, min(MAX_ELEVATION_DEG, elev + rng.gauss(0.0, 0.3 * err)))
    gs.train_deg = max(-MAX_TRAIN_DEG, min(MAX_TRAIN_DEG, train + rng.gauss(0.0, 0.5 * err)))
    gs.laid = True


# --- the crew at work -----------------------------------------------------


def crew_at_guns(state, ship: int) -> dict:
    """gun_index -> [(entity, station number)] of the men standing at that
    gun, alive and on their feet, the gun captain first."""
    world = state.world
    out: dict = {}
    for ent, (crew, task, pos) in world.get_components(c.CrewMember, c.CrewTask, c.DeckPosition):
        if crew.ship != ship or task.station_kind != "gun" or task.station is None:
            continue
        if (pos.x, pos.y) != tuple(task.station) or world.has_component(ent, pc.Dead):
            continue
        body = world.try_component(ent, pc.Body)
        if body is not None and (not body.alive or not body.conscious):
            continue
        out.setdefault(task.gun_index, []).append((ent, task.station_no or 9))
    for men in out.values():
        men.sort(key=lambda m: m[1])
    return out


def _skill(world, ent: int, skill: str) -> float:
    sk = world.try_component(ent, pc.Skills)
    return sk.get(skill) if sk is not None else 0.4


def _fatigue(world, ent: int) -> float:
    needs = world.try_component(ent, c.Needs)
    return needs.fatigue if needs is not None else 0.0


def take_store(state, ship: int, x: int, y: int, what: str) -> bool:
    """Spend a cartridge or a ball from a container within reach of the gun.
    Powder monkeys running up from the magazine come later; for now the
    cartridge box and the shot garland beside the gun are the supply."""
    from broadside.sim.items import Contents, Item, Stowed

    world = state.world
    for ent, (item, st, cont) in world.get_components(Item, Stowed, Contents):
        if st.ship != ship or st.x is None or abs(st.x - x) > 2 or abs(st.y - y) > 2:
            continue
        for kind, qty in cont.goods.items():
            if qty <= 0:
                continue
            if (what == "shot" and "shot" in kind) or kind == what:
                cont.goods[kind] = qty - 1
                return True
    return False


def begin_step(state, ship: int, spec, gs, step: Step, man: int, *, hands: int = 4, own_station: bool = True) -> bool:
    """Set a man to work on one step of the drill."""
    from broadside.sim.actions import Activity

    world = state.world
    if step.takes and not take_store(state, ship, spec.x, spec.y, step.takes):
        return False
    shot_kg, _dia, _v0 = gun_ballistics(spec.kind)
    dur = step_time(
        step,
        skill=_skill(world, man, step.skill),
        fatigue=_fatigue(world, man),
        physique_=physique(world, man),
        shot_kg=shot_kg,
        gun_kg=gun_mass_kg(spec.kind),
        hands=hands,
        own_station=own_station,
    )
    gs.working = man
    gs.working_key = step.key

    def done(st, gs_=gs, step_=step, man_=man, ship_=ship, spec_=spec):
        if step_.key == "laid":
            lay_gun(st, ship_, spec_, gs_, _skill(st.world, man_, "gunlaying"))
        else:
            setattr(gs_, step_.key, step_.want)
        gs_.loaded = ready(gs_)
        gs_.working = -1
        gs_.working_key = ""
        needs = st.world.try_component(man_, c.Needs)
        if needs is not None:
            needs.fatigue = min(1.0, needs.fatigue + fatigue_cost(step_))
        battery = st.world.try_component(ship_, c.Battery)
        if battery is not None and battery.verbose_drill and ship_ == st.player_ship:
            nm = st.world.try_component(man_, c.Name)
            st.say(f"{nm.full if nm else 'A hand'}: {step_.label.lower()}.", "gun")

    world.add_component(man, Activity(f"{step.label} ({spec.kind})", dur, dur, done))
    return True


def gun_drill_system(state, dt: float) -> None:
    """Every manned gun on deck is worked by its crew, step by step."""
    from broadside.sim.actions import Activity

    world = state.world
    for ship, (battery, body, orders) in world.get_components(c.Battery, c.ShipBody, c.ShipOrders):
        if battery.abstract_crew:
            continue
        crews = crew_at_guns(state, ship)
        for gs in battery.guns:
            spec = body.layout.guns[gs.index]
            if not spec.on_deck:
                continue
            if gs.working >= 0:
                if world.has_component(gs.working, Activity):
                    continue  # he is at it
                gs.working = -1  # killed, or called away: the job is dropped
                gs.working_key = ""
            step = next_step(gs)
            if step is None:
                gs.loaded = True
                continue
            at_gun = crews.get(gs.index, [])
            men = [m for m in at_gun if not world.has_component(m[0], Activity)]
            if not men:
                continue
            his = [m for m in men if m[1] == step.station]
            man, own = (his[0][0], True) if his else (men[0][0], False)
            if begin_step(state, ship, spec, gs, step, man, hands=len(at_gun), own_station=own):
                gs.starved = False
            elif not gs.starved:
                gs.starved = True
                if ship == state.player_ship:
                    want = "powder" if step.takes == "powder cartridge" else "shot"
                    state.say(f"No {want} at the {spec.kind} - the gun stands idle.", "alert")
