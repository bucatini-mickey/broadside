# The side panel: ship status, weather and visibility, what we know about
# the look readout and the small shared pieces the panels are built from
# for the cursor, and key help. Reads sim state; never mutates it.

from __future__ import annotations

import math
import textwrap
from typing import Optional

import numpy as np

from broadside.render.buffer import ScreenBuffer
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.spatial import COURSES_TRIM
from broadside.sim.units import bearing_degrees
from broadside.sim.vision import VIS_FAINT, Eye, direct_sampler, trace
from broadside.sim.world import terrain as tr
from broadside.view import style as S

TEXT = (225, 225, 225)
DIM = (140, 140, 150)
HEAD = (240, 210, 120)
RULE = (70, 70, 84)
KIND_COLORS = {"sight": (140, 200, 235), "gun": (240, 170, 110), "order": (200, 220, 140), "alert": (240, 110, 100), "info": (190, 190, 200)}

STATUS_TEXT = {"hull": "IN SIGHT", "topsails": "TOPSAILS", "lost": "LOST", "none": "-"}


class _Writer:
    def __init__(self, buf: ScreenBuffer, x0: int, y0: int, w: int, h: int):
        self.buf, self.x0, self.y0, self.w, self.h = buf, x0, y0, w, h
        self.row = 0

    @property
    def full(self) -> bool:
        return self.row >= self.h

    def line(self, text: str = "", fg=TEXT, bg=None) -> None:
        if self.full:
            return
        self.buf.draw_text(self.x0 + 1, self.y0 + self.row, text[: self.w - 2], fg=fg, bg=bg)
        self.row += 1

    def spans(self, parts) -> None:
        if self.full:
            return
        x = self.x0 + 1
        for text, fg in parts:
            room = self.x0 + self.w - 1 - x
            if room <= 0:
                break
            self.buf.draw_text(x, self.y0 + self.row, text[:room], fg=fg)
            x += len(text[:room])
        self.row += 1

    def rule(self, title: str = "") -> None:
        if self.full:
            return
        t = f"─ {title} " if title else ""
        self.buf.draw_text(self.x0 + 1, self.y0 + self.row, (t + "─" * self.w)[: self.w - 2], fg=RULE)
        if title:
            self.buf.draw_text(self.x0 + 3, self.y0 + self.row, title[: self.w - 5], fg=HEAD)
        self.row += 1


def describe_point(state, view, x: float, y: float, eye: Optional[Eye]) -> list[str]:
    """The 'look' readout for a world point: what's there, and whether (and
    why not) the current observer can see it."""
    scene = state.scene()
    content = scene.sample(np.array([x]), np.array([y]))
    lines = []
    code = int(content.terrain.code[0])
    h = float(content.terrain.height[0])
    what = tr.TERRAIN_NAMES.get(code, "?")
    if h > 0.5:
        what += f", {h:.0f} m high"
    si = int(content.ship[0])
    if si >= 0:
        g = scene.geoms[si]
        tile = sl.TILE_NAMES.get(int(content.tile[0]), "?")
        lines.append(f"{g.name}: {tile}")
    else:
        lines.append(what.capitalize())
    if int(content.sail[0]) >= 0:
        lines.append(f"  sail of {scene.geoms[int(content.sail[0])].name} overhead")
    for ent, (crew, dpos) in state.world.get_components(c.CrewMember, c.DeckPosition):
        g = scene.geom_for(crew.ship)
        if g is None or state.world.has_component(ent, c.Aloft):
            continue
        wx, wy = g.tile_world(dpos.x, dpos.y)
        if abs(wx - x) < 0.6 and abs(wy - y) < 0.6:
            from broadside.view.people_view import person_brief

            lines.extend(person_brief(state.world, ent))
    if si >= 0:
        from broadside.sim.items import Contents, items_at
        from broadside.sim.structure import StructureState

        g = scene.geoms[si]
        gx, gy = int(content.gx[0]), int(content.gy[0])
        sst = state.world.try_component(g.entity, StructureState)
        if sst is not None:
            cond = sst.condition_words(gx, gy)
            if cond:
                lines.append("  " + cond)
        for _e, item, cont in items_at(state.world, g.entity, gx, gy):
            goods = ", ".join(f"{q:g} {cont.unit} {k}" for k, q in cont.goods.items()) if cont else ""
            lines.append(f"  {item.kind}: {goods}")
    f = content.fields
    if f.fog_sigma[0] > 0.002:
        lines.append(f"  fog: visibility ~{3.912 / f.fog_sigma[0]:.0f} m")
    if f.smoke_sigma[0] > 0.005:
        lines.append(f"  powder smoke (density {f.smoke_sigma[0]:.2f})")
    if eye is not None:
        d = math.hypot(x - eye.x, y - eye.y)
        s = trace(
            eye,
            np.array([x]),
            np.array([y]),
            content.surface_h,
            content.tall_h,
            direct_sampler(scene, ignore_hull_of=state.player_ship),
            step_m=max(0.5, d / 400),
            haze_sigma=state.atmosphere.haze_sigma,
            end_skip_m=0.7,
            poles=scene.poles(),
            sails=scene.sail_walls(),
        )
        brg = bearing_degrees(x - eye.x, y - eye.y)
        if s.low[0] >= VIS_FAINT:
            vis = f"in sight ({s.low[0] * 100:.0f}% clarity)"
        elif s.high[0] >= VIS_FAINT:
            vis = "only its top is in sight"
        elif s.solid_low[0]:
            vis = "hidden - something solid in the way"
        else:
            vis = "hidden - lost in the murk"
        lines.append(f"  {d:,.0f} m, bearing {brg:03.0f}: {vis}")
    return lines
