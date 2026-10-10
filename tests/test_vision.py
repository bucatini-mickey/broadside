# Line-of-sight engine: terrain occlusion, 2.5D heights, fog attenuation,
# earth curvature, thin masts - checked directly against the tracer with
# hand-built scenes, no rendering involved.

import numpy as np

from broadside.sim.spatial import Poles, SceneQuery
from broadside.sim.vision import VIS_FAINT, Eye, RasterFields, direct_sampler, trace
from broadside.sim.world.atmosphere import Atmosphere, FogBank, sigma_for_visibility
from broadside.sim.world.terrain import Island, Rock, Terrain


def _look(scene, eye, x, y, low=0.3, high=None, **kw):
    high = low if high is None else high
    s = trace(eye, np.array([x]), np.array([y]), low, high, direct_sampler(scene), step_m=1.0, haze_sigma=0.0, **kw)
    return s.low[0], s.high[0], s.solid_low[0]


def test_open_sea_is_fully_visible():
    scene = SceneQuery(Terrain(), Atmosphere())
    low, _, solid = _look(scene, Eye(0, 0, 4.0), 300, 0)
    assert low > 0.99 and not solid


def test_island_blocks_sight_behind_it():
    scene = SceneQuery(Terrain([Island(200, 0, 50, peak_m=40)]), Atmosphere())
    low, high, solid = _look(scene, Eye(0, 0, 4.0), 400, 0, low=0.3, high=20.0)
    assert low == 0.0 and high == 0.0 and solid
    # ...but not off to the side of it.
    assert _look(scene, Eye(0, 0, 4.0), 0, 400)[0] > 0.9


def test_low_rock_hides_hull_but_not_masts():
    scene = SceneQuery(Terrain([Rock(150, 0, radius=5, height_m=8.0)]), Atmosphere())
    low, high, _ = _look(scene, Eye(0, 0, 4.0), 300, 0, low=4.5, high=40.0)
    assert low < VIS_FAINT
    assert high > VIS_FAINT


def test_higher_eye_sees_over_the_rock():
    scene = SceneQuery(Terrain([Rock(150, 0, radius=5, height_m=8.0)]), Atmosphere())
    assert _look(scene, Eye(0, 0, 28.0), 300, 0, low=4.5)[0] > VIS_FAINT


def test_fog_attenuates_and_has_a_top():
    bank = FogBank(0, 0, 5000, 5000, visibility_m=100.0, top_m=40.0, edge_fraction=0.01)
    scene = SceneQuery(Terrain(), Atmosphere(fog_banks=[bank]))
    near = _look(scene, Eye(0, 0, 4.0), 20, 0)[0]
    far = _look(scene, Eye(0, 0, 4.0), 150, 0)[0]
    assert near > VIS_FAINT > far
    # A line passing well above the fog's top is unaffected.
    assert _look(scene, Eye(0, 0, 60.0), 150, 0, low=60.0)[0] > 0.99


def test_curvature_puts_distant_hull_below_horizon():
    scene = SceneQuery(Terrain(), Atmosphere())
    low, high, _ = _look(scene, Eye(0, 0, 4.0), 17000, 0, low=4.5, high=45.0, max_samples=900)
    assert low == 0.0
    assert high > 0.5


def test_thin_pole_casts_only_a_narrow_shadow():
    scene = SceneQuery(Terrain(), Atmosphere())
    poles = Poles(np.array([5.0]), np.array([0.0]), np.array([0.35]), np.array([30.0]))
    assert _look(scene, Eye(0, 0, 4.0), 100, 0, poles=poles)[0] == 0.0
    assert _look(scene, Eye(0, 0, 4.0), 100, 12, poles=poles)[0] > 0.9


def test_raster_and_direct_sampling_agree():
    scene = SceneQuery(Terrain([Island(60, 20, 25, peak_m=30)]), Atmosphere())
    eye = Eye(0, 0, 4.0)
    xs, ys = np.meshgrid(np.arange(-50, 150, 7.0), np.arange(-60, 80, 7.0))
    raster = RasterFields.build(scene, -60, -70, 1.0, 220, 160)
    a = trace(eye, xs.ravel(), ys.ravel(), 0.3, 0.3, raster, step_m=1.0, haze_sigma=0.0)
    b = trace(eye, xs.ravel(), ys.ravel(), 0.3, 0.3, direct_sampler(scene), step_m=1.0, haze_sigma=0.0)
    agree = np.mean((a.low > VIS_FAINT) == (b.low > VIS_FAINT))
    assert agree > 0.97


def test_koschmieder_visibility():
    assert abs(sigma_for_visibility(1000.0) * 1000.0 - 3.912) < 1e-9
