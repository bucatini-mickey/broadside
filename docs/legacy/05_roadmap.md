# Roadmap

No deadlines — this project is explicitly open-ended. Phases are ordered by dependency and by the Dwarf Fortress principle of keeping something playable/interesting at (nearly) every step, rather than front-loading months of invisible infrastructure. "Effort" is a rough number of solo work sessions (a few focused hours each), not a calendar estimate — useful for sequencing, not for planning a launch date.

Each phase lists an entry condition (what it needs from before) and an exit condition (how you know it's actually done, not just started).

## Phase 0 — Skeleton (this repository, as delivered)

**Exit condition:** `python -m broadside.main` runs in a real terminal, shows a split screen with a ship's deck (hull outline, a handful of crew wandering with basic needs-driven behaviour) on the left and a live status panel on the right, wind is visible and affects a simplified sail/heading model, and the player can steer/trim with the keyboard. `pytest` passes a small headless test suite covering the sailing-physics function and basic ECS wiring.

**Effort:** done.

## Engine v1 — Vision & views (done, between Phase 0 and Phase 1)

Built ahead of Phase 1 because every later phase depends on it. It covers captain's-perspective line of sight (terrain, hulls, rigging, fog, smoke, darkness, earth curvature), planning mode, one camera from the 1 m deck view to the fleet chart, contact records, 1 m deck plans, crew stations with pathfinding, gun smoke, and a scenario library with automated checks. See `07_vision_and_views.md`. Parts of Phase 1 (helm and tacking, crew task routing) and Phase 2 (broadsides) now exist in a first, shallow form.

## Phase 1 — One ship, properly

**Entry:** Phase 0. **Focus:** make the single-ship simulation deep and correct before adding more ships.

- Full hull model: sectioned integrity, flooding, pumps, careening.
- Full sail plan per ship class (from data files) with individual sail damage/reefing, not the skeleton's simplified single trim value.
- Proper points-of-sail polar curve, tacking/wearing as timed manoeuvres with failure risk ("in irons").
- Crew: full needs/mood, skills, watches, and the task/scheduling system (repair jobs auto-routed to available hands).
- Injury system with per-limb tracking and a surgeon role/station.

**Exit condition:** you can take a single ship on a multi-hour simulated passage — including at least one real weather change and one rigging failure needing crew repair — and every number that changed (position, sail state, crew fatigue, an injury if one occurred) is traceable to a mechanism, not a script.

**Effort:** large (this is the deepest single phase — it's most of "everything simulated").

## Phase 2 — Combat, one ship vs one ship

**Entry:** Phase 1. **Focus:** the core Napoleonic set-piece — a single-ship gunnery duel.

- Typed guns with period range/reload/crew-size mechanics, ammunition types (round/chain/grape).
- Damage resolution against the Phase-1 hull/rigging/crew model (this phase should add very little new "damage" infrastructure — it should mostly *use* Phase 1's hull sections, rigging state, and individual sailors as the thing combat damages).
- A second, AI-controlled ship using a minimal captain-AI (close to gun range, choose a broadside side, disengage if badly damaged).
- Boarding as a resolved local crew-vs-crew engagement.

**Exit condition:** a full single-ship engagement — manoeuvring for the weather gage, exchanging broadsides, and a decisive outcome (strike, sink, or disengage) — playable start to finish, with combat casualties visible as specific injured/killed named sailors.

**Effort:** medium-large.

## Phase 3 — Fleet & semaphore

**Entry:** Phase 2. **Focus:** more than one ship simulated at once, and the communication constraint that makes that interesting.

- Multiple ships (player's + a small consort squadron) each running the full Phase 1–2 simulation simultaneously.
- Semaphore: signal book/vocabulary, line-of-sight/range/weather/night constraints, message delay and misread risk, relay chains.
- Switching "which ship you're aboard" (walking the deck of your flagship vs. giving orders to a consort only by flag).

**Exit condition:** command a 3–4 ship squadron through an engagement where at least one order to a consort has to travel by semaphore rather than being an instant click — and can plausibly fail to arrive in time.

**Effort:** medium.

## Phase 4 — World generation

**Entry:** Phase 3 (want ships/combat solid before generating a world to put them in). **Focus:** the procedural Mediterranean-like theatre from `04_world_campaign.md`.

- Heightmap → coastline → depth field → currents/regional wind → settlements → factions pipeline.
- A chart/fleet-map view in the UI (the right-hand pane grows a real map mode).
- Basic navigation: plotting a course across open water using the wind field, not a straight-line "travel to" command.

**Exit condition:** generate a new theatre from a seed, sail a multi-day passage across open water using real navigation (tacking as needed) to reach a generated port.

**Effort:** medium-large.

## Phase 5 — Economy & logistics

**Entry:** Phase 4. **Focus:** ports become more than a map marker.

- Resupply (food/water/powder/shot/cordage/sailcloth) as real consumable stock, not an abstract meter.
- Repair/careening/dockyard tiers by port size.
- Trade goods, prize capture and prize-crew mechanics, prize money.
- Crew replacement in port (volunteers, press gangs, desertion risk).

**Exit condition:** complete a cruise that runs out of a real resource (powder, food, or hull integrity) far enough from home that reaching a port to resupply is a genuine, foreseeable challenge, not a formality.

**Effort:** medium.

## Phase 6 — Campaign layer & succession

**Entry:** Phase 5. **Focus:** turn "a sandbox with ships in it" into "a campaign with a career in it."

- Faction territory/relationship state and a coarse strategic AI that moves enemy fleets and reinforces ports over campaign time.
- Rank progression and widening command scope (single ship → squadron → fleet).
- The promotion-on-death succession mechanic, using officers who have been simulated (service record, mood history, relationships) since they first appeared as crew.
- Loss condition (no plausible successor left).

**Exit condition:** lose a captain in action, get handed control of a named, previously-simulated officer, and keep playing the same campaign without a reset.

**Effort:** medium-large.

## Phase 7+ — Depth and polish (ongoing, no fixed end)

Not a single phase so much as a long tail, revisited as motivation dictates: fortress/shore bombardment as a distinct tactical mode; weather hazards (squalls, fog, lee-shore danger); a fuller discipline/morale toolkit (courts martial, mutiny risk at the extreme); accessibility/UX passes on the terminal UI; performance work if profiling ever demands the compiled-extension escape hatch from `01_architecture.md`; and — only if genuinely wanted later, and explicitly a non-goal for now — anything beyond the Mediterranean/Napoleonic scope, or beyond single-player.

## Working principle across all phases

Prefer, at every step, the version of a feature that's *simulated shallowly and honestly* over one that's *scripted deeply and convincingly*. A hand-scripted "storm event" is tempting and quick; a genuinely simulated wind field that occasionally produces a bad storm because that's what the noise field did this week is more work up front and pays for itself for the rest of the project's life. This is the same bet Dwarf Fortress made and the reason it stayed interesting for decades — worth restating here because it's the principle most likely to get quietly abandoned under time pressure on any single phase.
