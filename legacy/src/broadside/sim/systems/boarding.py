# Ships touching: collision, fouling, boarding, and hand-to-hand fighting.
#
# This is where the "every ship at the same granularity" principle pays
# off. Because every hull is a real 1 m plan in world space, two ships
# collide exactly where their tiles overlap; the planks that meet take the
# damage. Once fouled, touching deck tiles on both ships form gangways, and
# boarders walk across them - a man literally leaves one ship's grid and
# steps onto the other's. On the enemy deck, fights are individual: each
# blow is a skill contest that wounds a specific part of a specific body
# (sim/people/health.py), so men bleed, fall and die one by one.

from __future__ import annotations

import math

import numpy as np

from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.people import components as pc
from broadside.sim.people.health import wound
from broadside.sim.structure import StructureState, damage_tile
from broadside.sim.systems.crew_tasks import bfs_path
from broadside.sim.units import MS_PER_KNOT

# Men climb over both bulwarks: a deck tile on each side within ~3 m.
GANGWAY_OFFSETS = (-3.0, -1.5, 0.0, 1.5, 3.0)
BLOW_INTERVAL_S = 3.0
BOARDER_STEP_TICKS = 3
PARTS_WEIGHTED = [("head", 1), ("neck", 0.4), ("chest", 2), ("abdomen", 1.5), ("left arm", 1.5), ("right arm", 1.5),
                  ("left hand", 1), ("right hand", 1), ("left leg", 1.2), ("right leg", 1.2)]


def _world_tiles(g_pose, layout):
    u, v, gx, gy = sl.footprint_local(layout)
    x, y, head = g_pose
    fx, fy = math.sin(math.radians(head)), math.cos(math.radians(head))
    sx, sy = fy, -fx
    return x + u * fx + v * sx, y + u * fy + v * sy, gx, gy


def _to_grid(pose, layout, wx, wy):
    x, y, head = pose
    fx, fy = math.sin(math.radians(head)), math.cos(math.radians(head))
    sx, sy = fy, -fx
    dx, dy = wx - x, wy - y
    return layout.grid_from_local(dx * fx + dy * fy, dx * sx + dy * sy)


def _overlap(pa, la, pb, lb, pad: float = 0.0):
    """Tiles of A whose centres fall on a hull/deck tile of B."""
    wx, wy, ax, ay = _world_tiles(pa, la)
    bx, by = _to_grid(pb, lb, wx, wy)
    inside = (bx >= 0) & (bx < lb.width) & (by >= 0) & (by < lb.height)
    hit = np.zeros(wx.shape, dtype=bool)
    hit[inside] = (lb.tiles[by[inside], bx[inside]] != sl.NONE) & (lb.tiles[by[inside], bx[inside]] != sl.BOWSPRIT)
    return ax[hit], ay[hit], bx[hit], by[hit]


def gangways(pa, la, pb, lb) -> list:
    """Walkable tile pairs within reach of each other across two hulls."""
    wx, wy, ax, ay = _world_tiles(pa, la)
    walk_a = la.walkable[ay, ax]
    pairs = []
    for ox in GANGWAY_OFFSETS:
        for oy in GANGWAY_OFFSETS:
            bx, by = _to_grid(pb, lb, wx + ox, wy + oy)
            inside = (bx >= 0) & (bx < lb.width) & (by >= 0) & (by < lb.height) & walk_a
            idx = np.nonzero(inside)[0]
            ok = lb.walkable[by[idx], bx[idx]]
            for i in idx[ok]:
                pairs.append(((int(ax[i]), int(ay[i])), (int(bx[i]), int(by[i]))))
    # One crossing per tile on our side is plenty.
    best: dict = {}
    for a, b in pairs:
        best.setdefault(a, b)
    return sorted(best.items())


def collision_system(state, dt: float) -> None:
    world = state.world
    ships = [(e, pos, hd, body, spd) for e, (pos, hd, body, spd) in world.get_components(c.WorldPosition, c.Heading, c.ShipBody, c.Speed)]
    for i in range(len(ships)):
        ea, pa, ha, ba, sa = ships[i]
        for j in range(i + 1, len(ships)):
            eb, pb, hb, bb, sb = ships[j]
            la, lb = ba.layout, bb.layout
            reach = la.hull_length / 2 + lb.hull_length / 2 + 2
            if abs(pa.x_m - pb.x_m) > reach or abs(pa.y_m - pb.y_m) > reach:
                continue
            fa = world.try_component(ea, c.Fouled)
            if fa is not None and fa.other == eb:
                continue
            poseA = (pa.x_m, pa.y_m, ha.degrees)
            poseB = (pb.x_m, pb.y_m, hb.degrees)
            ax, ay, bx, by = _overlap(poseA, la, poseB, lb)
            if ax.size == 0:
                continue
            # Collision: the planks that met take the blow, scaled by the
            # closing speed; both ships lose their way; they're fouled.
            closing = abs(sa.knots - sb.knots) * MS_PER_KNOT + 0.3
            sta, stb = world.try_component(ea, StructureState), world.try_component(eb, StructureState)
            for (st, xs, ys) in ((sta, ax, ay), (stb, bx, by)):
                if st is not None:
                    for x, y in zip(xs.tolist(), ys.tolist()):
                        damage_tile(st, x, y, 0.15 * closing)
            # Back the faster ship off until the hulls just touch.
            mover, mpos, mhd = (pa, pa, ha) if sa.knots >= sb.knots else (pb, pb, hb)
            fx, fy = math.sin(math.radians(mhd.degrees)), math.cos(math.radians(mhd.degrees))
            for _ in range(40):
                poseA = (pa.x_m, pa.y_m, ha.degrees)
                poseB = (pb.x_m, pb.y_m, hb.degrees)
                if _overlap(poseA, la, poseB, lb)[0].size == 0:
                    break
                mpos.x_m -= fx * 0.25
                mpos.y_m -= fy * 0.25
            sa.knots = sb.knots = 0.0
            poseA = (pa.x_m, pa.y_m, ha.degrees)
            poseB = (pb.x_m, pb.y_m, hb.degrees)
            gw = gangways(poseA, la, poseB, lb)
            world.add_component(ea, c.Fouled(other=eb, since_s=state.now_s, gangways=gw))
            world.add_component(eb, c.Fouled(other=ea, since_s=state.now_s, gangways=[(b, a) for a, b in gw]))
            na = world.component_for_entity(ea, c.Name).full
            nb = world.component_for_entity(eb, c.Name).full
            state.say(f"{na} and {nb} fall aboard each other - fouled! ({len(gw)} places to cross)", "alert")


def pin_fouled_system(state, dt: float) -> None:
    """Fouled ships don't sail: keep them stopped."""
    for ent, (fouled, speed) in state.world.get_components(c.Fouled, c.Speed):
        speed.knots = 0.0


def _faction_of(world, ship: int) -> str:
    f = world.try_component(ship, c.Faction)
    return f.name if f else "neutral"


def boarding_system(state, dt: float) -> None:
    world = state.world
    rng = state.rng.stream("boarding")
    # Who is standing where, per ship.
    occupants: dict = {}
    for ent, (crew, pos) in world.get_components(c.CrewMember, c.DeckPosition):
        body = world.try_component(ent, pc.Body)
        if body is not None and not body.alive:
            continue
        occupants.setdefault(crew.ship, {}).setdefault((pos.x, pos.y), []).append(ent)

    for ship, (orders, fouled, body) in world.get_components(c.ShipOrders, c.Fouled, c.ShipBody):
        if not orders.boarders_away or not fouled.gangways:
            continue
        # Assign boarders once: marines and the best fighters, about half
        # the hands on deck.
        if not orders.boarders_assigned:
            hands = [(e, cm, t) for e, (cm, t) in world.get_components(c.CrewMember, c.CrewTask)
                     if cm.ship == ship and t.station_kind != "post" and world.has_component(e, c.DeckPosition)]
            hands = [h for h in hands if not world.has_component(h[0], pc.Dead)]
            skill = lambda e: world.try_component(e, pc.Skills).get("melee") if world.try_component(e, pc.Skills) else 0.3
            hands.sort(key=lambda h: -skill(h[0]))
            for e, cm, t in hands[: max(1, len(hands) // 2)]:
                t.kind, t.station, t.station_kind, t.path = "board", None, "board", []
            orders.boarders_assigned = True
            state.say(f"Boarders away! {max(1, len(hands) // 2)} men for the enemy's deck.", "order")

    # Move boarders / defenders.
    for ent, (crew, task, pos) in list(world.get_components(c.CrewMember, c.CrewTask, c.DeckPosition)):
        if task.kind not in ("board", "fight"):
            continue
        if world.has_component(ent, pc.Dead):
            continue
        body = world.try_component(ent, pc.Body)
        if body is not None and not body.conscious:
            continue
        if task.cooldown_ticks > 0:
            task.cooldown_ticks -= 1
            continue
        layout = world.component_for_entity(crew.ship, c.ShipBody).layout
        fouled = world.try_component(crew.ship, c.Fouled)
        if task.kind == "board" and fouled is not None:
            ends = {a: b for a, b in fouled.gangways}
            if (pos.x, pos.y) in ends:
                # Step across onto the other ship's deck.
                bx, by = ends[(pos.x, pos.y)]
                crew.ship = fouled.other
                pos.x, pos.y = bx, by
                task.kind, task.path = "fight", []
                task.cooldown_ticks = BOARDER_STEP_TICKS
                continue
            if not task.path:
                goal = min(ends, key=lambda a: abs(a[0] - pos.x) + abs(a[1] - pos.y))
                task.path = bfs_path(layout.walkable, (pos.x, pos.y), goal)
        elif task.kind == "fight":
            foes = [(xy, e) for xy, es in occupants.get(crew.ship, {}).items() for e in es if _enemy(world, ent, e)]
            if foes and not task.path:
                goal = min((xy for xy, _ in foes), key=lambda a: abs(a[0] - pos.x) + abs(a[1] - pos.y))
                if max(abs(goal[0] - pos.x), abs(goal[1] - pos.y)) > 1:
                    task.path = bfs_path(layout.walkable, (pos.x, pos.y), goal)[:-1]
        if task.path:
            pos.x, pos.y = task.path.pop(0)
        task.cooldown_ticks = BOARDER_STEP_TICKS

    # Defenders turn out when the enemy is on their deck.
    for ship, es_by_tile in occupants.items():
        intruders = any(_home_faction(world, e) != _faction_of(world, ship) for es in es_by_tile.values() for e in es)
        if not intruders:
            continue
        for e, (cm, t) in world.get_components(c.CrewMember, c.CrewTask):
            if cm.ship == ship and t.kind in ("idle", "station") and t.station_kind != "post" and not world.has_component(e, pc.Dead):
                t.kind, t.station, t.station_kind, t.path = "fight", None, "fight", []

    _melee(state, occupants, rng, dt)


def _home_faction(world, ent: int) -> str:
    cm = world.component_for_entity(ent, c.CrewMember)
    return _faction_of(world, cm.home_ship if cm.home_ship >= 0 else cm.ship)


def _enemy(world, a: int, b: int) -> bool:
    return _home_faction(world, a) != _home_faction(world, b)


def _melee(state, occupants, rng, dt) -> None:
    world = state.world
    for ship, tiles in occupants.items():
        for (x, y), es in tiles.items():
            for a in es:
                ta = world.try_component(a, c.CrewTask)
                ba = world.try_component(a, pc.Body)
                if ta is None or ta.kind != "fight" or (ba is not None and (not ba.alive or not ba.conscious)):
                    continue
                if rng.random() > dt / BLOW_INTERVAL_S:
                    continue
                near = [b for dx in (-1, 0, 1) for dy in (-1, 0, 1) for b in tiles.get((x + dx, y + dy), [])
                        if b != a and _enemy(world, a, b) and not world.has_component(b, pc.Dead)]
                if not near:
                    continue
                b = rng.choice(near)
                sa = world.try_component(a, pc.Skills)
                sb = world.try_component(b, pc.Skills)
                ma = sa.get("melee") if sa else 0.3
                mb = sb.get("melee") if sb else 0.3
                pa = world.try_component(a, pc.Psyche)
                fear = pa.fear if pa else 0.0
                p_hit = max(0.05, min(0.9, 0.35 + 0.5 * (ma - mb) - 0.2 * fear))
                if rng.random() < p_hit:
                    part = _weighted_part(rng)
                    sev = rng.uniform(0.08, 0.4) + 0.25 * ma * rng.random()
                    wound(state, b, part, sev, "cut")


def _weighted_part(rng) -> str:
    total = sum(w for _, w in PARTS_WEIGHTED)
    r = rng.uniform(0, total)
    for p, w in PARTS_WEIGHTED:
        r -= w
        if r <= 0:
            return p
    return "chest"
