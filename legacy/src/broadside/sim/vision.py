# Line of sight: what can a pair of eyes at (x, y, height) actually see?
#
# The approach is direct ray marching, vectorised with numpy: for each
# target point, sample the obstruction fields (sim/spatial.py) at regular
# steps along the straight line from the eye to it, and ask two questions:
#
#   1. Does the line pass through anything solid at the height the line is
#      at when it gets there? (2.5D: a 6 m rock blocks the line from a 4 m
#      eye to a hull, but not the line to that hull's 40 m topmasts. A sail
#      is an overhanging band - the line can pass under its foot.)
#   2. How much fog, smoke and haze does it pass through? Integrated
#      extinction gives a transmittance in [0, 1] (Beer-Lambert), so fog
#      thins what you see gradually rather than being a hard wall.
#
# Earth curvature is included as a bulge added under every sample, so ships
# far off go "hull down" - their hulls drop below the horizon while their
# topsails remain visible - without any special-casing.
#
# Everything is resolution-agnostic: the same function serves the 1 m deck
# view, the squadron and chart views, and the per-ship sighting system -
# only the sample spacing and target set differ. See
# docs/design/07_vision_and_views.md for the model and its trade-offs.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from broadside.sim.spatial import Fields, Poles, SailWalls, SceneQuery

# Effective earth radius with standard atmospheric refraction (7/6 R).
EARTH_RADIUS_EFF_M = 6_371_000.0 * 7.0 / 6.0

# Transmittance thresholds. Below FAINT nothing is discernible; between
# FAINT and CLEAR a shape is seen but not made out (drawn dim / "?").
VIS_FAINT = 0.02
VIS_CLEAR = 0.2

FieldSampler = Callable[[np.ndarray, np.ndarray], Fields]


@dataclass
class Eye:
    x: float
    y: float
    h: float  # metres above waterline
    skip_m: float = 0.8  # ignore obstruction this close to the eye (the observer's own tile)
    max_range_m: float = 40_000.0


@dataclass
class Sight:
    """Per-target results of a trace. `low` is the target's surface, `high`
    its tallest feature (mast top, sail head, treetops, summit)."""

    low: np.ndarray  # transmittance 0..1
    high: np.ndarray
    solid_low: np.ndarray  # bool: low line blocked by something solid
    solid_high: np.ndarray
    vol_low: np.ndarray  # optical depth from fog + smoke alone (not haze) on the low line


class RasterFields:
    """Obstruction fields pre-sampled on a regular grid, looked up by
    nearest cell - the fast path for tracing thousands of rays across one
    region (a view frame). Outside the grid, the fields read as open sea."""

    def __init__(self, x0: float, y0: float, cell_m: float, nx: int, ny: int, fields: Fields):
        self.x0 = x0
        self.y0 = y0
        self.cell_m = cell_m
        self.nx = nx
        self.ny = ny
        self.f = fields

    @classmethod
    def build(
        cls,
        query: SceneQuery,
        x0: float,
        y0: float,
        cell_m: float,
        nx: int,
        ny: int,
        *,
        include_ships: bool = True,
        include_people: bool = True,
        exclude_ship: Optional[int] = None,
        ignore_hull_of: Optional[int] = None,
        ignore_person: Optional[int] = None,
    ) -> "RasterFields":
        gx = x0 + (np.arange(nx) + 0.5) * cell_m
        gy = y0 + (np.arange(ny) + 0.5) * cell_m
        xs, ys = np.meshgrid(gx, gy)
        f = query.fields(xs.ravel(), ys.ravel(), include_ships=include_ships, include_people=include_people, exclude_ship=exclude_ship, ignore_hull_of=ignore_hull_of, ignore_person=ignore_person)
        return cls(x0, y0, cell_m, nx, ny, f)

    def __call__(self, px: np.ndarray, py: np.ndarray) -> Fields:
        ix = np.floor((px - self.x0) / self.cell_m).astype(np.int64)
        iy = np.floor((py - self.y0) / self.cell_m).astype(np.int64)
        inside = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        flat = np.where(inside, iy * self.nx + ix, 0)
        f = self.f

        def take(a: np.ndarray, default: float) -> np.ndarray:
            out = a[flat]
            out[~inside] = default
            return out

        return Fields(
            solid_top=take(f.solid_top, 0.0),
            over_bottom=take(f.over_bottom, np.inf),
            over_top=take(f.over_top, -np.inf),
            fog_sigma=take(f.fog_sigma, 0.0),
            fog_top=take(f.fog_top, 0.0),
            smoke_sigma=take(f.smoke_sigma, 0.0),
            smoke_top=take(f.smoke_top, 0.0),
        )


def direct_sampler(query: SceneQuery, exclude_ship: Optional[int] = None, ignore_hull_of: Optional[int] = None, include_people: bool = True) -> FieldSampler:
    """Sample the scene exactly at every ray step - slower per sample, but
    exact, and the right tool for a handful of long rays (sighting ships
    kilometres away).

    `include_people` off is for exactly those long rays: a man at the rail
    is an obstruction to what you are looking at on deck, not to a sail on
    the horizon."""

    def sample(px: np.ndarray, py: np.ndarray) -> Fields:
        return query.fields(
            px, py, exclude_ship=exclude_ship, ignore_hull_of=ignore_hull_of, include_people=include_people
        )

    return sample


def trace(
    eye: Eye,
    tx: np.ndarray,
    ty: np.ndarray,
    th_low: np.ndarray,
    th_high: np.ndarray,
    sampler: FieldSampler,
    *,
    step_m: float,
    haze_sigma: float,
    end_skip_m=0.0,
    batch: int = 1500,
    max_samples: int = 600,
    poles: Optional[Poles] = None,
    sails: Optional[SailWalls] = None,
) -> Sight:
    tx = np.asarray(tx, dtype=np.float64).ravel()
    ty = np.asarray(ty, dtype=np.float64).ravel()
    th_low = np.broadcast_to(np.asarray(th_low, dtype=np.float64), tx.shape).ravel()
    th_high = np.broadcast_to(np.asarray(th_high, dtype=np.float64), tx.shape).ravel()
    n = tx.size
    end_skip = np.broadcast_to(np.asarray(end_skip_m, dtype=np.float64), tx.shape).ravel()
    low = np.zeros(n)
    high = np.zeros(n)
    solid_low = np.zeros(n, dtype=bool)
    solid_high = np.zeros(n, dtype=bool)
    vol_low = np.zeros(n)

    dist_all = np.hypot(tx - eye.x, ty - eye.y)
    in_range = dist_all <= eye.max_range_m
    # Batch rays of similar length together so short rays don't pay for
    # the sample count of long ones.
    order = np.argsort(dist_all)
    order = order[in_range[order]]

    for start in range(0, order.size, batch):
        ids = order[start : start + batch]
        dx = tx[ids] - eye.x
        dy = ty[ids] - eye.y
        D = dist_all[ids]
        S = int(min(max_samples, max(2, math.ceil(float(D.max()) / step_m))))
        t = (np.arange(S) + 0.5) / S
        px = eye.x + dx[:, None] * t[None, :]
        py = eye.y + dy[:, None] * t[None, :]
        ds = D[:, None] * t[None, :]
        F = sampler(px.ravel(), py.ravel())
        shp = px.shape
        solid_top = F.solid_top.reshape(shp)
        ob = F.over_bottom.reshape(shp)
        ot = F.over_top.reshape(shp)
        fs = F.fog_sigma.reshape(shp)
        ft = F.fog_top.reshape(shp)
        ss = F.smoke_sigma.reshape(shp)
        st = F.smoke_top.reshape(shp)

        valid = (ds > eye.skip_m) & (ds < (D - end_skip[ids])[:, None])
        bulge = ds * (D[:, None] - ds) / (2.0 * EARTH_RADIUS_EFF_M)
        seg = D / S

        # Thin poles (masts): closest approach of each ray to each pole.
        pole_t = None
        if poles is not None and len(poles):
            qx = poles.x[None, :] - eye.x
            qy = poles.y[None, :] - eye.y
            l2 = np.maximum(dx * dx + dy * dy, 1e-9)[:, None]
            pole_t = np.clip((qx * dx[:, None] + qy * dy[:, None]) / l2, 0.0, 1.0)
            cx_ = dx[:, None] * pole_t - qx
            cy_ = dy[:, None] * pole_t - qy
            pd = pole_t * D[:, None]
            pole_hit = (cx_ * cx_ + cy_ * cy_ < (poles.r ** 2)[None, :]) & (pd > eye.skip_m) & (pd < (D - end_skip[ids])[:, None])

        # Sails: exact ray/segment crossings, blocked if the line passes
        # the sail within its height band.
        sail_t = None
        if sails is not None and len(sails):
            ax = sails.x0[None, :] - eye.x
            ay = sails.y0[None, :] - eye.y
            sxv = (sails.x1 - sails.x0)[None, :]
            syv = (sails.y1 - sails.y0)[None, :]
            rxv = dx[:, None]
            ryv = dy[:, None]
            denom = rxv * syv - ryv * sxv
            ok = np.abs(denom) > 1e-9
            safe = np.where(ok, denom, 1.0)
            st_ = (ax * syv - ay * sxv) / safe
            su_ = (ax * ryv - ay * rxv) / safe
            dist_ = st_ * D[:, None]
            sail_hit = ok & (st_ > 0) & (st_ < 1) & (su_ >= 0) & (su_ <= 1) & (dist_ > eye.skip_m) & (dist_ < (D - end_skip[ids])[:, None])
            sail_t = st_

        for which, th, out_t, out_solid in ((0, th_low[ids], low, solid_low), (1, th_high[ids], high, solid_high)):
            hl = eye.h + (th - eye.h)[:, None] * t[None, :]
            blocked = valid & ((hl < solid_top + bulge) | ((hl >= ob) & (hl < ot)))
            is_blocked = blocked.any(axis=1)
            if pole_t is not None:
                h_at_pole = eye.h + (th - eye.h)[:, None] * pole_t
                is_blocked |= (pole_hit & (h_at_pole < poles.top[None, :])).any(axis=1)
            if sail_t is not None:
                h_at_sail = eye.h + (th - eye.h)[:, None] * sail_t
                is_blocked |= (sail_hit & (h_at_sail >= sails.bottom[None, :]) & (h_at_sail < sails.top[None, :])).any(axis=1)
            sig = np.where(hl < ft, fs, 0.0) + np.where(hl < st, ss, 0.0)
            vol = (sig * valid).sum(axis=1) * seg
            if which == 0:
                vol_low[ids] = vol
            od = vol + haze_sigma * D
            tr = np.exp(-od)
            tr[is_blocked] = 0.0
            out_t[ids] = tr
            out_solid[ids] = is_blocked

    return Sight(low=low, high=high, solid_low=solid_low, solid_high=solid_high, vol_low=vol_low)
