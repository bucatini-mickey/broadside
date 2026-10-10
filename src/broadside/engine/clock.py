# Fixed-timestep simulation clock, decoupled from render/input rate, plus
# the period ship's-watch/bell system used for crew scheduling.
#
# See docs/design/01_architecture.md ("Fixed-timestep simulation clock").

from __future__ import annotations

from dataclasses import dataclass

# Four-hour watches, named per period convention. The Dog Watches split the
# 16:00-20:00 slot in two (First Dog / Last Dog) specifically so the watch
# rotation doesn't repeat identically every day - a real period detail with
# a real purpose, kept here because crew scheduling (later phases) is built
# around it.
WATCHES = [
    ("Middle Watch", 0, 4),
    ("Morning Watch", 4, 8),
    ("Forenoon Watch", 8, 12),
    ("Afternoon Watch", 12, 16),
    ("First Dog Watch", 16, 18),
    ("Last Dog Watch", 18, 20),
    ("First Watch", 20, 24),
]

SECONDS_PER_SIM_HOUR = 3600.0


def watch_and_bells(sim_hour_of_day: float) -> tuple[str, int]:
    """Given a time-of-day in [0, 24), return (watch name, bell count).

    Bells strike every half hour of a watch, from 1 up to 8 (8 bells marks
    the end of a watch), resetting to 1 at the start of the next watch.
    """
    hour = sim_hour_of_day % 24.0
    for name, start, end in WATCHES:
        if start <= hour < end:
            minutes_into_watch = (hour - start) * 60.0
            bell = int(minutes_into_watch // 30) + 1
            return name, min(bell, 8)
    # Unreachable given WATCHES covers [0, 24), but keep mypy/readers happy.
    return WATCHES[-1][0], 8


@dataclass
class SimClock:
    """Advances simulated time in fixed ticks, accumulated against however
    much wall-clock time has actually passed, so physics/AI behave
    identically regardless of the render frame rate.

    `time_scale` lets simulated time run faster than real time (for
    fast-forwarding a long passage) or be paused (time_scale = 0), entirely
    independent of rendering.
    """

    tick_hz: float = 10.0
    time_scale: float = 1.0
    tick_count: int = 0
    sim_seconds: float = 0.0
    _accumulator: float = 0.0

    @property
    def tick_seconds(self) -> float:
        return 1.0 / self.tick_hz

    def advance(self, wall_dt_seconds: float) -> int:
        """Feed in real elapsed wall-clock seconds; returns how many fixed
        sim ticks should now be run. Call `tick()`-equivalent logic that
        many times before rendering the next frame."""
        self._accumulator += wall_dt_seconds * self.time_scale
        ticks_to_run = 0
        step = self.tick_seconds
        while self._accumulator >= step:
            self._accumulator -= step
            self.tick_count += 1
            self.sim_seconds += step
            ticks_to_run += 1
        return ticks_to_run

    @property
    def sim_hour_of_day(self) -> float:
        return (self.sim_seconds / SECONDS_PER_SIM_HOUR) % 24.0

    @property
    def watch(self) -> str:
        return watch_and_bells(self.sim_hour_of_day)[0]

    @property
    def bells(self) -> int:
        return watch_and_bells(self.sim_hour_of_day)[1]

    def clock_display(self) -> str:
        hour = self.sim_hour_of_day
        h = int(hour)
        m = int((hour - h) * 60)
        watch, bells = watch_and_bells(hour)
        return f"{h:02d}:{m:02d} - {watch}, {bells} bell{'s' if bells != 1 else ''}"
