# Life aboard (watches, sleep, meals, weather), limbs and feelings, and the
# three new views: walking close in, the z levels, and the glass.

import math

import numpy as np

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import SceneBuilder, get
from broadside.sim import components as c
from broadside.sim.entities import find_observer
from broadside.sim.items import stores_summary
from broadside.sim.people import components as pc
from broadside.sim.people.health import apply_tourniquet, wound
from broadside.sim.people.life import Asleep, Watch, serve_meal
from broadside.sim.people.psyche import appraise, appraise_ship
from broadside.sim.systems.sighting import observer_eye
from broadside.view.firstperson import GLASS_FOV_DEG, NAKED_FOV_DEG, Look, draw_look, ships_in_view
from broadside.view.levels import clamp_level, deck_level_of, draw_levels, level_label


def _brig(crew=40, hour=10.0):
    b = SceneBuilder(31, wind_from=0.0, wind_knots=8.0, start_hour=hour)
    me = b.player("brig_14", name="Kestrel", heading_degrees=90.0, trim=0.4, crew=crew, victual_days=20)
    return b, me


def to_text(buf) -> str:
    return "\n".join("".join(buf.get(x, y).glyph for x in range(buf.width)) for y in range(buf.height))


# --- life aboard ----------------------------------------------------------


def test_the_watch_below_goes_below_and_quarters_turns_everyone_out():
    b, me = _brig(crew=40)
    run = b.build()
    st = run.state
    w = st.world
    run.sim.run_seconds(10)
    sides = {w.component_for_entity(e, Watch).side for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, Watch)}
    assert sides == {-1, 0, 1}, sides  # two watches and the idlers
    company = [e for e, cm in w.get_component(c.CrewMember) if cm.ship == me]
    run.sim.run_seconds(60)
    below = [e for e in company if w.has_component(e, c.Below)]
    assert 0 < len(below) < len(company)
    w.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(10)
    assert not [e for e in company if w.has_component(e, c.Below)], "quarters must turn every man out"


def test_men_sleep_at_night_and_sleeping_pays_off_fatigue():
    b, me = _brig(crew=40, hour=23.0)
    run = b.build()
    st = run.state
    w = st.world
    st.atmosphere.light = 0.1
    for e, (cm, needs) in w.get_components(c.CrewMember, c.Needs):
        if cm.ship == me:
            needs.fatigue = 0.6
    run.sim.run_seconds(120)
    sleepers = [e for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, Asleep)]
    assert sleepers, "the watch below should have turned in"
    run.sim.run_seconds(600)
    rested = [w.component_for_entity(e, c.Needs).fatigue for e in sleepers if w.has_component(e, c.Needs)]
    awake = [
        w.component_for_entity(e, c.Needs).fatigue
        for e, (cm, p) in w.get_components(c.CrewMember, c.DeckPosition)
        if cm.ship == me and w.has_component(e, c.Needs)
    ]
    assert sum(rested) / len(rested) < 0.6
    assert sum(rested) / len(rested) < sum(awake) / len(awake)


def test_meals_are_eaten_out_of_the_casks():
    b, me = _brig(crew=30)
    run = b.build()
    st = run.state
    before = stores_summary(st.world, me)
    share = serve_meal(st, me, {"ship's biscuit": 1.0, "salt beef": 0.5}, 30)
    after = stores_summary(st.world, me)
    assert share > 0.9  # a well-found ship can feed her people
    assert after["ship's biscuit"] < before["ship's biscuit"]
    assert after["salt beef"] < before["salt beef"]
    # An empty ship cannot.
    from broadside.sim.items import Contents, Item, Stowed

    for _e, (item, stw, cont) in st.world.get_components(Item, Stowed, Contents):
        if stw.ship == me:
            cont.goods = {k: 0 for k in cont.goods}
    assert serve_meal(st, me, {"ship's biscuit": 1.0}, 30) == 0.0


def test_hunger_is_relieved_at_dinner_time():
    b, me = _brig(crew=20, hour=11.98)
    run = b.build()
    st = run.state
    w = st.world
    for e, (cm, needs) in w.get_components(c.CrewMember, c.Needs):
        if cm.ship == me:
            needs.hunger = 0.8
    run.sim.run_seconds(120)  # noon passes
    hunger = [w.component_for_entity(e, c.Needs).hunger for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, c.Needs)]
    assert sum(hunger) / len(hunger) < 0.6
    assert any("dinner" in e.text for e in st.log)


def test_a_squall_brings_rain_wind_and_a_shorter_horizon():
    b, me = _brig(crew=12)
    run = b.build()
    st = run.state
    clear = st.atmosphere.effective_visibility_m()
    st.atmosphere.clear_visibility_m = st.atmosphere.haze_visibility_m
    st.atmosphere.squall_until_s = st.now_s + 300.0
    st.atmosphere.squall_gust_knots = 18.0
    before_wind = st.wind.current.speed_knots
    run.sim.run_seconds(120)
    assert st.atmosphere.rain > 0.5
    assert st.atmosphere.effective_visibility_m() < clear * 0.7
    assert st.wind.current.speed_knots > before_wind + 4.0
    # And it passes off.
    st.atmosphere.squall_until_s = st.now_s
    run.sim.run_seconds(400)
    assert st.atmosphere.rain < 0.05
    assert st.atmosphere.effective_visibility_m() > clear * 0.9


# --- limbs ----------------------------------------------------------------


def test_a_limb_is_made_of_things_that_can_be_hurt_separately():
    b, me = _brig(crew=6)
    run = b.build()
    st = run.state
    w = st.world
    man = next(e for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, pc.Body))
    body = w.component_for_entity(man, pc.Body)
    assert body.capability("grip") > 0.9 and body.capability("walk") > 0.9
    part = body.parts["right hand"]
    part.fractured = True
    assert part.usable < 0.2
    assert body.capability("grip") < 0.75
    part.splinted = True
    assert part.usable > 0.3
    part.tendon_cut = True
    assert part.usable < 0.2
    # A tourniquet saves the man and costs the limb's use.
    wound(st, man, "left leg", 0.9, "shot")  # deep enough to open the artery
    leg = body.parts["left leg"]
    assert leg.artery_cut and leg.bleed_ml_s > 1.0
    assert apply_tourniquet(st, man, "left leg")
    assert leg.tourniquet and leg.usable < 0.5
    run.sim.run_seconds(40)
    assert leg.bleed_ml_s < 0.5, "a tourniquet stops the bleeding"


def test_an_opened_artery_does_not_clot_by_itself():
    b, me = _brig(crew=6)
    run = b.build()
    st = run.state
    w = st.world
    men = [e for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, pc.Body)]
    a, bb = men[0], men[1]
    wound(st, a, "left leg", 0.95, "shot")  # deep: opens the artery
    wound(st, bb, "left hand", 0.2, "splinter")  # a scratch
    assert w.component_for_entity(a, pc.Body).parts["left leg"].artery_cut
    run.sim.run_seconds(240)
    body_a = w.component_for_entity(a, pc.Body)
    body_b = w.component_for_entity(bb, pc.Body)
    scratch = body_b.parts["left hand"].bleed_ml_s
    leg = body_a.parts["left leg"].bleed_ml_s
    assert scratch < 0.1, scratch  # a small wound clots
    assert not body_a.alive or leg > scratch * 5.0  # an artery does not
    assert not body_a.alive or body_a.blood_fraction < 0.9


def test_a_hurt_man_works_a_gun_more_slowly():
    from broadside.sim import gundrill as gd

    b, me = _brig(crew=20)
    run = b.build()
    st = run.state
    w = st.world
    man = next(e for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, pc.Body))
    sound = gd.physique(w, man)
    body = w.component_for_entity(man, pc.Body)
    body.parts["right arm"].missing = True
    hurt = gd.physique(w, man)
    assert hurt < sound * 0.85
    step = gd.BY_KEY["rammed"]
    assert gd.step_time(step, skill=0.5, physique_=hurt) > gd.step_time(step, skill=0.5, physique_=sound)


# --- feelings -------------------------------------------------------------


def test_events_are_felt_and_feelings_move_morale():
    b, me = _brig(crew=10)
    run = b.build()
    st = run.state
    w = st.world
    man = next(e for e, cm in w.get_component(c.CrewMember) if cm.ship == me and w.has_component(e, pc.Psyche))
    psy = w.component_for_entity(man, pc.Psyche)
    assert psy.feeling("pride") == 0.0
    appraise(st, man, "prize_taken")
    assert psy.feeling("pride") > 0.1 and psy.feeling("hope") > 0.1
    assert psy.spirits > 0.0
    # Diminishing returns: twenty broadsides do not make him twenty times prouder.
    for _ in range(20):
        appraise(st, man, "our_broadside")
    assert psy.feeling("pride") < 1.0
    # Grief and fear pull the other way.
    appraise(st, man, "mate_killed", 3.0)
    assert psy.feeling("grief") > 0.2
    # And feelings fade.
    high = psy.feeling("pride")
    run.sim.run_seconds(600)
    assert psy.feeling("pride") < high


def test_the_whole_company_feels_a_broadside():
    b, me = _brig(crew=20)
    run = b.build()
    st = run.state
    appraise_ship(st, me, "our_broadside", 1.0)
    felt = [
        psy.feeling("pride")
        for _e, (cm, psy) in st.world.get_components(c.CrewMember, pc.Psyche)
        if cm.ship == me
    ]
    assert felt and min(felt) > 0.0


# --- the three views ------------------------------------------------------


def test_the_level_view_cuts_the_world_into_slices():
    run = get("sandbox").build()
    run.sim.run_seconds(20)
    st = run.state
    view = run.deck
    view.fit = False
    view.subcell = 1
    view.local_zoom = 2
    deck_z = deck_level_of(st, st.player_ship)
    assert deck_z > 0.0
    seen = {}
    for z in (-10.0, 0.0, deck_z, deck_z + 12.0):
        view.z_m = z
        buf = ScreenBuffer(80, 24)
        info = draw_levels(buf, 0, 0, 80, 24, st, view)
        assert abs(info.z_m - clamp_level(z)) < 1e-6
        seen[z] = to_text(buf)
    # Below the waterline there is water and her hull; at the deck, her plan;
    # above her, masts and canvas. Every level is a different picture.
    assert len(set(seen.values())) == len(seen)
    assert "the waterline" in level_label(0.0)
    assert "below" in level_label(-6.0) and "above" in level_label(6.0)
    # Her own deck level must show deck planking and her people.
    view.z_m = deck_z
    buf = ScreenBuffer(80, 24)
    draw_levels(buf, 0, 0, 80, 24, st, view)
    text = to_text(buf)
    assert any(ch in text for ch in ".o@&gt")


def test_a_hill_reads_as_rock_below_and_canopy_above():
    run = get("sandbox").build()
    run.sim.run_seconds(5)
    st = run.state
    view = run.deck
    view.fit = False
    view.subcell = 1
    view.local_zoom = 3
    view.pan = (430.0, 60.0)  # the islet in the sandbox
    view.z_m = 2.0
    low = ScreenBuffer(70, 20)
    draw_levels(low, 0, 0, 70, 20, st, view)
    view.z_m = 10.0
    high = ScreenBuffer(70, 20)
    draw_levels(high, 0, 0, 70, 20, st, view)
    assert "█" in to_text(low)  # solid rock around you down low
    assert to_text(low) != to_text(high)


def test_the_glass_shows_a_picture_and_tells_you_what_is_there():
    run = get("demo").build()
    run.sim.run_seconds(30)
    st = run.state
    cap = find_observer(st.world, st.player_ship, "captain")
    eye = observer_eye(st, cap)
    assert eye is not None
    from broadside.sim.units import bearing_degrees

    e = st.world.component_for_entity(run.enemy, c.WorldPosition)
    # From the eye, not from the ship's centre: at a cable and a half the
    # difference between the quarterdeck and the mainmast is a few degrees.
    brg = bearing_degrees(e.x_m - eye.x, e.y_m - eye.y)
    look = Look(bearing_deg=brg, fov_deg=GLASS_FOV_DEG, glass=True)
    buf = ScreenBuffer(90, 30)
    draw_look(buf, 0, 0, 90, 30, st, eye, look)
    text = to_text(buf)
    assert "█" in text, "her hull should stand against the sea"
    assert "~" in text or "·" in text, "and there should be sea under her"
    # The glass is a narrow field: she is in it, and most of the world is not.
    in_view = [ent for _d, ent, _o in ships_in_view(st, eye, look, st.world)]
    assert run.enemy in in_view
    wide = Look(bearing_deg=brg, fov_deg=NAKED_FOV_DEG)
    assert len(ships_in_view(st, eye, wide, st.world)) >= len(in_view)


def test_the_glass_is_cheap_enough_to_sweep():
    import time

    run = get("demo").build()
    run.sim.run_seconds(20)
    st = run.state
    cap = find_observer(st.world, st.player_ship, "captain")
    eye = observer_eye(st, cap)
    buf = ScreenBuffer(95, 44)
    look = Look(bearing_deg=90.0, fov_deg=GLASS_FOV_DEG, glass=True)
    draw_look(buf, 0, 0, 95, 44, st, eye, look)
    t0 = time.perf_counter()
    for i in range(4):
        look.bearing_deg = (look.bearing_deg + 5.0) % 360.0
        draw_look(buf, 0, 0, 95, 44, st, eye, look)
    per = (time.perf_counter() - t0) / 4
    assert per < 0.09, f"{per * 1000:.0f} ms a look"


def test_men_on_deck_block_the_view_of_other_men_but_not_the_horizon():
    """A body is an obstruction close to, and ignored at a distance - one
    deck level is drawn, so everyone stands at the captain's own height."""
    from broadside.sim.spatial import BODY_BAND_BOTTOM_M, BODY_BAND_TOP_M

    assert BODY_BAND_BOTTOM_M < BODY_BAND_TOP_M < 1.8
    run = get("sandbox").build()
    run.sim.run_seconds(20)
    st = run.state
    scene = st.scene()
    assert len(scene.people) > 20
    index, bbox = scene.people_index()
    assert index and bbox[2] > bbox[0]
    # A man's own square metre carries his band.
    px, py, b0, b1, _ent = scene.people[0]
    import numpy as np

    content = scene.sample(np.array([px]), np.array([py]))
    assert content.fields.over_top[0] >= b1 - 1e-6
    assert math.isfinite(content.fields.over_bottom[0])
    # And the sighting system does not see bodies at all.
    from broadside.sim.vision import direct_sampler

    f = direct_sampler(scene, include_people=False)(np.array([px]), np.array([py]))
    assert not math.isfinite(f.over_top[0]) or f.over_top[0] < b1


# --- weather as a field ---------------------------------------------------


def test_weather_is_a_field_over_the_sea_not_a_dice_roll():
    from broadside.sim.world.weather import WeatherField, weather_words

    a = WeatherField(seed=7)
    b = WeatherField(seed=7)
    xs = np.array([0.0, 50_000.0, 120_000.0])
    ys = np.array([0.0, 20_000.0, -80_000.0])
    assert np.allclose(a.cloud(xs, ys), b.cloud(xs, ys))  # same seed, same sky
    # Different quarters of the sea have different tempers.
    unsettled = a.unsettled(np.linspace(0, 400_000, 40), np.zeros(40))
    assert unsettled.max() - unsettled.min() > 0.3
    # Clouds drift: the same place has a different sky an hour later.
    before = a.cloud(xs, ys).copy()
    a.tick(3600.0, 6.0, 0.0)
    assert not np.allclose(before, a.cloud(xs, ys))
    # A cloud's shadow is a slight drop in light, not a blackout.
    shade = a.shade(xs, ys)
    assert shade.min() > 0.7 and shade.max() <= 1.0
    assert weather_words(0.0, 0.0, 0.0) == "clear"
    assert "fog" in weather_words(0.9, 0.0, 0.8)
    assert "rain" in weather_words(0.9, 0.7, 0.0)


def test_rain_needs_thick_cloud_and_fog_needs_a_damp_calm():
    from broadside.sim.world.weather import WeatherField

    f = WeatherField(seed=3)
    # Over a long reach of sea, some places rain and most do not.
    rains = [f.rain(x, 0.0) for x in range(0, 300_000, 2_000)]
    assert max(rains) > 0.2 and sum(1 for r in rains if r == 0.0) > len(rains) // 3
    # Fog wants a damp quarter and a light air: a gale blows it away.
    fogs_calm = [f.fogginess(x, 0.0, 2.0) for x in range(0, 300_000, 2_000)]
    fogs_blow = [f.fogginess(x, 0.0, 25.0) for x in range(0, 300_000, 2_000)]
    assert max(fogs_calm) > 0.1
    assert max(fogs_blow) == 0.0


def test_the_weather_arrives_rather_than_switching_on():
    run = get("sandbox").build()
    st = run.state
    atm = st.atmosphere
    assert atm.weather is not None
    first = (atm.cloud, atm.rain, atm.fog_level)
    run.sim.run_seconds(300)
    later = (atm.cloud, atm.rain, atm.fog_level)
    assert later != first  # it moves
    assert 0.0 <= atm.cloud <= 1.0 and 0.0 <= atm.rain <= 1.0
    # Rain and mist shorten the horizon; neither ever lengthens it.
    assert atm.effective_visibility_m() <= atm.clear_visibility_m * 1.01
    assert isinstance(atm.words(), str)


def test_clouds_cast_shadows_on_the_view():
    run = get("sandbox").build()
    run.sim.run_seconds(60)
    st = run.state
    chart = run.chart
    buf = ScreenBuffer(80, 24)
    from broadside.view.compose import compose

    compose(buf, 0, 0, 80, 24, st, chart)
    lums = sorted(sum(buf.get(x, y).bg or (0, 0, 0)) for y in range(24) for x in range(80))
    # Not one flat wash of sea: there is light and shade on the water.
    assert lums[-1] - lums[0] > 12
    light = st.atmosphere.light_at(np.array([0.0, 4000.0]), np.array([0.0, 4000.0]))
    assert (light <= st.atmosphere.light + 1e-9).all()


# --- your own ship is veiled, not erased ---------------------------------


def test_your_own_ship_is_veiled_rather_than_blanked_out():
    """The captain knows his own ship. Her fabric is always drawn - her
    bulwarks, her guns, her hatches - and in her own deck view nothing of
    hers is in his way: not her canvas, not her guns, and not his own
    shipmates. Before that rule his company blocked his view of his own
    deck, and the sea alongside flickered as they walked about (see
    docs/design/23_the_slice_and_what_blocks_sight.md).

    The sighting system is a different question and unchanged: being
    blinded by your own courses is real, and own_sails_blind_spot proves
    it. What is gone is a rendering artefact."""
    run = get("tutorial_demo").build()
    run.sim.run_seconds(200)  # the guns have fired; smoke everywhere
    st = run.state
    buf = ScreenBuffer(95, 50)
    from broadside.view.compose import compose

    info = compose(buf, 0, 0, 95, 50, st, run.deck)
    assert info.visible_fraction > 0.95, "his own deck is not in his own way"
    text = to_text(buf)
    hull = text.count("#") + text.count("█")
    assert hull > 40, "her bulwarks should be drawn all round"
    # Her guns and her hatches too. A gun is drawn as a line pointing
    # outboard (style.dir_glyph), which is the live path; the plain "="
    # from the tile table is what a *remembered* gun looks like. This test
    # used to assert "=", and passed only because his own crew were
    # standing between him and his own guns - so half his deck was being
    # drawn from memory. With that fixed, his guns are drawn as they are.
    # Which glyphs depends on the zoom, and both forms are correct: at a
    # metre a cell a gun is a line pointing outboard (style.dir_glyph)
    # and a hatch is "=" bars; at two cells to the metre and finer each
    # tile is drawn in sub-cell detail (style.subtile), so a gun is a
    # muzzle and a carriage and a hatch is a grating. The plain "=" from
    # the tile table is what a *remembered* gun looks like - this test
    # asserted that for five rounds, and passed only because his own
    # crew stood between him and his own guns, so half his deck was
    # being drawn from memory rather than from sight.
    guns = ("─", "│", "╱", "╲", "═", "▄")
    assert any(g in text for g in guns), "her guns"
    hatches = ("≡", "░", "▒")
    assert any(g in text for g in hatches), "her hatches"
    very_dark = sum(1 for y in range(50) for x in range(95) if sum(buf.get(x, y).bg or (0, 0, 0)) < 45)
    assert very_dark < 400, f"{very_dark} black cells - the frame should not be full of holes"



# --- the glass ------------------------------------------------------------


def test_the_glass_looks_past_your_own_ship_but_not_through_an_island():
    run = get("sandbox").build()
    run.sim.run_seconds(20)
    st = run.state
    cap = find_observer(st.world, st.player_ship, "captain")
    eye = observer_eye(st, cap)
    buf = ScreenBuffer(90, 26)
    # Along the beam, right across our own deck and rigging.
    draw_look(buf, 0, 0, 90, 26, st, eye, Look(bearing_deg=90.0, fov_deg=NAKED_FOV_DEG))
    text = to_text(buf)
    assert "\u2550" not in text, "our own deck should not be in the picture"
    assert "~" in text or "\u00b7" in text, "we should be looking at the sea"
    # But the islet to starboard still blocks what is behind it.
    from broadside.sim.units import bearing_degrees

    pos = st.world.component_for_entity(st.player_ship, c.WorldPosition)
    to_island = bearing_degrees(430.0 - pos.x_m, 60.0 - pos.y_m)
    buf2 = ScreenBuffer(90, 26)
    draw_look(buf2, 0, 0, 90, 26, st, eye, Look(bearing_deg=to_island, fov_deg=20.0))
    land = to_text(buf2)
    assert any(ch in land for ch in "\u2591\u2592\u2593\u2663"), "the islet should fill part of the view"


def test_the_chart_shows_where_the_glass_is_pointed():
    run = get("demo").build()
    run.sim.run_seconds(20)
    st = run.state
    chart = run.chart
    chart.macro_zoom = 4
    from broadside.view.compose import compose

    def dots(fov):
        # By colour, not by glyph: the chart also dots out her own beams and
        # fore-and-aft line now (compose._draw_ship_axes), and those are not
        # the look sector.
        from broadside.view.compose import SECTOR_EDGE, SECTOR_FG

        chart.look_sector = (90.0, fov)
        buf = ScreenBuffer(90, 26)
        compose(buf, 0, 0, 90, 26, st, chart)
        return [(x, y) for y in range(26) for x in range(90)
                if buf.get(x, y).fg in (SECTOR_EDGE, SECTOR_FG)]

    narrow = dots(7.0)
    wide = dots(50.0)
    assert len(narrow) > 20, "the field should be marked on the chart"
    rows_narrow = len({y for _x, y in narrow})
    rows_wide = len({y for _x, y in wide})
    assert rows_wide > rows_narrow, "a wider field must cover more of the chart"
    chart.look_sector = None
    buf = ScreenBuffer(90, 26)
    compose(buf, 0, 0, 90, 26, st, chart)
    assert not [1 for y in range(26) for x in range(90) if buf.get(x, y).glyph == "+"]
