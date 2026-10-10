# Elevation view: a voxel structure seen face-on, as the gunner sees it.
#
# The top-down scene can only show how tall each column of a wall still
# is; the damage that matters - a hole knocked through low down, a crater
# in the face, the courses above sagging and falling - is on the face. This
# draws the structure's face from the side nearest the observer: each
# 0.5 m block is two columns by one row. Front blocks are drawn by their
# condition; where the front block is gone but something deeper remains,
# a darker recessed block shows the crater; where the whole thickness is
# gone you see sky through the breach. Rubble is sandy, dust hangs over
# the face, and recent impacts flash.

from __future__ import annotations

import math

import numpy as np

from broadside.render.buffer import ScreenBuffer
from broadside.sim import components as c
from broadside.sim.voxels import VoxelStructure
from broadside.view import style as S

SKY = (46, 60, 88)
GROUND = (116, 102, 68)
STONE = (168, 162, 150)
STONE_BG = (92, 88, 80)
RUBBLE = (190, 168, 120)
DUST = (196, 176, 136)


def nearest_structure(state):
    """(entity, VoxelStructure, pose) of the structure nearest the player."""
    world = state.world
    me = world.component_for_entity(state.player_ship, c.WorldPosition)
    best = None
    for ent, (vs, pos, hd) in world.get_components(VoxelStructure, c.WorldPosition, c.Heading):
        d = math.hypot(pos.x_m - me.x_m, pos.y_m - me.y_m)
        if best is None or d < best[0]:
            best = (d, ent, vs, (pos.x_m, pos.y_m, hd.degrees))
    return None if best is None else best[1:]


def draw_elevation(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state) -> str:
    found = nearest_structure(state)
    for yy in range(height):
        for xx in range(width):
            buf.set(x0 + xx, y0 + yy, " ", fg=SKY, bg=SKY)
    if found is None:
        buf.draw_text(x0 + 1, y0 + 1, "No structure nearby.", fg=(220, 220, 220), bg=SKY)
        return ""
    ent, vs, (sx, sy, head) = found
    nz, ny, nx = vs.shape
    world = state.world
    me = world.component_for_entity(state.player_ship, c.WorldPosition)
    # Which face do we see? The one toward the observer, along local v.
    fx, fy = math.sin(math.radians(head)), math.cos(math.radians(head))
    rx, ry = fy, -fx
    v_obs = (me.x_m - sx) * rx + (me.y_m - sy) * ry
    order = range(ny) if v_obs < 0 else range(ny - 1, -1, -1)
    mirror = v_obs > 0  # looking from +v, local +u runs to our left
    cols = min(nx, width // 2)
    xoff = (nx - cols) // 2
    ground_row = height - 3
    rows = min(nz, ground_row)
    for gz in range(rows):
        sy_ = ground_row - 1 - gz
        for i in range(cols):
            ix = xoff + (cols - 1 - i if mirror else i)
            depth = 0
            hit = None
            for iy in order:
                if vs.material[gz, iy, ix] >= 0:
                    hit = iy
                    break
                depth += 1
            if hit is None:
                g, fg, bg = " ", SKY, SKY
            else:
                integ = float(vs.integrity[gz, hit, ix])
                if vs.loose[gz, hit, ix]:
                    g, fg, bg = "▒", RUBBLE, S.blend(STONE_BG, (60, 50, 35), 0.4)
                else:
                    g = "█" if integ > 0.8 else ("▓" if integ > 0.5 else ("▒" if integ > 0.25 else "░"))
                    fg, bg = STONE, STONE_BG
                # Recessed (front blocks gone): darker the deeper it is.
                shade = min(0.75, depth * 0.18)
                fg, bg = S.blend(fg, (20, 20, 22), shade), S.blend(bg, (15, 15, 18), shade)
            for k in range(2):
                buf.set(x0 + 2 * i + k, y0 + sy_, g, fg=fg, bg=bg)
    for yy in range(ground_row, height):
        for xx in range(width):
            buf.set(x0 + xx, y0 + yy, "░", fg=S.blend(GROUND, (0, 0, 0), 0.2), bg=S.blend(GROUND, (0, 0, 0), 0.5))
    # Dust and smoke hanging over the face.
    us = (np.arange(cols) + xoff + 0.5 - nx / 2.0) * vs.voxel_m
    wx = sx + us * fx
    wy = sy + us * fy
    dust, _ = state.atmosphere.smoke_at(wx, wy, kind="dust")
    smoke, _ = state.atmosphere.smoke_at(wx, wy, kind="smoke")
    for i in range(cols):
        ci = cols - 1 - i if mirror else i
        d = float(dust[ci])
        sm = float(smoke[ci])
        if d + sm < 0.01:
            continue
        colr = S.blend(DUST, S.SMOKE, sm / (d + sm))
        h = int(min(rows, 2 + 20 * (d + sm)))
        for gz in range(h):
            yy = y0 + ground_row - 1 - gz
            for k in range(2):
                cell = buf.get(x0 + 2 * i + k, yy)
                a = min(0.8, (d + sm) * 2.5 * (1 - gz / max(h, 1)))
                buf.set(x0 + 2 * i + k, yy, "░" if cell.glyph == " " else cell.glyph, fg=S.blend(cell.fg, colr, a), bg=S.blend(cell.bg, colr, a))
    # Recent impacts flash.
    for t, ix, iy, iz in vs.impacts:
        if state.now_s - t > 0.6:
            continue
        i = ix - xoff
        if mirror:
            i = cols - 1 - i
        if 0 <= i < cols and 0 <= iz < rows:
            for k in range(2):
                buf.set(x0 + 2 * i + k, y0 + ground_row - 1 - iz, "*", fg=S.FLASH_FG, bg=S.FLASH_BG)
    total = int((vs.material >= 0).sum())
    info = f" {vs.name}: {total} blocks standing or fallen, {vs.destroyed} smashed, {vs.fallen} fell "
    buf.draw_text(x0, y0 + height - 1, info[:width].ljust(width), fg=(230, 230, 230), bg=(20, 22, 30))
    return vs.name
