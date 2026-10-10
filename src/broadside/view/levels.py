# The z axis: the world cut into horizontal levels you scroll through.
#
# Dwarf Fortress shows one level at a time and dims what lies below it. The
# same idea here, except the levels are metres above the waterline, and
# every kind of thing in the world knows how tall it is already:
#
#   the sea        level 0 is her surface; below it the water column, and
#                  the bottom coming up as you go down
#   land and hills a heightfield: rock below you, the ground where you
#                  stand, open air above
#   trees          a trunk at ground level and a canopy two to six metres up
#   ships          the hull from her draught to her rail, the weather deck
#                  at freeboard, then the sails as bands, then bare masts
#   fortifications voxel walls, which are already true 3D - the slice is
#                  read straight out of their blocks
#
# A cell that is open air at this level shows whatever is below it, dimmed
# by how far down it is, so you can read a hillside or a deck plan from
# above. This is the view the below-decks work will hang on: when the hold
# and the gundecks exist, they are just more levels.
#
# See docs/design/16_observation_and_targeting.md sec. 7 for the rule about
# when the player may scroll freely (time stopped) and when he must walk.

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from broadside.render.buffer import Cell, ScreenBuffer
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.view import style as S
from broadside.view.camera import Camera
from broadside.sim.world import terrain as tr

LEVEL_STEP_M = 1.0
MIN_LEVEL_M = -30.0
MAX_LEVEL_M = 60.0
# How much a level is dimmed per metre it lies below the one you are on.
FADE_PER_M = 0.13
MAX_FADE = 0.82
WATER_TINT = (30, 74, 120)
HOLD_FG = (96, 74, 48)
HOLD_BG = (30, 22, 14)
TRUNK_FG = (104, 80, 48)
CANOPY_FG = (74, 148, 72)
ROCK_FG = (150, 148, 152)
ROCK_BG = (44, 44, 50)
SKY_BG = (10, 12, 18)


@dataclass
class LevelInfo:
    camera: Camera
    z_m: float
    label: str


def clamp_level(z: float) -> float:
    return max(MIN_LEVEL_M, min(MAX_LEVEL_M, round(z / LEVEL_STEP_M) * LEVEL_STEP_M))


def _draught(g) -> float:
    """How deep she sits. Not modelled per class yet, so taken from her
    freeboard and length, which is close enough to read a hull by."""
    return 0.6 * g.freeboard + 0.02 * g.layout.hull_length


def _fade(colour, amount: float):
    return S.blend(colour, SKY_BG, min(MAX_FADE, max(0.0, amount)))


def draw_levels(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, view) -> LevelInfo:
    """Draw one horizontal slice of the world. Returns what was drawn."""
    z = clamp_level(view.z_m if view.z_m is not None else 0.0)
    cam = view.camera(state)
    scene = state.scene()
    xs, ys = cam.grid(width, height)
    content = scene.sample(xs, ys, include_ships=True)
    ter = content.terrain
    ground = ter.height.ravel()
    canopy = ter.canopy.ravel()
    codes = ter.code.ravel()
    ship_i = content.ship.ravel().tolist()
    tiles = content.tile.ravel().tolist()
    sails = content.sail.ravel().tolist()
    tall = content.tall_h.ravel()
    fu_l = content.fu.ravel().tolist()
    fv_l = content.fv.ravel().tolist()
    gx_l = content.gx.ravel().tolist()
    gy_l = content.gy.ravel().tolist()
    ground_l = ground.tolist()
    bed_l = ter.seabed.ravel().tolist()
    canopy_l = canopy.tolist()
    code_l = codes.tolist()
    tall_l = tall.tolist()
    xs_l = xs.ravel().tolist()
    ys_l = ys.ravel().tolist()
    geoms = scene.geoms
    buildings = scene.buildings
    top_band = z + LEVEL_STEP_M

    # Voxel structures: read the slice straight out of their blocks.
    bldg_slice = []
    for b in buildings:
        vs = b.vs
        iz = int(math.floor((z - vs.base_z_m) / vs.voxel_m))
        nz = vs.shape[0]
        layer = vs.material[iz] if 0 <= iz < nz else None
        loose = vs.loose[iz] if 0 <= iz < nz else None
        bldg_slice.append((b, layer, loose))

    men = {}
    for px, py, b0, b1, ent in scene.people:
        if b0 - 0.9 <= z <= b1:
            men[(int(round(px)), int(round(py)))] = ent

    cols = max(0, min(width, buf.width - x0))
    k = 0
    for row in range(height):
        yy = y0 + row
        if not (0 <= yy < buf.height):
            k += width
            continue
        cells = buf.row(yy)
        for col in range(cols):
            kk = k + col
            gh = ground_l[kk]
            code = code_l[kk]
            glyph, fg, bg = " ", (60, 60, 70), SKY_BG
            done = False

            # --- a wall's own blocks ---------------------------------
            for b, layer, loose in bldg_slice:
                if layer is None:
                    continue
                fx, fy = math.sin(math.radians(b.heading)), math.cos(math.radians(b.heading))
                dx, dy = xs_l[kk] - b.x, ys_l[kk] - b.y
                u, v = dx * fx + dy * fy, dx * fy - dy * fx
                vs = b.vs
                nzz, ny, nx = vs.shape
                ix = int(math.floor(u / vs.voxel_m + nx / 2.0))
                iy = int(math.floor(v / vs.voxel_m + ny / 2.0))
                if 0 <= ix < nx and 0 <= iy < ny and layer[iy, ix] >= 0:
                    rubble = bool(loose[iy, ix])
                    glyph = "▒" if rubble else "█"
                    fg = S.RUBBLE_FG if rubble else S.WALL_FG
                    bg = S.RUBBLE_BG if rubble else S.WALL_BG
                    done = True
                    break
            if done:
                cells[x0 + col] = Cell(glyph, fg, bg)
                continue

            # --- a ship ------------------------------------------------
            si = ship_i[kk]
            if si >= 0:
                g = geoms[si]
                tile = tiles[kk]
                deck_z = g.freeboard
                fit = sl.FITTING_TOP_M.get(tile, 0.0)
                mast_top = 0.0
                if tile == sl.MAST:
                    for m in g.layout.masts:
                        if (m.x, m.y) == (gx_l[kk], gy_l[kk]):
                            mast_top = deck_z + m.height_above_deck
                if tile == sl.MAST and z >= deck_z and z < mast_top:
                    d = ((fu_l[kk] - 0.5) ** 2 + (fv_l[kk] - 0.5) ** 2) ** 0.5
                    if d < 0.3:
                        cells[x0 + col] = Cell("█", (214, 172, 110), S.SHIP_BG)
                        continue
                elif deck_z - LEVEL_STEP_M < z <= deck_z + max(0.2, fit):
                    # Her weather deck, drawn as the plan.
                    dglyph, dfg, dbg = S.SHIP_TILE_STYLE.get(tile, ("?", (255, 0, 255), S.SHIP_BG))
                    man = men.get((int(round(xs_l[kk])), int(round(ys_l[kk]))))
                    if man is not None:
                        role = state.world.try_component(man, c.Role)
                        title = role.title if role is not None else ""
                        dglyph = S.crew_glyph(title)
                        dfg = S.CAPTAIN_FG if title == "Captain" else (226, 206, 176)
                    cells[x0 + col] = Cell(dglyph, dfg, dbg or S.SHIP_BG)
                    continue
                elif -_draught(g) <= z <= deck_z:
                    # Her hull: the side timbers, and the hold inside them.
                    edge = tile == sl.HULL
                    cells[x0 + col] = Cell("█" if edge else ":", (146, 104, 60) if edge else HOLD_FG, (70, 48, 28) if edge else HOLD_BG)
                    continue
            if sails[kk] >= 0 and z >= 0:
                g = geoms[sails[kk]]
                for sg in g.sails:
                    if sg.bottom_m <= z < sg.top_m:
                        cells[x0 + col] = Cell(S.SAIL_GLYPH, S.SAIL_FG, S.SHIP_BG)
                        done = True
                        break
                if done:
                    continue

            # --- trees ---------------------------------------------------
            if canopy_l[kk] > 0.5 and gh > 0:
                if gh <= z < gh + 1.0:
                    cells[x0 + col] = Cell("│", TRUNK_FG, (24, 34, 20))
                    continue
                if gh + 1.0 <= z < gh + canopy_l[kk]:
                    cells[x0 + col] = Cell("♣", CANOPY_FG, (20, 40, 22))
                    continue

            # --- rock, ground, seabed, water, air ------------------------
            floor = bed_l[kk]
            gl, gfg, gbg = S.TERRAIN_STYLE[code]
            if floor >= top_band:
                # Solid below or around us: looking into a hill, or into the
                # bank of a shoal.
                cells[x0 + col] = Cell("█", ROCK_FG, ROCK_BG)
                continue
            if z <= floor < top_band:
                # The floor at this level - the ground you would stand on,
                # or the bottom of the sea.
                if floor < 0.0:
                    cells[x0 + col] = Cell("▒", S.blend(gfg, WATER_TINT, 0.45), S.blend((120, 104, 72), WATER_TINT, 0.6))
                else:
                    cells[x0 + col] = Cell(gl, gfg, gbg)
                continue
            if z < 0.0:
                # In the water column: dimmer the deeper you go.
                shade = min(MAX_FADE, (-z) * 0.05)
                # A few specks of suspended matter, not a wall of texture:
                # the point of a level below the waterline is the hull in it.
                ripple = "·" if int(abs(xs_l[kk]) * 0.5 + abs(ys_l[kk]) * 0.5) % 7 == 0 else " "
                cells[x0 + col] = Cell(ripple, _fade((120, 170, 200), shade), _fade(WATER_TINT, shade))
                continue
            # Above the surface: look down at whatever is below, faded.
            surface = max(floor, 0.0)
            fade = min(MAX_FADE, max(0.0, z - surface) * FADE_PER_M)
            if surface <= 0.0:
                sglyph, sfg, sbg = S.TERRAIN_STYLE[code if code in (tr.SEA, tr.SHOAL, tr.REEF) else tr.SEA]
                cells[x0 + col] = Cell(sglyph, _fade(sfg, fade), _fade(sbg, fade))
                continue
            if canopy_l[kk] > 0.5 and z < tall_l[kk]:
                gl = "♣"
            cells[x0 + col] = Cell(gl, _fade(gfg, fade), _fade(gbg, fade))
        k += width

    label = level_label(z)
    return LevelInfo(camera=cam, z_m=z, label=label)


def level_label(z: float) -> str:
    if abs(z) < 1e-6:
        return "the waterline"
    if z < 0:
        return f"{abs(z):.0f} m below the waterline"
    return f"{z:.0f} m above the waterline"


def deck_level_of(state, ship: int) -> float:
    body = state.world.try_component(ship, c.ShipBody)
    return clamp_level(body.layout.freeboard_m if body is not None else 0.0)
