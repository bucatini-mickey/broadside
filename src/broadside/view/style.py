# Glyphs and colours for the scene view, and the colour maths for the
# three states every cell can be in: seen now, remembered, never seen.
#
# Kept apart from render/palette.py (the Phase 0 status-panel palette) so
# the scene's visual language lives in one file: change how a reef or a
# gun or fog looks here, nowhere else. Glyph choices stick to characters
# that Windows Terminal / Cascadia Mono, macOS Terminal and common Linux
# fonts all render (ASCII, Latin-1, box drawing, block elements, a few
# CP437 symbols).

from __future__ import annotations

import math

from broadside.sim import shiplayout as sl
from broadside.sim.world import terrain as tr

Color = tuple

VOID_BG = (6, 7, 10)
FOG = (150, 156, 164)
FOG_BG = (58, 62, 68)
SMOKE = (208, 206, 198)
HAZE = (120, 130, 145)

# terrain code -> (glyph, fg, bg)
TERRAIN_STYLE = {
    tr.SEA: (" ", (70, 120, 170), (14, 42, 78)),
    tr.SHOAL: (" ", (100, 170, 180), (26, 84, 104)),
    tr.REEF: ("·", (215, 232, 236), (44, 104, 112)),
    tr.BEACH: ("░", (214, 196, 140), (116, 102, 68)),
    tr.LAND: ('"', (150, 172, 92), (48, 60, 30)),
    tr.FOREST: ("♣", (72, 150, 70), (22, 48, 24)),
    tr.HILL: ("^", (176, 156, 116), (70, 60, 44)),
    tr.ROCK: ("▲", (168, 166, 170), (52, 54, 60)),
    tr.PEAK: ("▲", (236, 236, 232), (92, 82, 70)),
}

WAVE_GLYPHS = ("~", "≈")
FOAM = (226, 240, 246)
CREST_BG = (46, 96, 134)
TROUGH_BG = (8, 26, 54)

SHIP_BG = (58, 42, 26)
SHIP_TILE_STYLE = {
    sl.HULL: ("#", (178, 128, 76), (74, 50, 30)),
    sl.DECK: (".", (156, 124, 82), SHIP_BG),
    sl.MAST: ("O", (214, 172, 110), SHIP_BG),
    sl.GUN: ("=", (176, 178, 190), SHIP_BG),
    sl.WHEEL: ("Ø", (230, 196, 120), SHIP_BG),
    sl.CAPSTAN: ("Θ", (200, 160, 100), SHIP_BG),
    sl.HATCH: ("≡", (120, 94, 60), SHIP_BG),
    sl.BOWSPRIT: ("─", (190, 150, 96), None),
}
SEAM_FG = (108, 84, 56)
GUN_IRON = (150, 152, 164)
CARRIAGE = (120, 86, 52)


def subtile(tile: int, fu: float, fv: float, k: int, gun_side: int = 1):
    """What a square metre of ship looks like when a metre is several cells
    across: planking with its seams, a gun's barrel and carriage, the round
    of a mast, the bars of a grating. `fu`/`fv` are where in the tile the
    cell falls, along the ship's forward and starboard axes.

    Returns (glyph, fg) or None to leave the tile's plain style alone.

    Two cells to the metre is the ship view's own default (auto-fit picks
    it for anything under about a hundred feet), and the detail here has to
    work at that coarseness or the ship is drawn as her plain glyphs
    doubled, which reads as a broken, blocky picture rather than a ship.
    So each tile has a two-cell form as well as a fine one.
    """
    # Snap to the middle of the sub-cell this point falls in. The camera
    # rebuilds these fractions from the ship's position every frame, and
    # without this the last bit of floating-point noise flips a plank seam
    # on and off - which is visible, and reads as the deck twitching.
    fu = (int(fu * k) + 0.5) / k
    fv = (int(fv * k) + 0.5) / k
    coarse = k <= 2
    if tile == sl.DECK:
        # Planks run fore and aft; their seams are the lines you see. At two
        # cells to the metre a seam every other cell is a corduroy, so the
        # deck is left plain.
        if coarse:
            return None
        if fv < 1.0 / k:
            return "│", SEAM_FG
        return " ", SEAM_FG
    if tile == sl.HULL:
        if coarse:
            return "█", (150, 108, 64)
        return ("█", (150, 108, 64)) if 0.15 < fu < 0.85 else ("▓", (128, 92, 54))
    if tile == sl.HATCH:
        if coarse:
            return "▒", (146, 116, 74)
        bar = (fu < 1.0 / k) or (fv < 1.0 / k)
        return ("═", (146, 116, 74)) if bar else ("░", (74, 58, 38))
    if tile == sl.MAST:
        d = ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) ** 0.5
        if coarse:
            return "●", (214, 172, 110)
        if d < 0.22:
            return "█", (214, 172, 110)
        if d < 0.38:
            return "▓", (176, 138, 88)
        return " ", SEAM_FG
    if tile == sl.GUN:
        # The barrel points outboard: along +v for a starboard gun.
        along = fv if gun_side > 0 else 1.0 - fv
        if coarse:
            # Outboard half the muzzle, inboard half the carriage.
            return ("═", GUN_IRON) if along > 0.5 else ("▄", CARRIAGE)
        if abs(fu - 0.5) < 0.18:
            return ("═", GUN_IRON) if along > 0.35 else ("█", GUN_IRON)
        if 0.2 < fu < 0.8 and along < 0.45:
            return "▄", CARRIAGE
        return " ", SEAM_FG
    if tile == sl.WHEEL:
        # Hub, spokes and rim, so that at three or more cells to the metre
        # the wheel reads as a wheel and the player can find it: it is the
        # one thing on deck a tutorial sends you to by eye. At two cells it
        # is four spoked quarters.
        d = ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) ** 0.5
        if coarse:
            return "Ø", (242, 214, 150)
        if d < 0.14:
            return "Ø", (242, 214, 150)
        if d > 0.5:
            return " ", SEAM_FG
        if d > 0.34:
            return "●", (230, 196, 120)
        if abs(fu - 0.5) < 0.1:
            return "│", (206, 170, 104)
        if abs(fv - 0.5) < 0.1:
            return "─", (206, 170, 104)
        return " ", SEAM_FG
    if tile == sl.CAPSTAN:
        d = ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) ** 0.5
        if k <= 2:
            return "Θ", (200, 160, 100)
        return ("Θ", (200, 160, 100)) if d < 0.3 else (" ", SEAM_FG)
    return None


SAIL_FG = (238, 234, 222)
SAIL_GLYPH = "▒"
FLASH_FG = (255, 226, 120)
FLASH_BG = (190, 84, 20)

FACTION_COLORS = {
    "british": (90, 200, 235),
    "french": (235, 96, 76),
    "spanish": (236, 204, 70),
    "neutral": (205, 205, 205),
    "pirate": (190, 120, 230),
}

# Your own ship where you cannot see her this instant: veiled, not erased.
# The captain knows where his own guns and hatches are - he simply cannot see
# who is standing by them through his own canvas and powder smoke.
def veiled(fg, bg):
    return blend(fg, (104, 104, 116), 0.52), blend(bg, (26, 27, 33), 0.55)


CORPSE_FG = (170, 50, 45)
WALL_FG = (176, 170, 158)
WALL_BG = (96, 92, 84)
RUBBLE_FG = (196, 174, 128)
RUBBLE_BG = (98, 84, 58)
DUST = (200, 180, 138)
BLEEDING_BG = (110, 20, 20)
ITEM_STYLE = {
    "shot garland": ("\u2022", (150, 150, 160)),
    "scuttlebutt": ("\u00a4", (200, 160, 100)),
    "fire bucket": ("u", (190, 150, 90)),
    "cartridge box": ("▫", (200, 90, 70)),
}

CAPTAIN_FG = (255, 234, 110)
CAPTAIN_BG = (96, 72, 16)

# Who is who on a crowded deck. You are the only @ aboard; everyone else is
# lower-case, so your own man is findable at a glance - the oldest
# roguelike convention there is, and it works.
CREW_GLYPHS = {
    "Captain": "@",
    "Lieutenant": "&",
    "Midshipman": "&",
    "Master": "&",
    "Master's Mate": "&",
    "Gun Captain": "g",
    "Bosun's Mate": "b",
    "Quartermaster's Mate": "q",
    "Carpenter's Mate": "c",
    "Sailmaker's Mate": "s",
    "Cook's Mate": "k",
    "Loblolly Boy": "l",
    "Surgeon": "+",
    "Marine": "x",
    "Topman": "t",
    "Lookout": "t",
    "Ship's Boy": ",",
}
CREW_GLYPH_DEFAULT = "o"


def crew_glyph(role_title: str) -> str:
    return CREW_GLYPHS.get(role_title, CREW_GLYPH_DEFAULT)
CURSOR_BG = (220, 200, 60)
CURSOR_FG = (10, 10, 10)

# Screen direction -> ship symbol (one-cell ship at chart scale). Only the
# four cardinal triangles: the diagonal ones (and diagonal arrows) are
# missing from Consolas and Cascadia Mono, the default Windows fonts.
SHIP_ARROWS = ["▲", "►", "▼", "◄"]
TOPSAILS_GLYPH = "†"
GHOST_GLYPH = "?"
REPORT_GLYPH = "!"


def faction_color(name: str) -> Color:
    return FACTION_COLORS.get(name, FACTION_COLORS["neutral"])


def blend(a: Color, b: Color, t: float) -> Color:
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def remembered(c: Color) -> Color:
    """Memory colouring: desaturated and dark, faintly blue - legible as
    'this is how it was' without competing with what's in sight."""
    lum = 0.3 * c[0] + 0.55 * c[1] + 0.15 * c[2]
    v = 20 + lum * 0.4
    return (int(v * 0.85), int(v * 0.92), int(v * 1.12))


def remembered_bg(c: Color) -> Color:
    lum = 0.3 * c[0] + 0.55 * c[1] + 0.15 * c[2]
    v = 14 + lum * 0.3
    return (int(v * 0.85), int(v * 0.92), int(v * 1.2))


def dir_glyph(screen_dx: float, screen_dy: float) -> str:
    """A line glyph along a screen direction."""
    ang = math.degrees(math.atan2(-screen_dy, screen_dx)) % 180.0
    if ang < 22.5 or ang >= 157.5:
        return "─"
    if ang < 67.5:
        return "╱"
    if ang < 112.5:
        return "│"
    return "╲"


def arrow_for(screen_dx: float, screen_dy: float) -> str:
    ang = (math.degrees(math.atan2(screen_dx, -screen_dy)) + 360.0) % 360.0
    return SHIP_ARROWS[int((ang + 45.0) // 90) % 4]


_POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass_point(degrees: float) -> str:
    return _POINTS[int(((degrees % 360.0) + 11.25) // 22.5) % 16]
