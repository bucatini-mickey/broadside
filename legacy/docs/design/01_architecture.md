# Architecture

## High-level shape

```
┌─────────────────────────────────────────────────────────────────┐
│                            main.py                               │
│   owns: SimClock, EventBus, esper.World, TerminalRenderer        │
│   runs: fixed-timestep sim loop  +  render loop  +  input poll   │
└───────────────┬───────────────────────────────┬──────────────────┘
                │                                │
        ┌───────▼────────┐               ┌───────▼────────┐
        │   sim/ systems   │               │  render/ + ui/  │
        │ (pure logic,     │──ECS World──▶│ (reads ECS state,│
        │  no I/O)         │              │  never mutates it)│
        └───────┬─────────┘               └────────────────┘
                │
        ┌───────▼─────────┐
        │ world/ (map,     │
        │ wind fields,     │
        │ campaign state)  │
        └──────────────────┘
```

The rule that keeps this sane as it grows: **systems mutate the ECS world; renderers only read it.** No rendering code ever computes gameplay state, and no simulation code ever touches `blessed` or the screen buffer. This is what lets the headless test suite run the entire simulation without a terminal attached (see `tests/`), and it's what will let a future "server-authoritative" or "replay" mode exist without a rewrite.

## Entity-Component-System (ECS)

**Library choice: [`esper`](https://github.com/benmoran56/esper), pinned to the 2.x line.** It's a small, pure-Python ECS with no dependencies, sparse-set style storage, and a query API (`world.get_components(A, B, C)`) that's fast enough for the entity counts this project needs (hundreds of sailors per ship, tens of ships — thousands of entities, not millions). It was chosen over hand-rolling an ECS because the pattern is well-understood and esper is small enough to read end-to-end in an afternoon if it ever needs to be forked or replaced. The version pin matters: esper 3.x replaced the instantiable `esper.World` class with an implicit-global, `switch_world("name")`-style API, which is a worse fit for "pass an explicit World object around, spin up an isolated one per test, eventually one per scene" — so this project stays on 2.x (see the comment in `requirements.txt`).

Two conventions to hold from day one, because they're expensive to retrofit:

- **Components are plain `@dataclass` objects with no behaviour** — pure data (`sim/components.py`). Anything that looks like a method that mutates other components belongs in a system, not on the component.
- **One world per simulated "scene," not one world total.** A ship's deck (sailors walking around a local tile grid) and the world chart (ships moving through nautical-mile space) are different entity populations at different resolutions. The skeleton uses a single `esper.World` with components tagged by which space they belong to (`DeckPosition` vs `WorldPosition`); if profiling ever shows the mixed queries costing real time, splitting into separate `esper.World` instances per scene is a contained change because systems already only ever ask for the components they need.

## Two coordinate spaces

This is the architectural decision most worth getting right early, because the whole "DF-style deck view split-screen with a fleet/chart view" premise depends on it:

| | **DeckPosition** (local) | **WorldPosition** (chart) |
|---|---|---|
| Unit | integer tile (≈1–2 m per tile) | float nautical miles, lat/lon-like plane |
| Who has it | sailors, deck fittings, guns-as-objects, damage locations | ships, floating wreckage, ports, other fleets |
| Origin | ship-relative (0,0 = bow at the centreline, or similar) | world-relative (campaign map origin) |
| Update rate | every sim tick, ~10 Hz | every sim tick, but changes are small — ship speed is a handful of knots |
| Rendered in | left "deck" pane | right "chart / fleet" pane, or a modal chart view |

A sailor's `DeckPosition` is relative to their ship. When a ship moves (`WorldPosition` changes, heading changes), the deck grid moves with it as a rigid body — sailors don't need their `DeckPosition` touched by ship movement at all, which is exactly the simplification that makes this tractable. The transform from "sailor's deck tile" to "sailor's absolute world position" (needed only rarely — e.g. a sailor who falls overboard) is `world_position(ship) + rotate(deck_offset, ship.heading)`.

## Fixed-timestep simulation clock

`engine/clock.py`'s `SimClock` decouples simulation rate from render/input rate: the sim advances in fixed ticks (default 10 Hz — i.e. a "tick" is 0.1 simulated seconds' worth of physics/AI resolution), accumulated against wall-clock time, so the game behaves identically whether the terminal can push 60 frames/second or 5. This also means simulated time can be scaled — 1x, 4x, paused — independent of rendering, which is essential for a game where "sail 40 nautical miles to the next port" needs to be fast-forwardable without changing physics behaviour.

Time is also tracked in-period: `SimClock` exposes the ship's-watch bell system (four-hour watches, bells struck each half hour) because it's both period flavour and a genuine scheduling primitive — crew shift assignment (`sim/systems/crew_ai.py`, later phases) is built around watches, exactly as it would have been in 1800.

## Determinism and RNG

`engine/rng.py` provides a single seeded source of randomness (`random.Random` for scalar draws, `numpy.random.Generator` for vectorised draws), constructed from a campaign seed. Every system that needs randomness takes an RNG instance rather than calling the global `random` module. This buys three things worth the minor discipline cost: reproducible bug reports ("seed 481922, tick 40133, the mizzen topsail sheet just vanished"), deterministic automated tests of stochastic systems, and a foundation for an eventual battle-replay feature.

## Event bus

`engine/events.py` is a minimal synchronous pub/sub bus. It exists for the cases where a direct ECS query is the wrong tool — cross-cutting notifications like "a mast was just dismasted" (which the rigging system, the crew-morale system, the render log panel, and eventually an achievements/campaign system might all care about) are events, not components. Keep this bus for genuinely cross-cutting notifications; day-to-day state changes still belong in components, queried directly, not routed through events.

## Performance strategy: pure Python first, architected for compiled hot paths later

The user-facing decision was "pure Python is simpler; use judgement on future-proofing." The resolution: **write it in pure Python + NumPy, but keep every performance-sensitive system isolated behind a narrow functional interface that operates on plain arrays/buffers**, so that a hot path can be swapped for a compiled implementation later without touching its callers.

Concretely:

1. **NumPy for anything vectorisable across many entities at once** — wind field sampling, the diffed-buffer renderer, batched needs decay across a whole crew. `esper`'s storage is per-component-type, which already gives contiguous-ish access patterns; lean into it before reaching for a rewrite.
2. **Profile before optimising** — `python -m cProfile` / `py-spy` against a stress scenario (a full 300-crew ship, later a 6-ship fleet) before assuming where the cost is. Napoleonic naval combat does not require real-time twitch performance; the target is a smooth 10 Hz sim tick and a responsive render, which is a low bar.
3. **The extension escape hatch, if it's ever needed**: pathfinding (crew moving around a damaged, flooding deck), large-fleet AI, and collision/ballistics are the systems most likely to eventually justify a compiled implementation. Because systems are pure functions over component arrays (not methods on Python objects), any of the three can be reimplemented in Rust (via `PyO3`/`maturin`) or Cython behind the same call signature — `def resolve_pathfinding(grid: np.ndarray, starts, goals) -> np.ndarray` doesn't care what language computed it. Nothing in this skeleton requires that step; it just avoids designing it out.

## Module map

```
src/broadside/
  main.py            entry point: builds world, runs the loop
  engine/            infrastructure with no game knowledge
    rng.py             seeded RNG provider
    clock.py           fixed-timestep sim clock + ship's-bell time
    events.py          pub/sub event bus
  sim/               all gameplay simulation (no rendering, no I/O)
    components.py      ECS component dataclasses
    entities.py        entity factory functions (create_ship, create_sailor, ...)
    shipdata/          loads ship class definitions from data files
    data/ships/*.yaml   period ship-class stat blocks
    systems/           one module per simulated process
      wind.py            world wind field
      sailing.py         wind + trim + heading -> ship velocity
      crew_ai.py         needs decay, task assignment, deck movement AI
      movement.py        applies velocity to WorldPosition / DeckPosition
  render/            reads ECS state, draws to the terminal; never mutates state
    buffer.py           ScreenBuffer: the in-memory grid of (glyph, fg, bg)
    terminal.py         diffs buffers frame-to-frame, writes only changed cells
    viewport.py          camera/scroll math, world-or-deck coords -> screen coords
    layout.py            split-screen panel geometry
    palette.py           colour constants
  ui/                input handling, command parsing
    input.py
```

Everything under `sim/` should be importable and testable with zero terminal attached — that's the acceptance test for "did we keep simulation and rendering properly separated," and it's enforced informally by the test suite never importing `render/` or `ui/`.

## Save format (future phase, noted now so nothing here blocks it)

Not implemented in this skeleton, but the architecture anticipates it: because state lives entirely in ECS components (plain dataclasses) plus a handful of world-level singletons (wind field seed/state, campaign clock, RNG state), a save is "serialize every component table + world singletons + RNG state to a file" and a load is the reverse. `esper` doesn't provide serialization out of the box, so this becomes a thin custom (de)serializer once it's needed — deferred until the component set stabilises past the current skeleton, to avoid writing a serializer against a schema that's still changing weekly.
