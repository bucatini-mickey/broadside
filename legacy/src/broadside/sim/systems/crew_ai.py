# Needs decay and mood derivation for individual sailors.
#
# This is Phase 0's slice of the much larger crew simulation described in
# docs/design/02_simulation_systems.md sec. 3 (skills, watches, task
# scheduling, injury, discipline are all later phases). What's here is
# deliberately small but real: needs genuinely decay over sim time, and
# mood is genuinely derived from them each tick, rather than being a
# placeholder value - the point of the skeleton is to prove this loop
# works before building the much larger system on top of it.

from __future__ import annotations

import esper

from broadside.sim import components as c

# Needs decay toward "critical" this many units per simulated hour. Tuned so
# a multi-hour watch without relief is noticeable but not catastrophic -
# real relief mechanics (sleep, meals) are a later phase; for now decay is
# soft-capped at 1.0 rather than actually starving/exhausting the sailor.
FATIGUE_PER_HOUR = 0.05
HUNGER_PER_HOUR = 0.04
THIRST_PER_HOUR = 0.06


def needs_decay_system(world: esper.World, dt_seconds: float) -> None:
    dt_hours = dt_seconds / 3600.0
    for _entity, needs in world.get_component(c.Needs):
        needs.fatigue = min(1.0, needs.fatigue + FATIGUE_PER_HOUR * dt_hours)
        needs.hunger = min(1.0, needs.hunger + HUNGER_PER_HOUR * dt_hours)
        needs.thirst = min(1.0, needs.thirst + THIRST_PER_HOUR * dt_hours)


def mood_system(world: esper.World) -> None:
    """Derive Mood from Needs each tick. Later phases add event-based
    modifiers (battle, flogging, prize money, letters from home) on top of
    this needs-driven baseline - see docs/design/02_simulation_systems.md."""
    from broadside.sim.people.components import Psyche

    for entity, needs in world.get_component(c.Needs):
        mood = world.try_component(entity, c.Mood)
        if mood is None or world.has_component(entity, Psyche):
            # People with a full psyche get their mood from it instead
            # (sim/people/psyche.py).
            continue
        # Simple weighted average of "how satisfied," rescaled to [-1, 1].
        satisfaction = 1.0 - (
            0.5 * needs.fatigue + 0.3 * needs.hunger + 0.2 * needs.thirst
        )
        mood.value = satisfaction * 2.0 - 1.0
