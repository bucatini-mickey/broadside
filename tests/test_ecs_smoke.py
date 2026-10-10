# Smoke tests for the ECS wiring: world/ship/crew creation, and that
# running a batch of sim ticks headless doesn't blow up and produces
# sane-looking state. This is the test that most directly enforces "sim/
# must run without a terminal attached" (docs/design/01_architecture.md).

from broadside.engine.clock import SimClock, watch_and_bells
from broadside.main import build_world, run_sim_tick, _ship_grids
from broadside.sim import components as c


def test_build_world_creates_ship_and_crew():
    world, campaign_rng, ship, wind_field = build_world(seed=42)
    assert world.has_component(ship, c.ShipTag)
    crew = [e for e, _ in world.get_component(c.CrewMember)]
    assert len(crew) > 0
    for e in crew:
        assert world.component_for_entity(e, c.CrewMember).ship == ship


def test_seed_is_deterministic():
    world_a, rng_a, ship_a, wind_a = build_world(seed=7)
    world_b, rng_b, ship_b, wind_b = build_world(seed=7)
    assert wind_a.current.direction_degrees == wind_b.current.direction_degrees
    pos_a = world_a.component_for_entity(ship_a, c.WorldPosition)
    pos_b = world_b.component_for_entity(ship_b, c.WorldPosition)
    assert (pos_a.x_nm, pos_a.y_nm) == (pos_b.x_nm, pos_b.y_nm)


def test_running_many_ticks_headless_does_not_crash():
    world, campaign_rng, ship, wind_field = build_world(seed=123)
    clock = SimClock()
    grids = _ship_grids(world)

    for _ in range(300):
        run_sim_tick(world, campaign_rng, wind_field, clock.tick_seconds, grids)

    pos = world.component_for_entity(ship, c.WorldPosition)
    # After 300 ticks (30 sim seconds at 10Hz) the ship shouldn't have
    # teleported anywhere absurd.
    assert abs(pos.x_nm) < 5.0
    assert abs(pos.y_nm) < 5.0

    for _e, needs in world.get_component(c.Needs):
        assert 0.0 <= needs.fatigue <= 1.0
        assert 0.0 <= needs.hunger <= 1.0
        assert 0.0 <= needs.thirst <= 1.0

    for _e, mood in world.get_component(c.Mood):
        assert -1.0 <= mood.value <= 1.0


def test_watch_and_bells_covers_full_day():
    seen_watches = set()
    for hour in range(0, 24):
        watch, bells = watch_and_bells(hour + 0.01)
        seen_watches.add(watch)
        assert 1 <= bells <= 8
    assert len(seen_watches) == 7  # all named watches occur once per day
