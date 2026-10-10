# The command screen layout and the quarterdeck instruments' period
# vocabulary.

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import get, split_overrides
from broadside.sim.sailplan import beaufort, compass_32, log_reading, relative_bearing_words, square_sails_set
from broadside.view.export import to_text
from broadside.view.instruments import compass_tape
from broadside.view.screen import compose_screen


def test_compass_points_and_relative_bearings():
    assert compass_32(0) == "N"
    assert compass_32(56.25) == "NE by E"
    assert compass_32(350.0) == "N by W"
    assert relative_bearing_words(90) == "on the starboard beam"
    assert relative_bearing_words(270) == "on the larboard beam"
    assert relative_bearing_words(112.5) == "two points abaft the starboard beam"
    assert relative_bearing_words(45) == "broad on the starboard bow"
    assert relative_bearing_words(180) == "right astern"


def test_beaufort_log_and_sails():
    assert beaufort(12) == (4, "moderate breeze")
    assert beaufort(0.5) == (0, "calm")
    assert log_reading(5.25) == "5 knots 2 fathoms"
    fore = square_sails_set("fore", 0.4)
    assert fore["topsail"] and not fore["course"]
    assert square_sails_set("mizzen", 1.0)["course"] is None


def test_compass_tape_centres_on_heading():
    labels, ticks = compass_tape(90.0, 41)
    assert labels[20] == "E"
    assert len(ticks) == 41


def test_override_routing():
    deck, chart = split_overrides({"scale": "macro", "macro_zoom": 3, "pan": (1, 2), "paused": True})
    assert chart == {"macro_zoom": 3, "pan": (1, 2), "paused": True} and deck == {"paused": True}
    deck, chart = split_overrides({"local_zoom": 1, "pan": (5, 5)})
    assert deck == {"local_zoom": 1, "pan": (5, 5)} and chart == {}


def test_command_screen_layout():
    run = get("open_water").build()
    run.sim.run_seconds(2)
    buf = ScreenBuffer(190, 64)
    run.deck.paused = True  # planning view: the whole ship is drawn
    info = compose_screen(buf, run.state, run.deck, run.chart, footer="x")
    text = to_text(buf)
    # The panels have the instruments now (tests/test_panels.py covers
    # them); the always-on parts are the two scene panes and the strip.
    for heading in ("SHIP", "CHART", "1 LOG", "6 KEYS", "helm", "wind"):
        assert heading in text
    # Ship pane is the left half, bow up. Auto-fit draws the 30 m sloop at
    # 2x2 cells per metre on a 64-row screen: ~60 rows tall.
    x, y, w, h = info.deck_rect
    assert w == 95 and x == 0
    # Her bulwarks: "#" at a metre a cell, a solid block at two cells to
    # the metre and finer (view/style.subtile), which is what auto-fit
    # gives a 30 m sloop on a 64-row screen.
    rows = [r for r in text.split(chr(10))[y : y + h] if ("#" in r[:w] or "█" in r[:w])]
    assert info.deck.camera.cell_m == 0.5
    assert 55 <= len(rows) <= 61
