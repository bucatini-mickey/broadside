# The in-memory grid of (glyph, fg, bg) per cell, plus the diffed writer
# that turns two buffers (previous frame, current frame) into the minimal
# set of terminal writes needed to update the screen. See
# docs/design/03_rendering_ui.md, "The screen buffer and diffed rendering".
#
# Implemented as plain Python lists rather than a numpy structured array:
# at the cell counts this project targets that is simple, easy to read and
# fast enough. The cell itself is a NamedTuple rather than a dataclass,
# because profiling a 190x64 frame did put building and comparing ~13,000
# of them per frame on the hot path - construction and equality then run in
# C instead of Python, and everything else about it is unchanged.

from __future__ import annotations

from typing import NamedTuple, Optional

Color = tuple[int, int, int]

DEFAULT_FG: Color = (200, 200, 200)


class Cell(NamedTuple):
    glyph: str
    fg: Color
    bg: Color | None


BLANK_CELL = Cell(glyph=" ", fg=DEFAULT_FG, bg=None)


class ScreenBuffer:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._cells: list[list[Cell]] = [
            [BLANK_CELL for _ in range(width)] for _ in range(height)
        ]

    def clear(self, fill: Cell = BLANK_CELL) -> None:
        for row in self._cells:
            for x in range(self.width):
                row[x] = fill

    def set(self, x: int, y: int, glyph: str, fg: Color = DEFAULT_FG, bg: Optional[Color] = None) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._cells[y][x] = Cell(glyph[:1] or " ", fg, bg)

    def row(self, y: int) -> list:
        """The mutable row itself, for hot loops that write a whole pane and
        have already checked their bounds."""
        return self._cells[y]

    def get(self, x: int, y: int) -> Cell:
        return self._cells[y][x]

    def draw_text(self, x: int, y: int, text: str, fg: Color = DEFAULT_FG, bg: Color | None = None) -> None:
        for i, ch in enumerate(text):
            self.set(x + i, y, ch, fg=fg, bg=bg)

    def draw_hline(self, x: int, y: int, length: int, glyph: str = "-", fg: Color = DEFAULT_FG) -> None:
        for i in range(length):
            self.set(x + i, y, glyph, fg=fg)

    def draw_vline(self, x: int, y: int, length: int, glyph: str = "|", fg: Color = DEFAULT_FG) -> None:
        for i in range(length):
            self.set(x, y + i, glyph, fg=fg)

    def clone(self) -> "ScreenBuffer":
        """A snapshot copy, safe to keep around while `self` keeps being
        mutated. Cell is an immutable frozen dataclass, so a shallow copy
        of each row is sufficient - used by TerminalRenderer to remember
        "what did we draw last frame" for diffing."""
        new = ScreenBuffer(self.width, self.height)
        new._cells = [row[:] for row in self._cells]
        return new

    def blit(self, other: "ScreenBuffer", at_x: int, at_y: int) -> None:
        """Copy `other` onto self with its top-left corner at (at_x, at_y),
        clipped to self's bounds. Used to compose sub-panels (deck view,
        status panel) into one full-screen buffer - see render/layout.py."""
        for y in range(other.height):
            dest_y = at_y + y
            if not (0 <= dest_y < self.height):
                continue
            for x in range(other.width):
                dest_x = at_x + x
                if not (0 <= dest_x < self.width):
                    continue
                cell = other._cells[y][x]
                self._cells[dest_y][dest_x] = cell
