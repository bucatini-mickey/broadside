# A generated world: geography + settlements + nations + history, from one
# seed, with the player's own names applied.
#
#   world = generate_world(1805, CampaignSetup(captain="Jack Aubrey",
#                                              ship="Surprise",
#                                              nation="Albion"))
#
# Everything is deterministic from the seed: the same seed and setup give
# the same coasts, the same ports, the same history.

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from broadside.sim.people.cultures import CULTURES
from broadside.worldgen.geography import Geography, generate_geography
from broadside.worldgen.history import History, simulate_history
from broadside.worldgen.polity import Nation, Settlement, found_nations, place_settlements


@dataclass
class CampaignSetup:
    """What the player names. Everything else is generated."""

    captain: Optional[str] = None
    ship: Optional[str] = None
    nation: Optional[str] = None
    start_year: int = 1805


@dataclass
class World:
    seed: int
    setup: CampaignSetup
    geo: Geography
    settlements: list
    nations: list
    territory: np.ndarray  # [row, col] owning nation id, -1 = sea
    history: History
    player_ship_name: str = ""
    player_captain: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def player_nation(self) -> Nation:
        return next(n for n in self.nations if n.player)

    def settlement(self, sid: int) -> Settlement:
        return self.settlements[sid]

    def home_port(self) -> Settlement:
        return self.settlements[self.player_nation.capital]

    def places_of(self, nation_id: int) -> list:
        return [s.name for s in self.settlements if s.owner == nation_id]

    def battles_for(self, nation_id: int) -> list:
        """(year, name) of battles and sieges a veteran of this nation could
        have fought in - fed to people generation for their biographies."""
        return [(e.year, e.name) for e in self.history.battles_of(nation_id) if e.name]

    def summary(self) -> str:
        p = self.player_nation
        foes = [self.nations[b if a == p.id else a].name for a, b, s, e in self.history.wars if e is None and p.id in (a, b)]
        return (f"World {self.seed}: {self.geo.shape[1] * self.geo.cell_km:.0f} x {self.geo.shape[0] * self.geo.cell_km:.0f} km, "
                f"{len(self.settlements)} settlements, {len(self.nations)} nations, {len(self.history.events)} events of history "
                f"({self.history.start}-{self.history.end}). You are Capt. {self.player_captain} of the {self.player_ship_name}, "
                f"{p.name}. At war with: {', '.join(foes) or 'no one'}.")


def generate_world(seed: int, setup: Optional[CampaignSetup] = None, *, width: int = 360, height: int = 150) -> World:
    setup = setup or CampaignSetup()
    rng = random.Random(seed * 7919 + 17)
    geo = generate_geography(seed, width=width, height=height)
    settlements = place_settlements(geo, rng)
    from broadside.worldgen.polity import REGIONS, make_world_cultures

    cultures = make_world_cultures(seed, len(REGIONS) + 1)
    nations, territory = found_nations(geo, settlements, rng, cultures, player_nation=setup.nation)
    history = simulate_history(nations, settlements, rng, start=setup.start_year - 155, end=setup.start_year)
    cult = CULTURES[next(n for n in nations if n.player).culture]
    captain = setup.captain or " ".join(cult.person_name(rng))
    ship = setup.ship or cult.ship_name(rng)[0]
    return World(seed, setup, geo, settlements, nations, territory, history, ship, captain)


# --- Rendering the map ------------------------------------------------------


def render_map(buf, world: World, x0: int = 0, y0: int = 0, width: Optional[int] = None, height: Optional[int] = None, mode: str = "political") -> None:
    """Draw the world into a ScreenBuffer, downsampled to fit."""
    from broadside.view import style as S

    geo = world.geo
    Hm, Wm = geo.shape
    width = width or buf.width - x0
    height = height or buf.height - y0
    for yy in range(height):
        r = int((1.0 - (yy + 0.5) / height) * Hm)
        r = min(Hm - 1, max(0, r))
        for xx in range(width):
            c = min(Wm - 1, int((xx + 0.5) / width * Wm))
            h = float(geo.height[r, c])
            if h <= 0:
                deep = min(1.0, -h / 2500.0)
                bg = S.blend((40, 100, 140), (10, 30, 70), deep)
                glyph, fg = ("~" if (r + c) % 7 == 0 else " "), (80, 140, 190)
            else:
                if h > 1100:
                    glyph, fg, bg = "▲", (235, 235, 230), (95, 85, 75)
                elif h > 550:
                    glyph, fg, bg = "^", (190, 170, 130), (80, 70, 50)
                elif h > 120:
                    glyph, fg, bg = "♣", (90, 150, 80), (40, 65, 35)
                else:
                    glyph, fg, bg = '"', (160, 180, 100), (60, 75, 40)
                if mode == "political":
                    own = int(world.territory[r, c])
                    if own >= 0:
                        bg = S.blend(bg, world.nations[own].color, 0.45)
            buf.set(x0 + xx, y0 + yy, glyph, fg=fg, bg=bg)
    for s in world.settlements:
        xx = int((s.col + 0.5) / Wm * width)
        yy = int((1.0 - (s.row + 0.5) / Hm) * height)
        if not (0 <= xx < width and 0 <= yy < height):
            continue
        own = world.nations[s.owner] if s.owner >= 0 else None
        glyph = {"capital": "✪", "fortress": "■", "port": "●", "village": "·"}.get(s.kind, "o")
        if glyph == "✪":
            glyph = "*"
        buf.set(x0 + xx, y0 + yy, glyph, fg=own.color if own else (230, 230, 230), bg=(20, 20, 25))
