# Looking out: what the captain sees when he raises his eyes (or a glass).
#
# Not a plan view - a picture. For each column of the pane a ray is cast at
# that bearing and marched outward; every time the ray clears the top of
# something further off than anything it has passed yet, the band of rows
# between the old horizon and the new one is filled with whatever that thing
# is made of. March near to far and the picture builds from the bottom of
# the screen upward: your own rail, the sea, a hull, a wall's face, a
# hillside, a tree line, then sky.
#
# That is all a heightfield raycast, which is why it is cheap and why it
# needs no new data: the scene already knows how tall everything is
# (sim/spatial.py), and voxel walls already know their own blocks. The
# result is deliberately coarse - the point is to tell canvas from stone
# from hillside, and to see the *face* of a thing rather than its plan.
#
# With the glass the field narrows to a few degrees and distant things grow
# accordingly, which is how a telescope actually trades width for detail.
# See docs/design/16_observation_and_targeting.md sec. 2.

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from broadside.render.buffer import Cell, ScreenBuffer
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.vision import EARTH_RADIUS_EFF_M
from broadside.sim.world import terrain as tr
from broadside.view import style as S

NAKED_FOV_DEG = 70.0
GLASS_FOV_DEG = 7.0
CELL_ASPECT = 2.0  # a terminal cell is about twice as tall as it is wide
MAX_RANGE_M = 9000.0
NEAR_M = 1.2
STEP_GROWTH = 0.14  # the ray samples coarser the further out it gets
MIN_STEP_M = 0.5
MIN_VFOV_DEG = 9.0

SKY_TOP = (36, 58, 104)
SKY_HORIZON = (150, 178, 206)
SEA_NEAR = (26, 62, 104)
SEA_FAR = (62, 104, 140)

# material -> (glyph, fg, bg)
MATERIALS = {
    "sea": ("~", (118, 168, 205), (24, 58, 98)),
    "surf": ("≈", (226, 240, 246), (72, 124, 150)),
    "sand": ("░", (218, 200, 146), (134, 118, 78)),
    "rock": ("▓", (158, 156, 160), (72, 72, 80)),
    "grass": ("▒", (138, 164, 92), (54, 68, 34)),
    "forest": ("♣", (78, 142, 76), (28, 54, 28)),
    "snow": ("█", (236, 238, 240), (150, 156, 164)),
    "masonry": ("▓", (182, 176, 162), (96, 92, 84)),
    "rubble": ("▒", (196, 174, 128), (98, 84, 58)),
    "hull": ("█", (146, 104, 60), (74, 50, 30)),
    "deck": ("═", (164, 132, 88), (62, 46, 28)),
    "gun": ("▄", (170, 172, 184), (54, 54, 60)),
    "mast": ("│", (214, 172, 110), (48, 38, 24)),
    "canvas": ("░", (238, 234, 222), (142, 138, 128)),
    "man": ("§", (236, 214, 176), (40, 34, 28)),
}


@dataclass
class Look:
    bearing_deg: float
    fov_deg: float
    glass: bool = False
    label: str = ""
    # Where you are looking *relative to her head*, which is how a man
    # standing on her deck holds a glass: he faces three points off the
    # starboard bow, and if she comes round, so does he. Holding an
    # absolute compass bearing instead meant the view swung away from
    # whatever you were watching every time the helm moved.
    relative_deg: float = 0.0
    # Up and down, in degrees above the horizontal: the glass tilts.
    pitch_deg: float = 0.0
    # The ship being watched, if any: the glass follows her as she moves
    # and as we turn, which is what a man with a target does.
    target: int = -1
    # A ballistics.ShotPrediction to lay over the view: the arc the gun
    # captain reckons the shot will take, seen from where he stands.
    shot: object = None
    # Draw the centre mark - a reticle to lay the glass by.
    mark: bool = True
    # The last drawing of this view, so a look need not be recast every
    # frame (nothing in it moves far in a third of a second).
    _cache: object = None
    _key: object = None
    _at_s: float = -1e9

    @property
    def what(self) -> str:
        return "the glass" if self.glass else "the naked eye"


def draw_look_cached(buf, x0, y0, width, height, state, eye, look: "Look", refresh_s: float = 0.3) -> str:
    key = (width, height, round(look.bearing_deg, 1), round(look.fov_deg, 2), round(look.pitch_deg, 1),
           round(eye.x, 1), round(eye.y, 1), round(eye.h, 2), look.target, look.mark,
           None if look.shot is None else round(look.shot.graze_m, 1))
    if look._cache is None or look._key != key or state.now_s - look._at_s > refresh_s:
        pane = ScreenBuffer(width, height)
        label = draw_look(pane, 0, 0, width, height, state, eye, look)
        look._cache = (pane, label)
        look._key = key
        look._at_s = state.now_s
    pane, label = look._cache
    buf.blit(pane, x0, y0)
    return label


def _sky(row: int, horizon_row: int, height: int, light: float):
    """A plain graded sky, darker overhead, with the light of the day."""
    if horizon_row <= 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, row / max(1, horizon_row)))
    col = S.blend(SKY_TOP, SKY_HORIZON, t)
    return S.blend((6, 7, 10), col, max(0.08, light))


MATERIAL_ORDER = ("sea", "surf", "sand", "rock", "grass", "forest", "snow", "masonry", "rubble", "hull", "deck", "gun", "mast", "canvas", "man")
_MAT_INDEX = {name: i for i, name in enumerate(MATERIAL_ORDER)}
_TERRAIN_MAT = {
    tr.SEA: "sea",
    tr.SHOAL: "sea",
    tr.REEF: "surf",
    tr.BEACH: "sand",
    tr.LAND: "grass",
    tr.FOREST: "forest",
    tr.HILL: "rock",
    tr.ROCK: "rock",
    tr.PEAK: "snow",
}
_TERRAIN_LUT = np.array([_MAT_INDEX[_TERRAIN_MAT.get(code, "sea")] for code in range(max(_TERRAIN_MAT) + 1)], dtype=np.int16)


def _materials(content) -> np.ndarray:
    """One pass over a step's samples: which material each column just met."""
    codes = content.terrain.code.ravel()
    mats = _TERRAIN_LUT[np.minimum(codes, len(_TERRAIN_LUT) - 1)]
    ship = content.ship.ravel()
    tile = content.tile.ravel()
    on_ship = ship >= 0
    if on_ship.any():
        hull = np.full(ship.shape, _MAT_INDEX["hull"], dtype=np.int16)
        hull = np.where(tile == sl.MAST, _MAT_INDEX["mast"], hull)
        hull = np.where(tile == sl.GUN, _MAT_INDEX["gun"], hull)
        hull = np.where((tile == sl.DECK) | (tile == sl.HATCH), _MAT_INDEX["deck"], hull)
        mats = np.where(on_ship, hull, mats)
    sail = content.sail.ravel()
    mats = np.where(sail >= 0, _MAT_INDEX["canvas"], mats)
    if content.bldg is not None:
        b = content.bldg.ravel()
        dmg = content.bldg_damage.ravel()
        mats = np.where(b >= 0, np.where(dmg > 0.5, _MAT_INDEX["rubble"], _MAT_INDEX["masonry"]), mats)
    return mats


def _march(scene, eye, look: Look, far: float, own: int = -1) -> list:
    """The distances to sample along the rays.

    Terrain varies smoothly, so it is walked in geometrically growing steps.
    Ships and walls do not: a brig is ten metres thick, and a forty-metre
    step at two miles would stride straight through her. So every ship and
    structure whose bearing falls in the field gets its own span sampled a
    metre at a time."""
    ds = []
    d = NEAR_M
    while d < far:
        ds.append(d)
        d += max(MIN_STEP_M, d * STEP_GROWTH)
    half = look.fov_deg / 2.0 + 3.0
    near_first = []
    for ox, oy, radius in _objects(scene, own):
        dx, dy = ox - eye.x, oy - eye.y
        dist = math.hypot(dx, dy)
        if dist > far or dist < 1.0:
            continue
        brg = math.degrees(math.atan2(dx, dy)) % 360.0
        off = ((brg - look.bearing_deg + 180.0) % 360.0) - 180.0
        span = math.degrees(math.atan2(radius, dist)) + half
        if abs(off) > span or math.degrees(math.atan2(radius, dist)) < 0.08:
            continue  # out of the field, or too small to make a mark
        near_first.append((dist, radius))
    near_first.sort()
    for dist, radius in near_first[:4]:  # the nearest few are what you see
        step = max(1.0, dist / 300.0)
        x = max(NEAR_M, dist - radius - 2.0)
        while x <= dist + radius + 2.0:
            ds.append(x)
            x += step
    ds.sort()
    return ds


def _objects(scene, own: int = -1) -> list:
    """(x, y, radius) of everything that is not smooth terrain. Your own
    ship is not in it: she is left out of the glass (see draw_look)."""
    out = [(g.x, g.y, g.radius) for g in scene.geoms if g.entity != own]
    for b in scene.buildings:
        out.append((b.x, b.y, b.radius))
    return out


def draw_look(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, eye, look: Look) -> str:
    """Draw the view out along `look.bearing_deg`. Returns a caption.

    The whole fan - every column at every distance - is sampled in one go
    and swept with numpy: one scene query instead of one per step, which is
    the difference between a tenth of a second and a twentieth.

    Your own ship is left out of the picture. A captain with a glass moves
    his head, steps to the rail, or sends a midshipman to the crosstrees;
    what he does not do is spend five minutes looking at his own bulwark.
    Everything else - fog, smoke, islands, other ships - obstructs as ever.
    """
    scene = state.scene()
    fov = math.radians(look.fov_deg)
    # The pane's own proportions set the vertical field, with a floor: a
    # strong glass on a ship close aboard would otherwise be a letterbox
    # with her waterline in it and her masts off the top.
    vfov = max(math.radians(MIN_VFOV_DEG), fov * (height / max(1, width)) * CELL_ASPECT)
    half = fov / 2.0
    # Tilting the glass moves the top of the field, not the world.
    top_pitch = math.radians(look.pitch_deg)
    az = np.radians(look.bearing_deg) - half + fov * (np.arange(width) + 0.5) / width
    sin_az, cos_az = np.sin(az), np.cos(az)
    top_angle = vfov / 2.0 + top_pitch
    scale = height / vfov
    haze = state.atmosphere.haze_sigma
    light = state.atmosphere.light
    horizon_m = math.sqrt(max(1.0, 2.0 * EARTH_RADIUS_EFF_M * max(1.0, eye.h)))
    far = min(MAX_RANGE_M, max(400.0, min(state.atmosphere.effective_visibility_m() * 1.2, horizon_m + 2500.0)))

    ds = np.array(_march(scene, eye, look, far, state.player_ship), dtype=np.float64)
    if ds.size == 0:
        ds = np.array([NEAR_M])
    px = eye.x + sin_az[None, :] * ds[:, None]
    py = eye.y + cos_az[None, :] * ds[:, None]
    content = scene.sample(px, py, include_ships=True, with_air=False, exclude_ship=state.player_ship)
    tops = np.maximum(content.fields.solid_top, content.tall_h)
    over = content.fields.over_top
    tops = np.where(np.isfinite(over), np.maximum(tops, over), tops)
    drop = (ds * ds / (2.0 * EARTH_RADIUS_EFF_M))[:, None]
    angles = np.arctan2(tops - drop - eye.h, ds[:, None])
    # Sweeping outward, a thing is only seen if it stands higher than
    # everything nearer: the running maximum is the horizon so far.
    horizon = np.maximum.accumulate(angles, axis=0)
    rows = np.clip(np.rint((top_angle - horizon) * scale), 0, height).astype(np.int32)
    mats = _materials(content).reshape(rows.shape)
    buckets = np.rint(np.clip(1.0 - np.exp(-haze * ds), 0.0, 1.0) * 8.0).astype(np.int32)

    cache: dict = {}

    def cell_for(mat: int, bucket: int) -> Cell:
        key = (mat, bucket)
        got = cache.get(key)
        if got is None:
            glyph, fg, bg = MATERIALS[MATERIAL_ORDER[mat]]
            if MATERIAL_ORDER[mat] == "sea":
                glyph = ("~", " ", "\u00b7")[bucket % 3]
            shade = bucket / 8.0
            fgc = S.blend(fg, S.HAZE, shade * 0.9)
            bgc = S.blend(bg, S.FOG_BG, shade * 0.75)
            if light < 0.75:
                k = (0.75 - light) / 0.75
                fgc = S.blend(fgc, (12, 14, 22), 0.7 * k)
                bgc = S.blend(bgc, (6, 7, 12), 0.7 * k)
            got = Cell(glyph, fgc, bgc)
            cache[key] = got
        return got

    rows_l = rows.tolist()
    mats_l = mats.tolist()
    bucket_l = buckets.tolist()
    cells: list = [[None] * width for _ in range(height)]
    steps = len(rows_l)
    for col in range(width):
        prev = height
        for s_i in range(steps):
            r = rows_l[s_i][col]
            if r < prev:
                cell = cell_for(mats_l[s_i][col], bucket_l[s_i])
                for rr in range(r, prev):
                    cells[rr][col] = cell
                prev = r
                if prev == 0:
                    break

    sky_row = height
    for col in range(width):
        for r in range(height):
            if cells[r][col] is not None:
                sky_row = min(sky_row, r)
                break
    for r in range(height):
        yy = y0 + r
        if not (0 <= yy < buf.height):
            continue
        row_cells = buf.row(yy)
        sky = _sky(r, sky_row, height, light)
        blank = Cell(" ", sky, sky)
        for col in range(min(width, buf.width - x0)):
            cell = cells[r][col]
            row_cells[x0 + col] = blank if cell is None else cell

    # The horizontal, where the eye is level: the line a gun is laid along.
    level_row = int(round(top_angle * scale))
    if look.shot is not None:
        _draw_shot_arc(buf, x0, y0, width, height, state, eye, look, scale, top_angle)
    if look.mark:
        _draw_mark(buf, x0, y0, width, height, state, eye, look, level_row)
    _draw_scale(buf, x0, y0 + height - 1, width, look)
    return look.label


MARK_FG = (250, 232, 170)
ARC_FG = (252, 214, 130)


def _draw_mark(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, eye, look: Look, level_row: int) -> None:
    """A reticle: the centre of the field, on the horizontal, with what it
    is laid on written beside it. Without a mark a glass is a picture; with
    one it is an instrument you can lay a gun by."""
    from broadside.view.orientation import aspect_short, range_short, relative_short

    col = width // 2
    row = max(0, min(height - 2, level_row))

    def mark(c, r, glyph):
        if 0 <= c < width and 0 <= r < height and 0 <= y0 + r < buf.height:
            cell = buf.get(x0 + c, y0 + r)
            buf.set(x0 + c, y0 + r, glyph, fg=MARK_FG, bg=cell.bg)

    for d in (3, 4, 5):
        mark(col - d, row, "─")
        mark(col + d, row, "─")
    for d in (2, 3):
        mark(col, row - d, "│")
        mark(col, row + d, "│")
    mark(col, row, "+")
    note = relative_short(look.relative_deg)
    if look.target >= 0:
        world = state.world
        her = world.try_component(look.target, c.WorldPosition)
        her_name = world.try_component(look.target, c.Name)
        her_head = world.try_component(look.target, c.Heading)
        if her is not None:
            rng = math.hypot(her.x_m - eye.x, her.y_m - eye.y)
            note = f"{her_name.full if her_name is not None else 'her'}  {range_short(rng)}"
            if her_head is not None:
                bearing = math.degrees(math.atan2(her.x_m - eye.x, her.y_m - eye.y)) % 360.0
                note += f"  {aspect_short(her_head.degrees, bearing)}"
    text = f" {note} "
    start = max(0, min(width - len(text), col - len(text) // 2))
    tr = row + 5
    if 0 <= tr < height and 0 <= y0 + tr < buf.height:
        for i, ch in enumerate(text):
            if start + i < width:
                cell = buf.get(x0 + start + i, y0 + tr)
                buf.set(x0 + start + i, y0 + tr, ch, fg=MARK_FG, bg=cell.bg)


def _draw_shot_arc(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, eye, look: Look, scale: float, top_angle: float) -> None:
    """The shot's own flight, drawn where it would be seen from here: the
    arc rises out of the muzzle, flattens, and comes down at the splash."""
    shot = look.shot
    half = math.radians(look.fov_deg) / 2.0
    centre = math.radians(look.bearing_deg)
    last = None
    for (px, py, pz) in shot.points[1:]:
        dx, dy = px - eye.x, py - eye.y
        d = math.hypot(dx, dy)
        if d < 2.0:
            continue
        off = (math.atan2(dx, dy) - centre + math.pi) % (2.0 * math.pi) - math.pi
        if abs(off) > half:
            continue
        col = int(round(width * (off + half) / (2.0 * half)))
        drop = d * d / (2.0 * EARTH_RADIUS_EFF_M)
        el = math.atan2(pz - drop - eye.h, d)
        row = int(round((top_angle - el) * scale))
        if not (0 <= col < width and 0 <= row < height and 0 <= y0 + row < buf.height):
            continue
        cell = buf.get(x0 + col, y0 + row)
        buf.set(x0 + col, y0 + row, "·", fg=ARC_FG, bg=cell.bg)
        last = (col, row)
    if last is not None:
        cell = buf.get(x0 + last[0], y0 + last[1])
        buf.set(x0 + last[0], y0 + last[1], "×", fg=(255, 170, 90), bg=cell.bg)


def _draw_scale(buf: ScreenBuffer, x0: int, y: int, width: int, look: Look) -> None:
    from broadside.sim.sailplan import compass_32

    if not (0 <= y < buf.height):
        return
    for col in range(min(width, buf.width - x0)):
        buf.set(x0 + col, y, "─", fg=(90, 92, 104), bg=(14, 16, 22))
    for frac in (0.08, 0.5, 0.92):
        b = (look.bearing_deg - look.fov_deg / 2.0 + look.fov_deg * frac) % 360.0
        text = f" {compass_32(b)} {b:03.0f} "
        col = int(frac * width) - len(text) // 2
        if 0 <= col and col + len(text) <= width:
            buf.draw_text(x0 + col, y, text, fg=(214, 206, 180), bg=(14, 16, 22))


def ships_in_view(state, eye, look: Look, world) -> list:
    """Which ships lie within this field of view, nearest first - what a
    look through the glass tells you about, as opposed to what it draws."""
    from broadside.sim.units import bearing_degrees

    out = []
    for ent, (pos, _body) in world.get_components(c.WorldPosition, c.ShipBody):
        dx, dy = pos.x_m - eye.x, pos.y_m - eye.y
        d = math.hypot(dx, dy)
        if d < 5.0:
            continue
        off = ((bearing_degrees(dx, dy) - look.bearing_deg + 180.0) % 360.0) - 180.0
        if abs(off) <= look.fov_deg / 2.0:
            out.append((d, ent, off))
    out.sort()
    return out
