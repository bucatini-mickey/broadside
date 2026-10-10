# Applies velocity to position: ship WorldPosition from Speed+Heading, and
# sailors' DeckPosition toward their current Wanderer target. Two very
# different scales/rates - see docs/design/01_architecture.md, "Two
# coordinate spaces" - kept in one module for the skeleton since both are
# short; split apart if either grows enough to warrant it.

from __future__ import annotations

import math

import esper

from broadside.sim import components as c

NM_PER_KNOT_PER_SECOND = 1.0 / 3600.0  # 1 knot = 1 nautical mile per hour


def ship_movement_system(world: esper.World, dt_seconds: float) -> None:
    for _entity, (pos, heading, speed, _tag) in world.get_components(
        c.WorldPosition, c.Heading, c.Speed, c.ShipTag
    ):
        distance_nm = speed.knots * NM_PER_KNOT_PER_SECOND * dt_seconds
        heading_rad = math.radians(heading.degrees)
        # Heading 0 = north = +y, 90 = east = +x (screen/world convention
        # for this project; see render/viewport.py for how this maps to
        # screen rows/columns).
        pos.x_nm += distance_nm * math.sin(heading_rad)
        pos.y_nm += distance_nm * math.cos(heading_rad)


def crew_wander_system(world: esper.World, rng, ship_grids: dict[int, tuple[int, int]]) -> None:
    """Sailors with a Wanderer component drift toward a target deck tile,
    picking a new random target (within their ship's deck bounds) once they
    arrive. This is Phase 0's placeholder for the full task-scheduling
    system described in docs/design/02_simulation_systems.md sec. 3 - it
    exists so the deck view has believable idle motion to render and to
    prove out the deck-grid movement plumbing before real tasks exist."""
    STEP_COOLDOWN = 3  # roughly one deck-tile step every 3 ticks (~0.3s at 10Hz)

    for _entity, (pos, wanderer, crew) in world.get_components(
        c.DeckPosition, c.Wanderer, c.CrewMember
    ):
        if wanderer.cooldown_ticks > 0:
            wanderer.cooldown_ticks -= 1
            continue

        width, height = ship_grids.get(crew.ship, (10, 6))

        if wanderer.target is None or wanderer.target == (pos.x, pos.y):
            wanderer.target = (
                rng.randint(1, max(1, width - 2)),
                rng.randint(1, max(1, height - 2)),
            )
            continue

        tx, ty = wanderer.target
        if pos.x < tx:
            pos.x += 1
        elif pos.x > tx:
            pos.x -= 1
        if pos.y < ty:
            pos.y += 1
        elif pos.y > ty:
            pos.y -= 1
        wanderer.cooldown_ticks = STEP_COOLDOWN
