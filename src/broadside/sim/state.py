# The simulation's top-level state and its system pipeline.
#
# SimState bundles everything a scene consists of - the ECS world plus the
# world-level singletons (clock, RNG, wind, terrain, atmosphere) and a
# human-readable event log. Simulation owns an ordered list of systems,
# each run every N ticks, and an optional scripted timeline (used by the
# test scenarios to make things happen at set times: "at t=60s the enemy
# opens fire").
#
# This is the "one pipeline" the rest of the engine hangs off: the
# interactive game, headless runs, the scenario tests and the HTML replay
# exporter all drive the exact same Simulation.step().

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import esper

from broadside.engine.clock import SimClock
from broadside.engine.events import EventBus
from broadside.engine.rng import CampaignRNG
from broadside.sim.spatial import SceneQuery
from broadside.sim.systems.wind import WindField
from broadside.sim.world.atmosphere import Atmosphere
from broadside.sim.world.terrain import Terrain


@dataclass
class LogEntry:
    time_s: float
    text: str
    kind: str = "info"  # "info" | "sight" | "order" | "gun" | "alert"


@dataclass
class SimState:
    world: esper.World
    rng: CampaignRNG
    clock: SimClock
    wind: WindField
    terrain: Terrain
    atmosphere: Atmosphere
    player_ship: int
    events: EventBus = field(default_factory=EventBus)
    log: list = field(default_factory=list)
    # Short-lived happenings other systems react to: (time_s, kind, x, y,
    # intensity) - e.g. gunfire, which frightens men nearby. Kept ~10 s.
    recent: list = field(default_factory=list)
    # Things the player did at the keyboard that leave no trace in the
    # ship's own state - raising a glass on a particular ship, asking a gun
    # captain for his estimate. {what: (when_s, subject)}. The tutor reads
    # it; nothing in the simulation depends on it.
    did: dict = field(default_factory=dict)
    # Scene clock offset so scenarios can start at a chosen time of day.
    start_hour: float = 10.0
    _scene: Optional[SceneQuery] = field(default=None, repr=False)
    _scene_tick: int = field(default=-1, repr=False)

    @property
    def now_s(self) -> float:
        return self.clock.sim_seconds

    def scene(self) -> SceneQuery:
        """A spatial query snapshot of the current tick (cached per tick)."""
        if self._scene is None or self._scene_tick != self.clock.tick_count:
            self._scene = SceneQuery.from_world(self.world, self.terrain, self.atmosphere, self.wind.current.direction_degrees)
            self._scene_tick = self.clock.tick_count
        return self._scene

    def invalidate_scene(self) -> None:
        self._scene = None

    def note(self, what: str, subject: int = -1) -> None:
        """Record a player action that the world itself would not show."""
        self.did[what] = (self.now_s, subject)

    def say(self, text: str, kind: str = "info") -> None:
        self.log.append(LogEntry(self.now_s, text, kind))
        self.events.publish("log", self.log[-1])

    def clock_text(self) -> str:
        total_h = (self.start_hour + self.now_s / 3600.0) % 24.0
        h = int(total_h)
        m = int((total_h - h) * 60)
        s = int(((total_h - h) * 60 - m) * 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


System = Callable[[SimState, float], None]


@dataclass
class ScheduledSystem:
    name: str
    fn: System
    every: int = 1  # run every N ticks; receives dt * N


@dataclass
class TimelineEvent:
    time_s: float
    fn: Callable[[SimState], None]
    label: str = ""
    done: bool = False


class Simulation:
    def __init__(self, state: SimState, systems: Optional[list[ScheduledSystem]] = None):
        self.state = state
        self.systems = systems if systems is not None else default_systems()
        self.timeline: list[TimelineEvent] = []
        self.routines: list = []  # [[interval_s, next_due_s, fn]]

    def at(self, time_s: float, fn: Callable[[SimState], None], label: str = "") -> None:
        self.timeline.append(TimelineEvent(time_s, fn, label))
        self.timeline.sort(key=lambda e: e.time_s)

    def every(self, interval_s: float, fn: Callable[[SimState], None], start_s: float = 0.0) -> None:
        """Run `fn` every `interval_s` of sim time (scripted behaviour)."""
        self.routines.append([interval_s, start_s, fn])

    def step(self) -> None:
        st = self.state
        clock = st.clock
        dt = clock.tick_seconds
        for r in self.routines:
            if st.now_s + 1e-9 >= r[1]:
                r[1] = st.now_s + r[0]
                r[2](st)
        for ev in self.timeline:
            if not ev.done and ev.time_s <= st.now_s + 1e-9:
                ev.done = True
                if ev.label:
                    st.say(ev.label, "info")
                ev.fn(st)
        tick = clock.tick_count
        for sysd in self.systems:
            if tick % sysd.every == 0:
                sysd.fn(st, dt * sysd.every)
        clock.tick_count += 1
        clock.sim_seconds += dt
        if st.recent and tick % 10 == 0:
            st.recent = [e for e in st.recent if st.now_s - e[0] < 10.0]
        st.invalidate_scene()

    def run_ticks(self, n: int) -> None:
        for _ in range(n):
            self.step()

    def run_seconds(self, seconds: float) -> None:
        self.run_ticks(int(round(seconds / self.state.clock.tick_seconds)))


def default_systems() -> list[ScheduledSystem]:
    # Imported here to keep module import order simple (systems import
    # state types for annotations only).
    from broadside.sim import actions, gundrill, voxels
    from broadside.sim.people import health, life, psyche
    from broadside.sim.systems import ballistics, boarding, captain_ai, crew_ai, crew_tasks, gunnery, navigation, seamanship, signals, sighting

    return [
        ScheduledSystem("wind", lambda st, dt: st.wind.tick(st.rng.stream("wind"), st.atmosphere.squall_gust_knots)),
        ScheduledSystem("helm", navigation.helm_system),
        ScheduledSystem("sailing", navigation.sailing_inertia_system),
        ScheduledSystem("pin_fouled", boarding.pin_fouled_system),
        ScheduledSystem("anchor", seamanship.anchor_system),
        ScheduledSystem("movement", navigation.movement_system),
        ScheduledSystem("collision", boarding.collision_system),
        ScheduledSystem("atmosphere", navigation.atmosphere_system),
        ScheduledSystem("crew_tasks", crew_tasks.crew_task_system),
        ScheduledSystem("boarding", boarding.boarding_system),
        ScheduledSystem("activities", actions.activity_system),
        ScheduledSystem("gun_drill", gundrill.gun_drill_system),
        ScheduledSystem("gunnery", gunnery.gunnery_system),
        ScheduledSystem("ballistics", ballistics.ballistics_system),
        ScheduledSystem("structures", voxels.structure_system),
        ScheduledSystem("health", health.health_system, every=2),
        ScheduledSystem("sighting", sighting.sighting_system, every=5),
        ScheduledSystem("signals", signals.signals_system, every=5),
        ScheduledSystem("captains", captain_ai.captain_ai_system, every=10),
        ScheduledSystem("needs", lambda st, dt: crew_ai.needs_decay_system(st.world, dt), every=10),
        ScheduledSystem("mood", lambda st, dt: crew_ai.mood_system(st.world), every=10),
        ScheduledSystem("psyche", psyche.psyche_system, every=10),
        ScheduledSystem("rations", seamanship.rations_system, every=30),
        ScheduledSystem("life", life.life_system, every=30),
    ]
