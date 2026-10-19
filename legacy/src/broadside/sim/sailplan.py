# Which named sails are set, and the period vocabulary a quarterdeck used
# for wind and heading.
#
# The sim still drives sail area with a single `SailPlan.trim` value (Phase
# 1 replaces it with per-sail state). This module maps that value to the
# sails a square-rigger would actually have set at that setting - the
# order they're made and taken in follows practice: topsails first (the
# working sails), then courses, then topgallants, royals last - and it's
# the one place the vision engine's sail geometry (sim/spatial.py) and the
# player's sail-plan display agree on.

from __future__ import annotations

from broadside.sim.systems.sailing import angle_off_wind

# (sail, minimum trim at which it is set), lowest tier first.
SQUARE_TIERS = [("course", 0.55), ("topsail", 0.05), ("topgallant", 0.75), ("royal", 0.95)]
JIB_TRIM = 0.05
SPANKER_TRIM = 0.3


def square_sails_set(mast: str, trim: float) -> dict:
    """{sail: set?} for one mast. The mizzen course (the 'crossjack') was
    rarely set and never is here; the mizzen usually carried no royal."""
    out = {}
    for sail, need in SQUARE_TIERS:
        if mast == "mizzen" and sail in ("course", "royal"):
            out[sail] = None  # not carried
        else:
            out[sail] = trim >= need
    return out


def sail_setting_name(trim: float) -> str:
    if trim < 0.05:
        return "bare poles"
    if trim < 0.55:
        return "fighting sail (topsails)"
    if trim < 0.75:
        return "plain sail (courses & topsails)"
    if trim < 0.95:
        return "all plain sail (to t'gallants)"
    return "all sail (royals set)"


# --- Compass, wind and speed, the way they were spoken ----------------------

POINTS_32 = [
    "N", "N by E", "NNE", "NE by N", "NE", "NE by E", "ENE", "E by N",
    "E", "E by S", "ESE", "SE by E", "SE", "SE by S", "SSE", "S by E",
    "S", "S by W", "SSW", "SW by S", "SW", "SW by W", "WSW", "W by S",
    "W", "W by N", "WNW", "NW by W", "NW", "NW by N", "NNW", "N by W",
]


def compass_32(degrees: float) -> str:
    """Heading as the helmsman would sing it out: 'NE by E'."""
    return POINTS_32[int(((degrees % 360.0) + 5.625) // 11.25) % 32]


def relative_bearing_words(relative_degrees: float) -> str:
    """A direction relative to the ship's head, in points: 'two points
    abaft the starboard beam', 'broad on the larboard bow'."""
    rel = relative_degrees % 360.0
    side = "starboard" if rel <= 180.0 else "larboard"
    a = rel if rel <= 180.0 else 360.0 - rel
    p = int(round(a / 11.25))
    words = ["", "one", "two", "three", "four", "five", "six", "seven"]
    if p == 0:
        return "right ahead"
    if p == 16:
        return "right astern"
    if p < 4:
        return f"{words[p]} point{'s' if p > 1 else ''} on the {side} bow"
    if p == 4:
        return f"broad on the {side} bow"
    if p < 8:
        return f"{words[8 - p]} point{'s' if 8 - p > 1 else ''} before the {side} beam"
    if p == 8:
        return f"on the {side} beam"
    if p < 12:
        return f"{words[p - 8]} point{'s' if p - 8 > 1 else ''} abaft the {side} beam"
    if p == 12:
        return f"broad on the {side} quarter"
    return f"{words[16 - p]} point{'s' if 16 - p > 1 else ''} on the {side} quarter"


def point_of_sail(heading: float, wind_from: float) -> str:
    off = angle_off_wind(heading, wind_from)
    rel = (wind_from - heading) % 360.0
    tack = "starboard tack" if rel < 180.0 else "larboard tack"
    if off < 30:
        return "in irons - taken aback"
    if off < 70:
        return f"close-hauled, {tack}"
    if off < 110:
        return f"wind abeam, {tack}"
    if off < 160:
        return f"sailing large, {tack}"
    return "running before the wind"


# Beaufort's own 1806 wording (the scale is exactly period).
BEAUFORT = [
    (1, 0, "calm"), (4, 1, "light air"), (7, 2, "light breeze"), (11, 3, "gentle breeze"),
    (17, 4, "moderate breeze"), (22, 5, "fresh breeze"), (28, 6, "strong breeze"),
    (34, 7, "moderate gale"), (41, 8, "fresh gale"), (48, 9, "strong gale"),
    (56, 10, "whole gale"), (64, 11, "storm"), (9999, 12, "hurricane"),
]


def beaufort(knots: float) -> tuple[int, str]:
    for limit, force, name in BEAUFORT:
        if knots < limit:
            return force, name
    return 12, "hurricane"


def log_reading(knots: float) -> str:
    """Speed as the log-line gave it: whole knots and fathoms (eighths)."""
    k = max(0.0, knots)
    whole = int(k)
    fathoms = int(round((k - whole) * 8))
    if fathoms == 8:
        whole, fathoms = whole + 1, 0
    return f"{whole} knot{'s' if whole != 1 else ''} {fathoms} fathom{'s' if fathoms != 1 else ''}"
