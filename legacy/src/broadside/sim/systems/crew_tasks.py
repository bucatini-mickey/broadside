# Crew stations and deck movement.
#
# When the captain orders the ship to quarters, every available hand is
# assigned a station - gun crews first (alternating sides), then the helm,
# then sail-trimming posts at the masts - by nearest-free-sailor greedy
# assignment, and walks there along a BFS path across the actual 1 m deck
# plan (around masts, guns and hatches, never through the bulwarks). Stand
# down and they drift back to idle wandering. Movement takes real time -
# roughly a brisk walk idle, a run at quarters - so how long a ship takes
# to clear for action falls out of her deck plan and her crew's positions,
# not a fixed number.
#
# This is the seed of the full task system in
# docs/design/02_simulation_systems.md sec. 3.

from __future__ import annotations

from collections import deque
from itertools import zip_longest

from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.items import serve_out_ammunition

IDLE_STEP_TICKS = 8
QUARTERS_STEP_TICKS = 3
GUN_CREW = 4
# Ten cartridges a gun go up when the ship clears for action, and the boys
# keep the boxes filled while the action lasts - about this often. They are
# not people yet (see docs/STATUS_REPORT.md sec. 6); the powder they carry
# is real, and comes out of the magazine.
RESUPPLY_INTERVAL_S = 40.0
# Tasks owned by other systems (boarding, health): leave these men alone.
ACTION_TASKS = ("board", "fight", "dead")

_NEIGHBOURS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def bfs_path(walkable, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    """Shortest 8-connected path over walkable tiles (no cutting corners
    past obstacles). Returns the tiles to step onto, excluding `start`;
    empty if unreachable or already there."""
    if start == goal:
        return []
    h, w = walkable.shape
    gx, gy = goal
    if not (0 <= gx < w and 0 <= gy < h):
        return []
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        cx, cy = cur
        for dx, dy in _NEIGHBOURS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in prev:
                continue
            if not walkable[ny, nx] and (nx, ny) != goal:
                continue
            if dx and dy and not (walkable[cy, nx] and walkable[ny, cx]):
                continue
            prev[(nx, ny)] = cur
            q.append((nx, ny))
    if goal not in prev:
        return []
    path = []
    node = goal
    while node != start:
        path.append(node)
        node = prev[node]
    path.reverse()
    return path


def station_list(layout: sl.DeckLayout) -> list:
    """(kind, gun_index, tile, number) in fill-priority order. At a gun the
    number is the man's station in the crew: 1 is the gun captain, 2 the
    rammer, 3 the loader, 4 the tackle men (sim/gundrill.py)."""
    guns = [g for g in layout.guns if g.on_deck]
    port = [g for g in guns if g.side < 0]
    stbd = [g for g in guns if g.side > 0]
    stations: list = [("helm", -1, layout.helm, 0)]
    # Man guns pairwise, one port one starboard, crew-slot by crew-slot, so a
    # short-handed ship has every gun partly manned rather than half fully.
    for slot in range(GUN_CREW):
        for a, b in zip_longest(port, stbd):
            for g in (a, b):
                if g is not None and slot < len(g.crew_tiles):
                    stations.append(("gun", g.index, g.crew_tiles[slot], slot + 1))
    for m in layout.masts:
        for dx, dy in ((0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            x, y = m.x + dx, m.y + dy
            if layout.tile(x, y) in sl.WALKABLE:
                stations.append(("sail", -1, (x, y), 0))
    return stations


def _assign_quarters(state, ship: int, layout: sl.DeckLayout) -> None:
    world = state.world
    hands = []
    for ent, (crew, task, pos) in world.get_components(c.CrewMember, c.CrewTask, c.DeckPosition):
        if crew.ship != ship or task.station_kind == "post" or world.has_component(ent, c.Aloft) or task.kind in ACTION_TASKS:
            continue
        hands.append((ent, task, pos))
    free = list(hands)
    for kind, gun_index, tile, number in station_list(layout):
        if not free:
            break
        best = min(free, key=lambda h: abs(h[2].x - tile[0]) + abs(h[2].y - tile[1]))
        free.remove(best)
        _, task, pos = best
        task.kind = "station"
        task.station = tile
        task.station_kind = kind
        task.gun_index = gun_index
        task.station_no = number
        task.path = bfs_path(layout.walkable, (pos.x, pos.y), tile)
        task.cooldown_ticks = 0
    for _, task, _ in free:
        task.kind = "idle"
        task.station = None
        task.station_kind = ""
        task.gun_index = -1
        task.station_no = 0


def _stand_down(state, ship: int) -> None:
    for ent, (crew, task) in state.world.get_components(c.CrewMember, c.CrewTask):
        if crew.ship == ship and task.station_kind != "post" and task.kind not in ACTION_TASKS:
            task.kind = "idle"
            task.station = None
            task.station_kind = ""
            task.gun_index = -1
            task.station_no = 0
            task.path = []


def crew_task_system(state, dt: float) -> None:
    world = state.world
    rng = state.rng.stream("crew_tasks")
    bodies = {}
    for ship, (orders, body) in world.get_components(c.ShipOrders, c.ShipBody):
        bodies[ship] = body.layout
        battery = world.try_component(ship, c.Battery)
        if orders.quarters and battery is not None and state.now_s - battery.served_s >= RESUPPLY_INTERVAL_S:
            battery.served_s = state.now_s
            brought = serve_out_ammunition(world, ship, body.layout)
            if brought and ship == state.player_ship and battery.verbose_drill:
                state.say(f"The boys bring up {brought} more rounds of powder and shot.", "order")
        if orders.quarters != orders.applied_quarters:
            if orders.quarters:
                orders.quarters_since_s = state.now_s
                _assign_quarters(state, ship, body.layout)
                served = serve_out_ammunition(world, ship, body.layout)
                if battery is not None:
                    battery.served_s = state.now_s
                if ship == state.player_ship:
                    state.say("Drums beat to quarters - hands to stations!", "order")
                    if served:
                        state.say(f"The boys bring up {served} rounds of powder and shot from below.", "order")
            else:
                _stand_down(state, ship)
                if ship == state.player_ship:
                    state.say("Stand down from quarters.", "order")
            orders.applied_quarters = orders.quarters
        elif orders.quarters:
            # Men keep arriving while an action lasts: the watch below
            # turning out, the wounded replaced, hands coming down from
            # aloft. Anyone idle gets a station.
            idle = any(
                cm.ship == ship and t.kind == "idle" and not world.has_component(e, c.Below)
                for e, (cm, t) in world.get_components(c.CrewMember, c.CrewTask)
            )
            if idle:
                _assign_quarters(state, ship, body.layout)

    for ent, (crew, task, pos) in world.get_components(c.CrewMember, c.CrewTask, c.DeckPosition):
        layout = bodies.get(crew.ship)
        if layout is None or world.has_component(ent, c.Aloft) or task.kind in ACTION_TASKS:
            continue
        if task.cooldown_ticks > 0:
            task.cooldown_ticks -= 1
            continue
        if task.kind == "station":
            if task.station is None or (pos.x, pos.y) == tuple(task.station):
                continue
            if not task.path:
                task.path = bfs_path(layout.walkable, (pos.x, pos.y), tuple(task.station))
                if not task.path:
                    continue
            pos.x, pos.y = task.path.pop(0)
            task.cooldown_ticks = QUARTERS_STEP_TICKS
            continue
        # Idle: wander to a nearby deck tile, pause, repeat.
        if task.path:
            pos.x, pos.y = task.path.pop(0)
            task.cooldown_ticks = IDLE_STEP_TICKS
            continue
        for _ in range(6):
            tx = pos.x + rng.randint(-6, 6)
            ty = pos.y + rng.randint(-3, 3)
            if layout.tile(tx, ty) in sl.WALKABLE:
                task.path = bfs_path(layout.walkable, (pos.x, pos.y), (tx, ty))[:10]
                break
        task.cooldown_ticks = rng.randint(15, 60)


def manned_counts(state, ship: int) -> dict[int, int]:
    """gun_index -> number of assigned crew actually standing at that gun."""
    counts: dict[int, int] = {}
    for ent, (crew, task, pos) in state.world.get_components(c.CrewMember, c.CrewTask, c.DeckPosition):
        if crew.ship == ship and task.station_kind == "gun" and task.station is not None and (pos.x, pos.y) == tuple(task.station):
            counts[task.gun_index] = counts.get(task.gun_index, 0) + 1
    return counts
