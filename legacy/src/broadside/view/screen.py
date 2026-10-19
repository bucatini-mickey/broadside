# The command screen: how the whole terminal is laid out.
#
#   +--------------------------+---------------------------+
#   | SHIP  (1 m per cell or   | CHART  (macro view: the   |
#   | closer, bow up, full     | fleet, contacts, terrain) |
#   | height - a 74 is ~15     |                           |
#   | cells wide and ~65 tall; +---------------------------+
#   | in walk mode the view    | status strip: time, helm, |
#   | follows the captain)     | log, wind, sail, quarters |
#   |                          +---------------------------+
#   |                          | 1 LOG 2 CREW 3 ORDERS ... |
#   |                          | the chosen panel, with    |
#   |                          | the full width to itself  |
#   +--------------------------+---------------------------+
#   | footer: message                                      |
#   | footer: the few keys you need (5 shows them all)     |
#
# One panel at a time, rather than four things at once: the clutter was the
# complaint. The scene panes are the same composer (view/compose.py) with
# different ViewStates, sharing one map memory; the chart is redrawn a few
# times a second (compose_slow) so the ship pane can have every frame.
# Shared by the interactive app and every headless exporter, so a replay
# looks exactly like the game. See docs/design/08_interface.md.

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Optional

from broadside.render.buffer import ScreenBuffer
from broadside.sim import components as c
from broadside.view.compose import FrameInfo, ViewState, compose, compose_slow
from broadside.view.panels import UIState, draw_panel, draw_status_strip, draw_tab_bar

DIVIDER = (60, 62, 76)
TITLE_BG = (22, 24, 34)
TITLE_FOCUS_BG = (70, 58, 22)
TITLE_FG = (230, 230, 235)
# How stale the chart may be. At macro zoom a ship makes a fifth of a column
# in this time, while the ship pane is redrawn every frame.
CHART_REFRESH_S = 0.4
FOOTER_LINES = 2


@dataclass
class ScreenInfo:
    deck: FrameInfo
    chart: FrameInfo
    deck_rect: tuple  # (x, y, w, h) of the deck scene area
    chart_rect: tuple


def default_deck_view() -> ViewState:
    # A metre a cell for now. Half a metre - a cell to a cask, which is the
    # ratio we want - must wait on the sub-metre steadiness fix: below a
    # metre the sampling lattice is not locked to the ship's tile grid and
    # her bulwarks shimmer (docs/design/20_sighting_and_instruments_plan.md).
    return ViewState(scale="local", local_zoom=0, rotation="ship", fit=True)


def default_chart_view() -> ViewState:
    return ViewState(scale="macro", macro_zoom=4, rotation="north")


def _title(buf, x, y, w, text, focused) -> None:
    bg = TITLE_FOCUS_BG if focused else TITLE_BG
    buf.draw_text(x, y, (" " + text).ljust(w)[:w], fg=TITLE_FG, bg=bg)


def compose_screen(
    buf: ScreenBuffer,
    state,
    deck: ViewState,
    chart: ViewState,
    *,
    scenario=None,
    look: Optional[list] = None,
    focus: str = "deck",
    footer: Optional[str] = None,
    ui: Optional[UIState] = None,
    look_out=None,
) -> ScreenInfo:
    W, H = buf.width, buf.height
    content_h = H - FOOTER_LINES
    left_w = W // 2
    rx = left_w + 1
    rw = W - rx
    chart.memory = deck.memory  # one memory of what the screen has shown
    if ui is None:
        ui = UIState()
    if look:
        ui.look = list(look)

    ship_name = state.world.component_for_entity(state.player_ship, c.Name).full
    deck_rect = (0, 1, left_w, content_h - 1)
    look_out = look_out if look_out is not None else deck.look_out
    if look_out is not None:
        from broadside.sim.entities import find_observer
        from broadside.sim.systems.sighting import observer_eye
        from broadside.view.firstperson import draw_look_cached

        obs = find_observer(state.world, state.player_ship, deck.observer) or find_observer(state.world, state.player_ship, "captain")
        eye = observer_eye(state, obs) if obs is not None else None
        if eye is not None:
            draw_look_cached(buf, *deck_rect, state, eye, look_out)
            from broadside.sim.sailplan import compass_32

            from broadside.view.orientation import relative_short

            glass = "through the glass" if look_out.glass else "by eye"
            # Relative bearing first: where she is pointed matters more to
            # a man laying guns than where north is.
            where = relative_short(look_out.relative_deg)
            tilt = "" if abs(look_out.pitch_deg) < 0.5 else f", {abs(look_out.pitch_deg):.0f} deg {'up' if look_out.pitch_deg > 0 else 'down'}"
            held = ""
            if look_out.target >= 0:
                her = state.world.try_component(look_out.target, c.Name)
                held = f"  holding {her.full}" if her is not None else ""
            _title(
                buf, 0, 0, left_w,
                f"LOOKING {glass}  {where}{tilt}  - {compass_32(look_out.bearing_deg)} {look_out.bearing_deg:03.0f}, field {look_out.fov_deg:.0f} deg{held}",
                focus == "deck",
            )
            deck_info = FrameInfo(camera=deck.camera(state, rows=content_h - 1), width=left_w, height=content_h - 1, eye=eye, visible_fraction=1.0, letters={})
            chart_h = max(8, int(content_h * 0.46))
            chart_rect = (rx, 1, rw, chart_h - 1)
            _title(buf, rx, 0, rw, f"CHART  {chart.cell_m:g} m per column", focus == "chart")
            chart_info = compose_slow(buf, *chart_rect, state, chart, refresh_s=CHART_REFRESH_S)
            strip_y = chart_h
            draw_status_strip(buf, rx, strip_y, rw, state, ui)
            draw_tab_bar(buf, rx, strip_y + 1, rw, ui, focus == "panel")
            panel_y = strip_y + 2
            draw_panel(buf, rx, panel_y, rw, content_h - panel_y, state, deck, ui, info=deck_info, scenario=scenario, focused=focus == "panel")
            if footer is not None:
                lines = textwrap.wrap(footer.strip(), max(20, W - 2)) or [""]
                for i in range(FOOTER_LINES):
                    text = lines[i] if i < len(lines) else ""
                    buf.draw_text(0, H - FOOTER_LINES + i, (" " + text).ljust(W)[:W], fg=(200, 200, 205), bg=(24, 26, 36))
            for y in range(content_h):
                buf.set(left_w, y, "\u2502", fg=DIVIDER, bg=(12, 13, 18))
            return ScreenInfo(deck_info, chart_info, deck_rect, chart_rect)
    if deck.z_m is not None:
        from broadside.view.levels import draw_levels

        lvl = draw_levels(buf, *deck_rect, state, deck)
        deck_info = FrameInfo(camera=lvl.camera, width=left_w, height=content_h - 1, eye=None, visible_fraction=1.0, letters={})
        kk = round(1.0 / lvl.camera.cell_m) if lvl.camera.cell_m < 1 else 0
        scale_txt = f"{kk}x{kk} cells per metre" if kk > 1 else f"{lvl.camera.cell_m:g} m per cell"
        state_txt = "PLAN" if deck.paused else "LIVE"
        _title(buf, 0, 0, left_w, f"LEVEL  {lvl.label}  - {scale_txt}  [{state_txt}]  PgUp/PgDn", focus == "deck")
    else:
        deck_info = compose(buf, *deck_rect, state, deck)
        kk = round(1.0 / deck_info.camera.cell_m) if deck_info.camera.cell_m < 1 else 0
        scale_txt = f"{kk}x{kk} cells per metre" if kk > 1 else f"{deck_info.camera.cell_m:g} m per cell"
        who = "  WALKING" if deck.follow >= 0 else ""
        _title(buf, 0, 0, left_w, f"SHIP  {ship_name}  - {scale_txt}{who}", focus == "deck")

    for y in range(content_h):
        buf.set(left_w, y, "│", fg=DIVIDER, bg=(12, 13, 18))

    chart_h = max(8, int(content_h * 0.46))
    chart_rect = (rx, 1, rw, chart_h - 1)
    if chart.scale == "elevation":
        from broadside.view.elevation import draw_elevation

        name = draw_elevation(buf, *chart_rect, state)
        _title(buf, rx, 0, rw, f"ELEVATION  {name} seen face-on (0.5 m blocks)", focus == "chart")
        chart_info = deck_info
    else:
        _title(buf, rx, 0, rw, f"CHART  {chart.cell_m:g} m per column", focus == "chart")
        chart_info = compose_slow(buf, *chart_rect, state, chart, refresh_s=CHART_REFRESH_S)

    strip_y = chart_h
    draw_status_strip(buf, rx, strip_y, rw, state, ui)
    draw_tab_bar(buf, rx, strip_y + 1, rw, ui, focus == "panel")
    panel_y = strip_y + 2
    draw_panel(buf, rx, panel_y, rw, content_h - panel_y, state, deck, ui, info=deck_info, scenario=scenario, focused=focus == "panel")

    if footer is not None:
        lines = textwrap.wrap(footer.strip(), max(20, W - 2)) or [""]
        for i in range(FOOTER_LINES):
            text = lines[i] if i < len(lines) else ""
            buf.draw_text(0, H - FOOTER_LINES + i, (" " + text).ljust(W)[:W], fg=(200, 200, 205), bg=(24, 26, 36))
    return ScreenInfo(deck_info, chart_info, deck_rect, chart_rect)
