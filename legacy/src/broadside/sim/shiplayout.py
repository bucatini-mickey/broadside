# Generates a ship's 1 m deck plan from its class stat block.
#
# Every tile is one square metre of weather deck - the Dwarf-Fortress-scale
# unit the local view renders at. The plan is generated procedurally from
# the class's real length, beam, gun count and rig (sim/data/ships/*.yaml)
# rather than hand-drawn, so adding a ship class is a data change; a
# hand-authored ASCII plan in the YAML can replace this later per class.
#
# Grid convention: tiles[y, x], x runs stern (0) -> bow, y runs port (0) ->
# starboard. Local metric coordinates are (u forward, v starboard) measured
# from the ship's centre. The grid is wider than the hull: margins either
# side hold the yards (which overhang the rail) and the bow extension holds
# the bowsprit - things that exist aloft or outboard but belong to the ship.
#
# Heights here are metres above the *deck* for fittings, plus a freeboard
# (deck height above the waterline) for the ship as a whole. They feed the
# 2.5D line-of-sight model: bulwarks hide the water close alongside, masts
# are thin but tall, sails are an overhanging wall that blocks the view
# forward from the quarterdeck but not from the masthead.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from broadside.sim.shipdata.loader import ShipClassData

NONE = 0
HULL = 1  # bulwark / rail - the solid edge of the deck
DECK = 2
MAST = 3
GUN = 4
WHEEL = 5
CAPSTAN = 6
HATCH = 7
BOWSPRIT = 8

TILE_NAMES = {
    NONE: "open air",
    HULL: "bulwark",
    DECK: "deck planking",
    MAST: "mast",
    GUN: "gun",
    WHEEL: "ship's wheel",
    CAPSTAN: "capstan",
    HATCH: "hatch grating",
    BOWSPRIT: "bowsprit",
}

WALKABLE = {DECK, HATCH}

# Obstruction height above deck for each fitting. Masts are handled per
# mast (they differ in height).
FITTING_TOP_M = {
    HULL: 1.1,
    DECK: 0.0,
    GUN: 0.7,
    WHEEL: 1.3,
    CAPSTAN: 0.9,
    HATCH: 0.2,
    BOWSPRIT: 0.0,
}

EYE_ABOVE_DECK_M = 1.7
# Just below eye height: from the quarterdeck you see your own deck under
# the courses, but the near-horizontal line to the distant sea ahead runs
# into the canvas - the reason ships kept lookouts aloft.
SAIL_FOOT_ABOVE_DECK_M = 1.4

# Decks whose guns stand on the weather deck (and so appear on the plan
# with crews you can see). Guns on a covered gundeck still fire and smoke,
# but are worked out of sight below.
WEATHER_DECKS = {"main deck", "upper deck", "quarterdeck", "forecastle", "weather deck"}


@dataclass
class MastSpec:
    name: str
    x: int
    y: int
    height_above_deck: float
    yard_half_m: float  # half-length of the lowest (course) yard


@dataclass
class GunSpec:
    index: int
    x: int
    y: int
    side: int  # -1 = port, +1 = starboard
    kind: str
    crew_tiles: list[tuple[int, int]]
    on_deck: bool = True  # False = gundeck battery below, no tile


@dataclass
class DeckLayout:
    tiles: np.ndarray  # [y, x] uint8 tile codes
    hull_length: int
    beam: int
    overhang: int  # grid rows either side of the hull reserved for yards
    freeboard_m: float
    masts: list[MastSpec]
    guns: list[GunSpec]
    helm: tuple[int, int]
    captain_post: tuple[int, int]
    walkable: np.ndarray = field(repr=False, default=None)  # [y, x] bool

    @property
    def width(self) -> int:
        return int(self.tiles.shape[1])

    @property
    def height(self) -> int:
        return int(self.tiles.shape[0])

    @property
    def centre_row(self) -> int:
        return self.overhang + self.beam // 2

    @property
    def centre_x(self) -> float:
        """Grid x of the hull's midships point (u = 0)."""
        return (self.hull_length - 1) / 2.0

    def local_m(self, x: float, y: float) -> tuple[float, float]:
        """Tile centre -> (forward, starboard) metres from ship centre."""
        return float(x) - self.centre_x, float(y) - self.centre_row

    def grid_from_local(self, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        gx = np.floor(u + self.centre_x + 0.5).astype(np.int64)
        gy = np.floor(v + self.centre_row + 0.5).astype(np.int64)
        return gx, gy

    def tile(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return int(self.tiles[y, x])
        return NONE

    def main_mast(self) -> MastSpec | None:
        if not self.masts:
            return None
        return max(self.masts, key=lambda m: m.height_above_deck)

    def radius_m(self) -> float:
        """Bounding radius around the ship centre, generous enough to
        include yards and bowsprit."""
        return math.hypot(self.width, self.height) / 2.0 + 2.0

    def walkable_tiles(self) -> list[tuple[int, int]]:
        ys, xs = np.nonzero(self.walkable)
        return list(zip(xs.tolist(), ys.tolist()))


def _half_width(t: float, half_beam: float) -> float:
    """Hull half-breadth at fraction t along the hull (0 = stern, 1 = bow).
    A broad transom stern, full midships, and a curved bow tapering to the
    stem - the characteristic period hull plan."""
    if t < 0.12:
        return half_beam * (0.78 + 0.22 * (t / 0.12))
    if t < 0.58:
        return half_beam
    k = (t - 0.58) / 0.42
    return half_beam * math.sqrt(max(0.0, 1.0 - k * k)) * 0.97 + 0.35


def build_deck_layout(data: ShipClassData) -> DeckLayout:
    L = max(12, int(round(data.length_m)))
    B = max(5, int(round(data.beam_m)))
    if B % 2 == 0:
        B += 1  # an odd beam gives a true centreline row
    main_h = 0.95 * data.length_m
    yard_half = {"fore": 0.9 * data.beam_m, "main": 0.95 * data.beam_m, "mizzen": 0.7 * data.beam_m}
    overhang = int(math.ceil(max(yard_half.values()) - B / 2.0)) + 1
    bowsprit = int(round(0.28 * L))
    W = L + bowsprit
    H = B + 2 * overhang
    cy = overhang + B // 2
    half_beam = (B - 1) / 2.0

    tiles = np.zeros((H, W), dtype=np.uint8)
    for x in range(L):
        t = x / (L - 1)
        hw = _half_width(t, half_beam)
        for y in range(H):
            if abs(y - cy) <= hw + 0.25:
                tiles[y, x] = DECK

    # Bulwarks: any deck tile touching open air (4-neighbourhood).
    hull = tiles == DECK
    edge = np.zeros_like(hull)
    padded = np.pad(hull, 1, constant_values=False)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nb = padded[1 + dy : 1 + dy + H, 1 + dx : 1 + dx + W]
        edge |= hull & ~nb
    tiles[edge] = HULL

    # Bowsprit runs forward from the stem along the centreline.
    for x in range(L, W):
        tiles[cy, x] = BOWSPRIT

    masts: list[MastSpec] = []
    rig = data.sail_plan.lower()
    if "single" in rig or "lugger" in rig or "cutter" in rig:
        mast_defs = [("main", 0.58, 1.0)]
        yard_half["main"] = 0.8 * data.beam_m
    else:
        mast_defs = [("fore", 0.78, 0.88), ("main", 0.50, 1.0)]
    if "mizzen" in rig or ("ship" in rig and "single" not in rig):
        mast_defs.append(("mizzen", 0.23, 0.72))
    for name, t, hfrac in mast_defs:
        mx = int(round(t * (L - 1)))
        tiles[cy, mx] = MAST
        masts.append(MastSpec(name=name, x=mx, y=cy, height_above_deck=main_h * hfrac, yard_half_m=yard_half[name]))

    wheel_x = max(2, int(round(0.10 * (L - 1))))
    tiles[cy, wheel_x] = WHEEL
    capstan_x = int(round(0.38 * (L - 1)))
    if tiles[cy, capstan_x] == DECK:
        tiles[cy, capstan_x] = CAPSTAN
    for t in (0.33, 0.64, 0.66):
        hx = int(round(t * (L - 1)))
        for dy in (0, 1):
            if tiles[cy + dy, hx] == DECK:
                tiles[cy + dy, hx] = HATCH

    guns = _place_guns(tiles, data, L, cy)

    walkable = np.isin(tiles, list(WALKABLE))
    # The captain's post: windward-ish side of the quarterdeck, just forward
    # of the wheel. Pick the nearest walkable tile to the ideal spot.
    captain_post = _nearest_walkable(walkable, wheel_x + 1, cy - 2)
    helm = _nearest_walkable(walkable, wheel_x - 1, cy)

    freeboard = min(5.0, max(1.8, 0.08 * data.length_m))
    return DeckLayout(
        tiles=tiles,
        hull_length=L,
        beam=B,
        overhang=overhang,
        freeboard_m=freeboard,
        masts=masts,
        guns=guns,
        helm=helm,
        captain_post=captain_post,
        walkable=walkable,
    )


def _place_guns(tiles: np.ndarray, data: ShipClassData, L: int, cy: int) -> list[GunSpec]:
    guns: list[GunSpec] = []
    deck_guns: list[str] = []
    below_guns: list[str] = []
    for battery in data.guns:
        target = deck_guns if battery.deck.lower() in WEATHER_DECKS else below_guns
        target.extend([battery.type] * battery.count)

    per_side = len(deck_guns) // 2
    idx = 0
    if len(deck_guns) == 1:
        # A single gun: starboard side, just forward of midships.
        gx = int(round(0.42 * (L - 1)))
        gy = _inboard_of_rail(tiles, gx, cy, 1)
        if gy is not None and tiles[gy, gx] == DECK:
            tiles[gy, gx] = GUN
            guns.append(GunSpec(index=0, x=gx, y=gy, side=1, kind=deck_guns[0], crew_tiles=[(gx, gy - 1), (gx - 1, gy - 1), (gx + 1, gy - 1), (gx, gy - 2)]))
            idx = 1
    if per_side:
        xs = np.linspace(0.14 * (L - 1), 0.86 * (L - 1), per_side)
        for side in (-1, 1):
            for i, fx in enumerate(xs):
                gx = int(round(fx))
                # Find the first deck tile inboard of the bulwark on this side.
                gy = _inboard_of_rail(tiles, gx, cy, side)
                if gy is None:
                    continue
                # Don't put a gun on a mast or hatch; nudge along the side.
                if tiles[gy, gx] != DECK:
                    for nudge in (1, -1, 2, -2):
                        g2 = _inboard_of_rail(tiles, gx + nudge, cy, side)
                        if g2 is not None and tiles[g2, gx + nudge] == DECK:
                            gx, gy = gx + nudge, g2
                            break
                    else:
                        continue
                tiles[gy, gx] = GUN
                kind = deck_guns[(i * 2 + (0 if side < 0 else 1)) % len(deck_guns)]
                crew = [(gx, gy - side), (gx - 1, gy - side), (gx + 1, gy - side), (gx, gy - 2 * side)]
                guns.append(GunSpec(index=idx, x=gx, y=gy, side=side, kind=kind, crew_tiles=crew))
                idx += 1
    # Crew tiles must be actual walkable deck (after all guns are placed).
    for g in guns:
        g.crew_tiles = [(x, y) for (x, y) in g.crew_tiles if 0 <= y < tiles.shape[0] and 0 <= x < tiles.shape[1] and tiles[y, x] in WALKABLE]

    for side in (-1, 1):
        for i in range(len(below_guns) // 2):
            fx = int(round((0.12 + 0.76 * i / max(1, len(below_guns) // 2 - 1)) * (L - 1)))
            gy = _inboard_of_rail(tiles, fx, cy, side) or cy
            guns.append(GunSpec(index=idx, x=fx, y=gy, side=side, kind=below_guns[i], crew_tiles=[], on_deck=False))
            idx += 1
    return guns


def _inboard_of_rail(tiles: np.ndarray, x: int, cy: int, side: int) -> int | None:
    if not (0 <= x < tiles.shape[1]):
        return None
    y = cy
    last_deck = None
    while 0 <= y < tiles.shape[0]:
        t = tiles[y, x]
        if t == HULL:
            return last_deck
        if t in (DECK, HATCH, GUN, MAST, WHEEL, CAPSTAN):
            last_deck = y
        elif t == NONE:
            return last_deck
        y += side
    return last_deck


def _nearest_walkable(walkable: np.ndarray, x: int, y: int) -> tuple[int, int]:
    ys, xs = np.nonzero(walkable)
    if len(xs) == 0:
        return x, y
    d = (xs - x) ** 2 + (ys - y) ** 2
    i = int(np.argmin(d))
    return int(xs[i]), int(ys[i])


def render_ascii(layout: DeckLayout) -> str:
    """Debug helper: the plan as plain text, bow to the right."""
    glyphs = {NONE: " ", HULL: "#", DECK: ".", MAST: "O", GUN: "=", WHEEL: "&", CAPSTAN: "0", HATCH: "+", BOWSPRIT: "-"}
    rows = []
    for y in range(layout.height):
        rows.append("".join(glyphs.get(int(t), "?") for t in layout.tiles[y]))
    return "\n".join(rows)


_FOOTPRINTS: dict = {}


def footprint_local(layout: DeckLayout):
    """(u, v, gx, gy) of every hull or deck tile (not the bowsprit), in the
    ship's local metres - cached per layout."""
    key = id(layout)
    if key not in _FOOTPRINTS:
        ys, xs = np.nonzero((layout.tiles != NONE) & (layout.tiles != BOWSPRIT))
        _FOOTPRINTS[key] = (xs.astype(float) - layout.centre_x, ys.astype(float) - layout.centre_row, xs, ys)
    return _FOOTPRINTS[key]
