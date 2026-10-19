# Spatial queries over a scene: "what is at these world points, and how
# much does it block sight?"
#
# This is the single seam between the simulation's many representations
# (analytic terrain, gaussian smoke puffs, fog ellipses, ships as rotated
# 1 m deck plans with sails braced to the wind) and everything that needs
# to look at the world - the line-of-sight engine, the sighting system and
# every camera/zoom level of the view. All of it is vectorised over arrays
# of sample points, and none of it cares what resolution those points are
# spaced at: the deck view asks at 1 m spacing, the chart view at 200 m.
#
# Heights are metres above the waterline. Obstruction is 2.5D: each point
# has a solid column from the sea up to `solid_top` (hull, rock, land,
# trees), plus optionally an overhanging band `over_bottom..over_top`
# (sails - you can see under a course's foot to your own deck, but not
# past it to the horizon), plus fog and smoke volumes with their own tops.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import esper
import numpy as np

from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.systems.sailing import angle_off_wind
from broadside.sim.units import heading_axes
from broadside.sim.world.atmosphere import Atmosphere
from broadside.sim.world.terrain import Terrain, TerrainSample

SAIL_HALF_THICKNESS_M = 0.6
MAST_RADIUS_M = 0.35
COURSES_TRIM = 0.55  # at or above this sail setting the courses are set


@dataclass
class SailWalls:
    """Sails as analytic vertical walls: world-space segments with the
    height band they occupy. Traced exactly at any zoom (vision.trace)."""

    x0: np.ndarray
    y0: np.ndarray
    x1: np.ndarray
    y1: np.ndarray
    bottom: np.ndarray
    top: np.ndarray

    def __len__(self) -> int:
        return int(self.x0.size)


@dataclass
class Poles:
    x: np.ndarray
    y: np.ndarray
    r: np.ndarray
    top: np.ndarray

    def __len__(self) -> int:
        return int(self.x.size)


@dataclass
class SailSeg:
    """One sail seen from above: a line segment in the ship's local frame
    (u forward, v starboard, metres) with the height band it occupies."""

    u0: float
    v0: float
    u1: float
    v1: float
    bottom_m: float
    top_m: float
    kind: str  # "square" | "fore-aft"
    mast: str


@dataclass
class ShipGeom:
    """A ship's pose and body, snapshotted for one query batch."""

    entity: int
    x: float
    y: float
    heading: float
    layout: sl.DeckLayout
    faction: str
    sails: list[SailSeg]
    name: str = ""
    fx: float = 0.0
    fy: float = 1.0
    sx: float = 1.0
    sy: float = 0.0

    def __post_init__(self) -> None:
        self.fx, self.fy, self.sx, self.sy = heading_axes(self.heading)

    @property
    def radius(self) -> float:
        return self.layout.radius_m()

    @property
    def freeboard(self) -> float:
        return self.layout.freeboard_m

    def to_local(self, xs, ys):
        dx = xs - self.x
        dy = ys - self.y
        return dx * self.fx + dy * self.fy, dx * self.sx + dy * self.sy

    def to_world(self, u, v):
        return self.x + u * self.fx + v * self.sx, self.y + u * self.fy + v * self.sy

    def tile_world(self, gx: float, gy: float) -> tuple[float, float]:
        u, v = self.layout.local_m(gx, gy)
        return self.to_world(u, v)

    def mast_top_m(self) -> float:
        m = self.layout.main_mast()
        return self.freeboard + (m.height_above_deck if m else 10.0)

    def hull_top_m(self) -> float:
        return self.freeboard + sl.FITTING_TOP_M[sl.HULL]


def brace_angle_degrees(heading: float, wind_from: float) -> float:
    """How far the yards are braced round from square (athwartships), with
    sign: positive swings the starboard yardarm aft. Running before the
    wind the yards are square; on a reach or close-hauled they're braced
    sharp up (period square-riggers managed ~45-50 degrees at most), with
    the *leeward* yardarm hauled aft."""
    off = angle_off_wind(heading, wind_from)
    magnitude = min(48.0, max(0.0, (180.0 - off) * 0.42))
    rel = (wind_from - heading) % 360.0
    wind_on_starboard = rel < 180.0
    # Wind on the starboard side -> port (leeward) yardarm aft -> starboard
    # yardarm forward, i.e. negative in this convention.
    return -magnitude if wind_on_starboard else magnitude


def sails_for(layout: sl.DeckLayout, heading: float, trim: float, wind_from: float) -> list[SailSeg]:
    if trim < 0.05:
        return []
    fb = layout.freeboard_m
    brace = math.radians(brace_angle_degrees(heading, wind_from))
    segs: list[SailSeg] = []
    for m in layout.masts:
        mu, mv = layout.local_m(m.x, m.y)
        # Athwartship line (+v), rotated by the brace: starboard end moves aft.
        du = -math.sin(brace) * m.yard_half_m
        dv = math.cos(brace) * m.yard_half_m
        # Courses on fore and main set low; the mizzen normally carried no
        # course, only a topsail from about the mizzen top upward. Below
        # COURSES_TRIM the courses are clewed up ("fighting sail", as ships
        # stripped for battle): the lowest canvas is then the topsails, and
        # the quarterdeck can see under them.
        if m.name == "mizzen" or trim < COURSES_TRIM:
            bottom = fb + 0.42 * m.height_above_deck
        else:
            bottom = fb + sl.SAIL_FOOT_ABOVE_DECK_M
        top = max(bottom + 2.0, fb + m.height_above_deck * (0.35 + 0.55 * trim))
        segs.append(SailSeg(mu - du, mv - dv, mu + du, mv + dv, bottom, top, "square", m.name))
    names = {m.name: m for m in layout.masts}
    if "fore" in names:
        fore = names["fore"]
        fu, fv = layout.local_m(fore.x, fore.y)
        tip_u, _ = layout.local_m(layout.width - 1, layout.centre_row)
        segs.append(SailSeg(fu + 1.0, 0.0, tip_u, 0.0, fb + sl.SAIL_FOOT_ABOVE_DECK_M, fb + fore.height_above_deck * 0.6 * max(trim, 0.4), "fore-aft", "jib"))
    aft = names.get("mizzen") or names.get("main")
    if aft is not None:
        au, _ = layout.local_m(aft.x, aft.y)
        stern_u, _ = layout.local_m(0, layout.centre_row)
        segs.append(SailSeg(au - 1.0, 0.0, stern_u + 0.5, 0.0, fb + 2.5, fb + aft.height_above_deck * 0.55, "fore-aft", "spanker"))
    return segs


BODY_BAND_BOTTOM_M = 0.8  # chest height above the deck
BODY_BAND_TOP_M = 1.72  # the crown of his hat, just under a standing eye


def people_bands(world: esper.World, geoms: list) -> list:
    """(x, y, band bottom, band top, entity) for every man standing on a
    weather deck. A body blocks the view of what is behind it from the chest
    up - you still see the planking at his feet - so a crowd is something
    you have to see round, or move through."""
    from broadside.sim.people import components as pc

    by_ent = {g.entity: g for g in geoms}
    out = []
    for ent, (crew, dpos) in world.get_components(c.CrewMember, c.DeckPosition):
        g = by_ent.get(crew.ship)
        if g is None or world.has_component(ent, c.Aloft) or world.has_component(ent, c.Below):
            continue
        body = world.try_component(ent, pc.Body)
        if body is not None and not body.alive:
            continue  # a man down is not an obstruction to speak of
        lying = body is not None and not body.conscious
        x, y = g.tile_world(dpos.x, dpos.y)
        top = g.freeboard + (0.5 if lying else BODY_BAND_TOP_M)
        out.append((x, y, g.freeboard + (0.05 if lying else BODY_BAND_BOTTOM_M), top, ent))
    return out


def ship_geoms(world: esper.World, wind_from: float) -> list[ShipGeom]:
    geoms: list[ShipGeom] = []
    for ent, (pos, heading, body) in world.get_components(c.WorldPosition, c.Heading, c.ShipBody):
        sail = world.try_component(ent, c.SailPlan)
        trim = sail.trim if sail else 0.0
        fac = world.try_component(ent, c.Faction)
        name = world.try_component(ent, c.Name)
        geoms.append(
            ShipGeom(
                entity=ent,
                x=pos.x_m,
                y=pos.y_m,
                heading=heading.degrees,
                layout=body.layout,
                faction=fac.name if fac else "neutral",
                sails=sails_for(body.layout, heading.degrees, trim, wind_from),
                name=name.full if name else "",
            )
        )
    return geoms


@dataclass
class Fields:
    """Sight-obstruction fields at a set of points."""

    solid_top: np.ndarray
    over_bottom: np.ndarray
    over_top: np.ndarray
    fog_sigma: np.ndarray
    fog_top: np.ndarray
    smoke_sigma: np.ndarray
    smoke_top: np.ndarray


@dataclass
class Content:
    """Everything at a set of points: terrain, ship parts, sails, and the
    obstruction fields - plus the two target heights vision tests each
    point at (its surface, and its tallest feature)."""

    terrain: TerrainSample
    ship: np.ndarray  # index into geoms, -1 = none
    tile: np.ndarray  # shiplayout tile code where ship >= 0
    gx: np.ndarray
    gy: np.ndarray
    sail: np.ndarray  # index into geoms of the ship whose sail is here, -1 = none
    fields: Fields
    surface_h: np.ndarray
    tall_h: np.ndarray
    bldg: np.ndarray = None  # index into buildings, -1 = none
    bldg_top: np.ndarray = None  # column top above the waterline
    bldg_damage: np.ndarray = None  # 0..1
    # Where in its own tile the point falls, 0..1, along the ship's forward
    # (fu) and starboard (fv) axes - for drawing sub-metre detail.
    fu: np.ndarray = None
    fv: np.ndarray = None


@dataclass
class Building:
    """A voxel structure's pose and column heights, for one query batch."""

    entity: int
    x: float
    y: float
    heading: float
    vs: object  # sim.voxels.VoxelStructure
    top: np.ndarray  # [y, x] column top (m above waterline), 0 = empty
    damage: np.ndarray  # [y, x] 0 intact .. 1 rubble / badly cracked

    @property
    def radius(self) -> float:
        nz, ny, nx = self.vs.shape
        return math.hypot(nx, ny) * self.vs.voxel_m / 2.0 + 1.0


def buildings_of(world: esper.World) -> list:
    from broadside.sim.voxels import VoxelStructure

    out = []
    for ent, (vs, pos, hd) in world.get_components(VoxelStructure, c.WorldPosition, c.Heading):
        top = vs.column_top_m()
        solid = vs.solid
        n = solid.sum(axis=0)
        loose = (vs.loose & solid).sum(axis=0)
        integ = np.where(solid, vs.integrity, 0.0).sum(axis=0)
        damage = np.where(n > 0, np.maximum(loose / np.maximum(n, 1), 1.0 - integ / np.maximum(n, 1)), 0.0)
        out.append(Building(ent, pos.x_m, pos.y_m, hd.degrees, vs, top, damage))
    return out


@dataclass
class SceneQuery:
    terrain: Terrain
    atmosphere: Atmosphere
    geoms: list[ShipGeom] = field(default_factory=list)
    buildings: list = field(default_factory=list)
    # (x, y, band bottom, band top) for every man standing on a weather
    # deck: a body is not a wall - you see the planking at his feet - but it
    # hides what is behind it from chest height up, which is what makes a
    # crowded deck feel crowded.
    people: list = field(default_factory=list)
    # (x, y) rounded to the metre -> (band bottom, band top), built on first
    # use. A body occupies its own square metre, so this is exact.
    _people_index: Optional[dict] = field(default=None, repr=False)
    _people_bbox: Optional[tuple] = field(default=None, repr=False)

    def people_index(self):
        if self._people_index is None:
            idx: dict = {}
            for px, py, b0, b1, _ent in self.people:
                key = (int(round(px)), int(round(py)))
                have = idx.get(key)
                idx[key] = (min(have[0], b0), max(have[1], b1)) if have else (b0, b1)
            self._people_index = idx
            if self.people:
                xs = [p[0] for p in self.people]
                ys = [p[1] for p in self.people]
                self._people_bbox = (min(xs) - 0.6, min(ys) - 0.6, max(xs) + 0.6, max(ys) + 0.6)
            else:
                self._people_bbox = (0.0, 0.0, -1.0, -1.0)
        return self._people_index, self._people_bbox

    @classmethod
    def from_world(cls, world: esper.World, terrain: Terrain, atmosphere: Atmosphere, wind_from: float) -> "SceneQuery":
        geoms = ship_geoms(world, wind_from)
        return cls(terrain=terrain, atmosphere=atmosphere, geoms=geoms, buildings=buildings_of(world), people=people_bands(world, geoms))

    def geom_for(self, entity: int) -> Optional[ShipGeom]:
        for g in self.geoms:
            if g.entity == entity:
                return g
        return None

    def sample(
        self,
        xs,
        ys,
        *,
        include_ships: bool = True,
        exclude_ship: Optional[int] = None,
        ignore_hull_of: Optional[int] = None,
        with_air: bool = True,
        include_people: bool = True,
    ) -> Content:
        """Sample everything at the given world points.

        `exclude_ship` drops a ship entirely. `ignore_hull_of` keeps a
        ship's masts and sails as obstructions but not its hull and
        bulwarks - used for an observer's own ship: the captain can step to
        the rail, so his own bulwarks shouldn't hide the water alongside,
        but he can't see through his own mainsail."""
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        shape = xs.shape
        ter = self.terrain.sample(xs, ys)
        solid_top = ter.obstruction_top.copy()
        over_bottom = np.full(shape, np.inf)
        over_top = np.full(shape, -np.inf)
        surface_h = ter.height + 0.3
        tall_h = np.maximum(surface_h, ter.obstruction_top)
        ship = np.full(shape, -1, dtype=np.int32)
        tile = np.zeros(shape, dtype=np.uint8)
        gxs = np.zeros(shape, dtype=np.int32)
        gys = np.zeros(shape, dtype=np.int32)
        sail = np.full(shape, -1, dtype=np.int32)
        fu = np.zeros(shape)
        fv = np.zeros(shape)

        if include_ships:
            for i, g in enumerate(self.geoms):
                if g.entity == exclude_ship:
                    continue
                r = g.radius
                sel = (np.abs(xs - g.x) <= r) & (np.abs(ys - g.y) <= r)
                if not sel.any():
                    continue
                idx = np.nonzero(sel)
                u, v = g.to_local(xs[idx], ys[idx])
                gx, gy = g.layout.grid_from_local(u, v)
                inside = (gx >= 0) & (gx < g.layout.width) & (gy >= 0) & (gy < g.layout.height)
                t = np.zeros(u.shape, dtype=np.uint8)
                t[inside] = g.layout.tiles[gy[inside], gx[inside]]
                fu[idx] = u + g.layout.centre_x + 0.5 - gx
                fv[idx] = v + g.layout.centre_row + 0.5 - gy
                has = t != sl.NONE
                if has.any():
                    hi = tuple(a[has] for a in idx)
                    th = t[has]
                    ship[hi] = i
                    tile[hi] = th
                    gxs[hi] = gx[has]
                    gys[hi] = gy[has]
                    fit = np.zeros(th.shape)
                    for code, top in sl.FITTING_TOP_M.items():
                        fit[th == code] = top
                    mast_top = np.zeros(th.shape)
                    for m in g.layout.masts:
                        mast_top[(gx[has] == m.x) & (gy[has] == m.y)] = m.height_above_deck
                    # Masts are thin (well under a metre): they block sight as
                    # analytic poles (see poles() and vision.trace), not as a
                    # solid 1 m column, so their raster obstruction is just
                    # the deck they stand on.
                    hull_like = (th != sl.BOWSPRIT) & (th != sl.MAST)
                    if g.entity == ignore_hull_of:
                        hull_like = np.zeros_like(hull_like)
                    solid_top[hi] = np.where(hull_like, np.maximum(solid_top[hi], g.freeboard + fit), solid_top[hi])
                    fit = np.where(th == sl.MAST, mast_top, fit)
                    top_here = g.freeboard + fit
                    surf = np.where(th == sl.MAST, g.freeboard + 0.3, g.freeboard + np.minimum(fit, 1.2) + 0.3)
                    surface_h[hi] = np.where(th != sl.BOWSPRIT, surf, g.freeboard + 0.5)
                    tall_h[hi] = np.maximum(surface_h[hi], np.where(th != sl.BOWSPRIT, top_here, 0.0))
                # Sails (overhanging band), tested against every sampled
                # point near the ship including those outboard of the hull.
                for s in g.sails:
                    d = _dist_to_segment(u, v, s.u0, s.v0, s.u1, s.v1)
                    on = d <= SAIL_HALF_THICKNESS_M
                    if not on.any():
                        continue
                    oi = tuple(a[on] for a in idx)
                    # Rendering only: sails block sight as analytic walls
                    # (sail_walls() + vision.trace), exact at any zoom.
                    sail[oi] = i
                    tall_h[oi] = np.maximum(tall_h[oi], s.top_m)

        if include_ships and include_people and self.people:
            # Each man occupies his own square metre from the chest up. Only
            # the points that fall where people are get looked up at all.
            index, (bx0, by0, bx1, by1) = self.people_index()
            near = (xs >= bx0) & (xs <= bx1) & (ys >= by0) & (ys <= by1)
            if near.any():
                pidx = np.nonzero(near)
                keys_x = np.rint(xs[pidx]).astype(np.int64).tolist()
                keys_y = np.rint(ys[pidx]).astype(np.int64).tolist()
                flat = [int(i) for i in np.ravel_multi_index(pidx, shape)] if len(shape) > 1 else list(pidx[0])
                ob = over_bottom.reshape(-1)
                ot = over_top.reshape(-1)
                th_ = tall_h.reshape(-1)
                get = index.get
                for n, j in enumerate(flat):
                    band = get((keys_x[n], keys_y[n]))
                    if band is None:
                        continue
                    if band[0] < ob[j]:
                        ob[j] = band[0]
                    if band[1] > ot[j]:
                        ot[j] = band[1]
                    if band[1] > th_[j]:
                        th_[j] = band[1]

        bldg = np.full(shape, -1, dtype=np.int32)
        bldg_top = np.zeros(shape)
        bldg_damage = np.zeros(shape)
        for bi, b in enumerate(self.buildings):
            r = b.radius
            sel = (np.abs(xs - b.x) <= r) & (np.abs(ys - b.y) <= r)
            if not sel.any():
                continue
            idx = np.nonzero(sel)
            fx, fy = math.sin(math.radians(b.heading)), math.cos(math.radians(b.heading))
            dx, dy = xs[idx] - b.x, ys[idx] - b.y
            u, v = dx * fx + dy * fy, dx * fy - dy * fx
            ix, iy, _ = b.vs.local_to_voxel(u, v, np.zeros_like(u))
            nz, ny, nx = b.vs.shape
            inside = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
            top = np.zeros(u.shape)
            dmg = np.zeros(u.shape)
            top[inside] = b.top[iy[inside], ix[inside]]
            dmg[inside] = b.damage[iy[inside], ix[inside]]
            has = top > 0
            if has.any():
                hi = tuple(a[has] for a in idx)
                bldg[hi] = bi
                bldg_top[hi] = top[has]
                bldg_damage[hi] = dmg[has]
                solid_top[hi] = np.maximum(solid_top[hi], top[has])
                surface_h[hi] = np.maximum(surface_h[hi], top[has] + 0.2)
                tall_h[hi] = np.maximum(tall_h[hi], top[has] + 0.2)

        if with_air:
            fog_sigma, fog_top = self.atmosphere.fog_at(xs, ys)
            smoke_sigma, smoke_top = self.atmosphere.smoke_at(xs, ys)
        else:
            # Solid things only - for callers that cannot be blinded, like a
            # round shot asking what it has just run into.
            fog_sigma = np.zeros(shape)
            fog_top = np.zeros(shape)
            smoke_sigma = np.zeros(shape)
            smoke_top = np.zeros(shape)
        fields = Fields(solid_top, over_bottom, over_top, fog_sigma, fog_top, smoke_sigma, smoke_top)
        return Content(ter, ship, tile, gxs, gys, sail, fields, surface_h, tall_h, bldg, bldg_top, bldg_damage, fu, fv)

    def sail_walls(self, exclude_ship: Optional[int] = None) -> SailWalls:
        cols = [[], [], [], [], [], []]
        for g in self.geoms:
            if g.entity == exclude_ship:
                continue
            for sg in g.sails:
                ax, ay = g.to_world(sg.u0, sg.v0)
                bx, by = g.to_world(sg.u1, sg.v1)
                for col, v in zip(cols, (ax, ay, bx, by, sg.bottom_m, sg.top_m)):
                    col.append(v)
        return SailWalls(*(np.array(col, dtype=np.float64) for col in cols))

    def poles(self, exclude_ship: Optional[int] = None) -> "Poles":
        """Thin vertical obstructions (masts) as analytic circles."""
        xs, ys, rs, tops = [], [], [], []
        for g in self.geoms:
            if g.entity == exclude_ship:
                continue
            for m in g.layout.masts:
                x, y = g.tile_world(m.x, m.y)
                xs.append(x)
                ys.append(y)
                rs.append(MAST_RADIUS_M)
                tops.append(g.freeboard + m.height_above_deck)
        return Poles(np.array(xs), np.array(ys), np.array(rs), np.array(tops))

    def fields(self, xs, ys, *, include_ships: bool = True, exclude_ship: Optional[int] = None, ignore_hull_of: Optional[int] = None, ignore_person: Optional[int] = None, include_people: bool = True) -> Fields:
        if not include_people:
            return self.sample(
                xs, ys, include_ships=include_ships, exclude_ship=exclude_ship,
                ignore_hull_of=ignore_hull_of, include_people=False,
            ).fields
        if ignore_person is not None and self.people:
            kept = [p for p in self.people if p[4] != ignore_person]
            if len(kept) != len(self.people):
                import dataclasses as _dc

                return _dc.replace(self, people=kept).sample(
                    xs, ys, include_ships=include_ships, exclude_ship=exclude_ship, ignore_hull_of=ignore_hull_of
                ).fields
        return self.sample(xs, ys, include_ships=include_ships, exclude_ship=exclude_ship, ignore_hull_of=ignore_hull_of).fields


def _dist_to_segment(px, py, x0, y0, x1, y1):
    dx = x1 - x0
    dy = y1 - y0
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return np.hypot(px - x0, py - y0)
    t = np.clip(((px - x0) * dx + (py - y0) * dy) / l2, 0.0, 1.0)
    return np.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
