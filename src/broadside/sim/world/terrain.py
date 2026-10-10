# Static terrain: sea, shoals, reefs, rock stacks, islands and coastline.
#
# Terrain is defined analytically - a list of features, each a function of
# world position - rather than as one fixed-resolution raster. That is what
# lets the same coastline be sampled at 1 m for the deck view, at 20 m for
# the squadron view and at 200 m for the chart, and agree with itself at
# every scale (see docs/design/07_vision_and_views.md, "One world, any
# resolution"). Everything is vectorised over arrays of sample points.
#
# Each sample yields a terrain code (what it is) and a height in metres
# above the waterline (what it blocks). Trees add canopy height on top of
# the ground, since a wooded headland hides a ship far better than a bare
# one of the same elevation.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from broadside.sim.units import fractal_noise, value_noise

# Terrain codes, ordered by "landness": when features overlap, the higher
# code wins (a rock stack on a shoal is a rock stack).
SEA = 0
SHOAL = 1
REEF = 2
BEACH = 3
LAND = 4
FOREST = 5
HILL = 6
ROCK = 7
PEAK = 8

TERRAIN_NAMES = {
    SEA: "open sea",
    SHOAL: "shoal water",
    REEF: "reef, awash",
    BEACH: "beach",
    LAND: "scrub",
    FOREST: "woods",
    HILL: "hillside",
    ROCK: "rock stack",
    PEAK: "summit",
}

# Codes a hull can't pass over. Shoals are passable for the shallow-draught
# vessels modelled so far; reefs and anything drier are not.
IMPASSABLE = {REEF, BEACH, LAND, FOREST, HILL, ROCK, PEAK}

TREE_CANOPY_M = 12.0


# Depth of the bottom under each kind of water, metres below the surface.
# Rough, and deliberately so: the lead line and real soundings come with the
# environment work (docs/design/09_environment.md).
SEABED_M = {
    SEA: -28.0,
    SHOAL: -5.0,
    REEF: -1.2,
    BEACH: -0.3,
}
DEEP_M = -28.0


@dataclass
class TerrainSample:
    code: np.ndarray  # uint8 terrain code per point
    height: np.ndarray  # ground/rock height above waterline, metres
    canopy: np.ndarray  # extra obstruction height from trees, metres

    @property
    def obstruction_top(self) -> np.ndarray:
        return self.height + self.canopy

    @property
    def seabed(self) -> np.ndarray:
        """Where the bottom is: the ground where it stands above water, and
        the sea floor where it does not."""
        bed = np.full(self.height.shape, DEEP_M)
        for code, depth in SEABED_M.items():
            bed = np.where(self.code == code, depth, bed)
        return np.where(self.height > 0.0, self.height, bed)


class Feature:
    """Base class: a terrain feature knows its bounding box and how to
    evaluate (code, height) at points inside it."""

    def bbox(self) -> tuple[float, float, float, float]:
        raise NotImplementedError

    def evaluate(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError


@dataclass
class Island(Feature):
    """A roughly round island with a noisy coastline and a domed profile:
    beach at the edge, scrub or woods on the slopes, bare hill and a summit
    at the top, with a ring of shoal water around it."""

    x: float
    y: float
    radius: float
    peak_m: float = 40.0
    wooded: bool = True
    shoal_m: float = 40.0
    seed: int = 0
    _harmonics: list[tuple[int, float, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed + 7919)
        self._harmonics = [
            (k, float(rng.uniform(0.06, 0.22)) / k ** 0.7, float(rng.uniform(0, 2 * math.pi)))
            for k in range(2, 7)
        ]

    def bbox(self) -> tuple[float, float, float, float]:
        r = self.radius * 1.9 + self.shoal_m
        return self.x - r, self.y - r, self.x + r, self.y + r

    def _shape_radius(self, theta: np.ndarray) -> np.ndarray:
        r = np.ones_like(theta)
        for k, amp, phase in self._harmonics:
            r += amp * np.cos(k * theta + phase)
        return self.radius * np.clip(r, 0.35, 1.9)

    def evaluate(self, xs, ys):
        dx = xs - self.x
        dy = ys - self.y
        dist = np.hypot(dx, dy)
        theta = np.arctan2(dy, dx)
        rim = self._shape_radius(theta)
        # Small-scale roughness so the coast isn't a perfect smooth curve.
        rim = rim * (0.93 + 0.14 * value_noise(xs, ys, max(8.0, self.radius * 0.18), self.seed))
        q = dist / rim
        code = np.full(xs.shape, SEA, dtype=np.uint8)
        height = np.zeros(xs.shape)

        land = q < 1.0
        profile = np.clip(1.0 - q, 0.0, 1.0) ** 1.1
        h = self.peak_m * profile * (0.8 + 0.4 * fractal_noise(xs, ys, self.radius * 0.5, self.seed + 3))
        height = np.where(land, np.maximum(h, 0.6), 0.0)

        code[(q >= 1.0) & (dist < rim + self.shoal_m)] = SHOAL
        code[land] = BEACH
        code[land & (height > 2.0)] = FOREST if self.wooded else LAND
        code[land & (height > self.peak_m * 0.55)] = HILL
        code[land & (height > self.peak_m * 0.85)] = PEAK
        return code, height


@dataclass
class Rock(Feature):
    """A single rock stack standing clear of the water, with a skirt of
    awash reef and shoal around it. `height_m` is what matters for sight:
    a 3 m rock hides a boat but not a ship's topsails."""

    x: float
    y: float
    radius: float = 4.0
    height_m: float = 6.0
    reef_m: float = 5.0
    shoal_m: float = 12.0

    def bbox(self):
        r = self.radius + self.reef_m + self.shoal_m
        return self.x - r, self.y - r, self.x + r, self.y + r

    def evaluate(self, xs, ys):
        dist = np.hypot(xs - self.x, ys - self.y)
        code = np.full(xs.shape, SEA, dtype=np.uint8)
        height = np.zeros(xs.shape)
        code[dist < self.radius + self.reef_m + self.shoal_m] = SHOAL
        reef = dist < self.radius + self.reef_m
        code[reef] = REEF
        height[reef] = 0.3
        stack = dist < self.radius
        code[stack] = ROCK
        # Slightly domed so a big stack isn't a flat-topped cylinder.
        height[stack] = self.height_m * (1.0 - 0.3 * (dist[stack] / max(self.radius, 0.1)) ** 2)
        return code, height


@dataclass
class Coast(Feature):
    """A mainland coast: everything on one side of a (noisy) line is land,
    rising inland. `normal_degrees` is the compass direction pointing
    inland; `offset_m` is the distance of the shoreline from the origin
    along that direction."""

    normal_degrees: float
    offset_m: float
    rise_per_m: float = 0.08
    max_height_m: float = 120.0
    roughness_m: float = 60.0
    wooded: bool = True
    shoal_m: float = 60.0
    seed: int = 0

    def bbox(self):
        return -math.inf, -math.inf, math.inf, math.inf

    def evaluate(self, xs, ys):
        r = math.radians(self.normal_degrees)
        nx, ny = math.sin(r), math.cos(r)
        along = xs * ny - ys * nx
        s = xs * nx + ys * ny - self.offset_m
        s = s + self.roughness_m * (fractal_noise(along, np.zeros_like(along), self.roughness_m * 4, self.seed) - 0.5) * 2
        code = np.full(xs.shape, SEA, dtype=np.uint8)
        height = np.zeros(xs.shape)
        land = s > 0
        h = np.minimum(self.max_height_m, s * self.rise_per_m) * (0.75 + 0.5 * value_noise(xs, ys, 150.0, self.seed + 5))
        height = np.where(land, np.maximum(h, 0.6), 0.0)
        code[(~land) & (s > -self.shoal_m)] = SHOAL
        code[land] = BEACH
        code[land & (height > 2.0)] = FOREST if self.wooded else LAND
        code[land & (height > self.max_height_m * 0.55)] = HILL
        return code, height


@dataclass
class Terrain:
    """The static geography of a scene: a list of features composited on
    demand at whatever sample points a caller asks for."""

    features: list[Feature] = field(default_factory=list)

    def add(self, feature: Feature) -> Feature:
        self.features.append(feature)
        return feature

    def sample(self, xs, ys) -> TerrainSample:
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        code = np.zeros(xs.shape, dtype=np.uint8)
        height = np.zeros(xs.shape)
        for feat in self.features:
            x0, y0, x1, y1 = feat.bbox()
            sel = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
            if not sel.any():
                continue
            fc, fh = feat.evaluate(xs[sel], ys[sel])
            cur_c = code[sel]
            win = fc > cur_c
            cur_c[win] = fc[win]
            code[sel] = cur_c
            height[sel] = np.maximum(height[sel], fh)
        canopy = np.where(code == FOREST, TREE_CANOPY_M, 0.0)
        return TerrainSample(code=code, height=height, canopy=canopy)

    def code_at(self, x: float, y: float) -> int:
        return int(self.sample(np.array([x]), np.array([y])).code[0])


@dataclass
class WorldHeightmap(Feature):
    """Terrain for a scene cut from a generated world (broadside.worldgen).

    The world map is 10 km cells; a scene needs metres. Heights are sampled
    bilinearly from the map and given local detail with fractal noise, so
    the generated coast is the same coast at every zoom - the chart shows
    the bay, and the 1 m ship view shows its beaches and rocks. `origin_*`
    is where scene (0, 0) sits in world metres (from the map's SW corner).
    """

    geo: object
    origin_x_m: float
    origin_y_m: float
    detail_m: float = 25.0
    seed: int = 0

    def bbox(self):
        return -math.inf, -math.inf, math.inf, math.inf

    def evaluate(self, xs, ys):
        h = self.geo.sample_m(xs + self.origin_x_m, ys + self.origin_y_m).astype(np.float64)
        h = h + (fractal_noise(xs, ys, 400.0, self.seed) - 0.5) * 2 * self.detail_m + (value_noise(xs, ys, 40.0, self.seed + 1) - 0.5) * 4.0
        code = np.full(xs.shape, SEA, dtype=np.uint8)
        code[(h <= 0) & (h > -6)] = SHOAL
        land = h > 0
        code[land] = BEACH
        wooded = value_noise(xs, ys, 120.0, self.seed + 2) > 0.45
        code[land & (h > 3) & wooded] = FOREST
        code[land & (h > 3) & ~wooded] = LAND
        code[land & (h > 350)] = HILL
        code[land & (h > 900)] = PEAK
        return code, np.where(land, h, 0.0)
