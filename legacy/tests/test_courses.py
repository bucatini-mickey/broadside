# Proof that each of the five tutorial missions can actually be finished.
#
# Every mission is driven by a scripted student who does what a player
# would do - the same orders, the same keys - and the test passes only when
# the tutor itself declares the course complete. If a lesson's condition
# can never be met, or a consort's captain can refuse his way into a dead
# end, these tests are where it shows.

import math

import pytest

from broadside.scenarios.base import get
from broadside.scenarios.courses import QUAY_X, QUAY_Y
from broadside.sim import components as c
from broadside.sim.actions import walk_to
from broadside.sim.entities import find_observer
from broadside.sim.systems.captain_ai import ShipCaptainAI
from broadside.sim.systems.seamanship import splice_the_mainbrace
from broadside.sim.systems.signals import make_signal
from broadside.ui.app import App


class FakeTerm:
    width, height = 190, 58

    def __getattr__(self, name):
        return lambda *a, **k: ""


def _key(run) -> str:
    t = run.tutor
    return "" if t.finished else t.lessons[t.i].key


def _bits(run):
    st = run.state
    w = st.world
    me = st.player_ship
    return (st, w, me,
            w.component_for_entity(me, c.Helm),
            w.component_for_entity(me, c.SailPlan),
            w.component_for_entity(me, c.ShipOrders))


def _bearing_to(st, me, other) -> float:
    a = st.world.component_for_entity(me, c.WorldPosition)
    b = st.world.component_for_entity(other, c.WorldPosition)
    return math.degrees(math.atan2(b.x_m - a.x_m, b.y_m - a.y_m)) % 360.0


def _range_to(st, me, other) -> float:
    a = st.world.component_for_entity(me, c.WorldPosition)
    b = st.world.component_for_entity(other, c.WorldPosition)
    return math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)


def _play(key: str, student, limit_s: float = 2400.0):
    """Run a course with a student at the controls until the tutor says it
    is finished, or the clock runs out."""
    run = get(key).build()
    app = App(run, term=FakeTerm())
    elapsed = 0.0
    while elapsed < limit_s and not run.tutor.finished:
        student(run, app)
        run.sim.run_seconds(5.0)
        elapsed += 5.0
    assert run.tutor.finished, (
        f"{key} stuck on lesson {run.tutor.i + 1} of {len(run.tutor.lessons)} "
        f"({_key(run)}) after {elapsed:.0f}s"
    )
    return run


# --- 1: handling ----------------------------------------------------------


def _handling_student(run, app):
    st, w, me, helm, sail, orders = _bits(run)
    key = _key(run)
    if key == "walk":
        cap = find_observer(w, me, "captain")
        hx, hy = w.component_for_entity(me, c.ShipBody).layout.helm
        walk_to(st, cap, (hx + 1, hy))
    elif key == "levels":
        # Look above her deck and below it, the way the lesson asks.
        from broadside.view.levels import clamp_level

        app.handle("z")
        for _ in range(8):
            app.handle("KEY_PGUP")
        for _ in range(16):
            app.handle("KEY_PGDOWN")
        app.handle("z")
        _ = clamp_level
    elif key == "steer":
        helm.waypoints = []
        helm.desired_heading = 0.0
    elif key == "canvas":
        sail.trim = 1.0
    elif key == "point_of_sail":
        helm.desired_heading = (st.wind.current.direction_degrees - 160.0) % 360.0
    elif key == "course":
        helm.waypoints = [(QUAY_X, QUAY_Y - 320.0)]
        sail.trim = 1.0
    elif key == "approach":
        # Carry sail until she is nearly there, then come in under short
        # canvas - she carries her way for sixty metres and no more, so
        # taking it all off early just stops her short of the roads.
        helm.waypoints = [(QUAY_X, QUAY_Y - 240.0)]
        p = w.component_for_entity(me, c.WorldPosition)
        sail.trim = 0.25 if math.hypot(QUAY_X - p.x_m, QUAY_Y - p.y_m) < 560.0 else 0.6
    elif key == "anchor":
        sail.trim = 0.0  # she will not lie to her anchor under sail
        if w.component_for_entity(me, c.Speed).knots <= 2.5:
            orders.anchor = True
    elif key == "weigh":
        orders.anchor = False
        if not orders.anchored and orders.anchor_work_s <= 0.0:
            sail.trim = 1.0
            helm.waypoints = [(QUAY_X, QUAY_Y - 2200.0)]


def test_mission_one_can_be_finished():
    run = _play("tutorial_1_handling", _handling_student, limit_s=3600.0)
    # And she really did come to an anchor and weigh again.
    orders = run.state.world.component_for_entity(run.state.player_ship, c.ShipOrders)
    assert not orders.anchored


# --- 2: a squadron --------------------------------------------------------


def _squadron_student(run, app):
    st, w, me, helm, sail, orders = _bits(run)
    key = _key(run)
    sent = getattr(run, "_sent", set())
    run._sent = sent

    def signal(n, whom=-1):
        tag = (n, whom)
        if tag not in sent:
            sent.add(tag)
            st.say(make_signal(st, me, n, whom), "order")

    if key == "book":
        signal(4)
    elif key == "line":
        signal(2)
    elif key == "station":
        helm.desired_heading = 90.0
    elif key == "destination":
        pos = w.component_for_entity(me, c.WorldPosition)
        helm.waypoints = [(pos.x_m + 4000.0, pos.y_m)]
        sail.trim = 1.0
    elif key == "all_sail":
        signal(5)


def test_mission_two_can_be_finished():
    run = _play("tutorial_2_squadron", _squadron_student, limit_s=3600.0)
    missions = [run.state.world.component_for_entity(s, ShipCaptainAI).mission for s in run.squadron]
    assert any(m for m in missions)


# --- 3: ship against ship -------------------------------------------------


def _duel_student(run, app):
    st, w, me, helm, sail, orders = _bits(run)
    foe = run.foe
    key = _key(run)
    if key == "sight":
        if app.look_out is None:
            app.handle("t")
        else:
            app.handle("\t")
    elif key == "approach":
        sail.trim = 1.0
        rng = _range_to(st, me, foe)
        if rng > 900.0:
            helm.desired_heading = _bearing_to(st, me, foe)
        else:
            rel = (_bearing_to(st, me, foe) - w.component_for_entity(me, c.Heading).degrees) % 360.0
            side = 90.0 if rel < 180.0 else 270.0
            helm.desired_heading = (w.component_for_entity(me, c.Heading).degrees + rel - side) % 360.0
    elif key == "quarters":
        orders.quarters = True
    elif key == "lay":
        orders.gun_target = foe
    elif key == "estimate":
        if not app.preview:
            app.handle("p")
    elif key in ("fire", "hurt"):
        rel = (_bearing_to(st, me, foe) - w.component_for_entity(me, c.Heading).degrees) % 360.0
        orders.fire_side = 1 if rel < 180.0 else -1
        if key == "hurt":
            orders.fire_at_will = True


def test_mission_three_can_be_finished():
    run = _play("tutorial_3_duel", _duel_student, limit_s=4800.0)
    assert "estimate" in run.state.did, "the gun captain's estimate is part of the course"


# --- 4: a squadron in action ---------------------------------------------


def _fleet_student(run, app):
    st, w, me, helm, sail, orders = _bits(run)
    key = _key(run)
    sent = getattr(run, "_sent", set())
    run._sent = sent

    def signal(n, whom=-1):
        tag = (n, whom)
        if tag not in sent:
            sent.add(tag)
            st.say(make_signal(st, me, n, whom), "order")

    if key == "report":
        signal(4)
    elif key == "engage":
        signal(1)
    elif key in ("stand_off", "recall", "outcome"):
        # Keep away from the enemy: steer for the opposite quarter under
        # easy sail, which is what a senior officer does.
        away = (_bearing_to(st, me, run.enemies[0]) + 180.0) % 360.0
        helm.waypoints = []
        helm.desired_heading = away
        sail.trim = 0.5
        if key == "recall":
            signal(9, run.squadron[0])


def test_mission_four_can_be_finished():
    run = _play("tutorial_4_fleet_action", _fleet_student, limit_s=6000.0)
    assert run.tutor.stood_off_s >= 45.0


# --- 5: stores and the men -----------------------------------------------


def _supplies_student(run, app):
    st, w, me, helm, sail, orders = _bits(run)
    key = _key(run)
    if key in ("stores", "stretch", "grievance"):
        orders.short_allowance = True
    elif key == "mainbrace":
        splice_the_mainbrace(st, me)
    elif key == "full":
        orders.short_allowance = False


def test_mission_five_can_be_finished():
    run = _play("tutorial_5_supplies", _supplies_student, limit_s=6000.0)
    orders = run.state.world.component_for_entity(run.state.player_ship, c.ShipOrders)
    assert not orders.short_allowance
    assert orders.spliced_at_s > 0.0


# --- the menu -------------------------------------------------------------


def test_the_menu_offers_the_missions_and_can_be_driven():
    from broadside.game import QUIT, MenuState, draw_menu
    from broadside.render.buffer import ScreenBuffer

    menu = MenuState()
    buf = ScreenBuffer(110, 44)
    draw_menu(buf, menu)
    text = "\n".join("".join(buf.get(x, y).glyph for x in range(110)) for y in range(44))
    assert "BROADSIDE" in text
    for word in ("Handling your ship", "Commanding a squadron", "Ship against ship",
                 "A squadron in action", "Stores and your people", "Free sailing", "Quit"):
        assert word in text, word
    # Arrows move, ENTER plays, digits jump, q quits.
    assert MenuState().handle("3") == "tutorial_3_duel"
    m = MenuState()
    m.handle("KEY_DOWN")
    assert m.handle("KEY_ENTER") == "tutorial_2_squadron"
    assert MenuState().handle("q") == QUIT
    # Help is a page of its own, and q comes back from it.
    m = MenuState()
    m.handle("h")
    assert m.where == "help"
    buf = ScreenBuffer(110, 44)
    draw_menu(buf, m)
    help_text = "\n".join("".join(buf.get(x, y).glyph for x in range(110)) for y in range(44))
    assert "anchor" in help_text
    m.handle("q")
    assert m.where == "main"
    # The library is a submenu with the rest of the scenarios in it.
    m = MenuState()
    while m.current.key != "library":
        m.handle("KEY_DOWN")
    m.handle("KEY_ENTER")
    assert m.where == "library" and len(m.items) > 10
    assert m.handle("q") is None and m.where == "main"


def test_every_mission_in_the_menu_is_a_real_scenario():
    from broadside.game import main_items
    from broadside.scenarios.base import REGISTRY, all_scenarios

    all_scenarios()  # registers them
    for item in main_items():
        if item.key in ("help", "quit", "library"):
            continue
        assert item.key in REGISTRY, item.key


def test_the_menu_paints_itself_on_a_real_terminal():
    """Not the MenuState but the whole display path: a blessed Terminal
    writing to a buffer, the renderer diffing against nothing, the
    fullscreen context. "Menu not displaying" was a real fault - the menu
    held the alternate screen while a mission entered it again, and after
    the mission it was painting onto a screen nobody was looking at - so
    this drives run() itself rather than the drawing alone."""
    import io as _io
    import re
    import sys as _sys

    import blessed

    from broadside import game

    out = _io.StringIO()
    term = blessed.Terminal(stream=out, force_styling=True)
    keys = iter(["KEY_DOWN", "KEY_UP", "q"])

    class Key(str):
        @property
        def is_sequence(self):
            return self.startswith("KEY_")

        @property
        def name(self):
            return str(self) if self.startswith("KEY_") else None

    term.inkey = lambda timeout=None: Key(next(keys, "q"))
    was = _sys.stdout.isatty
    _sys.stdout.isatty = lambda: True
    try:
        rc = game.run(term=term)
    finally:
        _sys.stdout.isatty = was
    assert rc == 0
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][B0]", "", out.getvalue())
    for word in ("BROADSIDE", "Handling your ship", "Stores and your people", "Quit", "q quit"):
        assert word in text, f"{word!r} never reached the terminal"


def test_the_ship_is_drawn_in_detail_at_the_zoom_the_game_opens_at():
    """Auto-fit opens a small ship at two cells to the metre, and the tile
    art has to work there. It did not: every tile was its plain glyph
    doubled, which is what "the ship is broken" looked like."""
    from broadside.render.buffer import ScreenBuffer
    from broadside.view.compose import compose

    run = get("tutorial_1_handling").build()
    run.sim.run_seconds(12)
    buf = ScreenBuffer(95, 56)
    info = compose(buf, 0, 0, 95, 56, run.state, run.deck)
    assert info.camera.cell_m <= 0.5, "auto-fit should open a cutter at two cells to the metre"
    text = "\n".join("".join(buf.get(x, y).glyph for x in range(95)) for y in range(56))
    # Her fabric, in the sub-cell forms (style.subtile), not the plain
    # glyphs of the tile table: a solid bulwark, a gun with her muzzle
    # outboard and her carriage inboard, a grating, a mast, the wheel.
    assert text.count("█") > 40, "solid bulwarks"
    assert "═" in text and "▄" in text, "muzzle and carriage"
    assert "▒" in text, "a grating"
    assert "●" in text, "a mast"
    assert "Ø" in text, "the wheel"


def test_the_chart_cross_does_not_paint_over_the_legend():
    """Her axes are an instrument, not a web of dots across the whole sea -
    and they must never land on the legend row."""
    from broadside.render.buffer import ScreenBuffer
    from broadside.view.compose import compose

    run = get("tutorial_1_handling").build()
    run.sim.run_seconds(12)
    W, H = 94, 26
    buf = ScreenBuffer(W, H)
    compose(buf, 0, 0, W, H, run.state, run.chart)
    legend = "".join(buf.get(x, H - 1).glyph for x in range(W))
    assert "m/col" in legend, legend
    for word in ("ahead", "astern", "stbd", "port"):
        assert word not in legend, f"{word!r} written over the legend: {legend!r}"
    rows = ["".join(buf.get(x, y).glyph for x in range(W)) for y in range(H)]
    marks = sum(r.count("·") + r.count(":") for r in rows)
    assert 4 < marks < 260, f"{marks} axis marks - a cross, not a web"
