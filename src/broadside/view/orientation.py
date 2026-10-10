"""Which way she lies, in the words a sailor would use.

A compass bearing says where a thing is in the *world*. What a captain
needs in order to lay guns is where it is relative to his *own ship* - and
what of the other ship he can see, because a broadside into her bows does
little and the same weight of iron into her quarter can unship her rudder.
The old navy had precise words for both, so we use them.

A point is a thirty-second of the circle, 11.25 degrees. Bearings in the
forward quadrants are counted from ahead ("three points on the starboard
bow") and in the after quadrants from astern ("two points on the port
quarter"), with the beam named outright.
"""

from __future__ import annotations

import math

POINT_DEG = 360.0 / 32.0
HALF_POINT = POINT_DEG / 2.0
CABLE_M = 185.2


def relative_bearing(heading_deg: float, bearing_deg: float) -> float:
    """Where something bears from a ship on this heading, in degrees from
    -180 (astern, to port) through 0 (dead ahead) to +180, positive to
    starboard."""
    rel = (bearing_deg - heading_deg) % 360.0
    return rel - 360.0 if rel > 180.0 else rel


def points(rel_deg: float) -> float:
    """A relative bearing in points, the unit a lookout reported in."""
    return rel_deg / POINT_DEG


def _points_word(n: int) -> str:
    words = ("", "one point", "two points", "three points", "four points",
             "five points", "six points", "seven points")
    return words[n] if 0 <= n < len(words) else f"{n} points"


def relative_words(rel_deg: float) -> str:
    """"Three points on the starboard bow", and the rest of them."""
    if abs(rel_deg) < HALF_POINT:
        return "dead ahead"
    if abs(rel_deg) > 180.0 - HALF_POINT:
        return "right astern"
    side = "starboard" if rel_deg > 0.0 else "port"
    off = abs(rel_deg)
    if abs(off - 90.0) < HALF_POINT:
        return f"on the {side} beam"
    if off < 90.0:
        n = max(1, min(7, int(round(off / POINT_DEG))))
        return f"{_points_word(n)} on the {side} bow"
    n = max(1, min(7, int(round((180.0 - off) / POINT_DEG))))
    return f"{_points_word(n)} on the {side} quarter"


def relative_short(rel_deg: float) -> str:
    """The same, short enough for a status strip: "3pt stbd bow"."""
    if abs(rel_deg) < HALF_POINT:
        return "ahead"
    if abs(rel_deg) > 180.0 - HALF_POINT:
        return "astern"
    side = "stbd" if rel_deg > 0.0 else "port"
    off = abs(rel_deg)
    if abs(off - 90.0) < HALF_POINT:
        return f"{side} beam"
    if off < 90.0:
        n = max(1, min(7, int(round(off / POINT_DEG))))
        return f"{n}pt {side} bow"
    n = max(1, min(7, int(round((180.0 - off) / POINT_DEG))))
    return f"{n}pt {side} quarter"


def aspect_degrees(her_heading_deg: float, bearing_to_her_deg: float) -> float:
    """How she lies to us: where *we* bear from *her*, which is the angle at
    which we see her. 0 is bows on, 180 stern on, +90 her starboard side
    laid open to us."""
    return relative_bearing(her_heading_deg, bearing_to_her_deg + 180.0)


def aspect_words(her_heading_deg: float, bearing_to_her_deg: float) -> str:
    """What of her we can see - the number that decides whether a broadside
    will tell on her, or glance off two feet of oak end-on."""
    a = aspect_degrees(her_heading_deg, bearing_to_her_deg)
    side = "starboard" if a > 0.0 else "port"
    off = abs(a)
    if off < 22.5:
        return "bows on"
    if off > 157.5:
        return "stern on"
    if 67.5 <= off <= 112.5:
        return f"broadside on, her {side} side to us"
    if off < 90.0:
        return f"her {side} bow to us"
    return f"her {side} quarter to us"


def aspect_short(her_heading_deg: float, bearing_to_her_deg: float) -> str:
    a = aspect_degrees(her_heading_deg, bearing_to_her_deg)
    side = "stbd" if a > 0.0 else "port"
    off = abs(a)
    if off < 22.5:
        return "bows on"
    if off > 157.5:
        return "stern on"
    if 67.5 <= off <= 112.5:
        return f"broadside ({side})"
    return f"{side} {'bow' if off < 90.0 else 'quarter'}"


def range_words(metres: float) -> str:
    """Close work in yards, anything further in cables, which is how the
    range was called."""
    if metres < 200.0:
        return f"{metres:.0f} m"
    return f"{metres / CABLE_M:.1f} cables ({metres:.0f} m)"


def range_short(metres: float) -> str:
    if metres < 1000.0:
        return f"{metres:.0f} m"
    return f"{metres / 1000.0:.1f} km"


def bearing_and_range(from_xy, to_xy) -> tuple:
    """(bearing degrees, range metres) between two points."""
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    return math.degrees(math.atan2(dx, dy)) % 360.0, math.hypot(dx, dy)
