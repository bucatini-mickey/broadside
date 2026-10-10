# Broadside — Project Overview

## Vision

Broadside is a terminal-based, single-player simulation of command in the Napoleonic-era Mediterranean. It sits in the Dwarf Fortress lineage: rather than scripting outcomes, the game simulates the underlying mechanisms — wind, hull, rigging, gunnery, and the several hundred individual sailors who crew a ship — and lets events emerge from those mechanisms. The player does not "control a ship" in the way an arcade game controls a ship; they command a crew, who sail a ship, which responds to wind and water according to period-accurate seamanship.

The two things that make this project distinctive, and hard, are named directly in the brief and should stay load-bearing throughout development:

1. **Everything that can be simulated, is.** A sailor is not a hit-point value under a ship-strength total. A sailor has a name, a rank, a station, a body with limbs that can be wounded individually, a mood built from fatigue/hunger/fear/grief, and a task they are currently doing. The ship is not an HP bar either — it is a hull with sections that flood, rigging that parts, sails that tear, guns that overheat and crews that tire.
2. **You only know what you can see or what reaches you by signal.** Every vessel in the world — friendly, enemy, neutral — is simulated to the same fidelity as the player's ship, all the time, whether or not the player is nearby. The player's channel into that simulation is either physical presence (they are aboard) or semaphore (line-of-sight flag signalling, with all of that system's real limits: range, weather, night, message complexity). This is the mechanism that makes fleet command feel like command rather than a fixed camera — orders take time to arrive, get garbled, and can simply fail to be seen.

## Scope for this pass

This repository starts with:

- The full design document set (`docs/design/`) covering architecture, every simulated subsystem, rendering/UI, world & campaign structure, and a phased roadmap.
- A runnable code skeleton (`src/broadside/`) implementing the architectural spine — ECS world, fixed-timestep sim clock, a diffed terminal renderer, a split-screen layout, and one working vertical slice: a single ship, a crew wandering the deck, wind, and simplified sailing physics you can steer with the keyboard.
- Nothing here implements combat, multi-ship fleets, semaphore, world generation, or the campaign layer yet — those are fully specified in the docs but intentionally left as the next phases, so the skeleton stays small enough to actually run and be understood in one sitting.

There is no deadline on this project and it is expected to run for years. The roadmap (`05_roadmap.md`) is written accordingly: phases are ordered so that the game is *playable and interesting* at the end of nearly every phase, in the Dwarf Fortress tradition of "always have a game," rather than front-loading infrastructure that pays off only much later.

## Design principles

**Simulate the mechanism, not the outcome.** If a design question can be answered by "simulate the underlying physical/social process and let the number fall out," prefer that over a hand-tuned formula, even when the formula would ship faster. This is the whole point of the project and the reason to accept the extra cost.

**Data-oriented, not object-oriented.** Thousands of sailors across dozens of simulated ships means the entity/component/system (ECS) pattern throughout, not a `Sailor` class hierarchy. Components are plain data; systems are functions that operate over columns of it. This is both the idiomatic way to get emergent behaviour (systems compose freely) and the only realistic path to acceptable performance in Python (see `01_architecture.md`).

**Two coordinate scales, always kept distinct.** A ship moves through the world in continuous nautical-mile space. A sailor moves through their ship's deck in a discrete tile grid, like a tiny Dwarf-Fortress local map. These are different simulations at different resolutions running at different rates, and the architecture must never quietly conflate them.

**Determinism and replayability.** Every random process is drawn from a seeded RNG, and the campaign seed is the primary save-portable object. This buys reproducible bug reports, a foundation for an eventual "watch the last battle replay" feature, and sane automated testing of systems that are inherently stochastic.

**Terminal-native.** The renderer targets a real terminal (via `blessed`), not an SDL/graphics window pretending to be one. See `03_rendering_ui.md` for the reasoning and the alternative considered.

**Build for a solo, sessions-based cadence.** No sprints, no deadline. The roadmap is phased by dependency and by "is this fun/informative to reach," not by calendar weeks. Effort is estimated in rough work sessions, not dates.

## What "period-accurate" means here, practically

Two kinds of accuracy are being promised, and they should not be confused:

- **Mechanically accurate**: the *shape* of the mechanism matches reality — you cannot sail directly into the wind and must tack; a becalmed ship in light air genuinely goes nowhere; broadsides are fired from one side and a ship must present that side to fire; signal messages are drawn from a real flag vocabulary with real range and visibility limits.
- **Statistically/historically accurate**: the *numbers* (crew complements, gun counts and weights, hull dimensions, speeds under given sail and wind, rates of fire) are drawn from real Napoleonic-era reference figures for the ship classes represented (frigates, ships of the line, sloops, etc.), documented per-class in `sim/data/ships/*.yaml` with the source noted in comments.

Where the two are in tension (a fully accurate hydrodynamic/aerodynamic sail model would be a multi-year project on its own), the project takes the well-trodden sailing-game shortcut of a **polar performance curve**: for a given point of sail and sail trim, a boat has a known, tunable speed multiplier. This is what real sailing simulators and games (from *Sid Meier's Pirates!* to modern racing-yacht VPP tools) use, and it is the right level of fidelity for "mechanically accurate and fun to master," as opposed to "a fluid dynamics research project."

## Non-goals (for now)

- Multiplayer.
- Full 3D or graphical rendering — this is a terminal game by design, not by budget constraint.
- A fully general historical sandbox beyond the Mediterranean theatre and the Napoleonic Wars period (circa 1793–1815).
- Console/mobile ports.

These can be revisited once the core loop is proven; they are excluded now so the architecture stays focused.
