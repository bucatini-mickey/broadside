# The command screen after the declutter: the status strip, the five
# panels, the crew roster, walking with the camera on the captain, and the
# pacing of helm and canvas.

import time

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import get
from broadside.sim import components as c
from broadside.sim.actions import step_actor
from broadside.sim.entities import find_observer
from broadside.ui.app import App
from broadside.view.compose import person_world_position
from broadside.view.panels import PANELS, UIState, company
from broadside.view.screen import compose_screen


class FakeTerm:
    """Just enough Terminal for App to lay out a screen in a test."""

    width, height = 190, 58

    def __getattr__(self, name):
        return lambda *a, **k: ""


def _screen(run, ui=None, focus="deck", footer="msg"):
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=ui, focus=focus, footer=footer)
    return buf


def to_text(buf) -> str:
    return "\n".join("".join(buf.get(x, y).glyph for x in range(buf.width)) for y in range(buf.height))


def test_the_screen_has_one_panel_a_strip_and_a_tab_bar():
    run = get("sandbox").build()
    run.sim.run_seconds(3)
    text = to_text(_screen(run, UIState(panel="log")))
    assert "SHIP" in text and "CHART" in text
    for tab in ("1 LOG", "2 CREW", "3 ORDERS", "4 SIGNALS", "5 SHIP", "6 KEYS"):
        assert tab in text, tab
    assert "helm" in text and "log" in text and "wind" in text  # the status strip
    assert "Log" in text


def test_every_panel_draws_and_shows_its_own_thing():
    run = get("sandbox").build()
    run.sim.run_seconds(30)
    wanted = {
        "log": "Log",
        "crew": "of the company",
        "orders": "Standing orders",
        "signals": "The signal book",
        "ship": "Binnacle",
        "keys": "Every control",
    }
    for panel in PANELS:
        text = to_text(_screen(run, UIState(panel=panel)))
        assert wanted[panel] in text, panel
    # The instruments are no longer on top of everything else.
    assert "Binnacle" not in to_text(_screen(run, UIState(panel="log")))


def test_the_crew_roster_lists_the_company_with_skills():
    run = get("sandbox").build()
    run.sim.run_seconds(5)
    people = company(run.state, run.state.player_ship)
    assert len(people) > 20
    assert any(title == "Captain" for _e, title, _n in people)
    ui = UIState(panel="crew")
    text = to_text(_screen(run, ui))
    assert "NAME" in text and "ROLE" in text and "STATION" in text
    assert "gn gl" in text  # the skill grid's headers
    first_name = people[0][2]
    assert first_name.split()[-1] in text
    assert "The man" in text  # the selected man's sheet
    # Moving the selection keeps it inside the company and changes the sheet.
    ui.move(3, len(people))
    assert ui.crew_i == 3
    ui.move(-99, len(people))
    assert ui.crew_i == 0


def test_the_keys_panel_documents_every_key_the_app_handles():
    run = get("sandbox").build()
    text = to_text(_screen(run, UIState(panel="keys")))
    for key in ("SPACE", "TAB", "1 - 6", "m", "b", "x", "q"):
        assert key in text, key


def test_the_footer_wraps_instead_of_being_cut_off():
    run = get("sandbox").build()
    long = "a message that goes on " + "and on " * 30 + "to the very end"
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState(), footer=long)
    tail = to_text(buf).splitlines()[-2:]
    assert "to the very end" in tail[1] or "to the very end" in tail[0]
    assert tail[0].strip()  # both footer lines are used


def test_walking_zooms_in_and_the_view_follows_the_captain():
    run = get("sandbox").build()
    run.sim.run_seconds(5)
    app = App(run, term=FakeTerm())
    before = (run.deck.subcell, run.deck.fit)
    app.handle("m")
    cap = find_observer(run.state.world, run.state.player_ship, "captain")
    assert app.walk and run.deck.follow == cap
    assert run.deck.subcell >= 2 and run.deck.cell_m <= 0.5  # right in close
    cam = run.deck.camera(run.state)
    spot = person_world_position(run.state, cap)
    assert spot is not None
    # Within a cell of him: the camera is snapped to the ship's own grid, so
    # that her deck does not shimmer as she makes way (see
    # tests/test_fleet_and_smoothness.py).
    near = 2.0 * run.deck.cell_m * run.deck.aspect
    assert abs(cam.cx - spot[0]) < near and abs(cam.cy - spot[1]) < near
    # He walks, the camera goes with him.
    assert step_actor(run.state, cap, 1, 0)
    moved = run.deck.camera(run.state)
    assert (moved.cx, moved.cy) != (cam.cx, cam.cy)
    spot2 = person_world_position(run.state, cap)
    assert abs(moved.cx - spot2[0]) < near
    app.handle("m")  # and stepping out puts the view back as it was
    assert not app.walk and run.deck.follow == -1
    assert (run.deck.subcell, run.deck.fit) == before


def test_panel_keys_and_focus_cycle():
    run = get("sandbox").build()
    app = App(run, term=FakeTerm())
    assert app.ui.panel == "log"
    app.handle("3")
    assert app.ui.panel == "orders"
    app.handle("2")
    assert app.ui.panel == "crew"
    assert app.focus == "deck"
    app.handle("\t")
    assert app.focus == "chart"
    app.handle("\t")
    assert app.focus == "panel"
    app.handle("\t")
    assert app.focus == "deck"


def test_making_sail_is_an_order_the_ship_takes_time_to_obey():
    run = get("sandbox").build()
    app = App(run, term=FakeTerm())
    sail = run.state.world.component_for_entity(run.state.player_ship, c.SailPlan)
    sail.trim = 0.3
    for _ in range(5):
        app.handle("w")
    assert sail.ordered > 0.7
    assert sail.trim == 0.3  # nothing has moved yet: the hands are going aloft
    run.sim.run_seconds(3)
    part_way = sail.trim
    assert 0.3 < part_way < sail.ordered
    run.sim.run_seconds(30)
    assert abs(sail.trim - 0.8) < 0.02 and sail.ordered < 0


def test_a_ship_lying_still_hardly_answers_her_helm():
    run = get("sandbox").build()
    world = run.state.world
    me = run.state.player_ship
    helm = world.component_for_entity(me, c.Helm)
    heading = world.component_for_entity(me, c.Heading)
    speed = world.component_for_entity(me, c.Speed)
    sail = world.component_for_entity(me, c.SailPlan)
    sail.trim = 0.0
    helm.desired_heading = (heading.degrees + 90.0) % 360.0
    speed.knots = 0.0
    start = heading.degrees
    run.sim.run_seconds(20)
    becalmed = abs(heading.degrees - start)
    heading.degrees = start
    speed.knots = 7.0
    run.sim.run_seconds(20)
    under_way = abs(heading.degrees - start)
    assert under_way > becalmed * 1.8, (becalmed, under_way)


def test_the_chart_is_not_redrawn_every_frame_but_the_ship_pane_is():
    run = get("sandbox").build()
    run.sim.run_seconds(10)
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    first = run.chart._cache_at_s
    run.sim.run_seconds(0.2)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    assert run.chart._cache_at_s == first  # reused
    run.sim.run_seconds(0.6)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    assert run.chart._cache_at_s > first  # and refreshed once it is stale


def test_a_frame_is_quick_enough_to_look_like_motion():
    """The whole point of the pass: the ship pane has to be redrawn often
    enough that people, canvas and water move smoothly. This is a generous
    bound - it only fails if a frame gets dramatically slower."""
    run = get("sandbox").build()
    run.sim.run_seconds(20)
    buf = ScreenBuffer(190, 58)
    compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    t0 = time.perf_counter()
    frames = 8
    for _ in range(frames):
        run.sim.run_seconds(1 / 30.0)
        compose_screen(buf, run.state, run.deck, run.chart, ui=UIState())
    per_frame = (time.perf_counter() - t0) / frames
    assert per_frame < 0.12, f"{per_frame * 1000:.0f} ms a frame"


def test_fire_as_they_bear_is_an_order_of_its_own():
    run = get("demo").build()
    app = App(run, term=FakeTerm())
    orders = run.state.world.component_for_entity(run.state.player_ship, c.ShipOrders)
    assert not orders.fire_at_will
    app.handle("F")
    assert orders.fire_at_will
    assert any("fire as they bear" in e.text.lower() for e in run.state.log)
    text = to_text(_screen(run, UIState(panel="orders")))
    assert "firing as they bear" in text
    app.handle("F")
    assert not orders.fire_at_will


def test_the_demo_opens_with_a_word_of_guidance_and_hints_as_you_go():
    run = get("demo").build()
    run.sim.run_seconds(2)
    text = " ".join(e.text for e in run.state.log)
    assert "take the deck yourself" in text and "beat to quarters" in text
    # The hints are one-shot and tied to what you actually do.
    orders = run.state.world.component_for_entity(run.state.player_ship, c.ShipOrders)
    orders.quarters = True
    run.sim.run_seconds(3)
    said = [e.text for e in run.state.log if "Cleared for action" in e.text]
    assert len(said) == 1
    run.sim.run_seconds(30)
    assert len([e.text for e in run.state.log if "Cleared for action" in e.text]) == 1


def test_time_is_locked_to_the_clock_not_the_frame_rate():
    """A faster screen must never mean a faster ship: simulated time comes
    from fixed ticks accumulated against real elapsed time."""
    run = get("sandbox").build()
    app = App(run, term=FakeTerm())
    tick = run.state.clock.tick_seconds
    # One second of wall time, fed in as one big slice or as 120 small ones.
    app.advance(1.0)
    coarse = run.state.now_s
    run.state.clock.sim_seconds = 0.0
    run.state.clock.tick_count = 0
    app._acc = 0.0
    for _ in range(120):
        app.advance(1.0 / 120.0)
    fine = run.state.now_s
    assert abs(coarse - fine) <= tick + 1e-9, (coarse, fine)
    assert abs(coarse - 1.0) <= tick
    # And time_scale is the only thing that changes the rate.
    run.state.clock.sim_seconds = 0.0
    app._acc = 0.0
    run.state.clock.time_scale = 4.0
    app.advance(1.0)
    assert abs(run.state.now_s - 4.0) <= tick


def test_the_sight_field_is_reused_for_a_moment_but_not_for_long():
    """What is visible is re-traced a few times a second, not every frame;
    everything else - people, water, the ship's position - is redrawn every
    frame. It is what the ship pane's frame rate is bought with."""
    from broadside.view.compose import SIGHT_REUSE_S, compose

    run = get("sandbox").build()
    run.sim.run_seconds(10)
    buf = ScreenBuffer(90, 40)
    compose(buf, 0, 0, 90, 40, run.state, run.deck)
    first = run.deck._sight_at_s
    assert run.deck._sight is not None
    compose(buf, 0, 0, 90, 40, run.state, run.deck)
    assert run.deck._sight_at_s == first  # reused
    run.sim.run_seconds(SIGHT_REUSE_S + 0.1)
    compose(buf, 0, 0, 90, 40, run.state, run.deck)
    assert run.deck._sight_at_s > first  # and re-traced soon after
