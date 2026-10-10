# The shape of a fictional Mediterranean.
#
# Not the real map: a generated sea with the *structure* that made the
# Mediterranean what it was for sailing ships - a long east-west basin
# between two continents, a narrow strait at the west to an outer ocean,
# a closed eastern end, big peninsulas hanging from the northern shore,
# large islands in the middle, an island-crowded archipelago, and a
# narrow passage in the north-east to an inland sea. Each piece is a
# "landness" field (positive on land); they're combined, roughened with
# fractal noise, and thresholded at sea level. Heights and depths follow
# from distance to the coast plus ridged noise, so peninsulas have
# mountain spines and the sea shelves off into deep basins.
#
# Units: the map is a grid of `cell_km` cells (default 10 km); x runs west
# to east, y south to north (row 0 = south). All randomness comes from the
# seed.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from broadside.sim.units import fractal_noise, value_noise


@dataclass
class Geography:
    seed: int
    cell_km: float
    height: np.ndarray  # [row (south->north), col (west->east)] metres; < 0 = sea depth
    features: dict = field(default_factory=dict)  # named places: "strait" -> (col, row), ...

    @property
    def shape(self) -> tuple:
        return self.height.shape

    @property
    def land(self) -> np.ndarray:
        return self.height > 0.0

    @property
    def width_km(self) -> float:
        return self.height.shape[1] * self.cell_km

    @property
    def height_km(self) -> float:
        return self.height.shape[0] * self.cell_km

    def sample_m(self, x_m: np.ndarray, y_m: np.ndarray) -> np.ndarray:
        """Bilinear height at world metres (origin = SW corner of the map)."""
        c = np.asarray(x_m, dtype=np.float64) / (self.cell_km * 1000.0) - 0.5
        r = np.asarray(y_m, dtype=np.float64) / (self.cell_km * 1000.0) - 0.5
        H, W = self.height.shape
        c = np.clip(c, 0, W - 1.001)
        r = np.clip(r, 0, H - 1.001)
        c0 = np.floor(c).astype(int)
        r0 = np.floor(r).astype(int)
        fc = c - c0
        fr = r - r0
        h = self.height
        top = h[r0, c0] * (1 - fc) + h[r0, c0 + 1] * fc
        bot = h[r0 + 1, c0] * (1 - fc) + h[r0 + 1, c0 + 1] * fc
        return top * (1 - fr) + bot * fr


def _dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(l2, 1e-12), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def _coast_distance(land: np.ndarray, max_steps: int = 60) -> np.ndarray:
    """Grid steps from each cell to the nearest cell of the other kind
    (8-connected dilation; enough precision for shaping heights)."""
    dist = np.full(land.shape, max_steps, dtype=np.float64)
    for target in (land, ~land):
        frontier = ~target
        reached = frontier.copy()
        d = np.zeros(land.shape)
        for step in range(1, max_steps):
            grown = reached.copy()
            grown[1:, :] |= reached[:-1, :]
            grown[:-1, :] |= reached[1:, :]
            grown[:, 1:] |= reached[:, :-1]
            grown[:, :-1] |= reached[:, 1:]
            new = grown & ~reached
            if not new.any():
                break
            d[new & target] = step
            reached = grown
        dist = np.where(target, np.where(d > 0, d, max_steps), dist)
    return dist


def generate_geography(seed: int, width: int = 360, height: int = 150, cell_km: float = 10.0) -> Geography:
    rng = np.random.default_rng(seed)
    xs = (np.arange(width) + 0.5) / width
    ys = (np.arange(height) + 0.5) / height
    X, Y = np.meshgrid(xs, ys)
    aspect = height / width  # to keep round things round in x/y fractions
    noise = lambda sc, s: fractal_noise(X * width, Y * height, sc, seed * 31 + s, octaves=4) - 0.5  # noqa: E731

    strait_x = rng.uniform(0.085, 0.11)
    strait_y = rng.uniform(0.40, 0.50)
    gap = rng.uniform(0.012, 0.02)

    # Continents, with their coasts pinched together into the strait.
    pinch = np.exp(-(((X - strait_x) / 0.03) ** 2))
    north_coast = 0.74 + 0.07 * (fractal_noise(X * width, np.zeros_like(X), 40, seed + 1) - 0.5) * 2
    south_coast = 0.20 + 0.05 * (fractal_noise(X * width, np.zeros_like(X) + 99, 50, seed + 2) - 0.5) * 2
    north_coast = north_coast * (1 - pinch) + (strait_y + gap / 2) * pinch
    south_coast = south_coast * (1 - pinch) + (strait_y - gap / 2) * pinch
    north = Y - north_coast
    south = south_coast - Y
    # The outer ocean: west of the strait the continents fall away.
    ocean = np.clip((strait_x - 0.035 - X) * 40.0, 0, None)
    north = north - ocean
    south = south - ocean
    east_edge = 0.94 + 0.025 * (fractal_noise(np.zeros_like(Y), Y * height, 30, seed + 3) - 0.5) * 2
    east = X - east_edge
    field_ = np.maximum.reduce([north, south, east])

    feats = {"strait": (int(strait_x * width), int(strait_y * height))}

    # Peninsulas hanging from the north shore (an Italy, a Greece...).
    n_pen = int(rng.integers(2, 4))
    for i in range(n_pen):
        px = rng.uniform(0.25 + i * 0.22, 0.35 + i * 0.22)
        py = float(np.interp(px, xs, north_coast[0]))
        length = rng.uniform(0.25, 0.42)
        ang = math.radians(rng.uniform(-35, 35))
        bx = px + math.sin(ang) * length * aspect
        by = py - math.cos(ang) * length
        # A bend part-way down (a boot, a hand) so it isn't a straight bar.
        mx = (px + bx) / 2 + rng.uniform(-0.04, 0.04)
        my = (py + by) / 2
        w0 = rng.uniform(0.016, 0.03)
        for (sx0, sy0, sx1, sy1, taper0) in ((px, py, mx, my, 0.0), (mx, my, bx, by, 0.5)):
            d, t = _dist_to_segment(X, Y, sx0, sy0, sx1, sy1)
            width_ = w0 * (1.1 - 0.6 * (taper0 + 0.5 * t))
            field_ = np.maximum(field_, (width_ - d) * 1.5)
        feats[f"peninsula_{i}"] = (int(bx * width), int(by * height))

    # A cape from the southern shore, sometimes.
    if rng.random() < 0.7:
        px = rng.uniform(0.35, 0.65)
        py = float(np.interp(px, xs, south_coast[0]))
        bx, by = px + rng.uniform(-0.04, 0.04), py + rng.uniform(0.08, 0.14)
        d, t = _dist_to_segment(X, Y, px, py, bx, by)
        field_ = np.maximum(field_, (rng.uniform(0.015, 0.025) * (1.1 - 0.7 * t) - d) * 1.5)
        feats["cape"] = (int(bx * width), int(by * height))

    # Large islands.
    for i in range(int(rng.integers(4, 7))):
        cx, cy = rng.uniform(0.15, 0.85), rng.uniform(0.32, 0.62)
        rx, ry = rng.uniform(0.02, 0.05), rng.uniform(0.04, 0.09)
        a = rng.uniform(0, math.pi)
        u = (X - cx) * math.cos(a) + (Y - cy) * aspect * math.sin(a)
        v = -(X - cx) * math.sin(a) + (Y - cy) * aspect * math.cos(a)
        q = np.sqrt((u / rx) ** 2 + (v / (ry * aspect)) ** 2)
        field_ = np.maximum(field_, (1.0 - q) * 0.12)
        feats[f"island_{i}"] = (int(cx * width), int(cy * height))

    # An archipelago: many small islands off one peninsula's tip.
    tip = feats.get(f"peninsula_{n_pen - 1}", (int(0.7 * width), int(0.5 * height)))
    ax, ay = tip[0] / width + 0.05, tip[1] / height - 0.05
    for _ in range(int(rng.integers(18, 32))):
        cx, cy = ax + rng.normal(0, 0.05), ay + rng.normal(0, 0.08)
        r = rng.uniform(0.004, 0.011)
        q = np.hypot((X - cx), (Y - cy) * aspect) / r
        field_ = np.maximum(field_, (1.0 - q) * 0.06)
    feats["archipelago"] = (int(ax * width), int(ay * height))

    # A narrow passage in the north-east to an inland sea.
    ix, iy = rng.uniform(0.74, 0.86), rng.uniform(0.88, 0.95)
    inland = np.hypot((X - ix) / 0.09, (Y - iy) / 0.05) - 1.0
    cx0 = ix - 0.06
    coast_y = float(np.interp(cx0, xs, north_coast[0]))
    chan, _ = _dist_to_segment(X, Y, cx0, coast_y - 0.02, ix, iy)
    field_ = np.where(inland < 0, np.minimum(field_, inland * 0.05 - 0.01), field_)
    field_ = np.where(chan < 0.005, np.minimum(field_, -0.03), field_)
    feats["inland_passage"] = (int(cx0 * width), int(coast_y * height))

    # Roughen every coast, then decide land and sea.
    field_ = field_ + noise(18, 7) * 0.035 + noise(6, 8) * 0.012
    # Keep the strait open whatever the noise did: a channel from the outer
    # ocean into the basin, ~1.5-3 cells (15-30 km) wide.
    chan_w = gap * 0.5
    strait = (np.abs(Y - strait_y) < chan_w) & (X > strait_x - 0.06) & (X < strait_x + 0.06)
    field_ = np.where(strait, np.minimum(field_, -0.01), field_)
    land = field_ > 0

    dist = _coast_distance(land)
    ridged = 1.0 - np.abs(fractal_noise(X * width, Y * height, 30, seed + 11) - 0.5) * 2.0
    land_h = 5.0 + np.minimum(dist, 25) * 35.0 * (0.5 + ridged) + 900.0 * np.clip(field_ * 6, 0, 1) ** 1.5 * ridged
    sea_d = -(15.0 + np.minimum(dist, 20) ** 1.6 * 55.0 * (0.8 + 0.4 * value_noise(X * width, Y * height, 25, seed + 12)))
    h = np.where(land, land_h, sea_d)
    return Geography(seed=seed, cell_km=cell_km, height=h.astype(np.float32), features=feats)
