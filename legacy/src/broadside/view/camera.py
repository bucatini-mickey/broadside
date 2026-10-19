# A camera over world metres: centre, scale (metres per terminal column),
# row aspect, and rotation.
#
# Every view in the game is this one camera with different settings - the
# 1 m Dwarf-Fortress deck view, a 12 m squadron view, a 160 m chart view,
# north-up or ship-up. The composer asks the camera for the world point at
# the centre of each screen cell and samples the scene there, so zoom and
# rotation are free: nothing downstream knows or cares.
#
# `aspect` is metres per row divided by metres per column. Terminal cells
# are roughly twice as tall as wide, so aspect 1.0 gives true 1 m x 1 m
# cells (shapes look stretched vertically, as in DF's text mode) and 2.0
# gives cells that are 1 m wide and 2 m tall (shapes look right).

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Camera:
    cx: float
    cy: float
    cell_m: float = 1.0
    aspect: float = 1.0
    rotation: float = 0.0  # compass bearing that points screen-up

    def _axes(self) -> tuple[float, float, float, float]:
        r = math.radians(self.rotation)
        ux, uy = math.sin(r), math.cos(r)
        return uy, -ux, ux, uy  # right_x, right_y, up_x, up_y

    def grid(self, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        """World (x, y) of every screen cell centre, arrays shaped (height, width)."""
        rx, ry, ux, uy = self._axes()
        cols = (np.arange(width) + 0.5 - width / 2.0) * self.cell_m
        rows = (height / 2.0 - np.arange(height) - 0.5) * self.cell_m * self.aspect
        ox, oy = np.meshgrid(cols, rows)
        return self.cx + ox * rx + oy * ux, self.cy + ox * ry + oy * uy

    def to_screen(self, x, y, width: int, height: int):
        """World point(s) -> integer (col, row). Works on scalars or arrays;
        results may be off-screen (caller clips)."""
        rx, ry, ux, uy = self._axes()
        dx = np.asarray(x, dtype=np.float64) - self.cx
        dy = np.asarray(y, dtype=np.float64) - self.cy
        ox = dx * rx + dy * ry
        oy = dx * ux + dy * uy
        col = np.floor(ox / self.cell_m + width / 2.0).astype(np.int64)
        row = np.floor(height / 2.0 - oy / (self.cell_m * self.aspect)).astype(np.int64)
        return col, row

    def screen_vector(self, dx: float, dy: float) -> tuple[float, float]:
        """A world direction as a screen direction (col right, row down),
        aspect-corrected - for choosing directional glyphs."""
        rx, ry, ux, uy = self._axes()
        return dx * rx + dy * ry, -(dx * ux + dy * uy) / self.aspect

    def extent(self, width: int, height: int) -> tuple[float, float, float, float]:
        """World-axis bounding box (x0, y0, x1, y1) of the whole view."""
        hw = width * self.cell_m / 2.0
        hh = height * self.cell_m * self.aspect / 2.0
        rx, ry, ux, uy = self._axes()
        corners_x = [self.cx + sx * hw * rx + sy * hh * ux for sx in (-1, 1) for sy in (-1, 1)]
        corners_y = [self.cy + sx * hw * ry + sy * hh * uy for sx in (-1, 1) for sy in (-1, 1)]
        return min(corners_x), min(corners_y), max(corners_x), max(corners_y)


ZOOM_LEVELS_M = [1.0, 2.0, 4.0, 8.0, 12.0, 20.0, 40.0, 80.0, 160.0, 320.0, 640.0]


def compass_arrow(screen_dx: float, screen_dy: float) -> str:
    """Arrow glyph pointing along a screen-space direction (row down +).
    Four-way only: diagonal arrows are missing from common Windows fonts."""
    ang = (math.degrees(math.atan2(screen_dx, -screen_dy)) + 360.0) % 360.0
    return "↑→↓←"[int((ang + 45.0) // 90) % 4]
