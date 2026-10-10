# The quarterdeck instruments: what an officer of the watch actually had
# to know the ship's heading, the wind, her speed and the time - drawn the
# way he'd have read them, rather than as an omniscient north arrow.
#
#   binnacle   the steering compass beside the wheel: heading in points
#   pennant    the masthead pennant / dog-vane on the weather rail: the wind
#              *relative to the ship*, which is what sail-handling needs
#   log        the log-line heaved with a sand-glass: knots and fathoms
#   bell       the half-hour glass and the ship's bell: watch and bells
#   sails      the sail plan - which sails are set on which mast
#
# True wind direction is shown only as the officer of the watch would have
# chalked it on the log-board. See docs/design/08_interface.md.

from __future__ import annotations

from broadside.engine.clock import watch_and_bells
from broadside.render.buffer import ScreenBuffer
from broadside.sim import components as c
from broadside.sim.sailplan import (
    JIB_TRIM,
    SPANKER_TRIM,
    beaufort,
    compass_32,
    log_reading,
    point_of_sail,
    relative_bearing_words,
    sail_setting_name,
    square_sails_set,
)

BG = (12, 13, 18)
TEXT = (225, 225, 225)
DIM = (140, 140, 150)
HEAD = (240, 210, 120)
RULE = (70, 70, 84)
BRASS = (222, 186, 110)
CANVAS = (238, 234, 222)
FURLED = (95, 92, 86)

_TAPE_LABELS = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}


def compass_tape(heading: float, width: int) -> tuple[str, str]:
    """Two text rows: a strip of the compass card centred on the ship's
    head, like the card seen through the binnacle glass. Each column
    spans 180/width degrees; bearings increase to the right."""
    span = 180.0
    step = span / max(width, 1)
    labels = [" "] * width
    ticks = [" "] * width
    mid = width // 2
    for col in range(width):
        b = (heading + (col - mid) * step) % 360.0
        prev = (b - step) % 360.0
        # Point ticks every 11.25 degrees; heavier at the 8 principal points.
        k = int(b // 11.25)
        if int(prev // 11.25) != k or (b % 11.25) < 1e-9:
            ticks[col] = "┼" if k % 4 == 0 else "╵"
        else:
            ticks[col] = "─"
    for deg, text in _TAPE_LABELS.items():
        off = ((deg - heading + 180.0) % 360.0) - 180.0
        col = int(round(mid + off / step))
        start = col - len(text) // 2
        if 0 <= start and start + len(text) <= width:
            for i, ch in enumerate(text):
                labels[start + i] = ch
    return "".join(labels), "".join(ticks)


def draw_instruments(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state) -> None:
    for yy in range(height):
        for xx in range(width):
            buf.set(x0 + xx, y0 + yy, " ", fg=TEXT, bg=BG)
    world = state.world
    ship = state.player_ship
    heading = world.component_for_entity(ship, c.Heading).degrees
    speed = world.component_for_entity(ship, c.Speed).knots
    trim = world.component_for_entity(ship, c.SailPlan).trim
    body = world.try_component(ship, c.ShipBody)
    helm = world.try_component(ship, c.Helm)
    wind = state.wind.current
    row = 0

    def put(text, fg=TEXT, x=1):
        nonlocal row
        if row < height:
            buf.draw_text(x0 + x, y0 + row, text[: max(0, width - x - 1)], fg=fg, bg=BG)
        row += 1

    def spans(parts):
        nonlocal row
        if row >= height:
            row += 1
            return
        x = x0 + 1
        for text, fg in parts:
            room = x0 + width - 1 - x
            if room <= 0:
                break
            buf.draw_text(x, y0 + row, text[:room], fg=fg, bg=BG)
            x += len(text[:room])
        row += 1

    # Binnacle
    spans([("Binnacle ", DIM), (compass_32(heading), BRASS), (f"  {heading:03.0f}°", DIM)])
    if helm is not None and abs(((helm.desired_heading - heading + 180) % 360) - 180) > 2:
        spans([("  helm: steer ", DIM), (compass_32(helm.desired_heading), TEXT)])
    tw = max(9, width - 4)
    labels, ticks = compass_tape(heading, tw)
    if row < height:
        buf.draw_text(x0 + 2 + tw // 2, y0 + row, "▼", fg=HEAD, bg=BG)
    row += 1
    put(labels, BRASS, x=2)
    put(ticks, DIM, x=2)

    # Pennant: relative wind
    force, name = beaufort(wind.speed_knots)
    rel = (wind.direction_degrees - heading) % 360.0
    spans([("Pennant ", DIM), (f"{name}", TEXT), (f"  (force {force})", DIM)])
    put("  " + relative_bearing_words(rel), TEXT)
    put("  " + point_of_sail(heading, wind.direction_degrees), DIM)
    spans([("Log     ", DIM), (log_reading(speed), TEXT)])
    watch, bells = watch_and_bells((state.start_hour + state.now_s / 3600.0) % 24.0)
    spans([("Bell    ", DIM), (f"{bells} bell{'s' if bells != 1 else ''}, {watch.lower()}", TEXT)])
    spans([("Log-board: wind ", DIM), (compass_32(wind.direction_degrees), DIM), ("  ", DIM), (state.atmosphere.words(), DIM)])

    # What we have flying at the masthead, and who has answered it.
    from broadside.sim.systems.signals import Signals

    sig = world.try_component(ship, Signals)
    if sig is not None and sig.hoisted:
        spans([("Signal  ", DIM), (f"No. {sig.hoisted} ", BRASS), (f"\"{sig.text}\"", TEXT)])
        if sig.acknowledged:
            put(f"  answered by {len(sig.acknowledged)} ship" + ("s" if len(sig.acknowledged) != 1 else ""), DIM)

    # Sail plan
    if row < height:
        buf.draw_text(x0 + 1, y0 + row, ("─ Sail " + "─" * width)[: width - 2], fg=RULE, bg=BG)
        buf.draw_text(x0 + 3, y0 + row, "Sail", fg=HEAD, bg=BG)
    row += 1
    put(sail_setting_name(trim), TEXT)
    masts = [m.name for m in body.layout.masts] if body else ["fore", "main"]
    order = [m for m in ("fore", "main", "mizzen") if m in masts]
    header = "          " + "".join(f"{m[:4]:<6}" for m in order)
    put(header, DIM)
    for sail, label in (("royal", "royal"), ("topgallant", "t'gall"), ("topsail", "topsl"), ("course", "course")):
        if row >= height:
            break
        buf.draw_text(x0 + 2, y0 + row, f"{label:<8}", fg=DIM, bg=BG)
        for i, m in enumerate(order):
            state_ = square_sails_set(m, trim)[sail]
            glyph, fg = ("█", CANVAS) if state_ else (("·", FURLED) if state_ is False else (" ", BG))
            buf.draw_text(x0 + 10 + i * 6 + 1, y0 + row, glyph, fg=fg, bg=BG)
        row += 1
    jib = "█" if trim >= JIB_TRIM else "·"
    spk = "█" if trim >= SPANKER_TRIM else "·"
    spans([("  jib ", DIM), (jib, CANVAS if trim >= JIB_TRIM else FURLED), ("   spanker ", DIM), (spk, CANVAS if trim >= SPANKER_TRIM else FURLED)])
