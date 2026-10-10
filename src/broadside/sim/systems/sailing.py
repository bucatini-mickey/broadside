# Wind + heading + sail trim -> ship speed, via a polar performance curve.
#
# This is the mechanic the whole brief hinges on: you cannot sail directly
# into the wind, and speed depends on your angle to it. See
# docs/design/02_simulation_systems.md sec. 2 ("Sail plan and points of
# sail") for why a polar curve rather than a full aero/hydrodynamic model is
# the right level of fidelity here, and docs/design/06_research_references.md
# for the real-world precedent.

from __future__ import annotations

import math

import esper
import numpy as np

from broadside.sim import components as c
from broadside.sim.systems.wind import WindField

# Angle off the true wind (0 = dead into it, 180 = dead downwind) mapped to
# a speed multiplier. Interpolated with numpy.interp at runtime. Shape:
# - 0-30 degrees ("in irons"): can't make way to windward at all.
# - a ramp through close-hauled (~45 deg, the closest you can usefully sail)
# - peak on a reach (90-120 deg) - a boat's fastest point of sail
# - a slight fall-off running dead downwind (180 deg): the sails partly
#   blanket each other and there's no apparent-wind boost, a real effect on
#   square-rigged vessels in particular.
_POINT_OF_SAIL_ANGLES = [0.0, 30.0, 45.0, 60.0, 90.0, 120.0, 150.0, 165.0, 180.0]
_POINT_OF_SAIL_MULTIPLIERS = [0.0, 0.0, 0.55, 0.78, 0.97, 1.0, 0.92, 0.80, 0.70]

# Simplified "we're basically in irons" zone: within this many degrees of
# dead upwind, a ship makes no forward way at all regardless of trim.
IN_IRONS_HALF_ANGLE = 30.0

# Fraction of (multiplier * trim * wind speed) that converts to boat speed.
# A tuning constant, not a physical one - chosen so a well-trimmed sloop in
# a moderate breeze makes a plausible several knots. Adjust freely; nothing
# else depends on its exact value.
SPEED_COEFFICIENT = 0.55


def angle_off_wind(heading_degrees: float, wind_from_degrees: float) -> float:
    """Smallest angle (0-180) between the ship's heading and the direction
    the wind is coming from. 0 = sailing dead into the wind."""
    delta = abs((heading_degrees - wind_from_degrees + 180.0) % 360.0 - 180.0)
    return delta


def point_of_sail_multiplier(angle_deg: float) -> float:
    return float(np.interp(angle_deg, _POINT_OF_SAIL_ANGLES, _POINT_OF_SAIL_MULTIPLIERS))


def hull_speed_limit_knots(length_m: float) -> float:
    """The classic displacement-hull "hull speed" formula: a conventional
    (non-planing) hull is limited by the bow and stern wave it generates,
    to roughly 1.34 * sqrt(waterline length in feet) knots. A real,
    well-known naval-architecture rule of thumb - included because it ties
    a ship's actual dimensions to a believable speed ceiling for free,
    rather than an arbitrary per-class cap."""
    length_ft = length_m * 3.28084
    return 1.34 * math.sqrt(max(length_ft, 1.0))


def compute_ship_speed_knots(
    heading_degrees: float,
    trim: float,
    wind_from_degrees: float,
    wind_speed_knots: float,
    hull_length_m: float,
    hull_integrity: float = 1.0,
) -> float:
    angle = angle_off_wind(heading_degrees, wind_from_degrees)
    if angle < IN_IRONS_HALF_ANGLE:
        return 0.0
    multiplier = point_of_sail_multiplier(angle)
    raw_speed = multiplier * max(0.0, min(trim, 1.0)) * wind_speed_knots * SPEED_COEFFICIENT
    # Damaged hulls are slower and draggier - a coarse stand-in for the
    # fuller damage model in docs/design/02_simulation_systems.md.
    raw_speed *= 0.4 + 0.6 * max(0.0, min(hull_integrity, 1.0))
    return min(raw_speed, hull_speed_limit_knots(hull_length_m))


def sailing_system(world: esper.World, wind_field: WindField) -> None:
    """Update Speed for every ship from its current heading/trim and the
    current wind."""
    wind = wind_field.current
    for _entity, (ship_tag, heading, sail, speed, hull) in world.get_components(
        c.ShipTag, c.Heading, c.SailPlan, c.Speed, c.Hull
    ):
        speed.knots = compute_ship_speed_knots(
            heading_degrees=heading.degrees,
            trim=sail.trim,
            wind_from_degrees=wind.direction_degrees,
            wind_speed_knots=wind.speed_knots,
            hull_length_m=hull.length_m,
            hull_integrity=hull.integrity,
        )
