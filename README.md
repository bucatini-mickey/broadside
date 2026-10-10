# Broadside

A terminal-based, Dwarf-Fortress-style simulation of ship and fleet command in the Napoleonic-era Mediterranean.

Full design documentation lives in [`docs/design/`](docs/design/). Start with [`00_overview.md`](docs/design/00_overview.md) for the vision and design principles. [`docs/STATUS_REPORT.md`](docs/STATUS_REPORT.md) covers where things stand and what's next, and [`10_naval_primer.md`](docs/design/10_naval_primer.md) is a tutorial on the ships, sailing, command and combat being simulated. This README covers only how to run what's here.

## What's here right now

Phase 0 of the roadmap (the architectural skeleton), plus **engine v1**: the scene engine, described in [`docs/design/07_vision_and_views.md`](docs/design/07_vision_and_views.md).

- **Captain's-perspective line of sight.** You see only what the captain (or the masthead lookout) can see. Islands, rocks, trees, other hulls, your own masts and sails, fog, powder smoke, darkness and the curvature of the earth all obstruct. The model is 2.5D, so topsails show over a low islet or above smoke. Hidden ground is black, remembered ground is dim, and fog or smoke shows as a grey wall.
- **Planning mode.** Stop time (Dwarf-Fortress style) to see your whole ship and crew and give orders.
- **One camera, every scale.** A 1 m × 1 m deck view with individual sailors, and a macro view where ships are clusters of glyphs among the fleet. Zoom runs continuously from 1 m to 640 m per column, north-up or ship-up.
- **Supporting systems:** 1 m deck plans generated from ship data, helm with waypoints and tacking, crew beating to quarters along real paths, rippling broadsides that fill the air with drifting smoke, ship sighting and contact records, and grounding.
- **Generated languages** ([`14_languages.md`](docs/design/14_languages.md)). Every people speaks a language generated from the seed, blended from a dozen sound systems and mutated; names are meaningful compounds with translations (*Varnakkel*, "Saltbay").
- **Physics sandbox** ([`15_physics_sandbox.md`](docs/design/15_physics_sandbox.md)). Work a gun yourself (walk the deck, sponge, load, prime, lay, fire); round shot flies under gravity and drag and smashes 0.5 m blocks out of a wall, which cracks, breaches, collapses into rubble and throws up dust.
- **The gun drill, acted out** ([`17_drill_signals_and_tutorial.md`](docs/design/17_drill_signals_and_tutorial.md)). A gun is nine separate jobs - sponge, cartridge, ram, wad, shot, ram, run out, prime, lay - each done by a named man at a numbered station, each taking the time his skill, his fatigue, his surviving hands and the weight of the thing allow. Nobody stands beside a cannon while a bar fills, and rate of fire is a number nothing in the code sets. Gun captains lay their own pieces by solving the real trajectory, and misjudge the range by however green they are.
- **Signals.** A numbered code book at the quarterdeck locker: hoisting takes time, fog and smoke make flags illegible, and the other ship must read them before she answers.
- **A playable tutorial and a sandbox.** Eleven lessons in being the captain, each passed only when the ship's own state says you have done it; and a brig to walk about with casks to open, a hulk to fire into and a wall to knock down.
- **A command screen you can read** ([`08_interface.md`](docs/design/08_interface.md)). The ship pane takes the left half, bow up, auto-zoomed so small ships are drawn large; the chart sits top right; and below it **one panel at a time** - log, crew, orders, ship, keys - under a status strip that always shows heading, wind, log and sail. Walk mode (`m`) closes the ship pane right in to three cells a metre and follows the captain about the deck, with only what he can see drawn.
- **The z axis** ([`16_observation_and_targeting.md`](docs/design/16_observation_and_targeting.md)). `z` cuts the world into horizontal levels and PgUp/PgDn walks up and down them: the sea and its bottom, hills in cross-section, tree trunks and canopy, a ship's hull, her deck, her canvas and her mastheads.
- **The glass.** `t` gives the ship pane over to a first-person picture along one bearing - a heightfield raycast that tells canvas from stone from hillside, 70 degrees by eye or 7 through the glass - and reports what it finds ("a brig, hull up, bearing NNE, about 150 m").
- **Weather as a place** ([`09_environment.md`](docs/design/09_environment.md)). Not a dice roll: a field over the sea with stormy quarters and kindly ones, clouds that drift downwind and cast shadows on the water, rain that shortens the horizon, and fog that gathers in damp quarters when the wind falls light. The same patch of sea behaves the same way tomorrow.
- **Life aboard** ([`18_life_aboard.md`](docs/design/18_life_aboard.md)). Two watches; the watch below really goes below and sleeps at night; meals at the proper hours eaten out of the real casks; squalls with rain that shortens the horizon and wets the men. Beat to quarters at four in the morning and every man turns out, owing the sleep he did not get.
- **A squadron to command** ([`19_fleet_and_captains.md`](docs/design/19_fleet_and_captains.md)). Every ship but yours has a captain with parameters - skill, intelligence (how often he thinks at all), aggression, caution, discipline - drawn from the person generated for him. He chooses what to do from what his own lookouts have seen, and the only way you can tell him anything is the signal book: a hand is sent to the locker, the flags go up, his lookouts see them, his midshipman reads them (perhaps wrongly), and his captain obeys - or, if he is bold and the action is hot, does not.
- **A crew roster** in the Dwarf-Fortress spirit: the whole company with their stations and a grid of all fifteen skills, and the selected man's full sheet - character, devotion, drink, wounds and life story.
- **A playable demo** (`python -m broadside.main`): your brig under way with her whole company, a consort astern to signal, an enemy brig holding station a cable and a half off your larboard beam, and a fort's sea wall to starboard. Walk the deck, con the ship, beat to quarters, name a target and let the gun captains fight her. The log opens with what to try and hints as you go.
- **A library of 23 test scenarios**, each with captions and automated checks, playable, testable and exportable as HTML replays.
- **People with stories** ([`11_people.md`](docs/design/11_people.md)). Every sailor on every ship, friend or foe, is an individual: culture, nationality, birthplace, background, character, morale, stress, anxiety, depression, drink dependence, devotion, skills for every role, and a body with blood and a pulse. Death comes by blood loss, and each man has a biography.
- **Everything is data** ([`13_structures_and_items.md`](docs/design/13_structures_and_items.md)). Every deck tile has a material and a condition, and every cask its contents. Ships collide, foul and are boarded man by man.
- **World generation** ([`12_world_generation.md`](docs/design/12_world_generation.md)). A fictional Mediterranean with ports, nations and cultures, and 155 years of simulated history. You name your captain, ship and nation.

Still to come: sail handling as acted work aloft, the surgeon, materials that drag their neighbours when struck, the glass and fall-of-shot reports, weather, and lower decks. See `docs/STATUS_REPORT.md` section 6 and `docs/design/05_roadmap.md`.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the game

```bash
python -m broadside.main                         # the playable demo
python -m broadside.main --scenario fog_bank     # any scenario
python -m broadside.main --list
python -m broadside.main --classic               # the original Phase 0 demo
```

The screen is split: the **ship** at 1 m per cell, bow up, on the left half. The **chart** (macro view) is top right, with the **quarterdeck** instruments (binnacle, pennant, log, bell, sail plan) and **details** (sight, contacts, battery, log) below it. See [`docs/design/08_interface.md`](docs/design/08_interface.md).

It needs a true-colour terminal of at least 120x40. **190x64 or larger is recommended**, and a first rate needs about 75 rows to show bowsprit to taffrail. Windows Terminal full-screen (`F11`) with a slightly smaller font (`Ctrl -`) works well. Controls (also in the footer):

| Key | Action |
|---|---|
| `SPACE` | pause / resume. Paused = **planning mode**: your whole ship is revealed and orders apply when time runs |
| `TAB` | move focus: ship pane -> chart -> panel (then arrows move within the panel) |
| `1`-`6` | choose the panel: log, crew, orders, signals, ship, keys |
| `+` / `-` | zoom the focused pane |
| `r` / `c` | rotation / cell shape of the focused pane |
| `o` | captain's eyes vs masthead lookout |
| `a` / `d` (`A`/`D`) | helm 5° (30°) to larboard / starboard |
| `w` / `s` | call for more / less sail. The order is instant, the canvas is not: hands take about half a minute to set or take in the whole plan |
| `b` | beat to quarters / stand down |
| `[` / `]` | fire the larboard / starboard battery on your word |
| `F` | fire as they bear: each gun captain fires when his gun is ready and laid |
| `l`, arrows (`hjk`, `HJKL` ×10) | look cursor: describes what's there and why you can or can't see it |
| `x` | tell the guns to fire at whatever the look cursor is on - your gun captains take time to understand it |
| `t` / `T` | take up the glass / look out by eye: a first-person view along one bearing (arrows sweep it, `+`/`-` change the field). Your own ship is left out of the picture; the chart marks where you are looking |
| `z`, `PgUp`/`PgDn` | levels: cut the world into horizontal slices and walk up and down them |
| `g` | steer for the cursor; `f` re-centre |
| `<` / `>` | slow down / speed up time |
| `m` | **walk mode**: be the captain. The view closes in to five cells a metre, in true proportions, and follows him; arrows/`hjkl` walk the deck, `e` lists what you can do here (the next order of a gun's drill, casks to open, signals to hoist) with how long it will take you, `1`-`9` does it |
| `v` | reveal everything (debug: ignore line of sight) |
| `q` | quit |

## Scenarios (test environments)

```bash
python -m broadside.scenarios list
python -m broadside.scenarios run demo                # the playable demo (also `python -m broadside.main`)
python -m broadside.scenarios run tutorial            # eleven lessons in being the captain
python -m broadside.scenarios run sandbox             # a deck to walk, things to try
python -m broadside.scenarios run night_watch         # a night at sea: watches, sleep, a squall
python -m broadside.scenarios run fleet_orders        # signalling orders to a squadron
python -m broadside.scenarios run island_occlusion    # play one
python -m broadside.scenarios check --quick           # run headless, verify every checkpoint
python -m broadside.scenarios snapshot fog_bank --at 80   # print a frame as text
python -m broadside.scenarios replay                  # HTML replays of all -> replays/index.html
```

Pre-rendered replays of every scenario are in `replays/`. Open `replays/index.html` in a browser.

## World generation

```bash
python -m broadside.worldgen --seed 1805 --captain "Thomas Hardy" --ship Dauntless --nation Albion --out world
```

This prints a summary and writes `world/map.html` (political and terrain maps) and `world/chronicle.md` (the world's history). A pre-generated example is in `replays/world/`.

For a non-interactive smoke test (no terminal rendering, just runs the simulation for N ticks and prints a summary — useful for CI or checking the sim still behaves after a change):

```bash
python -m broadside.main --headless --ticks 500
```

## Running the tests

```bash
pip install -r requirements.txt   # includes pytest
pytest
```

The sim tests never need a terminal. The whole simulation is designed to run and be tested with none attached (see `docs/design/01_architecture.md`). `tests/test_vision.py` checks the line-of-sight model directly. `tests/test_scenarios.py` plays every scenario headless and checks its expectations; the two slow ones run only with `BROADSIDE_SLOW=1`.

## Project layout

```
docs/design/     the design documents — read these first
src/broadside/
  main.py          entry point
  engine/          infrastructure with no game knowledge (clock, RNG, events)
  sim/             all gameplay simulation logic (no rendering/IO)
    spatial.py       "what's at these points?" - the seam between sim and sight
    vision.py        2.5D line-of-sight ray marching
    shiplayout.py    1 m deck plans from ship data
    world/           terrain (islands, rocks, coasts) and atmosphere (haze, fog, smoke)
    state.py         SimState + the system pipeline
  view/            camera, map memory, frame composer, HUD, exporters (any scale)
  render/          terminal output: screen buffer + diffed renderer
  ui/              input handling and the interactive app
  scenarios/       the test-environment library, runner, CLI and HTML replays
tests/           headless tests against broadside.sim / broadside.engine
```
