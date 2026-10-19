# Materials and per-tile condition: every square metre of every ship (and,
# later, every fortress wall) is a piece of something with a condition.
#
# A ship class's deck plan (sim/shiplayout.py) is shared, read-only data.
# Each individual ship carries a StructureState: numpy arrays over the same
# grid holding, per tile, what it's made of, its integrity (1 = sound, 0 =
# gone), and whether it's burning. Damage, fire and repair act on these
# numbers; the renderer shades damaged planks and shows holes. The same
# component will serve fortresses (stone, earth, timber) as static
# structures on land - see docs/design/13_structures_and_items.md.

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from broadside.sim import shiplayout as sl


@dataclass(frozen=True)
class Material:
    key: str
    name: str
    toughness: float  # relative resistance to damage per metre (oak = 1)
    flammability: float  # 0..1
    splinters: float  # 0..1: how much it throws killing splinters when struck
    density: float  # kg/m^3


MATERIALS = {m.key: m for m in [
    Material("oak", "oak", 1.0, 0.35, 0.9, 750),
    Material("elm", "elm", 0.8, 0.35, 0.6, 600),
    Material("pine", "pine planking", 0.55, 0.55, 0.5, 520),
    Material("fir", "fir spar", 0.6, 0.55, 0.5, 520),
    Material("iron", "iron", 3.0, 0.0, 0.1, 7800),
    Material("copper", "copper", 2.0, 0.0, 0.0, 8900),
    Material("canvas", "canvas", 0.05, 0.9, 0.0, 600),
    Material("hemp", "hemp cordage", 0.1, 0.7, 0.0, 1100),
    Material("stone", "stone", 4.0, 0.0, 0.5, 2400),
    # Dressed stone in lime mortar - a fortification wall. Weaker than
    # solid rock: a 24-pounder at short range drives ~1-1.5 m into it.
    Material("masonry", "masonry", 3.0, 0.0, 0.6, 2200),
    Material("earth", "rammed earth", 2.5, 0.0, 0.0, 1800),
]}
MAT_CODES = {k: i for i, k in enumerate(MATERIALS)}
MAT_BY_CODE = {i: MATERIALS[k] for k, i in MAT_CODES.items()}

# What each deck-plan tile is built of. Hulls were oak; decks were planked
# in pine or fir; masts and spars fir; guns iron.
TILE_MATERIAL = {
    sl.HULL: "oak",
    sl.DECK: "pine",
    sl.MAST: "fir",
    sl.GUN: "iron",
    sl.WHEEL: "oak",
    sl.CAPSTAN: "elm",
    sl.HATCH: "oak",
    sl.BOWSPRIT: "fir",
}


@dataclass
class StructureState:
    material: np.ndarray  # [y, x] material codes (-1 = nothing)
    integrity: np.ndarray  # [y, x] 0..1
    burning: np.ndarray  # [y, x] 0..1 fire intensity
    events: list = field(default_factory=list)  # recent structural events

    def condition_words(self, x: int, y: int) -> str:
        if not (0 <= y < self.integrity.shape[0] and 0 <= x < self.integrity.shape[1]):
            return ""
        code = int(self.material[y, x])
        if code < 0:
            return ""
        i = float(self.integrity[y, x])
        state = "sound" if i > 0.9 else "scarred" if i > 0.6 else "splintered" if i > 0.3 else "shattered" if i > 0.0 else "shot away"
        fire = " - ON FIRE" if self.burning[y, x] > 0.05 else ""
        return f"{MAT_BY_CODE[code].name}, {state} ({i * 100:.0f}%){fire}"


def new_structure_state(layout: sl.DeckLayout) -> StructureState:
    mat = np.full(layout.tiles.shape, -1, dtype=np.int16)
    for tile, key in TILE_MATERIAL.items():
        mat[layout.tiles == tile] = MAT_CODES[key]
    integ = np.where(mat >= 0, 1.0, 0.0)
    return StructureState(material=mat, integrity=integ, burning=np.zeros(layout.tiles.shape))


def damage_tile(state: StructureState, x: int, y: int, amount: float) -> float:
    """Reduce a tile's integrity by `amount` of oak-equivalent damage
    (tougher materials lose less). Returns the integrity lost."""
    if not (0 <= y < state.integrity.shape[0] and 0 <= x < state.integrity.shape[1]):
        return 0.0
    code = int(state.material[y, x])
    if code < 0:
        return 0.0
    before = float(state.integrity[y, x])
    after = max(0.0, before - amount / MAT_BY_CODE[code].toughness)
    state.integrity[y, x] = after
    return before - after
