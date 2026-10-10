# Ballistics, voxel structures (breaking and collapse), gun handling as
# actions, and generated languages.

import math
import random

import numpy as np

from broadside.scenarios.base import SceneBuilder
from broadside.sim import components as c
from broadside.sim.actions import available_actions, walk_to
from broadside.sim.entities import find_observer
from broadside.sim.items import Contents, Item, Stowed, place_item
from broadside.sim.people.cultures import DEFAULT_KEYS, CULTURES, make_culture
from broadside.sim.people.language import make_language
from broadside.sim.systems.ballistics import Projectile, gun_ballistics
from broadside.sim.voxels import VoxelStructure, build_wall, supported


def test_gun_ballistics_are_period_plausible():
    mass, dia, v0 = gun_ballistics("24-pounder long gun")
    assert abs(mass - 10.9) < 0.2  # 24 lb
    assert 0.13 < dia < 0.15  # ~5.5 inch iron ball
    assert 440 < v0 < 470
    cm, cd, cv = gun_ballistics("32-pounder carronade")
    assert cv < v0 and cm > mass  # heavier ball, much slower


def test_wall_stands_until_its_support_is_cut():
    vs = build_wall(6.0, 1.0, 3.0, base_z_m=0.0)
    assert supported(vs)[vs.solid].all()
    nz, ny, nx = vs.shape
    m = 6
    # Knock out three blocks' width at the base: what's above can't arch it.
    vs.material[0, m : ny - m, m + 2 : m + 5] = -1
    sup = supported(vs)
    assert not sup[1, m + 1, m + 3]
    assert sup[1, m + 1, m]  # away from the hole it still stands


def _sandbox(with_wall: bool = True):
    b = SceneBuilder(9, wind_from=200.0, wind_knots=5.0)
    me = b.player("gunboat_24", name="Gunboat", heading_degrees=0.0, trim=0.0, crew=2, victual_days=5)
    if with_wall:
        # A sea wall standing in the shallows, so its base is at the
        # waterline whatever the seed's terrain does.
        b.wall(100.0, 0.0, 0.0, length_m=20.0, thickness_m=2.0, height_m=5.0)
    w = b.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    gun = layout.guns[0]
    gs = w.component_for_entity(me, c.Battery).guns[0]
    gs.loaded = gs.charged = gs.shotted = gs.primed = False
    place_item(w, me, "cartridge box", {"powder cartridge": 10}, "cartridges", 10, gun.x + 1, gun.y - 1)
    return b.build(), me, gun


def test_a_man_can_walk_to_a_gun_and_the_drill_is_offered_to_him():
    """Getting there is half of it: the actions a person has are the ones he
    can reach. Working the whole drill is tested in test_drill.py."""
    run, me, gun = _sandbox()
    st = run.state
    w = st.world
    cap = find_observer(w, st.player_ship, "captain")
    pos = w.component_for_entity(cap, c.DeckPosition)
    assert not available_actions(st, cap), "nothing to do on the quarterdeck yet"
    tx, ty = gun.crew_tiles[0]
    walk_to(st, cap, (tx, ty))
    for _ in range(600):
        run.sim.step()
        if (pos.x, pos.y) == (tx, ty):
            break
    assert (pos.x, pos.y) == (tx, ty)
    labels = [a.label for a in available_actions(st, cap)]
    assert any("powder cartridge" in lbl for lbl in labels), labels
    assert any(lbl.startswith("Train the gun") for lbl in labels)


def test_shot_flies_and_breaks_the_wall():
    run, me, gun = _sandbox()
    st = run.state
    w = st.world
    vs = next(v for _e, v in w.get_component(VoxelStructure))
    gs = w.component_for_entity(me, c.Battery).guns[0]
    gs.charged = gs.shotted = gs.primed = True
    gs.elevation_deg = 0.5
    from broadside.sim.systems.gunnery import discharge

    discharge(st, me, 0, gs)
    projectiles = [p for _e, p in w.get_component(Projectile)]
    assert len(projectiles) == 1
    p = projectiles[0]
    assert p.speed > 400 and p.energy_j > 800_000  # a 24-pounder's punch
    e0 = p.energy_j
    for _ in range(30):
        run.sim.step()
        if not p.alive or p.x > 110:
            break
    # It smashed blocks, and paid for them in energy: a 24-pounder drives
    # roughly a metre and a half into masonry before it lodges.
    assert 1 <= vs.destroyed <= 4
    assert not p.alive or p.energy_j < e0 * 0.35
    assert any(puff.kind == "dust" for puff in st.atmosphere.smoke)
    # Powder smoke at the gun as well as dust at the wall.
    assert any(puff.kind == "smoke" for puff in st.atmosphere.smoke)


def test_shot_at_a_low_angle_skips_off_the_water():
    run, me, gun = _sandbox(with_wall=False)
    st = run.state
    gs = st.world.component_for_entity(me, c.Battery).guns[0]
    gs.charged = gs.shotted = gs.primed = True
    gs.elevation_deg = -1.0  # into the sea, shallow: ricochet fire
    from broadside.sim.systems.gunnery import discharge

    discharge(st, me, 0, gs)
    p = next(p for _e, p in st.world.get_component(Projectile))
    for _ in range(40):
        run.sim.step()
        if not p.alive:
            break
    assert p.grazes >= 1


def test_generated_languages_are_distinct_and_stable():
    a = make_language(101, ["lat", "esp"])
    b = make_language(101, ["lat", "esp"])
    assert a.word("salt") == b.word("salt")  # deterministic
    c1 = make_culture("t1", 55, ["nah", "que"])
    c2 = make_culture("t2", 56, ["ger", "wel"])
    assert c1.name != c2.name
    assert set(c1.given) & set(c2.given) == set()  # different peoples, different names
    rng = random.Random(1)
    place = c1.place_name(rng)
    assert c1.meaning(place)  # every name means something
    for key in DEFAULT_KEYS:
        cult = CULTURES[key]
        assert len(cult.given) >= 40 and len(cult.family) >= 40
        assert all(len(n) >= 4 for n in cult.given)
