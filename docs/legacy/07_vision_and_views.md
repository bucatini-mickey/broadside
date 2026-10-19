# Vision, Line of Sight & Views (engine v1)

This document covers the scene engine added after Phase 0. It covers three things: the **captain's-perspective line-of-sight** model, **planning mode**, and **one camera at every scale**, from the 1 m Dwarf-Fortress deck view to the fleet chart. It also covers the **scenario library** used to test all of it. It sits alongside `01_architecture.md` (which it extends) and `03_rendering_ui.md` (whose split-screen/diffed-renderer design it builds on).

## Goals

1. **You see what the captain sees.** In live play the view shows only what is in sight from the observer's eyes. Rocks, land masses, trees, other hulls, your own masts and sails, fog, powder smoke, darkness and the curvature of the earth can all hide things. What is hidden is shown as hidden, Cataclysm-DDA style: black for never seen, dim "memory" colours for seen before, and a grey murk wall where the thing in the way is fog or smoke rather than something solid.
2. **Stop time and see your whole ship.** When paused (planning mode, DF-style), your own ship and crew are drawn in full whatever the sight lines. The captain knows his own ship. Everything beyond the rail stays as it was last seen.
3. **Two main perspectives, one engine.** The *local* view renders 1 m × 1 m cells: deck plans, individual sailors, guns, the smoke of each gun. The *macro* view looks down on a larger area, where ships are small clusters of glyphs, or a single heading symbol at chart scale. Zoom levels run continuously from 1 m to 640 m per column. North-up or ship-up rotation works at any zoom.
4. **Knowledge, not truth.** Ships you can't see aren't drawn at their true position. The sim keeps per-ship *contact records* (last seen where, how clearly, by whom), and the macro view draws those. A lost contact is a `?` at its last known position. This record is where semaphore reports will land in Phase 3.

## Pipeline

```
 sim/ (state)                       sim/spatial.py                sim/vision.py            view/
 ───────────                        ──────────────                ─────────────            ─────
 Terrain (analytic features) ─┐
 Atmosphere (haze, light,     ├──▶  SceneQuery.sample(xs, ys) ──▶  trace(eye, targets) ──▶  compose(): camera → cells
   fog banks, smoke puffs)    │     "what's here, how tall,        2.5D ray march:          seen / seen-above /
 Ships (ShipBody deck plans,  │      how much does it block?"      solid + overhang +       remembered / unknown
   sails braced to the wind) ─┘     at ANY resolution              fog/smoke/haze + poles   → ScreenBuffer
                                                                   + earth curvature          → terminal | text | HTML
```

- **`sim/spatial.py` is the single seam** between the sim's many representations and anything that looks at the world. It takes arrays of world points, at any spacing, and returns terrain code and height, which ship tile is there, whether a sail is overhead, fog/smoke density and the obstruction fields. The deck view calls it at 1 m spacing, the chart at 200 m, and the sighting system along individual rays.
- **`sim/vision.py`** traces lines of sight. It is pure numpy and has no rendering knowledge.
- **`view/`** holds the camera, map memory, frame composer and HUD. It reads the sim and never mutates it. Its only state is presentation state: zoom, rotation, whose eyes, and what the screen has shown before.

## One world, any resolution

Terrain is a list of analytic features (`Island`, `Rock`, `Coast`), each a vectorised function of position with noisy coastlines from deterministic value noise. It is not a fixed raster, so the same headland sampled at 1 m and at 100 m agrees with itself. Fog banks are noisy ellipses and smoke is a set of drifting gaussian puffs. Both are also functions of position.

Ships are the exception: each has a **1 m deck plan** (`sim/shiplayout.py`) generated from its class's real length, beam, gun count and rig. The plan has bulwarks, deck, masts, guns with crew stations, wheel, capstan, hatches and bowsprit. Sampling a ship means transforming the sample point into the ship's frame and looking up the plan. Sails are generated per query from the masts, the sail setting and the wind. Yards are braced round with the leeward yardarm aft, so the canvas you see (and that blocks your view) swings as the ship changes course.

## The line-of-sight model

For each target point the tracer samples the obstruction fields at regular steps along the line from the eye and asks:

| Question | Model |
|---|---|
| Is something solid in the way *at the height the line is at there*? | 2.5D: each point has a solid column `0..solid_top` (hull, rock, land, trees = ground + 12 m canopy), plus an optional overhanging band `over_bottom..over_top` (sails). A line can pass under a sail's foot. |
| Are thin poles in the way? | Masts are analytic circles (r = 0.35 m), not 1 m raster blocks. A mast 3 m in front of you hides a narrow wedge, not a quarter of the horizon. |
| Is a sail in the way? | Sails are analytic vertical walls (segments with a height band), tested exactly per ray, so they block the same way at 1 m and at chart scale. |
| How much murk does it pass through? | Fog, smoke and haze are all **extinction coefficients** σ (per metre). Transmittance is `exp(-∫σ)` (Beer–Lambert). Fog and smoke have *tops*: a line above them is unaffected. |
| Is it over the horizon? | Earth bulge (7/6 R for refraction) is added under each sample, so distant ships go **hull down** naturally. |

Visibility (meteorological, Koschmieder: `V = 3.912/σ`) is the unit scenarios are written in: "fog, 60 m visibility". Darkness scales effective visibility by the light level. Transmittance above `VIS_CLEAR` (0.2) is clear. Between that and `VIS_FAINT` (0.02) the thing is drawn but hazed. Below `VIS_FAINT` it can't be seen.

Every target is tested at **two heights**: its surface, and its tallest feature (mast head, sail head, treetop, summit). When only the tall one is visible, the cell draws just that feature. That's how you see topsails over a low islet or above a bank of smoke, or wooded crests over a headland.

### What blocks the captain

- **Other hulls, land, rocks, trees:** solid columns.
- **His own masts:** thin poles, so narrow wedges.
- **His own sails:** the courses' foot is 1.4 m above the deck and his eye is 1.7 m above it. He can see his own deck under the canvas, but the nearly level line to the distant sea ahead runs into it. That is why ships kept lookouts aloft. Reducing to **fighting sail** (below 55% sail setting) clews up the courses, and the forward view opens under the topsails. This matches period practice: ships stripped to fighting sail for battle partly for this reason.
- **His own bulwarks do not block.** The captain can step to the rail, so the observer's own hull is exempt (`ignore_hull_of`). His rigging is not exempt.

### Observers

Each fully crewed ship has a **captain** (quarterdeck, eye ≈ freeboard + 1.7 m) and a **lookout** at the main masthead (eye ≈ 29 m on the sloop). The lookout sees further and over more. His first sighting takes ~6 s to be called down to the deck ("Masthead: Sail ho!"). Press `o` in game to see through his eyes.

## Contacts (sim knowledge)

`sim/systems/sighting.py` runs twice a second. Each observer traces rays to three points along every other hull (at bulwark height) and to the main masthead:

- hull visible → `hull` ("IN SIGHT"); only masts visible → `topsails`;
- not seen for 3 s → `lost`, keeping the last known position, heading and time.

The macro view draws ships *from these records*. A `hull` contact is drawn as its cluster. A `topsails` contact is `†`. A `lost` contact is a `?` at its last known position. In the local view ships draw themselves cell by cell from sight lines, and known-but-unseen contacts show as `?` (lost) or `!` (masthead report). This is also why NPC ships don't need observers of their own yet (they will for AI in Phase 2).

## Views

*(The screen layout, the ship pane and chart pane side by side, is described in `08_interface.md`.)*

- **Camera** (`view/camera.py`): centre, metres per column, row aspect, rotation. Every view is this one camera with different settings. The composer asks for the world point at each cell centre and samples there, so zoom and rotation cost nothing extra.
- **Local** (≤ 2 m/col): deck tiles, crew `@` coloured by role (the captain highlighted), guns drawn as `─│╱╲` pointing outboard, sails `▒`, muzzle flashes `*`, smoke `░▒▓`. Cells default to true 1 m × 1 m (`c` toggles 1 m × 2 m for undistorted shapes).
- **Macro** (> 2 m/col): terrain plus ships splatted from contact records as `▓` clusters with a heading triangle and a letter label. At chart scale a ship is one symbol.
- **Memory** (`view/memory.py`): a sparse multi-resolution "seen" mask (1, 4, 16, 64, 256 m). Terrain is static, so remembered cells simply draw the terrain in memory colours. Ships are never remembered here; that is the contact records' job. A cell glimpsed up close doesn't make its whole coarse block "explored" when you zoom back in.
- **Planning mode** (`SPACE`): time stops, your ship and crew are revealed in full, and orders (quarters, fire, helm, sail, steer to cursor) apply immediately to the sim but nothing moves until time runs.

## Supporting systems added

- **Helm & navigation:** finite turn rate (worse with little way on), waypoint following with automatic tacking when the course lies inside the no-go zone, speed inertia (a tack costs way), grounding on reefs and land.
- **Crew stations:** beat to quarters assigns every hand a station (guns first, crew-slot by crew-slot on both sides, then helm and sail posts) by nearest-free greedy matching. Hands walk there on BFS paths over the real 1 m deck plan.
- **Gunnery:** guns reload only while manned (2+ crew; faster with 4). Broadsides ripple bow to stern, and every discharge emits a smoke puff with muzzle momentum. No ballistics or damage yet (Phase 2 hangs off the same fire event).
- **Smoke physics:** puffs billow, drift downwind, thin by spreading and dispersal, and are dropped only when their whole column is negligible. A broadside in a light breeze hides a hull for tens of seconds and clears in a few minutes, so the weather gage matters.
- **New ship classes:** `brig_14` (two-masted) and `ship_of_the_line_74` (main batteries on covered gundecks: they fire and smoke, but their crews are abstract).

## Scenario library (test environments)

`src/broadside/scenarios/`. Each scenario builds a scene, scripts timeline events, and declares **checkpoints**. A checkpoint has a caption saying what to look for, the view to look at it in, and machine-checked expectations such as "captain sees Hebe: none", "contact is lost", or "12+ guns manned".

| Key | Mechanism shown |
|---|---|
| `open_water` | baseline; 1 m deck view, planning vs live, macro clusters, ship-up rotation |
| `island_occlusion` | a frigate goes behind an island → `?` ghost → reappears |
| `topsails_over_reef` | 2.5D: hull hidden by a 9 m islet, topsails seen; masthead sees all |
| `fog_bank` | fog rolls through; visibility collapses; masthead sees mastheads above the fog |
| `broadside_smoke` | quarters, broadsides, smoke drifting over the enemy, clearing |
| `beat_to_quarters` | planning-mode orders; crew pathfind to stations; broadside |
| `hull_down` | earth curvature: topsails at 17 km, hull rises as you close *(slow)* |
| `night_passage` | nightfall shrinks visibility; distant ship lost, near one kept |
| `narrow_strait` | coasts, rocks, headland; autopilot through; hidden brig sighted *(slow)* |
| `fleet_action` | macro scale: two lines of 74s, an island screening part of one |
| `own_sails_blind_spot` | your own courses blind you; fighting sail clears the view |

```bash
python -m broadside.scenarios list
python -m broadside.scenarios run fog_bank          # play it
python -m broadside.scenarios check --quick         # verify expectations headless
python -m broadside.scenarios snapshot fog_bank --at 80
python -m broadside.scenarios replay                # HTML replays -> replays/index.html
```

`pytest` runs every scenario's checks (slow ones with `BROADSIDE_SLOW=1`).

## Performance

A full 150×46 frame (scene + HUD) takes ~110 ms in pure Python + numpy: ray tracing ~35%, per-cell glyph selection ~35%, memory/HUD the rest. The sim runs ~15–60× real time headless, depending on crew counts. Rays are batched by length. Frames trace against a raster pre-sampled at the camera's resolution (or coarser, capped at 360 cells a side), while the sighting system traces exact long rays. If profiling ever demands it, `trace()` has a plain-array signature ready for the compiled-extension path in `01_architecture.md`.

## Known limits / next steps

- Earth curvature is applied to obstructions and horizon but not to apparent heights for rendering. It is fine at the scales used.
- Masthead lookouts see but don't yet *report* terrain, and there are no telescopes (a magnification/identification layer is a natural addition).
- Contacts are per ship. Sharing between ships is exactly what semaphore (Phase 3) should do.
- Charts: coastlines currently start unknown. A "charted" layer (known but not seen) would suit the period.
- Only one deck level is modelled. Covered gundecks are abstract.
- Ships don't collide with each other. Grounding exists; shot ballistics and damage are Phase 2.
