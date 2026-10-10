# Engine pieces around the tracer: deck plans, crew stations, gunnery
# smoke, sighting/contacts, camera maths, map memory and frame composition
# at both scales.

import numpy as np

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import SceneBuilder
from broadside.sim import components as c
from broadside.sim import shiplayout as sl
from broadside.sim.shipdata.loader import available_ship_classes, load_ship_class
from broadside.sim.systems.crew_tasks import bfs_path, manned_counts
from broadside.sim.world.terrain import Island
from broadside.view.camera import Camera
from broadside.view.compose import ViewState, compose
from broadside.view.export import to_text
from broadside.view.memory import MapMemory


def test_every_ship_class_builds_a_sane_deck_plan():
    for key in available_ship_classes():
        data = load_ship_class(key)
        lay = sl.build_deck_layout(data)
        assert lay.hull_length == round(data.length_m)
        assert lay.walkable.sum() > 1.5 * lay.hull_length  # room to work
        assert lay.walkable[lay.captain_post[1], lay.captain_post[0]]
        assert len(lay.guns) == data.total_guns
        assert all(lay.walkable[y, x] for g in lay.guns for (x, y) in g.crew_tiles)


def test_bfs_path_goes_around_obstacles():
    lay = sl.build_deck_layout(load_ship_class("sloop_18"))
    m = lay.masts[0]
    start, goal = (m.x - 2, m.y), (m.x + 2, m.y)
    path = bfs_path(lay.walkable, start, goal)
    assert path and path[-1] == goal
    assert all(lay.walkable[y, x] for x, y in path)
    assert (m.x, m.y) not in path


def _duel():
    b = SceneBuilder(3, wind_from=0.0, wind_knots=8.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.4, crew=50)
    foe = b.ship("frigate_38", name="Foe", x_m=0.0, y_m=-150.0, heading_degrees=90.0, trim=0.3)
    return b.build(), me, foe


def test_quarters_mans_the_guns_and_broadside_makes_smoke():
    run, me, _ = _duel()
    st = run.state
    st.world.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(40)
    manned = sum(1 for v in manned_counts(st, me).values() if v >= 2)
    assert manned >= 14
    st.world.component_for_entity(me, c.ShipOrders).fire_side = 1
    run.sim.run_seconds(5)
    assert len(st.atmosphere.smoke) >= 9
    battery = st.world.component_for_entity(me, c.Battery)
    lay = st.world.component_for_entity(me, c.ShipBody).layout
    assert not any(g.loaded for g in battery.guns if lay.guns[g.index].side == 1)
    # Smoke drifts downwind (wind from the north -> southward). Follow the
    # puffs this broadside made, by identity: taking the mean over every
    # puff in the air measures the enemy's gunfire as much as our own, and
    # her captain has a mind of his own now (systems/captain_ai.py).
    ours = list(st.atmosphere.smoke)
    before = [p.y for p in ours]
    run.sim.run_seconds(20)
    after = [p.y for p in ours]
    assert np.mean(after) < np.mean(before)
    assert all(a <= b + 1e-6 for a, b in zip(after, before)), "every puff drifts the same way"


def test_sighting_records_and_loses_contacts():
    run, me, foe = _duel()
    run.sim.run_seconds(2)
    rec = run.state.world.component_for_entity(me, c.Contacts).records[foe]
    assert rec.status == "hull"
    # Park a big island between the ships: the contact is lost but its
    # last known position is kept.
    run.state.terrain.add(Island(0.0, -75.0, 40.0, peak_m=90.0))
    run.sim.run_seconds(6)
    assert rec.status == "lost"
    assert abs(rec.y_m + 150.0) < 30.0


def test_camera_round_trip_with_rotation():
    cam = Camera(cx=100.0, cy=-50.0, cell_m=2.0, aspect=2.0, rotation=37.0)
    xs, ys = cam.grid(40, 20)
    cols, rows = cam.to_screen(xs, ys, 40, 20)
    assert (cols == np.arange(40)[None, :]).all()
    assert (rows == np.arange(20)[:, None]).all()


def test_memory_fine_marks_do_not_leak_when_zooming_in():
    mem = MapMemory()
    mem.mark(np.array([10.5]), np.array([10.5]), np.array([True]), 1.0)
    assert mem.seen(np.array([10.5]), np.array([10.5]), 1.0)[0]
    assert not mem.seen(np.array([12.5]), np.array([12.5]), 1.0)[0]
    assert mem.seen(np.array([12.5]), np.array([12.5]), 16.0)[0]  # coarse view: explored
    mem.mark(np.array([500.0]), np.array([500.0]), np.array([True]), 64.0)
    assert mem.seen(np.array([510.0]), np.array([505.0]), 1.0)[0]  # glimpsed on the chart


def test_compose_local_macro_planning_and_masthead():
    run, me, _ = _duel()
    run.sim.run_seconds(3)
    for view in (ViewState(), ViewState(scale="macro"), ViewState(paused=True), ViewState(rotation="ship", observer="lookout")):
        buf = ScreenBuffer(100, 40)
        info = compose(buf, 0, 0, 100, 40, run.state, view)
        text = to_text(buf)
        assert 0.0 < info.visible_fraction <= 1.0
        if view.scale == "local":
            # Crew read by their trade now (style.crew_glyph): the only @
            # aboard is your own captain, and he is not in every frame.
            assert "#" in text
            assert any(ch in text for ch in "@o&gtbxq,")
    # Planning mode reveals at least as much of the ship as live mode.
    def crew_count(buf):
        t = to_text(buf)
        return sum(t.count(ch) for ch in "@o&gtbxq,")

    live, plan = ScreenBuffer(100, 40), ScreenBuffer(100, 40)
    compose(live, 0, 0, 100, 40, run.state, ViewState())
    compose(plan, 0, 0, 100, 40, run.state, ViewState(paused=True))
    assert crew_count(plan) >= crew_count(live)
