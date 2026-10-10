# Camera/scroll math: maps a space's coordinates (deck tiles, or later
# world nautical-mile coordinates) onto a rectangle of screen cells,
# clipping anything outside it. See docs/design/03_rendering_ui.md,
# "Coordinate spaces, cameras, and the split screen".
#
# Deliberately generic over "which space" - the deck viewport and the
# (Phase 4+) chart viewport are both just a Viewport with different origins
# and different callers feeding it coordinates already in the right space.
# Nothing here knows about DeckPosition vs WorldPosition; that translation
# happens in the render code that calls it (e.g. render of the deck panel).

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Viewport:
    """A window onto a larger coordinate space.

    `origin_x`/`origin_y` is the space-coordinate shown at the viewport's
    top-left screen cell. `width`/`height` is the viewport's size in screen
    cells (typically = the panel it's drawn into).
    """

    origin_x: int
    origin_y: int
    width: int
    height: int

    def to_screen(self, space_x: int, space_y: int) -> tuple[int, int] | None:
        """Convert a space coordinate to a screen coordinate local to this
        viewport (i.e. 0,0 = the viewport's own top-left, not the full
        terminal's). Returns None if outside the visible window."""
        sx = space_x - self.origin_x
        sy = space_y - self.origin_y
        if 0 <= sx < self.width and 0 <= sy < self.height:
            return sx, sy
        return None

    def centre_on(self, space_x: int, space_y: int) -> None:
        """Recentre the viewport so (space_x, space_y) is in the middle of
        the visible window - used to follow the player's ship on the
        (future) chart view."""
        self.origin_x = space_x - self.width // 2
        self.origin_y = space_y - self.height // 2

    @classmethod
    def fitting(cls, space_width: int, space_height: int, panel_width: int, panel_height: int) -> "Viewport":
        """A viewport sized to the panel, with the space centred within it
        if the space is smaller than the panel (the common case for a
        small ship's deck fitting comfortably in its pane) - avoids the
        deck view looking pinned to one corner on a larger terminal."""
        origin_x = -(max(0, panel_width - space_width) // 2)
        origin_y = -(max(0, panel_height - space_height) // 2)
        return cls(origin_x=origin_x, origin_y=origin_y, width=panel_width, height=panel_height)
