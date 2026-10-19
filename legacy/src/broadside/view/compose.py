# The frame composer: simulation state + camera + line of sight -> cells.
#
# One function, every scale. For each screen cell the camera gives a world
# point; the scene is sampled there (terrain, ship part, sail, fog, smoke);
# a ray is traced from the observer's eye to it; and the cell is drawn in
# one of four ways:
#
#   seen       - drawn in full colour, hazed toward grey by however much
#                fog/smoke/distance the line of sight passed through;
#   seen above - the surface is hidden but the cell's tall feature (a sail,
#                a masthead, a wooded hilltop) shows over the obstruction;
#   remembered - out of sight, but seen before: terrain in memory colours,
#                no ships (the sim's contact records draw those as ghosts);
#   unknown    - never seen: blank, or a fog wall if what's hiding it is
#                fog/smoke rather than something solid.
#
# In "planning" mode (time stopped, Dwarf-Fortress style) the player's own
# ship and crew are drawn in their entirety regardless of sight lines - the
# captain knows his own ship - while everything beyond the rail stays as
# the captain last saw it.
#
# At local scale (<= 2 m per cell) ships are drawn tile by tile from the
# sampled deck plans, crew and all. At larger scales ships are splatted as
# small clusters of glyphs (or one heading arrow) from the *contact
# records* - what the ship knows, not the truth.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from broadside.render.buffer import Cell, ScreenBuffer
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.entities import find_observer
from broadside.sim.systems.sighting import observer_eye
from broadside.sim.units import heading_axes, value_noise, wind_vector_ms
from broadside.sim.vision import VIS_CLEAR, VIS_FAINT, Eye, RasterFields, trace
from broadside.sim.world import terrain as tr
from broadside.view import style as S
from broadside.view.camera import ZOOM_LEVELS_M, Camera, compass_arrow
from broadside.view.memory import MapMemory

LOCAL_MAX_CELL_M = 2.0
HEAD_ABOVE_DECK_M = 1.6
MAX_RASTER = 360
# How long a traced sight field may be reused. What is visible changes as
# smoke drifts and the ship swings, but not in a tenth of a second - while
# the people, the water and the ship's position are redrawn every frame. It
# is what buys the ship pane its frame rate; see docs/design/08_interface.md.
SIGHT_REUSE_S = 0.12
# What a cloud's shadow tints the water toward.
CLOUD_SHADOW_TINT = (20, 24, 30)
# The world is modelled at one metre, so there is nothing to learn by
# tracing sight lines at a finer spacing than that: when the view is zoomed
# in past 1 m per cell (walk mode draws 2-3 cells per metre) the rays are
# traced on a 1 m grid and the answer is shared by the cells inside it.
# This is what makes a zoomed-in, smoothly moving view affordable.
TRACE_GRID_M = 1.0

# The local plan view is a slice, Dwarf-Fortress fashion: what you see is
# the level you are standing on. A sail's foot is 1.4 m above the deck
# (shiplayout.SAIL_FOOT_ABOVE_DECK_M), so the canvas belongs to the level
# above and is not drawn in the deck's slice - the mast is, as its trunk,
# exactly as a tree's trunk is in the ground slice and its leaves are not.
SLICE_ABOVE_DECK_M = 1.2

# The sea is never sampled finer than this. Below half a metre a cell is
# smaller than any feature of the water, and giving each one its own wave
# value made the surface boil from frame to frame instead of moving.
SEA_SAMPLE_M = 0.5


@dataclass
class ViewState:
    """Presentation state: which view, how zoomed, whose eyes, and what the
    player's screen remembers. Not simulation state."""

    scale: str = "local"  # "local" | "macro"
    local_zoom: int = 0  # index into ZOOM_LEVELS_M
    macro_zoom: int = 4
    rotation: str = "north"  # "north" | "ship" (bow up) | "bow" (bow right, port up)
    square_local: bool = False  # False = true 1 m x 1 m cells
    square_macro: bool = True
    observer: str = "captain"  # "captain" | "lookout"
    paused: bool = False  # True = planning mode
    reveal: bool = False  # debug: ignore line of sight entirely
    cursor: Optional[tuple] = None  # world (x, y) in metres
    pan: tuple = (0.0, 0.0)
    memory: MapMemory = field(default_factory=MapMemory)
    # Local scale below 1 m: `subcell` screen cells per metre (each 1 m
    # tile drawn k x k). `fit` picks the largest k at which the hull still
    # fits the pane, so small ships are drawn big (a sloop at 2x2).
    subcell: int = 1
    fit: bool = False
    # Walk mode: the view is centred on this person and goes where he goes,
    # close in, with his own eyes deciding what is visible.
    follow: int = -1
    # Set to a height in metres to draw a horizontal slice of the world at
    # that level instead of the captain's-eye view (view/levels.py).
    z_m: object = None
    # Set to a firstperson.Look to draw the view out along a bearing
    # instead of the plan - the glass, or just looking over the rail.
    look_out: object = None
    # Draw her own fore-and-aft line and her beams on this pane, so that a
    # north-up chart still says which way she is pointed and what bears
    # where *relative to her* - which is the only frame a gun cares about.
    show_axes: bool = True
    # An entity to run a dotted line to, with its bearing marked: the
    # contact you are laying guns on.
    contact: int = -1
    # A ballistics.ShotPrediction to draw: where the gun captain believes
    # this shot would go, before you give the word to fire.
    shot: object = None
    # (bearing, field of view) to mark on this pane: where you are looking,
    # so the chart says which way the glass is pointed and how wide a slice
    # of the world it is showing you.
    look_sector: object = None
    # A rendered copy of this pane, for views that need not be redrawn every
    # frame (see compose_slow).
    _cache: object = None
    _cache_key: object = None
    _cache_at_s: float = -1e9
    # The last sight field traced for this pane, reused for a fraction of a
    # second (see SIGHT_REUSE_S).
    _sight: object = None
    _sight_key: object = None
    _sight_at_s: float = -1e9

    @property
    def zoom_index(self) -> int:
        return self.local_zoom if self.scale == "local" else self.macro_zoom

    @property
    def cell_m(self) -> float:
        if self.scale == "local" and self.local_zoom == 0 and self.subcell > 1:
            return 1.0 / self.subcell
        return ZOOM_LEVELS_M[self.zoom_index]

    @property
    def aspect(self) -> float:
        sq = self.square_local if self.scale == "local" else self.square_macro
        return 2.0 if sq else 1.0

    def zoom(self, delta: int) -> None:
        if self.scale == "local":
            self.fit = False
            if delta < 0 and self.local_zoom == 0:
                self.subcell = min(6, self.subcell + 1)
            elif delta > 0 and self.subcell > 1:
                self.subcell -= 1
            else:
                self.local_zoom = max(0, min(len(ZOOM_LEVELS_M) - 1, self.local_zoom + delta))
        else:
            self.macro_zoom = max(0, min(len(ZOOM_LEVELS_M) - 1, self.macro_zoom + delta))

    def camera(self, state, rows: int = 0) -> Camera:
        """`rows` is the height of the pane this will be drawn in, needed
        only by auto-fit. The fit happens here rather than in the caller
        because the camera is snapped to the grid it will be sampled on:
        decide the cell size first, or the snap is to the wrong lattice and
        her planks flicker again."""
        pos = state.world.component_for_entity(state.player_ship, c.WorldPosition)
        heading = state.world.component_for_entity(state.player_ship, c.Heading)
        rot = {"ship": heading.degrees, "bow": heading.degrees - 90.0}.get(self.rotation, 0.0) % 360.0
        cx, cy = pos.x_m, pos.y_m
        if self.follow >= 0:
            spot = person_world_position(state, self.follow)
            if spot is not None:
                cx, cy = spot
        cx += self.pan[0]
        cy += self.pan[1]
        cell = self.cell_m
        if rows > 2 and self.fit and self.scale == "local" and self.local_zoom == 0:
            pbody = state.world.try_component(state.player_ship, c.ShipBody)
            if pbody is not None:
                # In rows, not metres: a square-celled deck covers `aspect`
                # metres a row, so twice the ship fits as the naive sum
                # says. At most 2 cells per metre: half a metre is about a
                # cask across, and finer than that reads as mush.
                # Rounded, not floored: a ship a row or two longer than the
                # pane is better drawn large with her bowsprit off the edge
                # than shrunk to half the detail.
                rows_m = (rows - 2) * self.aspect
                kfit = max(1, min(2, int(round(rows_m / max(1.0, float(pbody.layout.hull_length))))))
                cell = 1.0 / kfit
        if self.scale == "local" and self.rotation == "ship":
            # Hold the camera on the ship's own grid. Her position is
            # continuous, so without this the sampling grid slides under her
            # deck and every plank, gun and hatch shimmers a cell back and
            # forth as she makes way - which is what read as a "jumpy" ship.
            # Snapped in her own axes, the deck is rock-steady and the sea
            # slides past it instead, which is the way round it should be.
            fx, fy, sx, sy = heading_axes(heading.degrees)
            dx, dy = cx - pos.x_m, cy - pos.y_m
            fwd = dx * fx + dy * fy
            side = dx * sx + dy * sy
            row_m = cell * self.aspect
            # Half a cell off the lattice, so a sampled point never lands
            # exactly on a tile's edge - where the last bit of floating
            # point decides which tile it is in, and the deck flickers
            # between one plank and the next.
            fwd = (round(fwd / row_m) + 0.5) * row_m
            side = (round(side / cell) + 0.5) * cell
            cx = pos.x_m + fwd * fx + side * sx
            cy = pos.y_m + fwd * fy + side * sy
        return Camera(cx=cx, cy=cy, cell_m=cell, aspect=self.aspect, rotation=rot)


def compose_slow(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, view: ViewState, refresh_s: float = 0.4):
    """compose(), but reusing the last drawing of this pane for a short
    while. The chart is 12 m a column: nothing in it moves a whole column in
    half a second, and redrawing it every frame is what stopped the ship
    pane - which does need every frame - from being smooth."""
    cam = view.camera(state)
    grain = max(cam.cell_m, 1e-6)
    key = (
        width,
        height,
        round(cam.cell_m, 4),
        view.show_axes, view.contact,
        # By its numbers, not by object identity: the preview is a fresh
        # object every frame, and keying on id() would redraw the chart
        # every frame and throw away the slow-pane cache.
        None if view.shot is None else (round(view.shot.graze_m, 1), round(view.shot.bearing_deg, 1), view.shot.verdict),
        round(cam.rotation, 1),
        int(cam.cx / grain),
        int(cam.cy / grain),
        view.observer,
        view.reveal,
        view.paused,
        view.scale,
        None if view.look_sector is None else (round(view.look_sector[0], 1), round(view.look_sector[1], 1)),
    )
    fresh = view._cache is not None and view._cache_key == key and state.now_s - view._cache_at_s < refresh_s
    if not fresh:
        pane = ScreenBuffer(width, height)
        info = compose(pane, 0, 0, width, height, state, view)
        view._cache = (pane, info)
        view._cache_key = key
        view._cache_at_s = state.now_s
    pane, info = view._cache
    buf.blit(pane, x0, y0)
    return info


@dataclass
class FrameInfo:
    camera: Camera
    width: int
    height: int
    eye: Optional[Eye]
    visible_fraction: float
    letters: dict


def person_world_position(state, ent: int):
    """Where a person is standing, in world metres - his deck tile carried
    round by his ship's position and heading."""
    world = state.world
    crew = world.try_component(ent, c.CrewMember)
    dpos = world.try_component(ent, c.DeckPosition)
    if crew is None or dpos is None:
        return None
    body = world.try_component(crew.ship, c.ShipBody)
    pos = world.try_component(crew.ship, c.WorldPosition)
    hdg = world.try_component(crew.ship, c.Heading)
    if body is None or pos is None or hdg is None:
        return None
    u, v = body.layout.local_m(dpos.x, dpos.y)
    fx, fy, sx, sy = heading_axes(hdg.degrees)
    return pos.x_m + u * fx + v * sx, pos.y_m + u * fy + v * sy


def ship_letters(state) -> dict:
    """Stable one-letter labels for every ship but the player's."""
    ents = sorted(e for e, _ in state.world.get_component(c.ShipBody) if e != state.player_ship)
    return {e: chr(ord("A") + i) if i < 26 else chr(ord("a") + i - 26) for i, e in enumerate(ents)}


_GUN_SIDE_CACHE: dict = {}


def _gun_sides(layout: sl.DeckLayout) -> dict:
    key = id(layout)
    if key not in _GUN_SIDE_CACHE:
        _GUN_SIDE_CACHE[key] = {(g.x, g.y): g.side for g in layout.guns if g.on_deck}
    return _GUN_SIDE_CACHE[key]


_FOOTPRINT_CACHE: dict = {}


def _footprint(layout: sl.DeckLayout) -> tuple[np.ndarray, np.ndarray]:
    key = id(layout)
    if key not in _FOOTPRINT_CACHE:
        ys, xs = np.nonzero((layout.tiles != sl.NONE) & (layout.tiles != sl.BOWSPRIT))
        u = xs.astype(float) - layout.centre_x
        v = ys.astype(float) - layout.centre_row
        _FOOTPRINT_CACHE[key] = (u, v)
    return _FOOTPRINT_CACHE[key]


def compose(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, view: ViewState) -> FrameInfo:
    world = state.world
    scene = state.scene()
    cam = view.camera(state, rows=height)
    cell = cam.cell_m
    local = cell <= LOCAL_MAX_CELL_M + 1e-9
    W, H = width, height
    player = state.player_ship
    letters = ship_letters(state)

    xs, ys = cam.grid(W, H)
    content = scene.sample(xs, ys, include_ships=local)

    obs_ent = find_observer(world, player, view.observer) or find_observer(world, player, "captain")
    eye = observer_eye(state, obs_ent) if obs_ent is not None else None

    n = W * H
    raster = None
    if view.reveal or eye is None:
        vis_low = np.ones(n)
        vis_high = np.ones(n)
        solid_low = np.zeros(n, dtype=bool)
        vol_low = np.zeros(n)
    else:
        ex0, ey0, ex1, ey1 = cam.extent(W, H)
        ex0, ey0 = min(ex0, eye.x) - cell, min(ey0, eye.y) - cell
        ex1, ey1 = max(ex1, eye.x) + cell, max(ey1, eye.y) + cell
        r = max(cell if local else cell, max(ex1 - ex0, ey1 - ey0) / MAX_RASTER)
        nx = int(math.ceil((ex1 - ex0) / r))
        ny = int(math.ceil((ey1 - ey0) / r))
        sight_key = (
            W, H, round(cam.cell_m, 4), round(cam.rotation, 2),
            round(cam.cx, 2), round(cam.cy, 2), round(eye.x, 2), round(eye.y, 2), round(eye.h, 2),
            view.observer, view.paused, view.scale,
        )
        fresh = (
            view._sight is not None
            and view._sight_key == sight_key
            and state.now_s - view._sight_at_s < SIGHT_REUSE_S
        )
        raster = None
        if fresh:
            vis_low, vis_high, solid_low, vol_low, raster = view._sight
        if raster is None:
            # In her own deck view your own ship is wholly out of the way -
            # not her hull, her guns, her capstan or her masts. A man
            # standing on deck knows what is at his feet; the trouble was
            # that his eye at 1.7 m grazed his own guns at 1.3 m, so half
            # the sea alongside flickered in and out of sight as she moved.
            # Measured on the cutter: 27% of the traced field flipping every
            # quarter second, which is what read as black shadows jittering
            # on the water. Everything else occludes as before, and the
            # sighting system still counts her own canvas in full.
            raster = RasterFields.build(
                scene, ex0, ey0, r, nx, ny,
                include_ships=r <= 3.0,
                # Nor do his shipmates block his view of his own deck. A
                # crowd of men is not a wall: thirty hands on a cutter's
                # deck, each 1.75 m to his eye's 1.7 m, were cutting the
                # view into swinging wedges as they walked about. They are
                # still drawn, and they still occlude another ship's view
                # of this one.
                include_people=not local,
                exclude_ship=None,
                ignore_hull_of=player,
                ignore_person=obs_ent,
            )
            # One ray per TRACE_GRID_M of world, not per screen cell.
            step_x = max(1, int(round(TRACE_GRID_M / cell)))
            step_y = max(1, int(round(TRACE_GRID_M / max(1e-6, cell * cam.aspect))))
            sub = (slice(None, None, step_y), slice(None, None, step_x))
            tx, ty = xs[sub], ys[sub]
            sight = trace(
                eye,
                tx.ravel(),
                ty.ravel(),
                content.surface_h[sub].ravel(),
                content.tall_h[sub].ravel(),
                raster,
                step_m=r,
                haze_sigma=state.atmosphere.haze_sigma,
                end_skip_m=r * 0.7,
                # Your own ship is not in your own way at this scale: a
                # man on deck knows what is under his feet, and his own
                # courses throwing black wedges across the water alongside
                # read as a fault rather than as shadow. Everything else -
                # other ships' canvas, islands, fog, smoke - occludes as
                # ever, and the sighting system (which decides what you
                # have actually *seen*) still counts your own sails in
                # full: see scenarios/own_sails_blind_spot.
                poles=scene.poles(exclude_ship=player if local else None),
                sails=scene.sail_walls(exclude_ship=player if local else None),
            )
            vis_low, vis_high, solid_low, vol_low = sight.low, sight.high, sight.solid_low, sight.vol_low
            if step_x > 1 or step_y > 1:
                # Spread each traced answer over the screen cells it stands for.
                th, tw = tx.shape
                grid = np.arange(th * tw).reshape(th, tw)
                idx = np.repeat(np.repeat(grid, step_y, axis=0), step_x, axis=1)[:H, :W]
                if idx.shape != (H, W):  # a partial block at the right or bottom
                    pad = np.zeros((H, W), dtype=idx.dtype)
                    pad[: idx.shape[0], : idx.shape[1]] = idx
                    pad[idx.shape[0]:, :] = pad[max(0, idx.shape[0] - 1), :]
                    pad[:, idx.shape[1]:] = pad[:, max(0, idx.shape[1] - 1)][:, None]
                    idx = pad
                flat = idx.ravel()
                vis_low = vis_low[flat]
                vis_high = vis_high[flat]
                solid_low = solid_low[flat]
                vol_low = vol_low[flat]
            view._sight = (vis_low, vis_high, solid_low, vol_low, raster)
            view._sight_key = sight_key
            view._sight_at_s = state.now_s

    ship_idx = content.ship.ravel()
    sail_idx = content.sail.ravel()
    own_idx = next((i for i, g in enumerate(scene.geoms) if g.entity == player), -1)

    if view.paused and own_idx >= 0:
        own = (ship_idx == own_idx) | (sail_idx == own_idx)
        vis_low = np.where(own, np.maximum(vis_low, 1.0), vis_low)

    seen_now = vis_low >= VIS_FAINT
    view.memory.mark(xs.ravel(), ys.ravel(), seen_now, cell)
    remembered = view.memory.seen(xs.ravel(), ys.ravel(), cell)

    # Cloud shadows: where a cloud lies between the sun and the water, the
    # light is a little less. Sampled per cell, so the shadows drift across
    # the sea at both scales and give the weather somewhere to be.
    light_here = state.atmosphere.light_at(xs.ravel(), ys.ravel())
    base_light = max(1e-6, state.atmosphere.light)
    shade_l = np.clip(light_here / base_light, 0.0, 1.0).tolist()

    wx, wy = wind_vector_ms(state.wind.current.direction_degrees, state.wind.current.speed_knots)
    t = state.now_s
    if cell < SEA_SAMPLE_M:
        # Half-metre patches of water, each with one wave value, offset
        # half a step so no sample lands on a patch boundary.
        q = SEA_SAMPLE_M
        wxs = np.floor(xs.ravel() / q) * q + q * 0.5
        wys = np.floor(ys.ravel() / q) * q + q * 0.5
    else:
        wxs, wys = xs.ravel(), ys.ravel()
    wave = sea_surface(wxs, wys, t, max(cell, SEA_SAMPLE_M), state.wind.current)

    # The height this view is a slice of: the deck you are standing on.
    # None at chart scale, where you are looking down on the whole ship and
    # her canvas is part of the picture.
    slice_cut = None
    if local and view.z_m is None:
        pbody = world.try_component(player, c.ShipBody)
        if pbody is not None:
            slice_cut = float(pbody.layout.freeboard_m) + SLICE_ABOVE_DECK_M

    codes = content.terrain.code.ravel()
    bidx = content.bldg.ravel()
    btop = content.bldg_top.ravel()
    bdmg = content.bldg_damage.ravel()
    dust = state.atmosphere.smoke_at(xs.ravel(), ys.ravel(), kind="dust")[0]
    tiles = content.tile.ravel()
    gxs = content.gx.ravel()
    gys = content.gy.ravel()
    surface = content.surface_h.ravel()
    tall = content.tall_h.ravel()
    smoke = content.fields.smoke_sigma.ravel()
    fog = content.fields.fog_sigma.ravel()

    geoms = scene.geoms
    from broadside.sim.structure import StructureState

    structures = {i: world.try_component(g.entity, StructureState) for i, g in enumerate(geoms)}
    ship_screen_dirs = {}
    for i, g in enumerate(geoms):
        ship_screen_dirs[i] = cam.screen_vector(g.fx, g.fy), cam.screen_vector(g.sx, g.sy)

    # Per-cell drawing. Every array the loop reads is turned into a Python
    # list first: indexing numpy inside a 12,000-iteration Python loop costs
    # more than everything else in this function put together, and the cells
    # are written straight into the buffer's rows. Profiling a 190x64 frame
    # is what asked for this (docs/design/01_architecture.md: profile first).
    vl_l = vis_low.tolist()
    vh_l = vis_high.tolist()
    solid_l = solid_low.tolist()
    vol_l = vol_low.tolist()
    code_l = codes.tolist()
    ship_l = ship_idx.tolist()
    sail_l = sail_idx.tolist()
    bldg_l = bidx.tolist()
    btop_l = btop.tolist()
    bdmg_l = bdmg.tolist()
    dust_l = dust.tolist()
    tile_l = tiles.tolist()
    gx_l = gxs.tolist()
    gy_l = gys.tolist()
    surf_l = surface.tolist()
    tall_l = tall.tolist()
    smoke_l = smoke.tolist()
    fog_l = fog.tolist()
    wave_l = wave.tolist()
    rem_l = remembered.tolist()
    ground_l = content.terrain.height.ravel().tolist()
    # Zoomed in past a third of a metre a cell, a square metre of ship is
    # drawn as what it actually is - planks and their seams, a gun's barrel
    # and carriage, the round of a mast - instead of one repeated glyph.
    k_sub = int(round(1.0 / cell)) if cell < 1.0 else 1
    # Two cells to the metre is the auto-fit default for a small ship,
    # and style.subtile has a form for it: without this the ship was
    # drawn as her plain glyphs doubled, which reads as broken.
    sub_detail = k_sub >= 2
    fu_l = content.fu.ravel().tolist() if sub_detail else None
    fv_l = content.fv.ravel().tolist() if sub_detail else None
    subtile = S.subtile
    blend = S.blend
    tstyle = S.TERRAIN_STYLE
    sstyle = S.SHIP_TILE_STYLE
    wave_hi, wave_lo = S.WAVE_GLYPHS[1], S.WAVE_GLYPHS[0]
    cols = max(0, min(W, buf.width - x0))
    k = 0
    for row in range(H):
        yy = y0 + row
        if not (0 <= yy < buf.height):
            k += W
            continue
        cells = buf.row(yy)
        for col in range(cols):
            kk = k + col
            vl = vl_l[kk]
            code = code_l[kk]
            si = ship_l[kk]
            bi = bldg_l[kk]
            if vl >= VIS_FAINT and bi >= 0:
                top = btop_l[kk] - ground_l[kk]
                dmg = bdmg_l[kk]
                glyph = "\u2588" if top > 3.5 else ("\u2593" if top > 1.8 else ("\u2592" if top > 0.8 else ":"))
                fg = blend(S.WALL_FG, S.RUBBLE_FG, dmg)
                bg = blend(S.WALL_BG, S.RUBBLE_BG, dmg)
                if dmg > 0.6:
                    glyph = ":" if top < 1.2 else "\u2592"
                sm = smoke_l[kk]
                if sm > 0.008:
                    bg = blend(bg, blend(S.SMOKE, S.DUST, min(1.0, dust_l[kk] / sm)), min(0.7, sm * 3.0))
            elif vl >= VIS_FAINT:
                if si >= 0:
                    g = geoms[si]
                    tile = tile_l[kk]
                    glyph, fg, bg = sstyle.get(tile, ("?", (255, 0, 255), None))
                    if bg is None:
                        bg = tstyle[code][2]
                    if sub_detail:
                        side = _gun_sides(g.layout).get((gx_l[kk], gy_l[kk]), 1) if tile == sl.GUN else 1
                        detail = subtile(tile, fu_l[kk], fv_l[kk], k_sub, side)
                        if detail is not None:
                            dglyph, dfg = detail
                            if dglyph == " ":
                                glyph, fg = ".", S.SHIP_TILE_STYLE[sl.DECK][1]
                            else:
                                glyph, fg = dglyph, dfg
                    elif tile == sl.GUN:
                        side = _gun_sides(g.layout).get((gx_l[kk], gy_l[kk]), 1)
                        (sx_, sy_) = ship_screen_dirs[si][1]
                        glyph = S.dir_glyph(sx_ * side, sy_ * side)
                    if tile == sl.BOWSPRIT:
                        (fx_, fy_) = ship_screen_dirs[si][0]
                        glyph = S.dir_glyph(fx_, fy_)
                    if tile == sl.HULL and g.entity != player:
                        fg = blend(fg, S.faction_color(g.faction), 0.45)
                    sst = structures.get(si)
                    if sst is not None:
                        integ = float(sst.integrity[gy_l[kk], gx_l[kk]])
                        if integ < 0.25:
                            glyph, fg, bg = ":", (70, 50, 35), (25, 18, 12)
                        elif integ < 0.7:
                            fg = blend(fg, (90, 45, 30), 0.6)
                else:
                    glyph, fg, bg = tstyle[code]
                    if code == tr.SEA or code == tr.SHOAL:
                        # Swell: crests that march, drawn as a ramp rather
                        # than popping on and off at a threshold.
                        wv = wave_l[kk]
                        if wv > 0.88:
                            glyph = wave_hi
                            fg = S.blend(fg, S.FOAM, min(1.0, (wv - 0.88) * 6.0))
                            bg = S.blend(bg, S.CREST_BG, min(0.8, (wv - 0.82) * 3.0))
                        elif wv > 0.68:
                            glyph = wave_lo
                            bg = S.blend(bg, S.CREST_BG, (wv - 0.68) * 1.6)
                        else:
                            glyph = " "
                            if wv < 0.3:
                                bg = S.blend(bg, S.TROUGH_BG, (0.3 - wv) * 1.8)
                if slice_cut is None and sail_l[kk] >= 0 and (si < 0 or tile_l[kk] in (sl.DECK, sl.HATCH, sl.HULL, sl.BOWSPRIT)):
                    glyph, fg = S.SAIL_GLYPH, S.SAIL_FG
                haze = 1.0 - vl
                if haze > 0.05:
                    fg = blend(fg, S.HAZE if vol_l[kk] < 0.5 else S.FOG, haze * 0.85)
                    bg = blend(bg, S.FOG_BG if vol_l[kk] >= 0.5 else S.VOID_BG, haze * 0.6)
                sm = smoke_l[kk]
                if sm > 0.008:
                    colr = blend(S.SMOKE, S.DUST, min(1.0, dust_l[kk] / sm))
                    bg = blend(bg, colr, min(0.75, sm * 3.5))
                    if si < 0 and sail_l[kk] < 0:
                        glyph = "\u2593" if sm > 0.25 else ("\u2592" if sm > 0.08 else "\u2591")
                        fg = colr
                fgv = fog_l[kk]
                if fgv > 0.004:
                    bg = blend(bg, S.FOG_BG, min(0.7, fgv * 20))
            elif vh_l[kk] >= VIS_FAINT and tall_l[kk] > surf_l[kk] + 1.5:
                # Only the tall part shows: topsails over a low islet or
                # above smoke, a wooded crest over a headland.
                if sail_l[kk] >= 0:
                    glyph, fg = S.SAIL_GLYPH, S.SAIL_FG
                elif si >= 0 and tile_l[kk] == sl.MAST:
                    glyph, fg = "O", sstyle[sl.MAST][1]
                else:
                    glyph, fg, _ = tstyle[code]
                fg = blend(fg, S.FOG, (1.0 - vh_l[kk]) * 0.8)
                bg = S.remembered_bg(tstyle[code][2]) if rem_l[kk] else S.VOID_BG
            else:
                own_here = own_idx >= 0 and (si == own_idx or sail_l[kk] == own_idx)
                if own_here:
                    # Your own ship, out of sight this instant: veiled. Drawn
                    # exactly as she is drawn when lit - the same sub-metre
                    # detail - only dim, so that light flickering at the edge
                    # of sight changes her colour and never her shape.
                    tile = tile_l[kk]
                    if sail_l[kk] == own_idx and (si < 0 or tile in (sl.DECK, sl.HATCH, sl.HULL, sl.BOWSPRIT)):
                        glyph, fg, bg = S.SAIL_GLYPH, S.SAIL_FG, tstyle[code][2]
                    else:
                        glyph, fg, bg = sstyle.get(tile, (" ", S.VOID_BG, S.VOID_BG))
                        if bg is None:
                            bg = tstyle[code][2]
                        if sub_detail and si >= 0:
                            side = _gun_sides(geoms[si].layout).get((gx_l[kk], gy_l[kk]), 1) if tile == sl.GUN else 1
                            detail = subtile(tile, fu_l[kk], fv_l[kk], k_sub, side)
                            if detail is not None:
                                dglyph, dfg = detail
                                glyph, fg = (".", sstyle[sl.DECK][1]) if dglyph == " " else (dglyph, dfg)
                    fg, bg = S.veiled(fg, bg)
                elif rem_l[kk] or (local and code in (tr.SEA, tr.SHOAL)):
                    # Water alongside that your own rail hides is not a
                    # mystery: a captain knows the sea is there, and knows
                    # how it is running. Only at this scale - on the chart,
                    # unexplored water stays unknown.
                    glyph, fg0, bg0 = tstyle[code]
                    fg, bg = S.remembered(fg0), S.remembered_bg(bg0)
                    if code in (tr.SEA, tr.SHOAL):
                        wv = wave_l[kk]
                        if wv > 0.88:
                            glyph = wave_hi
                        elif wv > 0.68:
                            glyph = wave_lo
                else:
                    glyph, fg, bg = " ", S.VOID_BG, S.VOID_BG
                if not own_here and not solid_l[kk] and (vol_l[kk] >= 1.0 or smoke_l[kk] > 0.05):
                    # Hidden by smoke or fog rather than by anything solid:
                    # draw the murk itself, and in the colour of what it is -
                    # powder smoke is grey, not black.
                    sm = smoke_l[kk]
                    murk = blend(S.SMOKE, S.DUST, min(1.0, dust_l[kk] / sm)) if sm > 1e-6 else S.FOG
                    glyph = "\u2593" if sm > 0.25 else ("\u2592" if sm > 0.08 else "\u2591")
                    fg = blend(murk, S.FOG_BG, 0.25)
                    bg = blend(S.FOG_BG, murk, 0.35)
            sh = shade_l[kk]
            if sh < 0.96:
                # Under a cloud. A slight drop, not a blackout - and the
                # cloud field is kilometres wide, so on deck it is near
                # enough uniform; a strong tint there read as a stain on
                # the picture rather than weather.
                bg = blend(bg, CLOUD_SHADOW_TINT, (1.0 - sh) * 0.7)
            cells[x0 + col] = Cell(glyph, fg, bg)
        k += W

    visible_map = vis_low.reshape(H, W)

    def cell_visible(col: int, row: int) -> bool:
        return 0 <= col < W and 0 <= row < H and visible_map[row, col] >= VIS_FAINT

    # --- Stores on deck and crew (local scale) ---------------------------
    if local:
        from broadside.render.palette import role_color
        from broadside.sim.items import Item, Stowed
        from broadside.sim.people.components import Body

        geom_by_ent = {g.entity: g for g in geoms}
        for ent, (item, st) in world.get_components(Item, Stowed):
            if st.x is None:
                continue
            g = geom_by_ent.get(st.ship)
            if g is None:
                continue
            col, row = cam.to_screen(*g.tile_world(st.x, st.y), W, H)
            col, row = int(col), int(row)
            if not (0 <= col < W and 0 <= row < H):
                continue
            if not (view.reveal or cell_visible(col, row) or (st.ship == player and view.paused)):
                continue
            glyph, fg = S.ITEM_STYLE.get(item.kind, ("\u00a4", (190, 150, 100)))
            _put(buf, x0, y0, W, H, col, row, glyph, fg)

        drawn_alive: set = set()
        # People are tested at head height, not deck height: you see men's
        # heads and shoulders over a bulwark long before you see the deck
        # planking behind it.
        head_ok: dict = {}
        if raster is not None and eye is not None:
            cand = []
            for ent, (crew, dpos) in world.get_components(c.CrewMember, c.DeckPosition):
                g = geom_by_ent.get(crew.ship)
                if g is None or world.has_component(ent, c.Aloft):
                    continue
                cand.append((ent, g.tile_world(dpos.x, dpos.y), g.freeboard + HEAD_ABOVE_DECK_M))
            if cand:
                hx = np.array([p_[1][0] for p_ in cand])
                hy = np.array([p_[1][1] for p_ in cand])
                hh = np.array([p_[2] for p_ in cand])
                hs = trace(eye, hx, hy, hh, hh, raster, step_m=max(0.5, raster.cell_m), haze_sigma=state.atmosphere.haze_sigma,
                           end_skip_m=0.7, poles=scene.poles(), sails=scene.sail_walls())
                head_ok = {p_[0]: hs.low[i] >= VIS_FAINT for i, p_ in enumerate(cand)}
        for ent, (crew, dpos) in world.get_components(c.CrewMember, c.DeckPosition):
            if world.has_component(ent, c.Aloft):
                continue
            g = geom_by_ent.get(crew.ship)
            if g is None:
                continue
            wxp, wyp = g.tile_world(dpos.x, dpos.y)
            col, row = cam.to_screen(wxp, wyp, W, H)
            col, row = int(col), int(row)
            if not (0 <= col < W and 0 <= row < H):
                continue
            home = crew.home_ship if crew.home_ship >= 0 else crew.ship
            own = home == player
            # Planning mode: the captain knows where all his own people are,
            # even those who have boarded another ship.
            if not (view.reveal or cell_visible(col, row) or head_ok.get(ent, False) or (own and view.paused)):
                continue
            body = world.try_component(ent, Body)
            bg = buf.get(x0 + col, y0 + row).bg
            if body is not None and not body.alive:
                if (col, row) not in drawn_alive:
                    buf.set(x0 + col, y0 + row, "%", fg=S.CORPSE_FG, bg=bg)
                continue
            role = world.try_component(ent, c.Role)
            title = role.title if role else ""
            if title == "Captain" and own:
                buf.set(x0 + col, y0 + row, "@", fg=S.CAPTAIN_FG, bg=S.CAPTAIN_BG)
            else:
                hf = world.try_component(home, c.Faction)
                fg = role_color(title) if own else S.faction_color(hf.name if hf else "neutral")
                if body is not None and not body.conscious:
                    fg = S.blend(fg, (0, 0, 0), 0.55)
                elif body is not None and body.bleeding_ml_s > 0.3:
                    bg = S.BLEEDING_BG
                buf.set(x0 + col, y0 + row, S.crew_glyph(title), fg=fg, bg=bg)
            drawn_alive.add((col, row))

    # --- Muzzle flashes ---------------------------------------------------
    for ent, (battery, body) in world.get_components(c.Battery, c.ShipBody):
        g = next((gg for gg in geoms if gg.entity == ent), None)
        if g is None:
            continue
        for gs in battery.guns:
            if gs.flash_s <= 0:
                continue
            spec = body.layout.guns[gs.index]
            u, v = body.layout.local_m(spec.x, spec.y)
            wxp, wyp = g.to_world(u, v + spec.side * 1.5)
            col, row = cam.to_screen(wxp, wyp, W, H)
            col, row = int(col), int(row)
            if 0 <= col < W and 0 <= row < H and (view.reveal or not local or cell_visible(col, row) or visible_map[row, col] > 0.0005 or (ent == player)):
                buf.set(x0 + col, y0 + row, "*", fg=S.FLASH_FG, bg=S.FLASH_BG)

    # --- Round shot in flight ------------------------------------------------
    from broadside.sim.systems.ballistics import Projectile

    for _pe, proj in world.get_component(Projectile):
        for i, (tx_, ty_, _tz) in enumerate(proj.trail[:-1]):
            col, row = cam.to_screen(tx_, ty_, W, H)
            col, row = int(col), int(row)
            if 0 <= col < W and 0 <= row < H:
                _put(buf, x0, y0, W, H, col, row, "·", S.blend((90, 90, 95), (230, 230, 230), (i + 1) / len(proj.trail)))
        col, row = cam.to_screen(proj.x, proj.y, W, H)
        _put(buf, x0, y0, W, H, int(col), int(row), "●", (40, 40, 44), bg=(210, 200, 170))

    # --- Ships from knowledge (macro) and contact ghosts (both) ------------
    contacts = world.try_component(player, c.Contacts)
    records = contacts.records if contacts else {}
    for i, g in enumerate(geoms):
        own = g.entity == player
        rec = records.get(g.entity)
        if own or view.reveal:
            status, px, py, hdg = "hull", g.x, g.y, g.heading
        elif rec is not None and rec.status in ("hull", "topsails", "lost"):
            status, px, py, hdg = rec.status, rec.x_m, rec.y_m, rec.heading
        else:
            continue
        colr = S.faction_color(g.faction) if not own else (255, 255, 255)
        letter = letters.get(g.entity, "")
        ccol, crow = cam.to_screen(px, py, W, H)
        ccol, crow = int(ccol), int(crow)

        if local:
            # Deck-scale ships draw themselves from sight lines. Only mark
            # contacts the captain can't see directly: lost ones, and ones
            # known only from the masthead.
            if own or view.reveal:
                continue
            if 0 <= ccol < W and 0 <= crow < H and not cell_visible(ccol, crow):
                if status == "lost":
                    buf.set(x0 + ccol, y0 + crow, S.GHOST_GLYPH, fg=S.blend(colr, (0, 0, 0), 0.35), bg=buf.get(x0 + ccol, y0 + crow).bg)
                elif rec is not None and rec.seen_by == "lookout":
                    buf.set(x0 + ccol, y0 + crow, S.REPORT_GLYPH, fg=colr, bg=buf.get(x0 + ccol, y0 + crow).bg)
            continue

        dim = S.blend(colr, (0, 0, 0), 0.4)
        if status == "lost":
            _put(buf, x0, y0, W, H, ccol, crow, S.GHOST_GLYPH, dim)
            _label(buf, x0, y0, W, H, ccol + 1, crow, letter, dim)
            continue
        if status == "topsails":
            _put(buf, x0, y0, W, H, ccol, crow, S.TOPSAILS_GLYPH, dim)
            _label(buf, x0, y0, W, H, ccol + 1, crow, letter, dim)
            continue

        fx, fy, sx, sy = heading_axes(hdg)
        U, V = _footprint(g.layout)
        wxs = px + U * fx + V * sx
        wys = py + U * fy + V * sy
        cols, rows = cam.to_screen(wxs, wys, W, H)
        cells = set(zip(cols.tolist(), rows.tolist()))
        sdx, sdy = cam.screen_vector(fx, fy)
        arrow = S.arrow_for(sdx, sdy)
        if len(cells) <= 2:
            _put(buf, x0, y0, W, H, ccol, crow, arrow, colr)
            max_col = ccol
        else:
            bow_col, bow_row = cam.to_screen(px + fx * g.layout.hull_length * 0.45, py + fy * g.layout.hull_length * 0.45, W, H)
            if cell <= 8.0 and slice_cut is None:
                for s in g.sails:
                    for tt in np.linspace(0.0, 1.0, 9):
                        su = s.u0 + (s.u1 - s.u0) * tt
                        sv = s.v0 + (s.v1 - s.v0) * tt
                        scol, srow = cam.to_screen(px + su * fx + sv * sx, py + su * fy + sv * sy, W, H)
                        if (int(scol), int(srow)) not in cells:
                            _put(buf, x0, y0, W, H, int(scol), int(srow), "░", S.SAIL_FG)
            for (cc, rr) in cells:
                _put(buf, x0, y0, W, H, cc, rr, "▓", colr, bg=(44, 32, 20))
            _put(buf, x0, y0, W, H, int(bow_col), int(bow_row), arrow, colr, bg=(44, 32, 20))
            max_col = max(cc for cc, _ in cells)
        _label(buf, x0, y0, W, H, max_col + 1, crow, letter if not own else "", colr)

    # --- Cursor -----------------------------------------------------------
    if view.cursor is not None:
        ccol, crow = cam.to_screen(view.cursor[0], view.cursor[1], W, H)
        ccol, crow = int(ccol), int(crow)
        if 0 <= ccol < W and 0 <= crow < H:
            cur = buf.get(x0 + ccol, y0 + crow)
            buf.set(x0 + ccol, y0 + crow, cur.glyph if cur.glyph != " " else "X", fg=S.CURSOR_FG, bg=S.CURSOR_BG)

    # --- Legend -------------------------------------------------------------
    ndx, ndy = cam.screen_vector(0.0, 1.0)
    scale_txt = f"{cell:g} m/col" + ("" if cam.aspect == 1.0 else f" x {cell * cam.aspect:g} m/row")
    mode_txt = "PLANNING (paused)" if view.paused else "LIVE"
    eye_txt = {"captain": "captain's eye", "lookout": "masthead"}.get(view.observer, view.observer)
    if view.reveal:
        eye_txt = "REVEAL ALL (debug)"
    if view.rotation == "bow":
        north = "bow →"
    elif view.rotation == "ship":
        north = "bow ↑"
    else:
        north = f"N{compass_arrow(ndx, ndy)}"
    legend = f" {north}  {scale_txt}  {'local' if local else 'macro'}  {eye_txt}  {mode_txt} "
    buf.draw_text(x0, y0 + H - 1, legend[:W], fg=(230, 230, 230), bg=(20, 22, 30))

    if view.look_sector is not None:
        _draw_look_sector(buf, x0, y0, W, H, cam, state, view.look_sector)
    if view.show_axes and view.scale == "macro":
        # Only on the chart: on a bow-up deck view her fore-and-aft line is
        # the screen's own vertical, and the dots would be clutter.
        _draw_ship_axes(buf, x0, y0, W, H, cam, state)
    if view.contact >= 0:
        _draw_contact(buf, x0, y0, W, H, cam, state, view.contact)
    if view.shot is not None:
        _draw_shot(buf, x0, y0, W, H, cam, view.shot)

    return FrameInfo(camera=cam, width=W, height=H, eye=eye, visible_fraction=float(seen_now.mean()), letters=letters)


def _put(buf, x0, y0, W, H, col, row, glyph, fg, bg=None) -> None:
    if 0 <= col < W and 0 <= row < H:
        if bg is None:
            bg = buf.get(x0 + col, y0 + row).bg
        buf.set(x0 + col, y0 + row, glyph, fg=fg, bg=bg)


def _label(buf, x0, y0, W, H, col, row, text, fg) -> None:
    for i, ch in enumerate(text):
        _put(buf, x0, y0, W, H, col + i, row, ch, fg)


SECTOR_FG = (235, 206, 120)
SECTOR_EDGE = (150, 130, 70)
SECTOR_SKIP = (" ", "~", "≈", "·", "+", "░")


def _draw_look_sector(buf: ScreenBuffer, x0: int, y0: int, W: int, H: int, cam, state, sector) -> None:
    """Mark where you are looking: the two edges of the field and the
    bearing down the middle. Drawn over the chart, so with the glass up you
    can always see which way it is pointed and how much of the world is in
    it."""
    bearing, fov = sector
    pos = state.world.try_component(state.player_ship, c.WorldPosition)
    if pos is None:
        return
    reach = max(W, H) * cam.cell_m * 1.6
    for off, glyph, fg in ((-fov / 2.0, "·", SECTOR_EDGE), (fov / 2.0, "·", SECTOR_EDGE), (0.0, "+", SECTOR_FG)):
        b = math.radians(bearing + off)
        dx, dy = math.sin(b), math.cos(b)
        step = cam.cell_m * 0.6
        d = cam.cell_m * 2.0
        while d < reach:
            col, row = cam.to_screen(pos.x_m + dx * d, pos.y_m + dy * d, W, H)
            col, row = int(col), int(row)
            d += step
            if not (0 <= col < W and 0 <= row < H):
                continue
            cell = buf.get(x0 + col, y0 + row)
            if cell.glyph not in SECTOR_SKIP:
                continue  # never paint over a ship, a coast or a contact
            buf.set(x0 + col, y0 + row, glyph, fg=fg, bg=cell.bg)


AXIS_AHEAD = (228, 212, 150)
AXIS_BEAM = (120, 150, 170)
AXIS_DIAG = (84, 100, 118)
CONTACT_FG = (245, 150, 110)


def _ray(buf, x0, y0, W, H, cam, ox, oy, bearing, reach, glyph, fg, skip_near=2.0, label="", before=False, rows_max=None):
    """Dot a line out along a bearing from a point, never painting over
    anything that is actually there, and never over the legend."""
    b = math.radians(bearing)
    dx, dy = math.sin(b), math.cos(b)
    step = cam.cell_m * 1.6  # sparse: a mark every second cell or so
    d = cam.cell_m * skip_near
    limit = H - 1 if rows_max is None else rows_max
    last = None
    while d < reach:
        col, row = cam.to_screen(ox + dx * d, oy + dy * d, W, H)
        col, row = int(col), int(row)
        d += step
        if not (0 <= col < W and 0 <= row < limit):
            continue
        cell = buf.get(x0 + col, y0 + row)
        if cell.glyph not in SECTOR_SKIP:
            continue
        buf.set(x0 + col, y0 + row, glyph, fg=fg, bg=cell.bg)
        last = (col, row)
    if label and last is not None:
        # Keep the whole word on the pane: a label cut in half by the edge
        # is worse than one sitting a little inside it.
        col = last[0] - len(label) - 1 if before else min(last[0] + 1, W - len(label))
        if 0 <= last[1] < limit:
            _label(buf, x0, y0, W, H, max(0, col), last[1], label, fg)


def _draw_ship_axes(buf: ScreenBuffer, x0: int, y0: int, W: int, H: int, cam, state) -> None:
    """Her fore-and-aft line and her beams, marked out from her as a short
    cross with the quarter-points between. On a north-up chart this is what
    tells you how you lie to the enemy: a contact on the starboard beam
    line will take the whole broadside, one on the bow line will not.

    Deliberately short. Drawn the full width of the pane it was a web of
    dots across the whole sea, which read as a fault in the picture rather
    than as an instrument.
    """
    world = state.world
    pos = world.try_component(state.player_ship, c.WorldPosition)
    head = world.try_component(state.player_ship, c.Heading)
    if pos is None or head is None:
        return
    hdg = head.degrees
    # A cross about a third of the smaller side of the pane.
    reach = min(W * cam.cell_m, H * cam.cell_m * cam.aspect) * 0.34
    body = world.try_component(state.player_ship, c.ShipBody)
    near = 1.5 if body is None else max(1.5, (float(body.layout.hull_length) * 0.6) / max(0.01, cam.cell_m))
    if reach <= near * cam.cell_m * 1.5:
        return  # zoomed in so far that the cross would be all ship
    for off in (45.0, 135.0, 225.0, 315.0):
        _ray(buf, x0, y0, W, H, cam, pos.x_m, pos.y_m, hdg + off, reach * 0.45, "·", AXIS_DIAG, near)
    _ray(buf, x0, y0, W, H, cam, pos.x_m, pos.y_m, hdg + 90.0, reach, "·", AXIS_BEAM, near, "stbd")
    _ray(buf, x0, y0, W, H, cam, pos.x_m, pos.y_m, hdg - 90.0, reach, "·", AXIS_BEAM, near, "port", before=True)
    _ray(buf, x0, y0, W, H, cam, pos.x_m, pos.y_m, hdg + 180.0, reach * 0.8, "·", AXIS_BEAM, near, "astern")
    _ray(buf, x0, y0, W, H, cam, pos.x_m, pos.y_m, hdg, reach, ":", AXIS_AHEAD, near, "ahead")


def _draw_contact(buf: ScreenBuffer, x0: int, y0: int, W: int, H: int, cam, state, ent: int) -> None:
    """A line of fire: from us to what the guns are laid on, with her
    bearing, range and aspect written at her end of it."""
    from broadside.view.orientation import aspect_short, range_short, relative_short

    world = state.world
    mine = world.try_component(state.player_ship, c.WorldPosition)
    hers = world.try_component(ent, c.WorldPosition)
    head = world.try_component(state.player_ship, c.Heading)
    if mine is None or hers is None or head is None:
        return
    dx, dy = hers.x_m - mine.x_m, hers.y_m - mine.y_m
    rng = math.hypot(dx, dy)
    if rng < 1.0:
        return
    bearing = math.degrees(math.atan2(dx, dy)) % 360.0
    rel = (bearing - head.degrees + 180.0) % 360.0 - 180.0
    body = world.try_component(state.player_ship, c.ShipBody)
    near = 1.5 if body is None else max(1.5, (float(body.layout.hull_length) * 0.6) / max(0.01, cam.cell_m))
    _ray(buf, x0, y0, W, H, cam, mine.x_m, mine.y_m, bearing, rng * 0.92, "+", CONTACT_FG, near)
    her_head = world.try_component(ent, c.Heading)
    note = f"{relative_short(rel)} {range_short(rng)}"
    if her_head is not None:
        note += f" {aspect_short(her_head.degrees, bearing)}"
    col, row = cam.to_screen(hers.x_m, hers.y_m, W, H)
    # Written beside her if it fits, and on her other side if it does not.
    start = int(col) + 2
    if start + len(note) > W:
        start = int(col) - 1 - len(note)
    _label(buf, x0, y0, W, H, max(0, start), int(row) + 1, note, CONTACT_FG)


SHOT_FG = (250, 226, 150)
SHOT_FALL = (255, 170, 90)


def _draw_shot(buf: ScreenBuffer, x0: int, y0: int, W: int, H: int, cam, shot) -> None:
    """The gun captain's estimate of where this shot would go: its track
    over the water, the splash at the end of it, and how far out he may be.
    Drawn before you give the word, so laying a gun is a decision rather
    than a dice roll you watch afterwards."""
    for (px, py, pz) in shot.points[1:]:
        col, row = cam.to_screen(px, py, W, H)
        col, row = int(col), int(row)
        if not (0 <= col < W and 0 <= row < H):
            continue
        cell = buf.get(x0 + col, y0 + row)
        if cell.glyph not in SECTOR_SKIP:
            continue
        buf.set(x0 + col, y0 + row, "·" if pz > 1.0 else "-", fg=SHOT_FG, bg=cell.bg)
    fall = shot.points[-1]
    col, row = cam.to_screen(fall[0], fall[1], W, H)
    _put(buf, x0, y0, W, H, int(col), int(row), "×", SHOT_FALL)
    note = f"{shot.graze_m:.0f} m ±{shot.spread_m:.0f}"
    if shot.verdict:
        note += f" - {shot.verdict}"
    if shot.wants_deg is not None:
        note += f"; he wants {shot.wants_deg:+.1f} deg on the quoin"
    start = int(col) + 2
    if start + len(note) > W:
        start = int(col) - 1 - len(note)
    _label(buf, x0, y0, W, H, max(0, start), int(row), note, SHOT_FALL)


# --- The sea's surface -----------------------------------------------------
#
# A sum of travelling waves rather than a noise field thresholded into
# blotches: two swells running with the wind at the speed deep-water waves
# of their length actually run (c = sqrt(gL/2pi)), plus a slow noise
# modulation so the crests are not a corduroy of identical lines. Because
# the phase moves smoothly with time, a crest *marches* across the view
# instead of each cell popping on and off, which is what made the sea look
# jumpy. Wavelength scales with the zoom, so the deck view shows wind waves
# and the chart shows long swell.


def sea_surface(xs, ys, t: float, cell_m: float, wind) -> np.ndarray:
    """0..1 wave height at these points: 1 is a breaking crest."""
    length = max(7.0, cell_m * 11.0)
    speed = 1.25 * math.sqrt(length)  # deep-water phase speed, m/s
    # Waves run with the wind, the second train a little off it.
    to_x, to_y = wind_vector_ms(wind.direction_degrees, 1.0)
    steep = min(1.0, 0.25 + wind.speed_knots / 28.0)
    total = np.zeros(np.shape(xs))
    for i, (frac, skew, amp) in enumerate(((1.0, 0.0, 0.62), (0.57, 0.5, 0.38))):
        ax = to_x + skew * -to_y
        ay = to_y + skew * to_x
        norm = math.hypot(ax, ay) or 1.0
        ax, ay = ax / norm, ay / norm
        lam = length * frac
        k = 2.0 * math.pi / lam
        phase = (np.asarray(xs) * ax + np.asarray(ys) * ay) * k - (speed / math.sqrt(max(frac, 0.01))) * k * t
        total = total + amp * np.sin(phase)
    # Where the sea is making up and where it is smooth, drifting slowly.
    patch = value_noise(np.asarray(xs) - to_x * t * 2.0, np.asarray(ys) - to_y * t * 2.0, max(40.0, cell_m * 90.0), 23)
    return np.clip(0.5 + 0.5 * total * steep * (0.55 + 0.75 * patch), 0.0, 1.0)
