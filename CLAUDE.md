# Broadside (on Tachyon): handoff notes

This is **the** Broadside: Napoleonic naval command, Dwarf Fortress style. The Python game in `legacy/` is the old version and will be deleted once everything is ported; everything worth keeping from it has been copied here: its 25 design docs and status report are in `docs/legacy/` (read `00_overview.md` and `08_interface.md` first), and its ship classes are in `data/ships/*.yaml`.

The engine (`../Tachyon`, its own repo; this crate depends on it by path) stays game-agnostic: anything every game could use goes into the engine (the sea, ships, shot, sight, names, UI widgets went there); anything naval-specific stays here.

## Run
```
cargo run --release                                                (from Broadside/)
cargo run --release -- --scenario action --ticks 600 --quarters --snapshot snaps/bs.html
cargo run --release -- --scenario line --bench 600 --auto --log
cargo test --release
```
Scenarios: action (brig v brig), frigates, odds (sloop v brig + cutter), line (74 v 74), free (`--class <key>`).

## Layout
```
src/data.rs    ship classes from data/ships/*.yaml (flat YAML subset, no library)
src/hull.rs    a class -> her grid: hull narrowing to the keel, planked levels (hold, orlop, gundecks, weather deck),
               gunports, hatches with ladders, masts, wheel, capstan, bowsprit, lanterns, stores; stations; sails and rudder
src/crew.rs    her company: generated names (tachyon::lang), backgrounds, 15 skills, quarter-bill roles; men aboard as creatures
src/drill.rs   the nine-step gun drill (legacy rules: time from skill, fatigue, physique, ball and gun weight, hands)
src/melee.rs   hand-to-hand: cutlass, pike, pistol; skill, fatigue, will to fight; real wounds; the fallen stay (docs/MECHANICS.md)
src/ship.rs    orders (course, sail, quarters, fire, mark); quartermaster steers; topmen set sail; drill; laying; firing
src/ai.rs      captains from their own person: skill, wit, dash, caution; missions; same orders as the player
src/game.rs    the sea, ships, shot; splinters and shot wounds into bodies; dismounted guns; log; scenarios
src/glass.rs   the glass (t) and the eye (T): first-person view held relative to her head, tilt, reticle, TAB holds a ship;
               bearings in points, aspect, range in cables; "a brig, hull up, bearing NNE, about 150 m" (tachyon::sight)
src/screen.rs  the command screen (legacy 08_interface): ship pane, chart, status strip, 5 panels, walk/look/glass modes
src/main.rs    menu, keys, headless --snapshot / --bench
```

## Design rules carried over
- Orders, not puppetry: you order a course, sail, quarters, a mark, a broadside; your people carry them out as fast as they can. A dead quartermaster means nobody steers.
- Rate of fire is not a number anywhere: it is the drill as done by those men.
- You are the only `@`; others read by trade (`&` officers, `g` gun captains, `t` topmen, `x` marines, `b` bosun's/carpenter's mates, `,` boys, `o` the rest).
- Everything is data and simulated; what isn't simulated yet is said so.

## Status (2026-10-10)
Phase 1 playable: menu, 5 scenarios, all 7 classes, crews as creatures (capped at 220 aboard for your ship, 130 for others; the rest are generated but not embarked), the drill, laying with judged range, at-will and broadside fire, splinters and shot wounds, dismounted guns, holes and flooding, AI captains who engage, break off and strike, grounding, collisions, walk and look modes, crew roster with skills and wounds.

2026-10-19, the glass: `t`/`T` take up the glass (7 deg, x10) or look by eye (70 deg); arrows sweep a quarter-field and tilt (-20..+40 deg), `+`/`-` the field, `f` dead ahead, `TAB` holds the next ship in sight (nearest first) and follows her, Esc puts it down. The pane shows sea, land (`sight::ground_bands`), ships (hull band, masts, canvas if set; hidden below the horizon by `sight::look`; your own ship left out), a reticle on the horizontal and a compass foot; the chart marks the field; the LOG panel carries the report. Snapshot: `--glass` or `--eye` (held on ship 1, or `--rel <deg>` off her head). Not yet: raising the glass taking time, lookouts reporting with their own accuracy, the fall-of-shot preview (`p`), weather to windward.

## To port from the legacy game (in rough order)
1. ~~The glass~~ done (see status). Left from `21`: the gun captain's fall-of-shot preview through the glass and on the chart.
2. Signals and squadrons: the code book, hoisting, reading, obeying (`17`, `19`).
3. The tutorial courses (`22`), five missions passed from the ship's own state.
4. Life aboard: watches and bells, meals from the casks, grog, sleep (`18`); psyche and morale, grievance, mutiny risk (`11`).
5. The surgeon: tourniquet, splint, amputation, infection (engine work in `life/body`).
6. Boarding and hand-to-hand (`13`), the magazine and fire (a powder explosion is `projectile::explode` with the engine's fire).
7. Sail handling aloft as acted work; rigging and spar damage.
8. The generated world: polities, ports, history (`12`), and a campaign.
