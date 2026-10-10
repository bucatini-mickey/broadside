# Helm, sailing with inertia, movement with grounding, and the atmosphere
# tick - the ship-scale physical systems of the engine pipeline.
#
# The helm turns a ship toward a desired heading at a finite rate that
# depends on way made (a ship with no way on answers her helm sluggishly),
# and can follow waypoints, beating to windward on alternating tacks when
# the next waypoint lies inside the no-go zone. Speed approaches the polar
# curve's target with a time constant (a ship carries her way), so a tack
# genuinely costs speed as she passes through the wind.

from __future__ import annotations

import math

import numpy as np

from broadside.sim import components as c
from broadside.sim.systems.sailing import angle_off_wind, compute_ship_speed_knots
from broadside.sim.units import MS_PER_KNOT, angle_delta, bearing_degrees, heading_axes, wind_vector_ms
from broadside.sim.world.terrain import IMPASSABLE, TERRAIN_NAMES

CLOSE_HAULED_DEG = 55.0  # closest a square-rigger usefully points
TACK_HYSTERESIS_DEG = 25.0
SPEED_TIME_CONSTANT_S = 30.0  # she carries her way, and gathers it slowly
# Canvas: a full change of sail plan, bare poles to all plain sail, is the
# best part of half a minute's work for the topmen (and will become their
# actual work - see docs/design/17).
TRIM_RATE_PER_S = 0.035


def helm_system(state, dt: float) -> None:
    world = state.world
    wind_from = state.wind.current.direction_degrees
    for ent, (helm, heading, pos, speed) in world.get_components(c.Helm, c.Heading, c.WorldPosition, c.Speed):
        if helm.aground or world.has_component(ent, c.Fouled):
            continue
        if helm.waypoints:
            tx, ty = helm.waypoints[0]
            dx, dy = tx - pos.x_m, ty - pos.y_m
            if math.hypot(dx, dy) < helm.arrive_radius_m:
                wp = helm.waypoints.pop(0)
                if helm.loop:
                    helm.waypoints.append(wp)
                helm.tack_side = 0
            else:
                brg = bearing_degrees(dx, dy)
                if angle_off_wind(brg, wind_from) < CLOSE_HAULED_DEG:
                    if helm.tack_side == 0:
                        helm.tack_side = 1 if angle_delta(brg, wind_from) >= 0 else -1
                    cur = (wind_from + helm.tack_side * CLOSE_HAULED_DEG) % 360.0
                    other = (wind_from - helm.tack_side * CLOSE_HAULED_DEG) % 360.0
                    if abs(angle_delta(brg, other)) + TACK_HYSTERESIS_DEG < abs(angle_delta(brg, cur)):
                        helm.tack_side = -helm.tack_side
                        cur = other
                    helm.desired_heading = cur
                else:
                    helm.tack_side = 0
                    helm.desired_heading = brg
        delta = angle_delta(helm.desired_heading, heading.degrees)
        # A ship with no way on hardly answers her helm at all: the rudder
        # needs water flowing past it.
        answer = min(1.1, max(0.18, 0.18 + speed.knots / 6.0))
        max_step = helm.turn_rate_dps * answer * dt
        heading.degrees = (heading.degrees + max(-max_step, min(max_step, delta))) % 360.0


def sailing_inertia_system(state, dt: float) -> None:
    world = state.world
    wind = state.wind.current
    k = min(1.0, dt / SPEED_TIME_CONSTANT_S)
    for ent, (_tag, heading, sail, speed, hull) in world.get_components(c.ShipTag, c.Heading, c.SailPlan, c.Speed, c.Hull):
        # Canvas follows the order at the speed men can set or take it in.
        if sail.ordered >= 0.0:
            want = max(0.0, min(1.0, sail.ordered))
            step = TRIM_RATE_PER_S * dt
            if abs(want - sail.trim) <= step:
                sail.trim = want
                sail.ordered = -1.0
            else:
                sail.trim += step if want > sail.trim else -step
        helm = world.try_component(ent, c.Helm)
        if helm is not None and helm.aground:
            speed.knots = 0.0
            continue
        target = compute_ship_speed_knots(
            heading_degrees=heading.degrees,
            trim=sail.trim,
            wind_from_degrees=wind.direction_degrees,
            wind_speed_knots=wind.speed_knots,
            hull_length_m=hull.length_m,
            hull_integrity=hull.integrity,
        )
        speed.knots += (target - speed.knots) * k


def movement_system(state, dt: float) -> None:
    world = state.world
    for ent, (pos, heading, speed, _tag) in world.get_components(c.WorldPosition, c.Heading, c.Speed, c.ShipTag):
        if speed.knots <= 0.0:
            continue
        fx, fy, _sx, _sy = heading_axes(heading.degrees)
        d = speed.knots * MS_PER_KNOT * dt
        pos.x_m = pos.x_m + fx * d
        pos.y_m = pos.y_m + fy * d

        helm = world.try_component(ent, c.Helm)
        body = world.try_component(ent, c.ShipBody)
        if helm is None or body is None or helm.aground:
            continue
        # Grounding: sample the keel at the forefoot and midships.
        half = body.layout.hull_length / 2.0
        xs = np.array([pos.x_m + fx * half * 0.85, pos.x_m])
        ys = np.array([pos.y_m + fy * half * 0.85, pos.y_m])
        codes = state.terrain.sample(xs, ys).code
        for code in codes:
            if int(code) in IMPASSABLE:
                helm.aground = True
                speed.knots = 0.0
                name = world.try_component(ent, c.Name)
                state.say(f"{name.full if name else 'A ship'} has run aground on {TERRAIN_NAMES[int(code)]}!", "alert")
                break


def atmosphere_system(state, dt: float) -> None:
    wx, wy = wind_vector_ms(state.wind.current.direction_degrees, state.wind.current.speed_knots)
    state.atmosphere.tick(dt, wx, wy)
    pos = state.world.try_component(state.player_ship, c.WorldPosition)
    px, py = (pos.x_m, pos.y_m) if pos is not None else (0.0, 0.0)
    news = state.atmosphere.weather_tick(
        dt,
        state.now_s,
        state.rng.stream("weather"),
        x=px,
        y=py,
        wind_knots=state.wind.current.speed_knots,
        wind_vx=wx,
        wind_vy=wy,
    )
    if news.get("squall"):
        state.say(f"A squall coming up to windward - wind freshening by {news['squall']:.0f} knots, and rain with it.", "alert")
    if news.get("rain"):
        state.say("It comes on to rain.", "info")
    elif news.get("clearing"):
        state.say("The rain passes off to leeward.", "info")
    if news.get("fog"):
        state.say("Mist gathering - the horizon is closing in.", "alert")
    elif news.get("fog_clearing"):
        state.say("The mist thins and lifts.", "info")
