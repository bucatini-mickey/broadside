# A steady ship and a moving sea; the glass taking the keys from walking;
# captains with skills; and signals that carry orders to a squadron.

import io
import math

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import SceneBuilder, get
from broadside.sim import components as c
from broadside.sim.systems.captain_ai import (
    CLOSE,
    ENGAGE,
    HEAVE_TO,
    STATION,
    WITHDRAW,
    ShipCaptainAI,
    from_person,
)
from broadside.sim.systems.signals import SIGNAL_BOOK, Signals, hoist, make_signal
from broadside.ui.app import App
from broadside.view.compose import compose, sea_surface


class FakeTerm:
    width, height = 190, 50
    normal = ""

    def __init__(self):
        self.stream = io.StringIO()

    def __getattr__(self, name):
        return lambda *a, **k: ""


def _ship_cells(buf, width, height):
    """Where her bulwarks are drawn. Only the bulwarks: nobody can stand on
    them, so unlike her guns and hatches they are never covered by a man
    walking past, which makes them the honest test of whether the picture
    of the ship is holding still."""
    return {(x, y) for y in range(height) for x in range(width) if buf.get(x, y).glyph == "#"}


# --- smoothness -----------------------------------------------------------


def _steady(run, follow=None):
    """A ship on a steady helm in a steady breeze, so the only thing that
    can move the picture of her is her own progress through the water."""
    st = run.state
    w = st.world
    me = st.player_ship
    run.sim.run_seconds(20)
    helm = w.component_for_entity(me, c.Helm)
    helm.waypoints = []
    helm.desired_heading = w.component_for_entity(me, c.Heading).degrees
    st.wind.direction_volatility = 0.0
    st.wind.speed_volatility = 0.0
    st.wind.reversion_rate = 0.0
    if follow is not None:
        run.deck.follow = follow
        run.deck.fit = False
        run.deck.subcell = 5
        run.deck.square_local = True
    run.sim.run_seconds(5)
    assert w.component_for_entity(me, c.Speed).knots > 1.0, "she must be making way"
    return st


def test_the_ship_does_not_jump_about_as_she_makes_way():
    """Her position is continuous, so an unsnapped camera slid the sampling
    grid under her deck and her every plank shimmered a cell back and forth
    as she sailed. The camera now holds to her own grid."""
    run = get("night_watch").build()  # a ship alone: nothing else in the pane
    st = _steady(run)
    frames = []
    for _ in range(5):
        buf = ScreenBuffer(70, 40)
        compose(buf, 0, 0, 70, 40, st, run.deck)
        frames.append(_ship_cells(buf, 70, 40))
        run.sim.run_seconds(0.3)
    assert len(frames[0]) > 30, "her bulwarks should be drawn"
    for later in frames[1:]:
        shifted = len(later ^ frames[0]) / len(frames[0])
        # About a tenth of her bulwark cells still move at a metre a cell,
        # and that residual is a known open fault, not a tolerance: the
        # sampling lattice is rotated to her heading while her tile grid is
        # axis-aligned in her own frame, so the two drift out of phase.
        # Quantising the rendered heading to land the view axis-aligned
        # takes it to 0%, which is the evidence it is the rotation and not
        # the translation. It is item 0 in
        # docs/design/20_sighting_and_instruments_plan.md, and the
        # cask-per-cell zoom waits on it. Walk mode, where this was 31%, is
        # covered by the next test and is now 0.6%.
        assert shifted < 0.13, f"{shifted:.0%} of her bulwarks moved while she sailed"


def test_walking_the_deck_is_steady_too():
    """Walk mode is where this really told: the camera rides on the captain,
    who rides on a moving ship."""
    run = get("night_watch").build()
    from broadside.sim.entities import find_observer

    cap = find_observer(run.state.world, run.state.player_ship, "captain")
    st = _steady(run, follow=cap)

    def fabric():
        buf = ScreenBuffer(70, 40)
        compose(buf, 0, 0, 70, 40, st, run.deck)
        return {
            (x, y)
            for y in range(40)
            for x in range(70)
            if buf.get(x, y).glyph in "\u2588\u2593\u2502\u2550\u2584"
        }

    base = fabric()
    assert len(base) > 200, "close in, her fabric fills the pane"
    for _ in range(4):
        run.sim.run_seconds(0.25)
        now = fabric()
        moved = len(base ^ now) / max(1, len(base))
        assert moved < 0.04, f"{moved:.0%} of her fabric shifted in a quarter second"


def test_the_sea_runs_in_waves_that_travel():
    import numpy as np

    run = get("demo").build()
    st = run.state
    wind = st.wind.current
    xs = np.linspace(0.0, 120.0, 240)
    ys = np.zeros_like(xs)
    a = sea_surface(xs, ys, 0.0, 0.5, wind)
    b = sea_surface(xs, ys, 0.6, 0.5, wind)
    assert a.min() >= 0.0 and a.max() <= 1.0
    # It is a wave, not noise: smooth along the line, and it has moved.
    steps = np.abs(np.diff(a))
    assert steps.max() < 0.25, "no cliffs in the surface"
    assert not np.allclose(a, b), "the crests must travel"
    # And it travels at something like the speed of a wave of its length,
    # not at random: the pattern correlates with itself, shifted.
    shift = np.argmax([np.corrcoef(a[: len(a) - k], b[k:])[0, 1] for k in range(1, 40)]) + 1
    assert shift > 1, "the crests should march a measurable distance in 0.6 s"


# --- the glass takes the keys ---------------------------------------------


def test_raising_the_glass_takes_the_arrows_from_walking():
    run = get("demo").build()
    run.sim.run_seconds(10)
    app = App(run, term=FakeTerm())
    app.handle("m")
    assert app.walk
    app.handle("t")
    assert not app.walk, "you cannot walk the deck and study the horizon at once"
    assert app.look_out is not None
    was = app.look_out.bearing_deg
    app.handle("KEY_RIGHT")
    assert app.look_out.bearing_deg != was, "the arrows must sweep the glass"
    app.handle("t")
    assert app.look_out is None
    app.handle("m")
    assert app.walk  # and walking works again afterwards


# --- captains -------------------------------------------------------------


def test_a_captain_is_made_of_his_own_skills_and_character():
    from broadside.sim.people.generate import generate_person
    from broadside.engine.rng import CampaignRNG

    rng = CampaignRNG(seed=4).stream("test")
    bold = generate_person(rng, nation="british", main_culture="k0", year=1805, background="gentleman_officer")
    bold.personality.bravery = 0.95
    bold.personality.discipline = 0.2
    bold.skills.level["navigation"] = 0.9
    timid = generate_person(rng, nation="british", main_culture="k0", year=1805, background="gentleman_officer")
    timid.personality.bravery = 0.1
    timid.personality.discipline = 0.95
    timid.skills.level["navigation"] = 0.2
    a, b = from_person(bold), from_person(timid)
    assert a.aggression > b.aggression and a.caution < b.caution
    assert b.discipline > a.discipline
    assert a.skill > b.skill
    # A dull captain thinks more slowly - and that is the whole of his lag.
    slow = ShipCaptainAI(intelligence=0.0)
    quick = ShipCaptainAI(intelligence=1.0)
    assert slow.think_interval_s > quick.think_interval_s * 3
    # And a bold captain fights closer than a cautious one.
    assert ShipCaptainAI(aggression=1.0).wants_range_m < ShipCaptainAI(aggression=0.0).wants_range_m


def _duel(aggression=0.6, caution=0.3, discipline=0.7, foe_class="brig_14"):
    b = SceneBuilder(12, wind_from=0.0, wind_knots=10.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=90.0, trim=0.5, crew=24)
    b.set_speed(me, 4.0)
    foe = b.ship(foe_class, name="Vigilante", faction="french", x_m=1500.0, y_m=700.0, heading_degrees=250.0, trim=0.6, crew=16, observers=True)
    b.set_speed(foe, 4.5)
    run = b.build()
    ai = run.state.world.component_for_entity(foe, ShipCaptainAI)
    ai.aggression, ai.caution, ai.discipline, ai.intelligence, ai.skill = aggression, caution, discipline, 0.8, 0.7
    return run, me, foe, ai


def test_an_enemy_captain_finds_you_closes_and_fights():
    run, me, foe, ai = _duel(aggression=0.7)
    st = run.state
    w = st.world

    def gap():
        a = w.component_for_entity(me, c.WorldPosition)
        b_ = w.component_for_entity(foe, c.WorldPosition)
        return math.hypot(a.x_m - b_.x_m, a.y_m - b_.y_m)

    start = gap()
    run.sim.run_seconds(420)
    assert ai.mission in (ENGAGE, "chase"), ai.mission
    assert ai.target == me
    assert gap() < start - 300.0, f"he should have closed: {start:.0f} -> {gap():.0f}"
    orders = w.component_for_entity(foe, c.ShipOrders)
    assert orders.quarters and orders.fire_at_will, "and cleared for action on his own account"


def test_a_captain_hauls_off_when_he_has_had_enough():
    run, me, foe, ai = _duel(aggression=0.2, caution=0.9)
    st = run.state
    w = st.world
    run.sim.run_seconds(60)
    w.component_for_entity(foe, c.Hull).integrity = 0.4  # knocked about
    run.sim.run_seconds(40)
    assert ai.mission == WITHDRAW, ai.mission


# --- signals as orders ----------------------------------------------------


def _squadron():
    b = SceneBuilder(5, wind_from=0.0, wind_knots=10.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=90.0, trim=0.5, crew=30)
    b.set_speed(me, 4.0)
    mate = b.ship("sloop_18", name="Swift", faction="british", x_m=-700.0, y_m=300.0, heading_degrees=100.0, trim=0.5, crew=20, observers=True)
    b.set_speed(mate, 4.0)
    foe = b.ship("brig_14", name="Vigilante", faction="french", x_m=2200.0, y_m=1200.0, heading_degrees=250.0, trim=0.6, crew=0)
    run = b.build()
    ai = run.state.world.component_for_entity(mate, ShipCaptainAI)
    ai.discipline, ai.intelligence, ai.skill = 0.95, 0.8, 0.7
    return run, me, mate, foe, ai


def test_a_signal_is_made_by_a_man_and_takes_time_to_fly():
    run, me, mate, _foe, _ai = _squadron()
    st = run.state
    said = make_signal(st, me, 2)
    assert "signal locker" in said
    sig = st.world.try_component(me, Signals)
    assert sig is None or sig.hoisted == 0, "nothing is flying until he gets there"
    run.sim.run_seconds(30)
    sig = st.world.component_for_entity(me, Signals)
    assert sig.hoisted == 2


def test_form_line_of_battle_puts_a_consort_in_her_station():
    run, me, mate, _foe, ai = _squadron()
    st = run.state
    w = st.world
    run.sim.run_seconds(20)
    hoist(st, me, 2)
    run.sim.run_seconds(90)
    assert ai.mission == STATION and ai.leader == me
    assert ai.ordered_until_s > st.now_s, "an admiral's order holds him to it"

    def off_station():
        lead = w.component_for_entity(me, c.WorldPosition)
        head = w.component_for_entity(me, c.Heading).degrees
        brg = math.radians(head + ai.station_bearing)
        wx = lead.x_m + math.sin(brg) * ai.station_m
        wy = lead.y_m + math.cos(brg) * ai.station_m
        her = w.component_for_entity(mate, c.WorldPosition)
        return math.hypot(wx - her.x_m, wy - her.y_m)

    before = off_station()
    run.sim.run_seconds(420)
    assert off_station() < before, f"she should be closing her station: {before:.0f} -> {off_station():.0f}"


def test_the_book_carries_real_orders_and_an_answer():
    run, me, mate, foe, ai = _squadron()
    st = run.state
    hoist(st, me, 8)  # report your damage
    run.sim.run_seconds(60)
    assert any("answers: hull" in e.text for e in st.log), [e.text for e in st.log[-4:]]
    hoist(st, me, 10)  # anchor - she lies quiet
    run.sim.run_seconds(90)
    assert ai.mission == HEAVE_TO
    hoist(st, me, 7)  # come within hail
    run.sim.run_seconds(90)
    assert ai.mission == CLOSE and ai.target == me


def test_your_flags_do_not_command_the_enemy():
    run, me, mate, foe, _ai = _squadron()
    st = run.state
    enemy_ai = st.world.try_component(foe, ShipCaptainAI)
    hoist(st, me, 10)  # "anchor", which the enemy would be delighted to obey
    run.sim.run_seconds(120)
    sig = st.world.component_for_entity(me, Signals)
    assert foe not in sig.acknowledged
    if enemy_ai is not None:
        assert enemy_ai.mission != HEAVE_TO


def test_an_addressed_signal_is_for_one_ship_only():
    run, me, mate, _foe, ai = _squadron()
    st = run.state
    other = st.world.try_component(mate, ShipCaptainAI)
    hoist(st, me, 10, to_ship=_foe)  # addressed to another ship entirely
    run.sim.run_seconds(90)
    assert other.mission != HEAVE_TO
    hoist(st, me, 10, to_ship=mate)
    run.sim.run_seconds(90)
    assert other.mission == HEAVE_TO


def test_the_signals_panel_shows_the_book_and_the_squadron():
    run, me, mate, _foe, _ai = _squadron()
    st = run.state
    run.sim.run_seconds(10)
    app = App(run, term=FakeTerm())
    app.handle("4")
    assert app.ui.panel == "signals"
    app.handle("\t")
    app.handle("\t")
    assert app.focus == "panel"
    app.handle("a")  # address it to a particular ship
    assert app.ui.signal_to in (mate, -1)
    app.handle("KEY_DOWN")
    app.handle("KEY_ENTER")
    assert "signal locker" in app.message or "no one at hand" in app.message
    from broadside.view.screen import compose_screen

    buf = ScreenBuffer(190, 50)
    compose_screen(buf, st, app.deck, app.chart, ui=app.ui, focus="panel", footer="x")
    text = "\n".join("".join(buf.get(x, y).glyph for x in range(190)) for y in range(50))
    assert "The signal book" in text
    assert SIGNAL_BOOK[1] in text
    assert "Your squadron" in text and "Swift" in text
    assert "obedience" in text  # his parameters are on show
