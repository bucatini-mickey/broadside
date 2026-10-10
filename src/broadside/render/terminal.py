# Diffs a ScreenBuffer against the previous frame's and writes only the
# cells that changed - the core performance technique described in
# docs/design/03_rendering_ui.md, "The screen buffer and diffed rendering".
# A naive full-grid redraw every frame is the classic terminal-app
# performance/flicker trap; this avoids it explicitly rather than trusting
# a library to do it invisibly, since understanding it matters for
# everything built on top of render/ later.
#
# Changed cells are written in horizontal runs: one cursor move per run,
# and colour escape codes only when the colour actually changes within the
# run. Colour sequences are cached per RGB value, since blessed's
# colour-matching (for terminals without true colour) is not free and a
# scene frame asks for the same few dozen colours thousands of times.

from __future__ import annotations

import sys
from typing import TextIO

from blessed import Terminal

from broadside.render.buffer import Cell, ScreenBuffer

DEFAULT_BG = (6, 7, 10)


class TerminalRenderer:
    def __init__(self, term: Terminal | None = None):
        self.term = term or Terminal()
        self._previous: ScreenBuffer | None = None
        self._fg_cache: dict = {}
        self._bg_cache: dict = {}

    def _fg(self, rgb) -> str:
        s = self._fg_cache.get(rgb)
        if s is None:
            s = self.term.color_rgb(*rgb)
            self._fg_cache[rgb] = s
        return s

    def _bg(self, rgb) -> str:
        s = self._bg_cache.get(rgb)
        if s is None:
            s = self.term.on_color_rgb(*rgb)
            self._bg_cache[rgb] = s
        return s

    def render(self, buffer: ScreenBuffer, out: TextIO | None = None) -> None:
        term = self.term
        out = out or getattr(term, "stream", None) or sys.stdout
        prev = self._previous
        same_shape = prev is not None and prev.width == buffer.width and prev.height == buffer.height

        writes: list[str] = []
        w = buffer.width
        fg_of = self._fg
        bg_of = self._bg
        move = term.move_xy
        for y in range(buffer.height):
            # Whole rows at a time, straight off the buffer: a frame is
            # twelve thousand cells and this runs on every one of them.
            row = buffer.row(y)
            old_row = prev.row(y) if same_shape else None
            if old_row is not None and row == old_row:
                continue
            x = 0
            while x < w:
                cell = row[x]
                if old_row is not None and old_row[x] == cell:
                    x += 1
                    continue
                # Start of a run of changed cells.
                writes.append(move(x, y))
                last_fg = None
                last_bg = None
                while x < w:
                    cell = row[x]
                    if old_row is not None and old_row[x] == cell:
                        break
                    bg = cell.bg or DEFAULT_BG
                    if cell.fg != last_fg:
                        writes.append(fg_of(cell.fg))
                        last_fg = cell.fg
                    if bg != last_bg:
                        writes.append(bg_of(bg))
                        last_bg = bg
                    writes.append(cell.glyph)
                    x += 1

        if writes:
            # A single joined write + flush, rather than many small writes,
            # to avoid a syscall per changed cell.
            out.write("".join(writes) + term.normal)
            out.flush()

        self._previous = buffer.clone()

    def force_full_redraw_next_frame(self) -> None:
        """Call after a terminal resize (or anything else that might have
        invalidated what's actually on screen) to force the next render()
        to redraw every cell rather than trust the diff."""
        self._previous = None


def _cell_write(term: Terminal, x: int, y: int, cell: Cell) -> str:
    # Kept for callers that want a single self-contained cell write.
    parts = [term.move_xy(x, y), term.normal, term.color_rgb(*cell.fg)]
    if cell.bg is not None:
        parts.append(term.on_color_rgb(*cell.bg))
    parts.append(cell.glyph)
    return "".join(parts)
