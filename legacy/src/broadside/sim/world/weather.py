# Weather as a place, not a dice roll.
#
# The sea has regions: a stretch where it blows hard and the sky is never
# clear, a lee under the land where it falls calm and the mist hangs about.
# So weather here is a *field* over the world, sampled wherever you ask -
# the same seed giving the same weather at the same place - with three
# scales laid over each other:
#
#   synoptic  ~70 km   whether this stretch of sea is unsettled or kindly,
#                      and whether it is a damp, foggy quarter
#   cloud      ~3 km   the clouds themselves, drifting downwind: cover,
#                      their shadows on the water, and rain under the thick
#                      ones
#   gust      ~500 m   the puffs inside a breeze
#
# Nothing here is random per tick: it is a continuous field in space and
# time, so sailing into bad weather is something you can see coming, and
# the same patch of sea behaves the same way tomorrow.
#
# The view asks for `cloud` to shade the water (clouds cast shadows - a
# slight drop in light, no more), the atmosphere asks for `rain`, `fog` and
# `gust` where the ship is, and fog banks are raised and dispersed by the
# damp field rather than placed by hand.
#
# See docs/design/09_environment.md and docs/design/18_life_aboard.md sec. 2.

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from broadside.sim.units import value_noise

SYNOPTIC_SCALE_M = 70_000.0
CLOUD_SCALE_M = 3_000.0
GUST_SCALE_M = 500.0
# Clouds drift with the wind, a little faster than the ship ever sails.
CLOUD_DRIFT_FRACTION = 1.2
# How much of the light a solid overcast takes away where its shadow falls.
CLOUD_SHADOW = 0.26
RAIN_CLOUD_THRESHOLD = 0.72
FOG_DAMP_THRESHOLD = 0.68
FOG_CALM_KNOTS = 14.0


@dataclass
class WeatherField:
    """The weather over the whole sea, as a function of place and time."""

    seed: int = 20
    # How far the cloud pattern has drifted, metres (integrated from wind).
    drift_x: float = 0.0
    drift_y: float = 0.0

    # --- the slow background -------------------------------------------

    def unsettled(self, xs, ys):
        """0..1: how stormy this stretch of sea is inclined to be."""
        return value_noise(xs, ys, SYNOPTIC_SCALE_M, self.seed + 11)

    def damp(self, xs, ys):
        """0..1: how much this quarter holds mist and fog."""
        return value_noise(xs, ys, SYNOPTIC_SCALE_M * 0.6, self.seed + 29)

    # --- what you can see ----------------------------------------------

    def cloud(self, xs, ys):
        """0..1 cloud cover, drifting downwind. Two scales so the sky has
        both weather and texture."""
        x = np.asarray(xs, dtype=np.float64) - self.drift_x
        y = np.asarray(ys, dtype=np.float64) - self.drift_y
        big = value_noise(x, y, CLOUD_SCALE_M, self.seed + 3)
        small = value_noise(x, y, CLOUD_SCALE_M * 0.3, self.seed + 7)
        base = 0.68 * big + 0.32 * small
        # Unsettled air carries more cloud; a kindly quarter clears.
        lift = (self.unsettled(x, y) - 0.5) * 0.5
        return np.clip(base + lift, 0.0, 1.0)

    def shade(self, xs, ys):
        """The factor to multiply light by: a cloud's shadow on the water."""
        return 1.0 - CLOUD_SHADOW * self.cloud(xs, ys)

    # --- what you feel --------------------------------------------------

    def rain(self, x: float, y: float) -> float:
        """Rain where the cloud is thick and the air unsettled, 0..1."""
        xs = np.array([x], dtype=np.float64)
        ys = np.array([y], dtype=np.float64)
        cloud = float(self.cloud(xs, ys)[0])
        unsettled = float(self.unsettled(xs, ys)[0])
        threshold = RAIN_CLOUD_THRESHOLD - 0.18 * unsettled
        if cloud <= threshold:
            return 0.0
        return float(min(1.0, (cloud - threshold) / max(0.05, 1.0 - threshold)))

    def fogginess(self, x: float, y: float, wind_knots: float) -> float:
        """Fog forms in damp quarters when the wind is light; a breeze
        blows it away."""
        damp = float(self.damp(np.array([x]), np.array([y]))[0])
        if damp <= FOG_DAMP_THRESHOLD:
            return 0.0
        calm = max(0.0, 1.0 - wind_knots / FOG_CALM_KNOTS)
        return float(min(1.0, (damp - FOG_DAMP_THRESHOLD) / (1.0 - FOG_DAMP_THRESHOLD) * calm))

    def gust(self, x: float, y: float) -> float:
        """-1..1 of the breeze, the puffs and lulls inside it."""
        g = float(value_noise(np.array([x - self.drift_x]), np.array([y - self.drift_y]), GUST_SCALE_M, self.seed + 5)[0])
        return (g - 0.5) * 2.0

    # --- evolution ------------------------------------------------------

    def tick(self, dt: float, wind_vx: float, wind_vy: float) -> None:
        self.drift_x += wind_vx * CLOUD_DRIFT_FRACTION * dt
        self.drift_y += wind_vy * CLOUD_DRIFT_FRACTION * dt


def weather_words(cloud: float, rain: float, fog: float) -> str:
    """What the officer of the watch would write in the log-board."""
    if fog > 0.5:
        return "thick fog"
    if fog > 0.15:
        return "hazy, mist about"
    if rain > 0.6:
        return "heavy rain"
    if rain > 0.15:
        return "rain"
    if cloud > 0.8:
        return "overcast"
    if cloud > 0.45:
        return "cloudy"
    if cloud > 0.2:
        return "fair, some cloud"
    return "clear"
