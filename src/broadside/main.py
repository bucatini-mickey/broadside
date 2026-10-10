# Entry point.
#
#   python -m broadside.main                      the game: a menu with the
#                                                 tutorial missions in it
#                                                 (same as broadside.game)
#   python -m broadside.main --scenario KEY       interactive: a named scenario
#   python -m broadside.main --list               list scenarios
#   python -m broadside.main --classic            the original Phase 0 demo
#   python -m broadside.main --headless --ticks N runs the Phase 0 sim only,
#                                                 no terminal - for smoke
#                                                 testing / CI, and for
#                                                 seeing that sim/ truly
#                                                 doesn't need a terminal
#                                                 attached to run.
#
# The scenario library has its own fuller CLI: python -m broadside.scenarios
#
# See docs/design/01_architecture.md for the overall loop shape this
# implements (fixed-timestep sim, render/input decoupled from it).

from __future__ import annotations

import argparse
import sys
import time

import esper
from blessed import Terminal

from broadside.engine.clock import SimClock
from broadside.engine.rng import CampaignRNG
from broadside.render.buffer import ScreenBuffer
from broadside.render.layout import SplitScreenLayout
from broadside.render.palette import TEXT_DIM
from broadside.render.panels import draw_deck_panel, draw_status_panel
from broadside.render.terminal import TerminalRenderer
from broadside.sim import components as c
from broadside.sim.entities import create_sailor, create_ship
from broadside.sim.systems.crew_ai import mood_system, needs_decay_system
from broadside.sim.systems.movement import crew_wander_system, ship_movement_system
from broadside.sim.systems.sailing import sailing_system
from broadside.sim.systems.wind import WindField
from broadside.ui.input import poll_command

DEFAULT_CREW_SIZE = 14  # a small demo crew, well under the sloop's full complement
DEFAULT_SCENARIO = "demo"  # the playable demo (scenarios/demo.py)


def build_world(seed: int, ship_class: str = "sloop_18") -> tuple[esper.World, CampaignRNG, int, WindField]:
    campaign_rng = CampaignRNG(seed=seed)
    world = esper.World()

    ship, data = create_ship(world, ship_class)

    crew_rng = campaign_rng.stream("crew_demo")
    for _ in range(DEFAULT_CREW_SIZE):
        create_sailor(world, ship, data.deck_width, data.deck_height, crew_rng)

    wind_rng = campaign_rng.stream("wind")
    wind_field = WindField.steady(wind_rng, direction_degrees=wind_rng.uniform(0, 360), speed_knots=12.0)

    return world, campaign_rng, ship, wind_field


def run_sim_tick(world: esper.World, campaign_rng: CampaignRNG, wind_field: WindField, dt_seconds: float, ship_grids: dict[int, tuple[int, int]]) -> None:
    wind_field.tick(campaign_rng.stream("wind"))
    sailing_system(world, wind_field)
    ship_movement_system(world, dt_seconds)
    needs_decay_system(world, dt_seconds)
    mood_system(world)
    crew_wander_system(world, campaign_rng.stream("crew_wander"), ship_grids)


def _ship_grids(world: esper.World) -> dict[int, tuple[int, int]]:
    return {e: (g.width, g.height) for e, g in world.get_component(c.DeckGrid)}


def run_headless(seed: int, ticks: int) -> None:
    world, campaign_rng, ship, wind_field = build_world(seed)
    clock = SimClock()
    grids = _ship_grids(world)

    for _ in range(ticks):
        run_sim_tick(world, campaign_rng, wind_field, clock.tick_seconds, grids)
        clock.tick_count += 1
        clock.sim_seconds += clock.tick_seconds

    pos = world.component_for_entity(ship, c.WorldPosition)
    speed = world.component_for_entity(ship, c.Speed)
    heading = world.component_for_entity(ship, c.Heading)
    moods = [m.value for _e, m in world.get_component(c.Mood)]
    avg_mood = sum(moods) / len(moods) if moods else 0.0

    print(f"Ran {ticks} ticks ({clock.sim_seconds / 3600:.2f} sim hours).")
    print(f"Ship position: ({pos.x_nm:.3f}, {pos.y_nm:.3f}) nm, heading {heading.degrees:.1f} deg, speed {speed.knots:.2f} kn")
    print(f"Wind: {wind_field.current.speed_knots:.1f} kn from {wind_field.current.direction_degrees:.1f} deg")
    print(f"Crew average mood: {avg_mood:+.2f} ({len(moods)} sailors)")


def run_interactive(seed: int) -> None:
    world, campaign_rng, ship, wind_field = build_world(seed)
    clock = SimClock()
    grids = _ship_grids(world)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    term = Terminal()
    renderer = TerminalRenderer(term)

    with term.fullscreen(), term.hidden_cursor(), term.cbreak():
        last_time = time.perf_counter()
        last_dims = (term.width, term.height)

        while True:
            now = time.perf_counter()
            dt = now - last_time
            last_time = now

            ticks_to_run = clock.advance(dt)
            for _ in range(ticks_to_run):
                run_sim_tick(world, campaign_rng, wind_field, clock.tick_seconds, grids)

            cmd = poll_command(term, timeout=0.0)
            if cmd.quit:
                break
            if cmd.turn_delta_degrees or cmd.trim_delta:
                heading = world.component_for_entity(ship, c.Heading)
                sail = world.component_for_entity(ship, c.SailPlan)
                heading.degrees = (heading.degrees + cmd.turn_delta_degrees) % 360.0
                sail.trim = max(0.0, min(1.0, sail.trim + cmd.trim_delta))

            dims = (term.width, term.height)
            if dims != last_dims:
                renderer.force_full_redraw_next_frame()
                last_dims = dims

            buffer = ScreenBuffer(term.width, term.height)
            layout = SplitScreenLayout(term.width, term.height)
            draw_deck_panel(buffer, layout.left, world, ship)
            draw_status_panel(buffer, layout.right, world, ship, wind_field, clock)
            layout.draw_divider(buffer)
            buffer.draw_text(
                layout.footer.x + 1, layout.footer.y,
                "[a/d] turn  [w/s] sail  [q] quit",
                fg=TEXT_DIM,
            )

            renderer.render(buffer)

            # Cap render/input polling rate; the sim itself is paced by
            # SimClock regardless of this sleep.
            time.sleep(1.0 / 30.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="broadside", description="A terminal simulation of Napoleonic-era ship command.")
    parser.add_argument("--headless", action="store_true", help="run the simulation without a terminal UI")
    parser.add_argument("--ticks", type=int, default=100, help="ticks to run in --headless mode")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--scenario", default=None, help="scenario to play, skipping the menu")
    parser.add_argument("--list", action="store_true", help="list the available scenarios")
    parser.add_argument("--classic", action="store_true", help="run the original Phase 0 split-screen demo")
    args = parser.parse_args(argv)

    if args.headless:
        run_headless(args.seed if args.seed is not None else 1815, args.ticks)
        return 0

    if args.list:
        from broadside.scenarios.__main__ import main as scenarios_main

        return scenarios_main(["list"])

    if not sys.stdout.isatty():
        print("broadside: stdout is not a terminal - run with --headless, or run in a real terminal.", file=sys.stderr)
        return 1

    if args.classic:
        run_interactive(args.seed if args.seed is not None else 1815)
        return 0

    if args.scenario is None:
        # The front door: the menu, with the tutorial missions in it.
        from broadside.game import run as run_menu

        return run_menu()

    from broadside.scenarios.base import get
    from broadside.ui.app import run_interactive as run_engine

    scn = get(args.scenario)
    run = scn.build(args.seed) if args.seed is not None else scn.build()
    return run_engine(run, scn)


if __name__ == "__main__":
    raise SystemExit(main())
