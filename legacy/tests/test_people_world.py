# People (generation, bodies, psyche), ship structure and stores, and world
# generation.

import random

import numpy as np

from broadside.scenarios.base import SceneBuilder
from broadside.sim import components as c
from broadside.sim.items import stores_summary
from broadside.sim.people import components as pc
from broadside.sim.people.generate import assign_roles, generate_person
from broadside.sim.people.health import wound
from broadside.sim.people.psyche import ShipMorale
from broadside.sim.structure import StructureState, damage_tile
from broadside.sim.world.terrain import WorldHeightmap
from broadside.worldgen import CampaignSetup, generate_world


def test_people_are_coherent_and_reproducible():
    a = [generate_person(random.Random(5)) for _ in range(1)][0]
    b = generate_person(random.Random(5))
    assert a.identity.full == b.identity.full and a.skills.level == b.skills.level
    rng = random.Random(11)
    crew = [generate_person(rng) for _ in range(200)]
    assign_roles(crew, rng)
    assert all(p.role for p in crew)
    landsmen = [p for p in crew if p.identity.background == "pressed_landsman"]
    seamen = [p for p in crew if p.identity.background == "merchant_seaman"]
    assert np.mean([p.skills.get("seamanship") for p in seamen]) > np.mean([p.skills.get("seamanship") for p in landsmen]) + 0.2
    assert np.mean([p.psyche.grievance for p in landsmen]) > np.mean([p.psyche.grievance for p in seamen])
    gun_captains = [p for p in crew if p.role == "Gun Captain"]
    assert gun_captains and min(p.skills.get("gunlaying") for p in gun_captains) >= np.median([p.skills.get("gunlaying") for p in crew])
    assert all(p.biography.events[0][1].startswith("Born in") for p in crew)


def _ship_with_crew():
    b = SceneBuilder(4)
    me = b.player("sloop_18", crew=30)
    return b.build(), me


def test_every_ship_carries_its_whole_company_and_stores():
    run, me = _ship_with_crew()
    w = run.state.world
    company = [e for e, cm in w.get_component(c.CrewMember) if cm.home_ship == me]
    assert len(company) >= 121  # full establishment, not just the 30 on deck
    on_deck = [e for e in company if w.has_component(e, c.DeckPosition)]
    below = [e for e in company if w.has_component(e, c.Below)]
    assert len(on_deck) >= 30 and len(below) > 80
    assert all(w.has_component(e, pc.Body) and w.has_component(e, pc.Biography) for e in company)
    stores = stores_summary(w, me)
    assert stores["fresh water"] > 20000 and stores["rum"] > 1000 and stores["gunpowder"] > 1000


def test_a_bad_wound_bleeds_a_man_to_death_and_a_small_one_clots():
    run, me = _ship_with_crew()
    st = run.state
    w = st.world
    men = [e for e, (cm, _p) in w.get_components(c.CrewMember, c.DeckPosition) if cm.ship == me]
    a, b = men[0], men[1]
    wound(st, a, "left leg", 0.95, "shot")
    wound(st, b, "left hand", 0.2, "cut")
    run.sim.run_seconds(300)
    ba, bb = w.component_for_entity(a, pc.Body), w.component_for_entity(b, pc.Body)
    assert not ba.alive and w.has_component(a, pc.Dead)
    assert bb.alive and bb.bleeding_ml_s == 0.0 and bb.blood_fraction > 0.9


def test_psyche_and_ship_morale_update():
    run, me = _ship_with_crew()
    run.sim.run_seconds(30)
    sm = run.state.world.component_for_entity(me, ShipMorale)
    assert sm.alive >= 121 and -1 <= sm.morale <= 1 and 0 <= sm.mutiny_risk <= 1


def test_planks_have_materials_and_take_damage():
    run, me = _ship_with_crew()
    st = run.state.world.component_for_entity(me, StructureState)
    lay = run.state.world.component_for_entity(me, c.ShipBody).layout
    gun = lay.guns[0]
    assert "iron" in st.condition_words(gun.x, gun.y)
    x, y = lay.captain_post
    assert "pine" in st.condition_words(x, y)
    damage_tile(st, x, y, 0.4)
    assert st.integrity[y, x] < 0.5  # pine is softer than oak


def test_world_generation_is_deterministic_and_complete():
    setup = CampaignSetup(captain="Ann Example", ship="Tenacious", nation="Carthemon")
    w1 = generate_world(21, setup)
    w2 = generate_world(21, setup)
    assert np.array_equal(w1.geo.height, w2.geo.height)
    assert [s.name for s in w1.settlements] == [s.name for s in w2.settlements]
    assert w1.player_nation.name == "Carthemon" and w1.player_captain == "Ann Example"
    assert 0.3 < w1.geo.land.mean() < 0.75
    assert len(w1.nations) >= 6 and len(w1.settlements) >= 40
    assert any(e is None and w1.player_nation.id in (a, b) for a, b, s, e in w1.history.wars)
    assert len(w1.history.events) > 200
    # The strait is open water.
    sc, sr = w1.geo.features["strait"]
    assert (w1.geo.height[sr - 1 : sr + 2, sc] < 0).any()


def test_world_terrain_bridges_to_scene_scale():
    world = generate_world(3)
    port = world.home_port()
    cell = world.geo.cell_km * 1000.0
    feat = WorldHeightmap(world.geo, (port.col + 0.5) * cell, (port.row + 0.5) * cell)
    xs, ys = np.meshgrid(np.linspace(-20000, 20000, 60), np.linspace(-20000, 20000, 60))
    code, h = feat.evaluate(xs.ravel(), ys.ravel())
    assert (h > 0).any() and (code == 0).any()  # both land and open sea near a port
