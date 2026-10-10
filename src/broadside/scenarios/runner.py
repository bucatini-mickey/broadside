# Headless scenario playback: step a scenario's simulation, evaluate its
# checkpoint expectations, and capture full-screen frames (scene + HUD)
# for the snapshot printer and the HTML replay exporter.

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import Scenario, ScenarioRun, split_overrides
from broadside.view.screen import compose_screen


@dataclass
class CheckResult:
    time_s: float
    label: str
    ok: bool
    detail: str


@dataclass
class Frame:
    time_s: float
    caption: str
    buffer: ScreenBuffer
    checkpoint: bool = False
    results: list = field(default_factory=list)


@dataclass
class Playback:
    scenario: Scenario
    run: ScenarioRun
    results: list
    frames: list
    wall_s: float

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)


def play(
    scn: Scenario,
    *,
    seed: Optional[int] = None,
    width: int = 190,
    height: int = 64,
    frames: bool = True,
    every_s: Optional[float] = None,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Playback:
    t0 = time.perf_counter()
    run = scn.build(seed) if seed is not None else scn.build()
    sim = run.sim
    deck, chart = run.deck, run.chart
    chart.memory = deck.memory
    events: dict[float, list] = {}
    for cp in run.checkpoints:
        events.setdefault(round(cp.time_s, 3), []).append(cp)
    if every_s:
        t = 0.0
        while t <= run.duration_s + 1e-6:
            events.setdefault(round(t, 3), [])
            t += every_s
    results: list[CheckResult] = []
    captured: list[Frame] = []
    for t in sorted(events):
        while sim.state.now_s + 1e-6 < t:
            sim.step()
        if on_progress:
            on_progress(t)
        cps = events[t]
        if not cps:
            if frames:
                buf = ScreenBuffer(width, height)
                compose_screen(buf, sim.state, deck, chart, scenario=scn, footer=_footer(scn, t, ""))
                captured.append(Frame(t, "", buf))
            continue
        for cp in cps:
            cp_results = []
            for chk in cp.checks:
                try:
                    ok, detail = chk.fn(sim.state)
                except Exception as exc:  # a broken check is a failed check
                    ok, detail = False, f"error: {exc!r}"
                cp_results.append(CheckResult(t, chk.label, bool(ok), str(detail)))
            results.extend(cp_results)
            if frames:
                d_over, c_over = split_overrides(cp.view)
                # A checkpoint may give a callable instead of a value, for
                # things that can only be worked out at the moment of the
                # snapshot - a shot prediction, say, or an entity found by
                # name in the scene.
                d_over = {k: (v(sim.state) if callable(v) else v) for k, v in d_over.items()}
                c_over = {k: (v(sim.state) if callable(v) else v) for k, v in c_over.items()}
                buf = ScreenBuffer(width, height)
                compose_screen(buf, sim.state, dataclasses.replace(deck, **d_over), dataclasses.replace(chart, **c_over), scenario=scn, footer=_footer(scn, t, cp.caption))
                captured.append(Frame(t, cp.caption, buf, checkpoint=True, results=cp_results))
    return Playback(scn, run, results, captured, time.perf_counter() - t0)


def _footer(scn: Scenario, t: float, caption: str) -> str:
    return f" [{scn.key}] t={t:5.1f}s  {caption}"
