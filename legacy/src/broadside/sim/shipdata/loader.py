# Loads and caches ship class stat blocks from sim/data/ships/*.yaml.
#
# Kept deliberately simple (a dataclass + a dict-returning YAML load) rather
# than a full schema/validation layer - worth revisiting once more ship
# classes exist and mistakes in a YAML file become likely enough to want
# caught early. See docs/design/02_simulation_systems.md for the full stat
# model this will eventually need to support (per-section hull, per-sail
# damage, etc.) - this loader's job is just to get the raw data in.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ships"


@dataclass
class GunBattery:
    type: str
    count: int
    deck: str


@dataclass
class ShipClassData:
    name: str
    ship_class: str
    rate: str
    length_m: float
    beam_m: float
    draught_m: float
    tonnage_bm: float
    max_crew: int
    guns: list[GunBattery]
    sail_plan: str
    deck_width: int
    deck_height: int
    notes: str = ""

    @property
    def total_guns(self) -> int:
        return sum(g.count for g in self.guns)


def _parse(raw: dict[str, Any]) -> ShipClassData:
    guns = [GunBattery(**g) for g in raw.get("guns", [])]
    grid = raw.get("deck_grid", {"width": 20, "height": 8})
    return ShipClassData(
        name=raw["name"],
        ship_class=raw["ship_class"],
        rate=raw.get("rate", "Unrated"),
        length_m=float(raw["length_m"]),
        beam_m=float(raw["beam_m"]),
        draught_m=float(raw.get("draught_m", 0.0)),
        tonnage_bm=float(raw.get("tonnage_bm", 0.0)),
        max_crew=int(raw["max_crew"]),
        guns=guns,
        sail_plan=raw.get("sail_plan", ""),
        deck_width=int(grid["width"]),
        deck_height=int(grid["height"]),
        notes=raw.get("notes", ""),
    )


@lru_cache(maxsize=None)
def load_ship_class(ship_class: str) -> ShipClassData:
    """Load a ship class by its key (matching a filename under
    sim/data/ships/, e.g. "sloop_18" -> sloop_18.yaml)."""
    path = DATA_DIR / f"{ship_class}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in DATA_DIR.glob("*.yaml"))
        raise FileNotFoundError(
            f"No ship class data for '{ship_class}' (looked in {path}). "
            f"Available: {available}"
        )
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _parse(raw)


def available_ship_classes() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob("*.yaml"))
