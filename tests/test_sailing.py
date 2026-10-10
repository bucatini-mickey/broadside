# Headless tests for the sailing/wind physics - no terminal, no esper
# world needed for most of these, just the pure functions. Run with
# `pytest`.

import math

from broadside.sim.systems.sailing import (
    angle_off_wind,
    compute_ship_speed_knots,
    hull_speed_limit_knots,
    point_of_sail_multiplier,
)


def test_dead_upwind_makes_no_way():
    # Heading directly into a wind blowing from the same direction: "in
    # irons", should produce zero speed regardless of trim.
    speed = compute_ship_speed_knots(
        heading_degrees=0.0,
        trim=1.0,
        wind_from_degrees=0.0,
        wind_speed_knots=15.0,
        hull_length_m=30.0,
    )
    assert speed == 0.0


def test_reach_is_faster_than_close_hauled():
    close_hauled = compute_ship_speed_knots(
        heading_degrees=45.0, trim=1.0, wind_from_degrees=0.0,
        wind_speed_knots=15.0, hull_length_m=30.0,
    )
    reach = compute_ship_speed_knots(
        heading_degrees=90.0, trim=1.0, wind_from_degrees=0.0,
        wind_speed_knots=15.0, hull_length_m=30.0,
    )
    assert reach > close_hauled > 0.0


def test_zero_trim_means_no_speed():
    speed = compute_ship_speed_knots(
        heading_degrees=90.0, trim=0.0, wind_from_degrees=0.0,
        wind_speed_knots=15.0, hull_length_m=30.0,
    )
    assert speed == 0.0


def test_speed_never_exceeds_hull_speed_limit():
    # An unrealistically strong wind shouldn't push a displacement hull
    # past its hull-speed ceiling.
    speed = compute_ship_speed_knots(
        heading_degrees=100.0, trim=1.0, wind_from_degrees=0.0,
        wind_speed_knots=200.0, hull_length_m=30.0,
    )
    assert speed <= hull_speed_limit_knots(30.0) + 1e-9


def test_angle_off_wind_wraps_correctly():
    # Heading 350, wind from 10: only 20 degrees apart, not 340.
    assert math.isclose(angle_off_wind(350.0, 10.0), 20.0)
    assert math.isclose(angle_off_wind(0.0, 0.0), 0.0)
    assert math.isclose(angle_off_wind(0.0, 180.0), 180.0)


def test_point_of_sail_multiplier_is_monotonic_from_irons_to_reach():
    values = [point_of_sail_multiplier(a) for a in (0, 30, 45, 60, 90, 120)]
    assert values == sorted(values)
    assert values[0] == 0.0
