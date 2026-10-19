# Shared units and small geometry helpers.
#
# The sim keeps ship positions in nautical miles (WorldPosition), but
# everything spatial at human scale - vision, terrain, smoke, the 1 m deck
# view - works in metres. These helpers are the one place the two meet.
#
# World axes: +x = east, +y = north (metres or nm). Headings are compass
# degrees, 0 = north, increasing clockwise.

from __future__ import annotations

import math

import numpy as np

M_PER_NM = 1852.0
MS_PER_KNOT = M_PER_NM / 3600.0


def heading_axes(heading_degrees: float) -> tuple[float, float, float, float]:
    """(forward_x, forward_y, starboard_x, starboard_y) unit vectors for a
    ship on the given heading. Forward points along the keel toward the bow;
    starboard is 90 degrees clockwise of forward."""
    r = math.radians(heading_degrees)
    fx, fy = math.sin(r), math.cos(r)
    return fx, fy, fy, -fx


def bearing_degrees(dx: float, dy: float) -> float:
    """Compass bearing of the vector (dx east, dy north)."""
    return math.degrees(math.atan2(dx, dy)) % 360.0


def angle_delta(target: float, current: float) -> float:
    """Shortest signed delta from `current` to `target`, in degrees."""
    return (target - current + 180.0) % 360.0 - 180.0


def wind_vector_ms(direction_from_degrees: float, speed_knots: float) -> tuple[float, float]:
    """The velocity (m/s, east/north) of air for a wind blowing FROM the
    given compass direction - i.e. the direction smoke and fog drift."""
    to = math.radians((direction_from_degrees + 180.0) % 360.0)
    v = speed_knots * MS_PER_KNOT
    return math.sin(to) * v, math.cos(to) * v


# --- Deterministic value noise -------------------------------------------
#
# Used for coastline roughness, fog-bank wisps and sea-surface texture. A
# hash of integer lattice coordinates, smoothly interpolated - cheap,
# vectorised, and fully determined by (seed, x, y), so terrain sampled at
# 1 m for the deck view and at 50 m for the chart view agrees exactly.


def _hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF).astype(np.float64) / 65535.0


def value_noise(xs: np.ndarray, ys: np.ndarray, scale: float, seed: int = 0) -> np.ndarray:
    """Smooth noise in [0, 1] with features roughly `scale` units across."""
    x = np.asarray(xs, dtype=np.float64) / scale
    y = np.asarray(ys, dtype=np.float64) / scale
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = x - x0
    fy = y - y0
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    ix = x0.astype(np.int64)
    iy = y0.astype(np.int64)
    n00 = _hash2(ix, iy, seed)
    n10 = _hash2(ix + 1, iy, seed)
    n01 = _hash2(ix, iy + 1, seed)
    n11 = _hash2(ix + 1, iy + 1, seed)
    top = n00 + (n10 - n00) * sx
    bottom = n01 + (n11 - n01) * sx
    return top + (bottom - top) * sy


def fractal_noise(xs: np.ndarray, ys: np.ndarray, scale: float, seed: int = 0, octaves: int = 3) -> np.ndarray:
    """A few octaves of value noise summed, normalised back to ~[0, 1]."""
    total = np.zeros(np.shape(xs), dtype=np.float64)
    amp = 1.0
    norm = 0.0
    s = scale
    for o in range(octaves):
        total += amp * value_noise(xs, ys, s, seed + 101 * o)
        norm += amp
        amp *= 0.5
        s *= 0.5
    return total / norm
