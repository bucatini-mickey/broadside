# The view layer: cameras, map memory and the frame composer that turns
# simulation state + a line-of-sight computation into cells of
# (glyph, fg, bg) at any scale - the 1 m deck view, the squadron view and
# the chart. It reads the sim and never mutates it; its only state of its
# own is presentation state (camera, zoom, what the player's screen has
# shown before). Output-agnostic: the same frames go to the terminal, to
# plain text and to the HTML replay exporter.
