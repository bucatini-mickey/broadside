# Working guns by hand and by crew: the drill, its timings, laying, the
# supply of powder from the magazine, and flag signals.

from broadside.scenarios.base import SceneBuilder
from broadside.scenarios.tutorial import LESSONS
from broadside.sim import components as c
from broadside.sim import gundrill as gd
from broadside.sim.actions import Activity, available_actions, perform, walk_to
from broadside.sim.entities import find_observer
from broadside.sim.items import Contents, Item, Stowed, cartridge_lb, serve_out_ammunition, stores_summary
from broadside.sim.systems.gunnery import discharge
from broadside.sim.systems.signals import SIGNAL_BOOK, Signals, hoist


def _brig(crew: int = 30, **kw):
    b = SceneBuilder(21, wind_from=0.0, wind_knots=8.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=0.0, trim=0.3, crew=crew, victual_days=20, **kw)
    return b, me


def test_the_drill_is_nine_steps_in_order():
    keys = [s.key for s in gd.DRILL]
    assert keys == [
        "needs_sponge", "charged", "charge_rammed", "wadded", "shotted",
        "rammed", "run_out", "primed", "laid",
    ]
    gs = c.GunState(index=0)
    assert gd.ready(gs)  # as she is stowed for sea: loaded and run out
    gd.reset_after_firing(gs)
    assert not gd.ready(gs)
    # Each step in turn is the next thing wanted, and nothing may be skipped.
    for step in gd.DRILL:
        assert gd.next_step(gs) is step
        setattr(gs, step.key, step.want)
    assert gd.ready(gs)


def test_a_job_takes_longer_for_a_green_man_a_tired_one_and_a_wounded_one():
    ram = gd.BY_KEY["rammed"]
    crack = gd.step_time(ram, skill=0.85)
    green = gd.step_time(ram, skill=0.15)
    assert green > crack * 1.5
    assert gd.step_time(ram, skill=0.5, fatigue=0.9) > gd.step_time(ram, skill=0.5)
    assert gd.step_time(ram, skill=0.5, physique_=0.4) > gd.step_time(ram, skill=0.5)
    # A heavier ball is a slower lift, and a heavier gun a slower haul.
    load = gd.BY_KEY["shotted"]
    assert gd.step_time(load, shot_kg=14.5) > gd.step_time(load, shot_kg=4.1)
    run = gd.BY_KEY["run_out"]
    heavy = gd.gun_mass_kg("24-pounder long gun")
    assert gd.step_time(run, gun_kg=heavy, hands=1) > 4 * gd.step_time(run, gun_kg=heavy, hands=6)


def test_a_gun_crew_works_its_gun_and_fires_without_being_told_how():
    b, me = _brig(crew=36)
    run = b.build()
    st = run.state
    w = st.world
    battery = w.component_for_entity(me, c.Battery)
    for gs in battery.guns:
        gd.reset_after_firing(gs)
        gs.needs_sponge = False
    orders = w.component_for_entity(me, c.ShipOrders)
    orders.quarters = True
    orders.fire_at_will = True
    run.sim.run_seconds(240)
    # They took her through all nine steps unaided, and more than once:
    # nothing in this test told them how.
    salvoes = [e for e in st.log if "fire" in e.text.lower() and e.kind == "gun"]
    assert len(salvoes) >= 3, [e.text for e in st.log[-5:]]
    gun0 = battery.guns[0]
    assert gun0.needs_sponge or gun0.charged  # she is somewhere in the cycle
    assert gun0.working >= 0 or gd.ready(gun0)
    # And the work tired them: fatigue is paid for by the man who does it.
    men = gd.crew_at_guns(st, me)
    assert men, "nobody at the guns"
    worked = [w.component_for_entity(ent, c.Needs).fatigue for ent, _n in men[0]]
    assert max(worked) > 0.0


def test_the_crew_has_numbered_stations():
    b, me = _brig(crew=36)
    run = b.build()
    st = run.state
    w = st.world
    w.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(30)
    men = gd.crew_at_guns(st, me)
    assert men
    numbers = sorted(n for gun in men.values() for _e, n in gun)
    assert 1 in numbers and 2 in numbers  # a gun captain and a rammer at least


def test_cartridges_come_up_from_the_magazine_and_the_powder_goes_down():
    b, me = _brig(crew=30)
    run = b.build()
    st = run.state
    w = st.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    powder_before = stores_summary(w, me)["gunpowder"]
    served = serve_out_ammunition(w, me, layout)
    assert served > 0
    on_deck = 0
    for _e, (item, stw, cont) in w.get_components(Item, Stowed, Contents):
        if stw.ship == me and item.kind == "cartridge box":
            on_deck += cont.goods.get("powder cartridge", 0)
    assert on_deck == served
    spent = powder_before - stores_summary(w, me)["gunpowder"]
    assert spent > 0
    # Every cartridge cost its own gun's service charge, a third of the
    # weight of her shot.
    kinds = sorted({g.kind for g in layout.guns if g.on_deck})
    lo, hi = min(cartridge_lb(k) for k in kinds), max(cartridge_lb(k) for k in kinds)
    assert served * lo - 1.0 <= spent <= served * hi + 1.0


def test_a_gun_with_nothing_to_load_stands_idle_and_says_so():
    b, me = _brig(crew=36)
    run = b.build()
    st = run.state
    w = st.world
    # Empty the ship of powder and shot.
    for _e, (item, stw, cont) in w.get_components(Item, Stowed, Contents):
        if stw.ship == me:
            cont.goods = {k: 0 for k in cont.goods}
    for gs in w.component_for_entity(me, c.Battery).guns:
        gd.reset_after_firing(gs)
        gs.needs_sponge = False
    w.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(60)
    assert any("no powder" in e.text.lower() for e in st.log), [e.text for e in st.log[-4:]]


def test_laying_a_gun_solves_for_the_range_and_respects_her_arc():
    # Point blank is nearly level; a longer shot wants the quoin out.
    near = gd.solve_elevation("24-pounder long gun", 120.0, -1.0)
    far = gd.solve_elevation("24-pounder long gun", 900.0, 0.0)
    assert -1.0 < near < 1.0
    assert far > near
    b = SceneBuilder(9, wind_from=200.0, wind_knots=5.0)
    me = b.player("gunboat_24", name="Gunboat", heading_degrees=0.0, trim=0.0, crew=6, victual_days=5)
    b.wall(100.0, 0.0, 0.0, length_m=20.0, thickness_m=2.0, height_m=5.0)
    run = b.build()
    st = run.state
    w = st.world
    spec = w.component_for_entity(me, c.ShipBody).layout.guns[0]
    gs = w.component_for_entity(me, c.Battery).guns[0]
    gd.lay_gun(st, me, spec, gs, skill=0.9)
    assert gs.target != -1  # the wall lies square off her starboard side
    assert abs(gs.train_deg) < 3.0
    assert gd.MIN_ELEVATION_DEG <= gs.elevation_deg <= gd.MAX_ELEVATION_DEG
    # Something dead astern cannot be brought to bear at all.
    t = gd.train_for(0.0, 1, 0.0, 0.0, 0.0, -500.0)
    assert not gd.bears(t)


def test_the_captain_can_work_a_gun_himself_through_the_whole_drill():
    b = SceneBuilder(9, wind_from=200.0, wind_knots=5.0)
    me = b.player("gunboat_24", name="Gunboat", heading_degrees=0.0, trim=0.0, crew=1, victual_days=5)
    b.wall(100.0, 0.0, 0.0, length_m=20.0, thickness_m=2.0, height_m=5.0)
    run = b.build()
    st = run.state
    w = st.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    serve_out_ammunition(w, me, layout)
    gun = layout.guns[0]
    gs = w.component_for_entity(me, c.Battery).guns[0]
    gd.reset_after_firing(gs)
    gs.needs_sponge = False
    cap = find_observer(w, me, "captain")
    pos = w.component_for_entity(cap, c.DeckPosition)
    walk_to(st, cap, gun.crew_tiles[0])
    for _tick in range(400):
        run.sim.step()
        if (pos.x, pos.y) == tuple(gun.crew_tiles[0]):
            break
    assert (pos.x, pos.y) == tuple(gun.crew_tiles[0])
    garland = next(cont for _e, (item, stw, cont) in w.get_components(Item, Stowed, Contents) if item.kind == "shot garland")
    shot_before = sum(garland.goods.values())
    started = st.now_s
    for _ in range(12):
        step = gd.next_step(gs)
        if step is None:
            break
        labels = [a.label for a in available_actions(st, cap) if a.note != "unavailable"]
        assert any(lbl.startswith(step.label) for lbl in labels), (step.label, labels)
        assert perform(st, cap, step.label)
        for _tick in range(600):
            run.sim.step()
            if w.try_component(cap, Activity) is None:
                break
    assert gd.ready(gs)
    assert sum(garland.goods.values()) == shot_before - 1  # one ball used
    # Single-handed, the whole drill on a 24-pounder is the best part of a
    # minute and a half - most of it spent running her out.
    assert st.now_s - started > 45.0
    assert perform(st, cap, "FIRE")
    run.sim.run_seconds(1)
    assert gs.needs_sponge and not gs.run_out  # fired, and recoiled inboard


def test_signals_are_hoisted_read_and_answered():
    b, me = _brig(crew=20)
    consort = b.ship("sloop_18", name="Swift", faction="british", x_m=300.0, y_m=400.0, heading_degrees=0.0, trim=0.4, observers=True)
    run = b.build()
    st = run.state
    assert 1 in SIGNAL_BOOK
    hoist(st, me, 1)
    sig = st.world.component_for_entity(me, Signals)
    assert sig.text == SIGNAL_BOOK[1]
    assert consort not in sig.acknowledged  # she has to read it first
    run.sim.run_seconds(90)
    assert consort in sig.acknowledged
    assert any("answers the signal" in e.text for e in st.log)


def test_every_ship_has_a_signal_locker_within_reach_of_her_wheel():
    b, me = _brig(crew=12)
    run = b.build()
    w = run.state.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    hx, hy = layout.helm
    lockers = [
        (stw.x, stw.y)
        for _e, (item, stw) in w.get_components(Item, Stowed)
        if stw.ship == me and item.kind == "signal locker" and stw.x is not None
    ]
    assert lockers
    assert min(max(abs(x - hx), abs(y - hy)) for x, y in lockers) <= 1


def test_the_tutorial_course_is_well_formed():
    keys = [l.key for l in LESSONS]
    assert len(keys) == len(set(keys)) == 11
    for lesson in LESSONS:
        assert lesson.tell and lesson.praise
        assert callable(lesson.done)


def test_firing_resets_the_whole_drill():
    b, me = _brig(crew=20)
    run = b.build()
    st = run.state
    gs = st.world.component_for_entity(me, c.Battery).guns[0]
    assert gd.ready(gs)
    discharge(st, me, 0, gs)
    assert not gd.ready(gs)
    assert gd.next_step(gs).key == "needs_sponge"


def test_a_named_target_is_obeyed_but_not_instantly():
    """The captain names a mark; the gun captains take time to take it in,
    and a green one takes much longer than a good one."""
    b = SceneBuilder(9, wind_from=200.0, wind_knots=5.0)
    me = b.player("gunboat_24", name="Gunboat", heading_degrees=0.0, trim=0.0, crew=6, victual_days=5)
    near = b.wall(100.0, 0.0, 0.0, length_m=16.0, thickness_m=2.0, height_m=5.0, name="near wall")
    far = b.wall(260.0, 0.0, 0.0, length_m=16.0, thickness_m=2.0, height_m=5.0, name="far wall")
    run = b.build()
    st = run.state
    w = st.world
    spec = w.component_for_entity(me, c.ShipBody).layout.guns[0]
    gs = w.component_for_entity(me, c.Battery).guns[0]
    # Left to himself a gun captain takes the nearest thing that bears.
    gd.lay_gun(st, me, spec, gs, skill=0.8)
    assert gs.target == near
    orders = w.component_for_entity(me, c.ShipOrders)
    orders.gun_target = far
    orders.gun_target_since_s = st.now_s
    gd.lay_gun(st, me, spec, gs, skill=0.8)
    assert gs.target == near, "the word has not reached him yet"
    run.sim.run_seconds(gd.COMPREHEND_BASE_S + gd.COMPREHEND_GREEN_S + 1.0)
    gd.lay_gun(st, me, spec, gs, skill=0.8)
    assert gs.target == far
    # A green crew is still on the old mark when a crack one has shifted.
    assert gd.understood_target(st, me, 0.9) == far
    orders.gun_target_since_s = st.now_s - 10.0
    assert gd.understood_target(st, me, 0.9) == far
    assert gd.understood_target(st, me, 0.05) == -1


def test_spent_shot_is_cleared_away():
    """esper defers deletions until world.process(), which this engine never
    calls - so a battle used to leave every ball it had fired lying in the
    world, being stepped over on every tick."""
    from broadside.sim.systems.ballistics import Projectile

    b, me = _brig(crew=30)
    run = b.build()
    st = run.state
    w = st.world
    gs = w.component_for_entity(me, c.Battery).guns[0]
    for _ in range(3):
        gs.needs_sponge = False
        gs.charged = gs.charge_rammed = gs.wadded = gs.shotted = True
        gs.rammed = gs.run_out = gs.primed = gs.laid = gs.loaded = True
        discharge(st, me, gs.index, gs)
        run.sim.run_seconds(20)
    assert sum(1 for _e, _p in w.get_component(Projectile)) == 0


def test_shot_strikes_a_hull_below_the_rail_and_flies_over_above_it():
    from broadside.sim.systems.ballistics import Projectile, ballistics_system

    b, me = _brig(crew=8)
    foe = b.ship("brig_14", name="Target", faction="french", x_m=0.0, y_m=120.0, heading_degrees=90.0, trim=0.0)
    run = b.build()
    st = run.state
    w = st.world
    w.component_for_entity(me, c.Heading).degrees = 90.0
    hull = w.component_for_entity(foe, c.Hull)

    def fire(z, vz=0.0):
        ent = w.create_entity(Projectile(0.0, 100.0, z, 0.0, 300.0, vz, 4.1, 0.1, owner=me))
        p = w.component_for_entity(ent, Projectile)
        for _ in range(20):
            ballistics_system(st, 0.05)
            if not p.alive:
                break
        return p

    low = fire(2.5)  # below her rail: through the side
    assert low.fate.startswith("struck"), low.fate
    assert hull.integrity < 1.0
    high = fire(9.0)  # over everything: nothing but rigging up there
    assert not high.fate.startswith("struck"), high.fate


def test_a_ball_aboard_wounds_the_men_around_it():
    from broadside.sim.people import components as pc
    from broadside.sim.systems.ballistics import Projectile, ballistics_system

    b, me = _brig(crew=40)
    foe = b.ship("brig_14", name="Target", faction="french", x_m=0.0, y_m=120.0, heading_degrees=90.0, trim=0.0, crew=30)
    run = b.build()
    st = run.state
    w = st.world
    w.component_for_entity(me, c.Heading).degrees = 90.0
    def wounds():
        # Generated men come aboard with old scars, so count the wounds, not
        # the wounded.
        return sum(
            len(part.wounds)
            for _e, (crew, body) in w.get_components(c.CrewMember, pc.Body)
            if crew.ship == foe
            for part in body.parts.values()
        )

    before = wounds()
    for i in range(12):  # spread along her side, as a broadside would be
        ent = w.create_entity(Projectile(float(i - 6) * 2.0, 100.0, 2.5, 0.0, 320.0, 0.0, 4.1, 0.1, owner=me))
        p = w.component_for_entity(ent, Projectile)
        for _ in range(20):
            ballistics_system(st, 0.05)
            if not p.alive:
                break
    assert wounds() > before


def test_powder_and_shot_keep_coming_up_while_the_action_lasts():
    b, me = _brig(crew=36)
    run = b.build()
    st = run.state
    w = st.world
    tot = stores_summary(w, me)
    assert any("shot" in k for k in tot), "no shot locker aboard"
    # Empty a garland, beat to quarters, and the boys refill it from below.
    garland = next(cont for _e, (item, stw, cont) in w.get_components(Item, Stowed, Contents) if item.kind == "shot garland")
    kind = next(iter(garland.goods))
    garland.goods[kind] = 0
    w.component_for_entity(me, c.ShipOrders).quarters = True
    run.sim.run_seconds(2)
    assert sum(garland.goods.values()) > 0
    locker_before = sum(v for k, v in stores_summary(w, me).items() if "shot" in k)
    garland.goods[kind] = 0
    run.sim.run_seconds(60)  # the resupply comes round again
    assert sum(garland.goods.values()) > 0
    assert sum(v for k, v in stores_summary(w, me).items() if "shot" in k) <= locker_before
