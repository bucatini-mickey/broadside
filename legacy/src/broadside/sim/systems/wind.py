# World wind.
#
# The full design (docs/design/02_simulation_systems.md sec. 1) calls for a
# *field* of wind cells with regional weather systems, evolving smoothly
# over time. This skeleton implements the time-evolution part only, as a
# single global wind (no spatial variation yet) - the natural first slice,
# since every other system (sailing, rendering) can be built and tested
# against "the wind" before "the wind field" exists. Promoting this to a
# per-cell grid later is additive: WindField gets a grid of these same
# (direction, speed) pairs and a sample(x, y) method: everything downstream
# that currently reads `wind_field.direction_degrees` would instead call
# `wind_field.sample(ship_x, ship_y).direction_degrees`.

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Wind:
    # Meteorological convention: the compass direction the wind is blowing
    # FROM (e.g. 0 = a northerly, blowing from north to south). This is the
    # convention sailors actually use ("the wind backed to the south-west")
    # and it's what sim/systems/sailing.py's point-of-sail math expects.
    direction_degrees: float
    speed_knots: float


@dataclass
class WindField:
    """Single global wind that drifts gradually via a simple mean-reverting
    random walk (an Ornstein-Uhlenbeck-style process), rather than jumping
    discontinuously - real wind changes gradually except in genuine squalls
    (a distinct, later mechanic per the design doc, not modelled by this
    drift)."""

    current: Wind
    mean_direction_degrees: float
    mean_speed_knots: float
    direction_volatility: float = 4.0  # degrees of random drift per tick, roughly
    speed_volatility: float = 0.3  # knots of random drift per tick, roughly
    reversion_rate: float = 0.02  # how strongly it's pulled back to the mean, per tick

    @classmethod
    def steady(
        cls,
        rng: random.Random,
        *,
        direction_degrees: float,
        speed_knots: float,
    ) -> "WindField":
        return cls(
            current=Wind(direction_degrees=direction_degrees, speed_knots=speed_knots),
            mean_direction_degrees=direction_degrees,
            mean_speed_knots=speed_knots,
        )

    def tick(self, rng: random.Random, gust_knots: float = 0.0) -> None:
        # Mean reversion pulls direction/speed back toward the regional
        # mean; gaussian noise makes it wander in between. Clamped to sane
        # ranges.
        dir_pull = _angle_delta(self.mean_direction_degrees, self.current.direction_degrees)
        self.current.direction_degrees = (
            self.current.direction_degrees
            + dir_pull * self.reversion_rate
            + rng.gauss(0.0, self.direction_volatility)
        ) % 360.0

        # A squall's gust is a target the wind runs up to, not a jump.
        target = self.mean_speed_knots + gust_knots
        speed_pull = (target - self.current.speed_knots) * (self.reversion_rate + (0.08 if gust_knots else 0.0))
        self.current.speed_knots = max(
            0.0,
            self.current.speed_knots + speed_pull + rng.gauss(0.0, self.speed_volatility * (3.0 if gust_knots else 1.0)),
        )


def _angle_delta(target: float, current: float) -> float:
    """Shortest signed delta from `current` to `target`, in degrees, so
    reversion pulls the right way around the compass (e.g. 350 -> 10 is a
    +20 pull, not a -340 one)."""
    return (target - current + 180.0) % 360.0 - 180.0
