# Knowing how you lie to the enemy, and what your shot would do about it:
# relative bearings and aspect, a glass held relative to her head, the
# chart's own axes and line of fire, and the gun captain's estimate of the
# fall of shot before the word is given.

import math

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import SceneBuilder, get
from broadside.sim import components as c
from broadside.sim.systems.ballistics import Projectile, gun_to_bear, predict_shot
from broadside.ui.app import App
from broadside.view.compose import compose
from broadside.view.firstperson import ARC_FG, GLASS_FOV_DEG, Look, draw_look
from broadside.view.orientation import (
    aspect_degrees,
    aspect_short,
    aspect_words,
    range_words,
    relative_bearing,
    relative_short,
    relative_words,
)
from broadside.view.panels import UIState
from broadside.view.screen import compose_screen


class FakeTerm:
    width, height = 190, 58

    def __getattr__(self, name):
        return lambda *a, **k: ""


def to_text(buf) -> str:
    return "\n".join("".join(buf.get(x, y).glyph for x in range(buf.width)) for y in range(buf.height))


# --- the words themselves -------------------------------------------------


def test_bearings_are_given_the_way_a_lookout_gave_them():
    assert relative_bearing(90.0, 90.0) == 0.0
    assert relative_bearing(350.0, 10.0) == 20.0
    assert relative_bearing(10.0, 350.0) == -20.0
    assert relative_words(0.0) == "dead ahead"
    assert relative_words(90.0) == "on the starboard beam"
    assert relative_words(-90.0) == "on the port beam"
    assert "starboard bow" in relative_words(34.0)
    assert "three points" in relative_words(34.0)  # 34 deg is three points
    assert "port quarter" in relative_words(-135.0)
    assert relative_words(179.0) == "right astern"
    assert relative_short(45.0) == "4pt stbd bow"


def test_aspect_says_what_of_her_we_can_see():
    # She steers north; we are due south of her, so we see her stern.
    assert aspect_words(0.0, 0.0) == "stern on"
    # She steers north; we are due north of her: bows on.
    assert aspect_words(0.0, 180.0) == "bows on"
    # She steers north and bears due east of us: her port side is to us.
    assert "broadside on" in aspect_words(0.0, 90.0)
    assert "port side" in aspect_words(0.0, 90.0)
    assert abs(aspect_degrees(0.0, 90.0)) == 90.0
    assert aspect_short(0.0, 90.0) == "broadside (port)"
    assert "cables" in range_words(800.0)
    assert range_words(120.0) == "120 m"


# --- the glass --------------------------------------------------------------


def _scene():
    """Her, and an enemy lying on her starboard beam at fighting range."""
    b = SceneBuilder(21, wind_from=0.0, wind_knots=11.0)
    me = b.player("frigate_38", name="Kestrel", heading_degrees=0.0, trim=0.5, crew=120)
    b.set_speed(me, 4.0)
    foe = b.ship("brig_14", name="Vigilante", faction="french", x_m=500.0, y_m=0.0,
                 heading_degrees=0.0, trim=0.5, crew=40, observers=True)
    b.set_speed(foe, 3.0)
    run = b.build()
    return run, me, foe


def test_the_glass_is_held_relative_to_her_head_not_to_the_compass():
    """The bug: the view was pinned to a compass bearing, so every movement
    of the helm swung it off whatever you were watching."""
    run, me, _foe = _scene()
    run.sim.run_seconds(5)
    app = App(run, term=FakeTerm())
    w = run.state.world
    app.handle("t")
    for _ in range(6):
        app.handle("KEY_RIGHT")
    rel = app.look_out.relative_deg
    assert rel > 0.0, "sweeping right should look to starboard"
    assert abs(app.look_out.bearing_deg - rel) < 1.0  # heading is 0
    # Now put the helm over and let her come round.
    helm = w.component_for_entity(me, c.Helm)
    helm.waypoints = []
    helm.desired_heading = 60.0
    run.sim.run_seconds(180)
    app._sync_look()
    heading = w.component_for_entity(me, c.Heading).degrees
    assert heading > 20.0, "she must have come round for this test to mean anything"
    assert abs(app.look_out.relative_deg - rel) < 0.01, "the held bearing is relative to her"
    assert abs(((app.look_out.bearing_deg - (heading + rel)) + 180.0) % 360.0 - 180.0) < 0.01


def test_up_and_down_tilt_the_glass_instead_of_scrolling_the_log():
    """The other half of the same bug: up and down fell through to the
    panel underneath, so the glass could not be raised or lowered."""
    run, _me, _foe = _scene()
    app = App(run, term=FakeTerm())
    app.handle("t")
    before = app.ui.index if hasattr(app.ui, "index") else None
    app.handle("KEY_UP")
    app.handle("KEY_UP")
    assert app.look_out.pitch_deg > 0.0, "the glass should be looking up"
    app.handle("KEY_DOWN")
    app.handle("KEY_DOWN")
    app.handle("KEY_DOWN")
    assert app.look_out.pitch_deg < 0.0, "and down again"
    if before is not None:
        assert app.ui.index == before, "the panel underneath must not scroll"
    # And the tilt reaches the picture: the sea's horizon moves.
    run.sim.run_seconds(2)


def test_tilting_the_glass_moves_the_horizon_in_the_picture():
    run, _me, _foe = _scene()
    run.sim.run_seconds(5)
    st = run.state
    from broadside.sim.entities import find_observer
    from broadside.sim.systems.sighting import observer_eye

    eye = observer_eye(st, find_observer(st.world, st.player_ship, "captain"))

    def horizon(pitch):
        look = Look(bearing_deg=90.0, fov_deg=GLASS_FOV_DEG, glass=True)
        look.pitch_deg = pitch
        look.mark = False
        buf = ScreenBuffer(80, 30)
        draw_look(buf, 0, 0, 80, 30, st, eye, look)
        col = 40
        for row in range(30):
            if buf.get(col, row).glyph in ("~", " ", "·"):
                if buf.get(col, row).glyph != " ":
                    return row
        return -1

    level = horizon(0.0)
    up = horizon(2.0)
    assert level >= 0 and up >= 0
    assert up > level, "looking up puts the sea lower in the picture"


def test_tab_takes_a_ship_into_the_glass_and_holds_her():
    run, me, foe = _scene()
    run.sim.run_seconds(20)
    app = App(run, term=FakeTerm())
    app.handle("t")
    app.handle("\t")
    assert app.look_out.target == foe
    assert "Vigilante" in app.message
    assert "beam" in app.message or "bow" in app.message or "quarter" in app.message
    assert "broadside" in app.message or "bow" in app.message or "quarter" in app.message
    was = app.look_out.bearing_deg
    run.sim.run_seconds(90)  # both ships have moved
    app._sync_look()
    w = run.state.world
    mine = w.component_for_entity(me, c.WorldPosition)
    hers = w.component_for_entity(foe, c.WorldPosition)
    want = math.degrees(math.atan2(hers.x_m - mine.x_m, hers.y_m - mine.y_m)) % 360.0
    off = abs(((app.look_out.bearing_deg - want) + 180.0) % 360.0 - 180.0)
    assert off < 2.0, "the glass follows her"
    assert abs(app.look_out.bearing_deg - was) > 0.01, "and she has moved"
    # Sweeping by hand lets her go, as it should.
    app.handle("KEY_LEFT")
    assert app.look_out.target < 0


# --- the chart -------------------------------------------------------------


def test_the_chart_draws_her_own_axes_so_a_north_up_view_still_has_a_bow():
    run, _me, _foe = _scene()
    run.sim.run_seconds(10)
    buf = ScreenBuffer(90, 44)
    compose(buf, 0, 0, 90, 44, run.state, run.chart)
    text = to_text(buf)
    # Short labels: the cross is an instrument beside the ship, not a web
    # of dots and words across the whole sea (round 12).
    for label in ("ahead", "stbd", "port", "astern"):
        assert label in text, label


def test_the_chart_runs_a_line_of_fire_to_the_target_with_her_aspect():
    run, me, foe = _scene()
    run.sim.run_seconds(10)
    run.chart.contact = foe
    buf = ScreenBuffer(90, 44)
    compose(buf, 0, 0, 90, 44, run.state, run.chart)
    text = to_text(buf)
    assert "beam" in text
    assert "broadside" in text, "her aspect is the number that decides the broadside"


def test_the_strip_says_how_the_enemy_bears_from_us():
    run, me, foe = _scene()
    run.sim.run_seconds(10)
    run.state.world.component_for_entity(me, c.ShipOrders).gun_target = foe
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    text = to_text(buf)
    assert "guns on" in text
    assert "Vigilante" in text


# --- the fall of shot ------------------------------------------------------


def test_a_gun_can_be_laid_on_what_bears_and_not_on_what_does_not():
    run, me, foe = _scene()
    run.sim.run_seconds(5)
    w = run.state.world
    hers = w.component_for_entity(foe, c.WorldPosition)
    gi, train = gun_to_bear(run.state, me, hers.x_m, hers.y_m)
    assert gi >= 0, "a ship on the beam must bear"
    assert abs(train) < 20.0
    mine = w.component_for_entity(me, c.WorldPosition)
    ahead = (mine.x_m, mine.y_m + 2000.0)  # dead ahead: no broadside gun bears
    gi2, _t2 = gun_to_bear(run.state, me, ahead[0], ahead[1])
    assert gi2 < 0


def test_the_preview_is_a_dry_run_that_changes_nothing():
    run, me, foe = _scene()
    run.sim.run_seconds(5)
    w = run.state.world
    before = len(list(w.get_component(Projectile)))
    pos = w.component_for_entity(me, c.WorldPosition)
    was = (pos.x_m, pos.y_m)
    hers = w.component_for_entity(foe, c.WorldPosition)
    gi, train = gun_to_bear(run.state, me, hers.x_m, hers.y_m)
    for _ in range(5):
        predict_shot(run.state, me, gi, train_deg=train, target=foe, skill=0.6)
    assert len(list(w.get_component(Projectile))) == before, "nothing is fired"
    assert (pos.x_m, pos.y_m) == was


def test_elevation_tells_you_short_over_or_home():
    run, me, foe = _scene()
    run.sim.run_seconds(5)
    w = run.state.world
    hers = w.component_for_entity(foe, c.WorldPosition)
    gi, train = gun_to_bear(run.state, me, hers.x_m, hers.y_m)
    low = predict_shot(run.state, me, gi, elevation_deg=-2.0, train_deg=train, target=foe, skill=0.6)
    high = predict_shot(run.state, me, gi, elevation_deg=8.0, train_deg=train, target=foe, skill=0.6)
    assert low.graze_m < high.graze_m, "more elevation, more range"
    assert "short" in low.verdict, low.verdict
    assert "over" in high.verdict or "rigging" in high.verdict, high.verdict
    # And the estimate is the gun captain's, so his skill sets its vagueness.
    green = predict_shot(run.state, me, gi, train_deg=train, target=foe, skill=0.1)
    crack = predict_shot(run.state, me, gi, train_deg=train, target=foe, skill=0.95)
    assert green.spread_m > crack.spread_m * 2.0


def test_there_is_nobody_to_ask_until_she_is_at_quarters():
    """The estimate is the gun captain's, so it is only to be had when he
    is standing at a loaded gun - not with her guns housed and her decks
    lumbered."""
    run, me, foe = _scene()
    run.sim.run_seconds(10)
    app = App(run, term=FakeTerm())
    run.state.world.component_for_entity(me, c.ShipOrders).gun_target = foe
    app.handle("p")
    assert not app.preview
    assert "beat to quarters" in app.message.lower()
    app.handle("b")
    run.sim.run_seconds(90)  # the drums, the decks cleared, men to the guns
    app.handle("p")
    assert app.preview, app.message
    # And if the men leave the guns again, the estimate goes with them.
    run.state.world.component_for_entity(me, c.ShipOrders).quarters = False
    app._update_preview()
    assert not app.preview and app.chart.shot is None


def test_the_preview_is_drawn_on_the_chart_and_in_the_glass():
    run, me, foe = _scene()
    app = App(run, term=FakeTerm())
    run.state.world.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(90)
    run.state.world.component_for_entity(me, c.ShipOrders).gun_target = foe
    app.handle("t")
    app.handle("	")
    app.handle("p")
    assert app.preview, app.message
    app.chart.contact = foe
    # Far enough out that the splash is on the pane: laid for her range,
    # the shot grazes about where she is, six cables off.
    app.chart.macro_zoom = 5
    app._update_preview()
    assert app.chart.shot is not None
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=app.ui, look_out=app.look_out)
    text = to_text(buf)
    assert "×" in text, "the splash is marked where the shot would fall"
    assert "m ±" in text, "and how far out the estimate may be"
    arc = sum(1 for y in range(58) for x in range(95) if buf.get(x, y).fg == ARC_FG)
    assert arc > 2, "the arc of the shot is drawn through the glass"
    # Turning it off takes both away.
    app.handle("p")
    assert not app.preview and app.chart.shot is None and app.look_out.shot is None


def test_an_existing_scenario_still_renders_with_all_of_this_on():
    run = get("demo_fight").build()
    run.sim.run_seconds(30)
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    assert to_text(buf).strip()
