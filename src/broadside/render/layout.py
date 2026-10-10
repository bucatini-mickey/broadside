# Split-screen panel geometry: divides the terminal into a left (deck view)
# and right (status/fleet) pane with a divider, plus a footer row for
# command hints. Recomputed whenever the terminal is resized. See
# docs/design/03_rendering_ui.md, "Coordinate spaces, cameras, and the
# split screen".

from __future__ import annotations

from dataclasses import dataclass

from broadside.render import palette
from broadside.render.buffer import ScreenBuffer

FOOTER_HEIGHT = 1


@dataclass
class Panel:
    x: int
    y: int
    width: int
    height: int


@dataclass
class SplitScreenLayout:
    total_width: int
    total_height: int
    left_fraction: float = 0.6

    @property
    def divider_x(self) -> int:
        return int(self.total_width * self.left_fraction)

    @property
    def content_height(self) -> int:
        return max(1, self.total_height - FOOTER_HEIGHT)

    @property
    def left(self) -> Panel:
        return Panel(x=0, y=0, width=self.divider_x, height=self.content_height)

    @property
    def right(self) -> Panel:
        x = self.divider_x + 1
        return Panel(x=x, y=0, width=max(0, self.total_width - x), height=self.content_height)

    @property
    def footer(self) -> Panel:
        return Panel(x=0, y=self.content_height, width=self.total_width, height=FOOTER_HEIGHT)

    def draw_divider(self, buffer: ScreenBuffer) -> None:
        buffer.draw_vline(self.divider_x, 0, self.content_height, glyph="│", fg=palette.PANEL_DIVIDER)
