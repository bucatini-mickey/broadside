# Round shot in flight: a real projectile, not a hit roll.
#
# A gun fires a ball of its calibre (mass from the pounder rating, diameter
# from iron's density) at its muzzle velocity, along the gun's bearing -
# the side it's on, trained forward or aft - and elevation. The ball flies
# under gravity and quadratic air drag, sub-stepped a metre at a time so
# it can't tunnel through anything. Every step asks what's there:
#
#   a voxel structure (a wall)  -> impact: the ball spends energy breaking
#                                  blocks, maybe punching through
#                                  (sim/voxels.py); stone dust thrown up
#   a ship's hull or deck tile  -> planks damaged by the ball's energy,
#                                  anyone standing there wounded
#   water                       -> a splash; at a grazing angle the ball
#                                  skips (ricochet fire was a real tactic)
#   land                        -> buries itself in a puff of sand
#
# See docs/design/15_physics_sandbox.md.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.people.health import wound
from broadside.sim.structure import StructureState, damage_tile
from broadside.sim.units import heading_axes
from broadside.sim.voxels import VoxelStructure, impact

G = 9.81
AIR_DENSITY = 1.2
DRAG_CD = 0.47
IRON_DENSITY = 7870.0
LB = 0.4536
MAX_FLIGHT_S = 12.0
RICOCHET_MAX_DEG = 7.0
RAIL_ABOVE_DECK_M = 1.1  # bulwark height: shot below this line hits her
STEP_M = 0.25


@dataclass
class Projectile:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    mass_kg: float
    diameter_m: float
    owner: int = -1
    age: float = 0.0
    trail: list = field(default_factory=list)  # recent (x, y, z)
    alive: bool = True
    fate: str = ""
    grazes: int = 0

    @property
    def speed(self) -> float:
        return math.sqrt(self.vx * self.vx + self.vy * self.vy + self.vz * self.vz)

    @property
    def energy_j(self) -> float:
        return 0.5 * self.mass_kg * self.speed ** 2


def gun_ballistics(kind: str) -> tuple[float, float, float]:
    """(mass kg, diameter m, muzzle velocity m/s) for a gun description like
    '24-pounder long gun' or '32-pounder carronade'."""
    m = re_pounds(kind)
    mass = m * LB
    diameter = (6.0 * mass / (math.pi * IRON_DENSITY)) ** (1.0 / 3.0)
    carronade = "carronade" in kind.lower()
    velocity = 250.0 if carronade else 430.0 + min(50.0, m * 1.2)
    return mass, diameter, velocity


def re_pounds(kind: str) -> float:
    digits = ""
    for ch in kind:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return float(digits or 12)


def fire_gun(state, ship: int, gun_index: int, *, elevation_deg: float = 0.0, train_deg: float = 0.0, dispersion_deg: float = 0.25) -> int:
    """Launch a ball from a ship's gun. Returns the projectile entity."""
    world = state.world
    body = world.component_for_entity(ship, c.ShipBody)
    pos = world.component_for_entity(ship, c.WorldPosition)
    hdg = world.component_for_entity(ship, c.Heading).degrees
    spec = body.layout.guns[gun_index]
    mass, diameter, v0 = gun_ballistics(spec.kind)
    rng = state.rng.stream("gunlaying")
    # The gun points out of its side, trained forward (+) or aft (-).
    bearing = hdg + spec.side * 90.0 - spec.side * train_deg + rng.gauss(0, dispersion_deg)
    elev = math.radians(elevation_deg + rng.gauss(0, dispersion_deg * 0.6))
    b = math.radians(bearing)
    fx, fy, sx, sy = heading_axes(hdg)
    u, v = body.layout.local_m(spec.x, spec.y)
    v_out = v + spec.side * 1.2
    x0 = pos.x_m + u * fx + v_out * sx
    y0 = pos.y_m + u * fy + v_out * sy
    z0 = body.layout.freeboard_m + 0.7
    vh = v0 * math.cos(elev)
    ent = world.create_entity(Projectile(x0, y0, z0, vh * math.sin(b), vh * math.cos(b), v0 * math.sin(elev), mass, diameter, owner=ship))
    return ent


def ballistics_system(state, dt: float) -> None:
    world = state.world
    structures = [(e, vs, (p.x_m, p.y_m, h.degrees)) for e, (vs, p, h) in world.get_components(VoxelStructure, c.WorldPosition, c.Heading)]
    scene = None
    for ent, proj in list(world.get_component(Projectile)):
        if not proj.alive:
            # immediate: esper otherwise defers deletion until world.process(),
            # which this engine never calls - it runs its own pipeline. Spent
            # shot was piling up for the whole action and being stepped over
            # every tick.
            world.delete_entity(ent, immediate=True)
            continue
        proj.age += dt
        if proj.age > MAX_FLIGHT_S:
            proj.alive = False
            continue
        k = 0.5 * AIR_DENSITY * DRAG_CD * math.pi * (proj.diameter_m / 2.0) ** 2 / proj.mass_kg
        # Sub-step a quarter metre at a time so the ball can't skip a 0.5 m
        # block; the costlier ship/ground tests run every metre.
        n = max(1, int(math.ceil(proj.speed * dt / STEP_M)))
        h = dt / n
        per_coarse = max(1, int(round(1.0 / STEP_M)))
        for i in range(n):
            sp = proj.speed
            ax = -k * sp * proj.vx
            ay = -k * sp * proj.vy
            az = -G - k * sp * proj.vz
            proj.vx += ax * h
            proj.vy += ay * h
            proj.vz += az * h
            proj.x += proj.vx * h
            proj.y += proj.vy * h
            proj.z += proj.vz * h
            if _hit_structures(state, proj, structures):
                break
            if not proj.alive:
                break
            if i % per_coarse and i != n - 1:
                continue
            if scene is None:
                scene = state.scene()
            if _hit_ship(state, proj, scene):
                break
            if _hit_ground(state, proj):
                break
        proj.trail.append((proj.x, proj.y, proj.z))
        proj.trail = proj.trail[-12:]


def _hit_structures(state, proj: Projectile, structures) -> bool:
    for ent, vs, (sx, sy, head) in structures:
        fx, fy = math.sin(math.radians(head)), math.cos(math.radians(head))
        rx, ry = fy, -fx
        dx, dy = proj.x - sx, proj.y - sy
        u, v = dx * fx + dy * fy, dx * rx + dy * ry
        ix, iy, iz = vs.local_to_voxel(np.array(u), np.array(v), np.array(proj.z))
        ix, iy, iz = int(ix), int(iy), int(iz)
        nz, ny, nx = vs.shape
        if not (0 <= ix < nx and 0 <= iy < ny and 0 <= iz < nz) or vs.material[iz, iy, ix] < 0:
            continue
        sp = proj.speed
        # Direction in grid axes (x = along the wall's u, y = v, z = up).
        vu = (proj.vx * fx + proj.vy * fy) / sp
        vv = (proj.vx * rx + proj.vy * ry) / sp
        vz = proj.vz / sp
        e_before = proj.energy_j
        left, broke = impact(state, ent, vs, ix, iy, iz, e_before, (vu, vv, vz))
        state.atmosphere.emit_smoke(proj.x, proj.y, radius=1.2 + broke * 0.6, sigma_peak=0.35 + 0.15 * broke, kind="dust", top_m=proj.z + 2.0)
        state.recent.append((state.now_s, "impact", proj.x, proj.y, 1.0))
        if left <= 0:
            proj.alive = False
            proj.fate = f"lodged in the {vs.name}"
            state.say(f"Shot strikes the {vs.name}{' - a block smashed' if broke else ''}; lodged.", "gun")
            return True
        scale = math.sqrt(left / e_before)
        proj.vx *= scale
        proj.vy *= scale
        proj.vz *= scale
        state.say(f"Shot smashes into the {vs.name}, breaking {broke} block{'s' if broke != 1 else ''}, and carries on.", "gun")
        return False
    return False


def _hit_ship(state, proj: Projectile, scene) -> bool:
    content = scene.sample(np.array([proj.x]), np.array([proj.y]), with_air=False, include_people=False)
    si = int(content.ship[0])
    if si < 0:
        return False
    g = scene.geoms[si]
    if g.entity == proj.owner and proj.age < 0.3:
        return False
    # A hull is solid from the waterline to the rail, not just where a
    # fitting happens to stand: a ball that crosses the deck below the
    # bulwarks strikes the ship (and the men on that spot). Higher than the
    # rail and it passes over - through the rigging, which is not modelled
    # yet - so it misses.
    if proj.z > g.freeboard + RAIL_ABOVE_DECK_M or proj.z < -0.5:
        return False
    world = state.world
    gx, gy = int(content.gx[0]), int(content.gy[0])
    st = world.try_component(g.entity, StructureState)
    e = proj.energy_j
    if st is not None:
        damage_tile(st, gx, gy, e / 200_000.0)
    hull = world.try_component(g.entity, c.Hull)
    if hull is not None:
        # The coarse figure the sailing model and the details panel read.
        hull.integrity = max(0.05, hull.integrity - e / 25_000_000.0)
    # The ball itself kills one man; the splinters it tears out of the side
    # are what hurt the rest, and they were the great killer of the period.
    from broadside.sim.people.psyche import appraise, appraise_ship

    appraise_ship(state, g.entity, "struck", 0.5, on_deck_only=True)
    rng = state.rng.stream("splinters")
    for ent, (crew, dpos) in world.get_components(c.CrewMember, c.DeckPosition):
        if crew.ship != g.entity or not world.has_component(ent, pc.Body):
            continue
        d = max(abs(dpos.x - gx), abs(dpos.y - gy))
        if d == 0:
            wound(state, ent, "chest", 0.9, "round shot")
            appraise_ship(state, g.entity, "mate_killed", 0.6, on_deck_only=True)
        elif d <= 2 and rng.random() < (0.7 if d == 1 else 0.35):
            part = rng.choice(["left arm", "right arm", "left leg", "right leg", "head", "abdomen"])
            wound(state, ent, part, 0.4 if d == 1 else 0.2, "splinter")
            appraise(state, ent, "struck", 1.0)
            appraise_ship(state, g.entity, "mate_hurt", 0.4, on_deck_only=True)
    proj.alive = False
    proj.fate = f"struck {g.name}"
    if proj.owner >= 0:
        appraise_ship(state, proj.owner, "enemy_struck", 0.5, on_deck_only=True)
    state.say(f"Shot strikes {g.name}!", "gun")
    return True


def _hit_ground(state, proj: Projectile) -> bool:
    ts = state.terrain.sample(np.array([proj.x]), np.array([proj.y]))
    ground = float(ts.height[0])
    if proj.z > max(0.0, ground):
        return False
    if ground <= 0.05:
        sp = proj.speed
        horiz = math.hypot(proj.vx, proj.vy)
        angle = math.degrees(math.atan2(-proj.vz, horiz))
        state.atmosphere.emit_smoke(proj.x, proj.y, radius=1.5, sigma_peak=0.25, kind="spray")
        if angle < RICOCHET_MAX_DEG and sp > 120.0 and proj.grazes < 4:
            proj.grazes += 1
            proj.z = 0.05
            proj.vz = -proj.vz * 0.5
            proj.vx *= 0.7
            proj.vy *= 0.7
            return False
        proj.alive = False
        proj.fate = "fell into the sea"
        state.say("Shot falls into the sea.", "gun")
        return True
    state.atmosphere.emit_smoke(proj.x, proj.y, radius=1.5, sigma_peak=0.3, kind="dust", top_m=3.0)
    proj.alive = False
    proj.fate = "buried in the ground"
    state.say("Shot buries itself ashore in a spray of sand.", "gun")
    return True


# --- What the gun captain thinks will happen ------------------------------
#
# A dry run of exactly the model above - same drag, same muzzle velocity,
# same elevation - with nothing created and nothing touched. It is what the
# man at the breech believes as he squints along the barrel, so its
# precision is *his*: a green crew's estimate is honestly vague, and the
# preview says so rather than drawing a confident line.


@dataclass
class ShotPrediction:
    gun_index: int
    bearing_deg: float
    elevation_deg: float
    points: list  # (x, y, z) along the flight, about ten a second
    graze_m: float  # ground range at which it first touches the water
    apex_m: float  # highest it rises
    flight_s: float
    spread_m: float  # how far out this estimate may be, from his skill
    verdict: str = ""  # against the target, if there is one
    # What the quoin would have to be set to for her present range, when
    # that differs from how the gun is actually lying.
    wants_deg: Optional[float] = None


def predict_shot(
    state,
    ship: int,
    gun_index: int,
    *,
    elevation_deg: Optional[float] = None,
    train_deg: Optional[float] = None,
    target: int = -1,
    skill: float = 0.5,
    dt: float = 1.0 / 30.0,
) -> ShotPrediction:
    """Where this gun's shot would go if it were fired now, at its present
    lay. No randomness: the scatter is reported as a figure, not rolled."""
    world = state.world
    body = world.component_for_entity(ship, c.ShipBody)
    pos = world.component_for_entity(ship, c.WorldPosition)
    hdg = world.component_for_entity(ship, c.Heading).degrees
    spec = body.layout.guns[gun_index]
    battery = world.try_component(ship, c.Battery)
    gs = None if battery is None else next((g for g in battery.guns if g.index == gun_index), None)
    if elevation_deg is None:
        elevation_deg = 0.0 if gs is None else gs.elevation_deg
    if train_deg is None:
        train_deg = 0.0 if gs is None else gs.train_deg
    mass, diameter, v0 = gun_ballistics(spec.kind)
    bearing = hdg + spec.side * 90.0 - spec.side * train_deg
    elev = math.radians(elevation_deg)
    b = math.radians(bearing)
    fx, fy, sx, sy = heading_axes(hdg)
    u, v = body.layout.local_m(spec.x, spec.y)
    v_out = v + spec.side * 1.2
    x = pos.x_m + u * fx + v_out * sx
    y = pos.y_m + u * fy + v_out * sy
    z = body.layout.freeboard_m + 0.7
    x0, y0 = x, y
    vh = v0 * math.cos(elev)
    vx, vy, vz = vh * math.sin(b), vh * math.cos(b), v0 * math.sin(elev)
    k = 0.5 * AIR_DENSITY * DRAG_CD * math.pi * (diameter / 2.0) ** 2 / mass
    points = [(x, y, z)]
    apex = z
    t = 0.0
    while t < MAX_FLIGHT_S:
        sp = math.sqrt(vx * vx + vy * vy + vz * vz)
        vx -= k * sp * vx * dt
        vy -= k * sp * vy * dt
        vz -= (G + k * sp * vz) * dt
        x += vx * dt
        y += vy * dt
        z += vz * dt
        t += dt
        apex = max(apex, z)
        points.append((x, y, z))
        if z <= 0.0:
            break
    graze = math.hypot(x - x0, y - y0)
    # His own estimate of the range is what is really uncertain: a quarter
    # of the range for a raw crew, a twentieth for a crack one.
    spread = graze * (0.25 - 0.20 * max(0.0, min(1.0, skill)))
    pred = ShotPrediction(gun_index, bearing % 360.0, elevation_deg, points, graze, apex, t, spread)
    if target >= 0:
        her = world.try_component(target, c.WorldPosition)
        if her is not None:
            d = math.hypot(her.x_m - x0, her.y_m - y0)
            if graze < d - max(10.0, spread * 0.3):
                pred.verdict = f"falls {d - graze:.0f} m short of her"
            else:
                # Not where it lands but how high it is passing when it
                # reaches her: a ball still rising at her rail goes through
                # her rigging, one below it hits her side.
                hz = _height_at(points, x0, y0, d)
                her_body = world.try_component(target, c.ShipBody)
                rail = RAIL_ABOVE_DECK_M + (2.0 if her_body is None else float(her_body.layout.freeboard_m))
                tops = 22.0 if her_body is None else max(rail + 4.0, float(getattr(her_body.layout, "mast_height_m", 22.0)))
                if hz <= rail:
                    pred.verdict = "would strike her hull"
                elif hz <= tops:
                    pred.verdict = f"would pass {hz:.0f} m up - her rigging, not her hull"
                else:
                    pred.verdict = f"goes {hz:.0f} m over her"
            # And what he would have to set the quoin to for her range.
            from broadside.sim.gundrill import solve_elevation

            want = solve_elevation(spec.kind, d, 0.0)
            if abs(want - elevation_deg) > 0.4:
                pred.wants_deg = want
    return pred


def _height_at(points, x0: float, y0: float, ground_m: float) -> float:
    """How high the shot is when it has run this far over the water."""
    prev_d, prev_z = 0.0, points[0][2]
    for (px, py, pz) in points[1:]:
        d = math.hypot(px - x0, py - y0)
        if d >= ground_m:
            span = max(1e-6, d - prev_d)
            f = (ground_m - prev_d) / span
            return prev_z + (pz - prev_z) * f
        prev_d, prev_z = d, pz
    return prev_z


def gun_to_bear(state, ship: int, tx: float, ty: float) -> tuple:
    """Which of her guns can be laid on a point, and the training it needs:
    (gun index, train degrees), or (-1, 0.0) if nothing will bear that way.
    A gun is trained round with handspikes within its port, so the shot to
    preview is the one that *can* be pointed there, not the one that
    happens to be pointing there."""
    from broadside.sim import gundrill as gd  # gundrill imports this module

    world = state.world
    body = world.component_for_entity(ship, c.ShipBody)
    pos = world.component_for_entity(ship, c.WorldPosition)
    hdg = world.component_for_entity(ship, c.Heading).degrees
    fx, fy, sx, sy = heading_axes(hdg)
    best, train, off = -1, 0.0, 1e9
    for i, spec in enumerate(body.layout.guns):
        u, v = body.layout.local_m(spec.x, spec.y)
        gx = pos.x_m + u * fx + v * sx
        gy = pos.y_m + u * fy + v * sy
        t = gd.train_for(hdg, spec.side, gx, gy, tx, ty)
        if not gd.bears(t):
            continue
        if abs(t) < off:
            best, train, off = i, t, abs(t)
    return best, train
