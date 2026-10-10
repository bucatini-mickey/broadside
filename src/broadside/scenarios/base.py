# Scenario framework: small, self-contained test environments.
#
# A scenario builds a scene (terrain, weather, ships, crews), optionally
# scripts events on a timeline ("at t=40 s the enemy fires"), and declares
# checkpoints: moments worth looking at, each with a caption saying what to
# look for, the view to look at it in, and machine-checkable expectations.
#
# The same scenario object serves four purposes:
#   - play it interactively   (python -m broadside.scenarios run <key>)
#   - snapshot it headless    (python -m broadside.scenarios snapshot <key>)
#   - export an HTML replay   (python -m broadside.scenarios replay)
#   - test it                 (pytest tests/test_scenarios.py)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import esper

from broadside.engine.clock import SimClock
from broadside.engine.rng import CampaignRNG
from broadside.sim import components as c
from broadside.sim.entities import find_observer, spawn_ship
from broadside.sim.state import SimState, Simulation
from broadside.sim.systems.wind import WindField
from broadside.sim.world.atmosphere import Atmosphere, FogBank
from broadside.sim.world.weather import WeatherField
from broadside.sim.world.terrain import Coast, Island, Rock, Terrain
from broadside.view.compose import ViewState


@dataclass
class Check:
    label: str
    fn: Callable[[SimState], tuple]  # -> (ok: bool, detail: str)


@dataclass
class Checkpoint:
    time_s: float
    caption: str
    # ViewState overrides for the snapshot. local_zoom/square_local go to the
    # ship pane, macro_zoom/square_macro to the chart; pan/rotation go to
    # whichever pane "scale" names (default: the ship pane); observer,
    # paused and reveal apply to both.
    view: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)


@dataclass
class ScenarioRun:
    sim: Simulation
    deck: ViewState  # left pane: the ship at 1 m, bow up
    chart: ViewState  # right pane: the macro view
    checkpoints: list
    duration_s: float

    @property
    def state(self) -> SimState:
        return self.sim.state


@dataclass
class Scenario:
    key: str
    title: str
    summary: str
    look_for: list
    build: Callable[[int], ScenarioRun]
    duration_s: float = 120.0
    slow: bool = False  # long-running; skipped by the quick test tier
    # A scene that only means anything with a player at the keyboard - a
    # tutorial mission. Checked headless like everything else, but left out
    # of the HTML replays: with nobody at the wheel it is twenty megabytes
    # of a ship drifting.
    interactive: bool = False


REGISTRY: dict[str, Scenario] = {}


def scenario(key: str, title: str, summary: str, look_for=(), duration_s: float = 120.0, slow: bool = False, interactive: bool = False):
    def deco(fn):
        # Caught the hard way: a list passed where the summary goes gets
        # through registration, through every check, and only blows up in
        # the replay index writer after an hour of rendering.
        if not isinstance(title, str) or not isinstance(summary, str):
            raise TypeError(f"scenario({key!r}): title and summary must be strings - did a look_for list go in positionally?")
        REGISTRY[key] = Scenario(key=key, title=title, summary=summary, look_for=list(look_for), build=fn, duration_s=duration_s, slow=slow, interactive=interactive)
        return fn

    return deco


def get(key: str) -> Scenario:
    from broadside.scenarios import courses, demo, fleet, gunlaying, library, sandbox, tutorial  # noqa: F401  (registers scenarios)

    if key not in REGISTRY:
        raise KeyError(f"unknown scenario '{key}'. Available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def all_scenarios() -> list[Scenario]:
    from broadside.scenarios import courses, demo, fleet, gunlaying, library, sandbox, tutorial  # noqa: F401

    return list(REGISTRY.values())


class SceneBuilder:
    """Fluent helper for assembling a scene."""

    def __init__(self, seed: int = 1805, *, wind_from: float = 0.0, wind_knots: float = 12.0, haze_m: float = 15000.0, light: float = 1.0, start_hour: float = 10.0, gusty: bool = False):
        self.seed = seed
        self.world = esper.World()
        self.rng = CampaignRNG(seed=seed)
        self.terrain = Terrain()
        self.atmosphere = Atmosphere(haze_visibility_m=haze_m, light=light, clear_visibility_m=haze_m)
        # Weather is a field over the sea, seeded with the scene: stormy
        # quarters and kindly ones, clouds that drift and cast shadows.
        self.atmosphere.weather = WeatherField(seed=seed)
        self.wind = WindField.steady(self.rng.stream("wind"), direction_degrees=wind_from, speed_knots=wind_knots)
        if not gusty:
            self.wind.direction_volatility = 0.15
            self.wind.speed_volatility = 0.02
            self.wind.reversion_rate = 0.05
        self.start_hour = start_hour
        self.player_ship: Optional[int] = None
        self._spawn_rng = self.rng.stream("spawn")

    # --- ships ----------------------------------------------------------

    def player(self, ship_class: str = "sloop_18", *, name: str = "HMS Kestrel", crew: int = 40, **kw) -> int:
        ent = spawn_ship(self.world, ship_class, self._spawn_rng, name=name, crew=crew, faction=kw.pop("faction", "british"), **kw)
        self.player_ship = ent
        return ent

    def ship(self, ship_class: str, *, name: str, faction: str = "french", crew: int = 0, observers: bool = False, **kw) -> int:
        """An NPC ship. By default no crew entities (its guns are worked
        abstractly) and no observers of its own - enough to be seen, fire
        and manoeuvre, without paying for a full crew simulation."""
        return spawn_ship(self.world, ship_class, self._spawn_rng, name=name, faction=faction, crew=crew, observers=observers, **kw)

    def waypoints(self, ship: int, points, loop: bool = False) -> None:
        helm = self.world.component_for_entity(ship, c.Helm)
        helm.waypoints = [tuple(p) for p in points]
        helm.loop = loop

    def set_speed(self, ship: int, knots: float) -> None:
        """Start a ship already under way (avoids a slow start from rest)."""
        self.world.component_for_entity(ship, c.Speed).knots = knots

    # --- terrain & weather -------------------------------------------

    def island(self, x, y, radius, **kw) -> Island:
        return self.terrain.add(Island(x, y, radius, seed=kw.pop("seed", self.seed + len(self.terrain.features)), **kw))

    def rock(self, x, y, **kw) -> Rock:
        return self.terrain.add(Rock(x, y, **kw))

    def coast(self, normal_degrees, offset_m, **kw) -> Coast:
        return self.terrain.add(Coast(normal_degrees, offset_m, seed=kw.pop("seed", self.seed + len(self.terrain.features)), **kw))

    def wall(self, x: float, y: float, heading: float = 0.0, *, length_m: float = 20.0, thickness_m: float = 2.0, height_m: float = 5.0, material: str = "masonry", name: str = "curtain wall") -> int:
        """A voxel wall standing on whatever ground is at (x, y), running
        along `heading` (its length), thickness across it."""
        import numpy as _np

        from broadside.sim.voxels import build_wall

        ground = float(self.terrain.sample(_np.array([x]), _np.array([y])).height[0])
        vs = build_wall(length_m, thickness_m, height_m, base_z_m=ground, material=material, name=name)
        return self.world.create_entity(vs, c.WorldPosition(x_nm=x / c.M_PER_NM, y_nm=y / c.M_PER_NM), c.Heading(degrees=heading), c.Name(name))

    def fog(self, x, y, rx, ry, **kw) -> FogBank:
        bank = FogBank(x, y, rx, ry, seed=kw.pop("seed", self.seed + len(self.atmosphere.fog_banks)), **kw)
        self.atmosphere.fog_banks.append(bank)
        return bank

    # --- assemble ---------------------------------------------------

    def build(self, *, chart: Optional[ViewState] = None, deck: Optional[ViewState] = None, duration_s: float = 120.0, checkpoints=()) -> ScenarioRun:
        if self.player_ship is None:
            raise ValueError("scenario has no player ship")
        state = SimState(
            world=self.world,
            rng=self.rng,
            clock=SimClock(),
            wind=self.wind,
            terrain=self.terrain,
            atmosphere=self.atmosphere,
            player_ship=self.player_ship,
            start_hour=self.start_hour,
        )
        from broadside.view.screen import default_chart_view, default_deck_view

        return ScenarioRun(
            sim=Simulation(state),
            deck=deck or default_deck_view(),
            chart=chart or default_chart_view(),
            checkpoints=list(checkpoints),
            duration_s=duration_s,
        )


# --- Check helpers ---------------------------------------------------------


def ship_named(state: SimState, name: str) -> int:
    for ent, nm in state.world.get_component(c.Name):
        if nm.full == name and state.world.has_component(ent, c.ShipTag):
            return ent
    raise KeyError(name)


def contact(name: str, *allowed: str) -> Check:
    """The player's contact record for `name` has one of the statuses."""

    def fn(state):
        rec = state.world.component_for_entity(state.player_ship, c.Contacts).records.get(ship_named(state, name))
        status = rec.status if rec else "none"
        return status in allowed, f"status={status}"

    return Check(f"contact {name} is {'/'.join(allowed)}", fn)


def eyes(post: str, name: str, *allowed: str) -> Check:
    """What the player's `post` observer can see of `name` right now."""
    from broadside.sim.systems.sighting import sight_ship

    def fn(state):
        obs = find_observer(state.world, state.player_ship, post)
        got = sight_ship(state, obs, ship_named(state, name)) if obs is not None else "none"
        return got in allowed, f"{post} sees {got}"

    return Check(f"{post} sees {name}: {'/'.join(allowed)}", fn)


def expect(label: str, fn: Callable[[SimState], tuple]) -> Check:
    return Check(label, fn)


def log_contains(text: str) -> Check:
    def fn(state):
        hit = any(text.lower() in e.text.lower() for e in state.log)
        return hit, "found" if hit else "not in log"

    return Check(f"log mentions '{text}'", fn)


_DECK_KEYS = {"local_zoom", "square_local"}
_CHART_KEYS = {"macro_zoom", "square_macro", "look_sector"}
_BOTH_KEYS = {"observer", "paused", "reveal"}


def split_overrides(overrides: dict) -> tuple[dict, dict]:
    """Route a checkpoint's view overrides to (deck, chart) panes."""
    deck, chart = {}, {}
    to_chart = overrides.get("scale") == "macro" or ("scale" not in overrides and any(k in _CHART_KEYS for k in overrides))
    target = chart if to_chart else deck
    for k, v in overrides.items():
        if k == "scale":
            continue
        if k in _DECK_KEYS:
            deck[k] = v
        elif k in _CHART_KEYS:
            chart[k] = v
        elif k in _BOTH_KEYS:
            deck[k] = v
            chart[k] = v
        else:
            target[k] = v
    return deck, chart
