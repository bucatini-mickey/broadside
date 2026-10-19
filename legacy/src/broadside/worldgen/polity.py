# Settlements, nations and territory on a generated geography.
#
# Ports go where a real port would: on the coast, in bays (enough sea
# around to anchor, sheltered by land on several sides), spaced out along
# the shore. Nations grow from regional capitals over land, the way
# kingdoms did, each region with its own generated people and language.
# One outside maritime power - the player's by default, a sea empire from
# beyond the strait - holds only a scatter of island and strait bases,
# which is exactly the position Britain was in historically.

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from broadside.sim.people.cultures import CULTURES, GOVERNMENTS, make_culture, register
from broadside.worldgen.geography import Geography

NATION_COLORS = [(90, 200, 235), (235, 96, 76), (236, 204, 70), (150, 210, 120), (190, 120, 230), (240, 150, 70), (120, 150, 240), (230, 130, 190), (170, 170, 170)]


@dataclass
class Settlement:
    id: int
    name: str
    col: int
    row: int
    kind: str  # "capital" | "city" | "port" | "village" | "fortress"
    population: int
    harbour: float  # 0..1 anchorage quality
    fortified: bool
    owner: int = -1
    founded: int = 0
    history: list = field(default_factory=list)


@dataclass
class Nation:
    id: int
    name: str
    adjective: str
    culture: str
    government: str
    color: tuple
    capital: int  # settlement id
    navy: int = 10  # ships of force, roughly
    strength: float = 1.0
    player: bool = False
    outside_power: bool = False
    relations: dict = field(default_factory=dict)  # nation id -> -1..1


def _coastal(land: np.ndarray) -> np.ndarray:
    sea = ~land
    near = np.zeros_like(land)
    near[1:, :] |= sea[:-1, :]
    near[:-1, :] |= sea[1:, :]
    near[:, 1:] |= sea[:, :-1]
    near[:, :-1] |= sea[:, 1:]
    return land & near


def _sea_fraction(land: np.ndarray, r: int = 3) -> np.ndarray:
    sea = (~land).astype(np.float32)
    k = 2 * r + 1
    pad = np.pad(sea, r, mode="edge")
    acc = np.zeros_like(sea)
    for dy in range(k):
        for dx in range(k):
            acc += pad[dy : dy + sea.shape[0], dx : dx + sea.shape[1]]
    return acc / (k * k)


def place_settlements(geo: Geography, rng: random.Random, n_ports: int = 70, spacing: int = 6) -> list:
    land = geo.land
    coast = _coastal(land)
    seafrac = _sea_fraction(land, 3)
    H, W = land.shape
    rows, cols = np.nonzero(coast)
    # Bays score best: some sea around, but land on most sides. Low ground
    # scores better than cliffs.
    bay = 1.0 - np.abs(seafrac[rows, cols] - 0.35) * 2.2
    low = 1.0 - np.clip(geo.height[rows, cols] / 800.0, 0, 1)
    edge = (cols > 2) & (cols < W - 3) & (rows > 2) & (rows < H - 3)
    score = np.where(edge, bay * 0.7 + low * 0.3 + np.array([rng.random() * 0.25 for _ in rows]), -9)
    order = np.argsort(-score)
    chosen = []
    taken = np.zeros_like(land)
    for i in order:
        if len(chosen) >= n_ports:
            break
        r, c = int(rows[i]), int(cols[i])
        if taken[max(0, r - spacing) : r + spacing + 1, max(0, c - spacing) : c + spacing + 1].any():
            continue
        taken[r, c] = True
        chosen.append((r, c, float(np.clip(bay[i], 0, 1))))
    out = []
    for k, (r, c, h) in enumerate(chosen):
        kind = "port" if h > 0.55 else "village"
        pop = int(rng.lognormvariate(8.3 if kind == "port" else 6.8, 0.6))
        out.append(Settlement(k, "", c, r, kind, pop, h, fortified=kind == "port" and rng.random() < 0.35))
    return out


# Regional heartlands, in fractional map coordinates. Each gets its own
# generated people and language (cultures.py) - nothing is tied to a real
# people; which sound systems a region's language blends is chosen by the
# world seed.
REGIONS = [(0.20, 0.82), (0.42, 0.85), (0.58, 0.72), (0.78, 0.74), (0.93, 0.50), (0.35, 0.12), (0.75, 0.12)]


def make_world_cultures(seed: int, n: int) -> list:
    """n fresh peoples for a world, keys unique to the seed."""
    return [register(make_culture(f"w{seed}c{i}", seed * 131 + i * 7919)).key for i in range(n)]


def found_nations(geo: Geography, settlements: list, rng: random.Random, cultures: list, player_nation: str | None = None, player_culture: str | None = None) -> list:
    """`cultures`: generated culture keys, one per region; the last extra
    one (or `player_culture`) is the outside sea power's people."""
    H, W = geo.shape
    land = geo.land
    nations: list[Nation] = []
    used = set()
    # Regional powers: the best port near each region's heartland.
    for i, (fx, fy) in enumerate(REGIONS):
        cult = cultures[i % len(cultures)]
        tx, ty = fx * W, fy * H
        cands = sorted((s for s in settlements if s.id not in used), key=lambda s: (s.col - tx) ** 2 + ((s.row - ty) * 2.2) ** 2 - s.harbour * 400)
        if not cands:
            continue
        cap = cands[0]
        used.add(cap.id)
        cap.kind = "capital"
        cap.population = int(cap.population * rng.uniform(6, 12))
        cap.fortified = True
        c = CULTURES[cult]
        nations.append(Nation(len(nations), c.nation_name(rng), c.adjective, cult, rng.choice(GOVERNMENTS), NATION_COLORS[len(nations) % len(NATION_COLORS)], cap.id, navy=rng.randint(6, 30)))
    # Territory: grow from capitals over land (multi-source BFS, mountains
    # slow the spread); islands go to whoever's capital is nearest.
    owner = np.full(land.shape, -1, dtype=np.int16)
    frontier = []
    by_id = {s.id: s for s in settlements}
    for n in nations:
        cap = by_id[n.capital]
        owner[cap.row, cap.col] = n.id
        frontier.append((cap.row, cap.col, n.id))
    cost = np.where(geo.height > 900, 3, 1)
    budget = np.zeros(land.shape)
    from collections import deque

    q = deque(frontier)
    while q:
        r, c, nid = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and land[rr, cc] and owner[rr, cc] < 0:
                budget[rr, cc] = budget[r, c] + cost[rr, cc]
                owner[rr, cc] = nid
                q.append((rr, cc, nid))
    unowned = land & (owner < 0)
    if unowned.any():
        caps = np.array([[by_id[n.capital].row, by_id[n.capital].col] for n in nations])
        rr, cc = np.nonzero(unowned)
        d = (rr[:, None] - caps[None, :, 0]) ** 2 * 4 + (cc[:, None] - caps[None, :, 1]) ** 2
        owner[rr, cc] = np.array([nations[i].id for i in np.argmin(d, axis=1)])
    for s in settlements:
        s.owner = int(owner[s.row, s.col])

    # The outside sea power: bases at the strait and on the best island
    # harbours, taken from their owners.
    player_culture = player_culture or cultures[-1]
    c = CULTURES[player_culture]
    outside = Nation(len(nations), player_nation or c.nation_name(rng), c.adjective, player_culture, rng.choice(["kingdom", "empire", "commonwealth", "republic"]),
                     NATION_COLORS[len(nations) % len(NATION_COLORS)], -1, navy=rng.randint(30, 45), outside_power=True, player=True)
    sc, sr = geo.features.get("strait", (0, H // 2))
    strait_port = min(settlements, key=lambda s: (s.col - sc) ** 2 + (s.row - sr) ** 2)
    island_ports = sorted((s for s in settlements if _on_island(geo, s)), key=lambda s: -s.harbour)[:2]
    bases = [strait_port] + [s for s in island_ports if s is not strait_port]
    for s in bases:
        s.owner = outside.id
        s.fortified = True
        s.kind = "fortress" if s is strait_port else "port"
    outside.capital = bases[0].id
    nations.append(outside)
    # Name every settlement in its owner's tongue.
    names = set()
    for s in settlements:
        cult = CULTURES[nations[s.owner].culture if s.owner >= 0 else cultures[0]]
        for _ in range(10):
            nm = cult.place_name(rng)
            if nm not in names:
                break
        names.add(nm)
        s.name = nm
    for a in nations:
        for b in nations:
            if a.id != b.id:
                a.relations[b.id] = rng.uniform(-0.4, 0.5)
    return nations, owner


def _on_island(geo: Geography, s: Settlement, big: int = 2500) -> bool:
    """Crude: flood the land region containing the settlement; small ones
    are islands."""
    land = geo.land
    H, W = land.shape
    seen = {(s.row, s.col)}
    stack = [(s.row, s.col)]
    while stack and len(seen) < big:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and land[rr, cc] and (rr, cc) not in seen:
                seen.add((rr, cc))
                stack.append((rr, cc))
    return len(seen) < big
