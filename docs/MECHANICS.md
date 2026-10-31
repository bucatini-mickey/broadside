# Broadside mechanics ledger

One row per mechanic found in the legacy design docs (`docs/legacy/*.md`), checked against the Rust port in `src/` as of commit 91d9553 (2026-10-31, branch `queue/broadside`, from main).

Completeness over polish. Rows are grouped by area; ids are stable handles for `depends on`.

## How to read it

- **Source**: legacy doc number and section (`16 s6` = `16_observation_and_targeting.md`, section 6; `ST` = `STATUS_REPORT.md`; `P1`..`P7` = phases in `05_roadmap.md`).
- **Status**: `ported` (works in `src/` or in Tachyon as used by `src/`), `partial` (some of it, or a different/shallower form), `missing` (nothing yet).
- **Side**: where the work belongs. `engine` = general, belongs in Tachyon (`E:/Claude/Personal/Game Dev/Tachyon`); this ledger only notes it, nothing is implemented here. `game` = naval-only, stays in Broadside. `both` = engine supplies the primitive, Broadside supplies the naval rule.
- **Where / note**: the Rust file or Tachyon module that carries it today, or what is lacking. Where the engine already provides a mechanic the legacy game had to build itself, the status is `ported` and the note says `tachyon::...`.
- Status of engine-side rows was judged from Tachyon's module docs and from what `src/` actually calls; "engine has it, game does not use it" is marked `missing` with a note, so the gap shows up here.

## Summary

Counts are by status; the full list is below.

| Area | ported | partial | missing |
|---|---|---|---|
| Environment and sea | 7 | 5 | 12 |
| Ship, hull and sailing | 14 | 7 | 20 |
| Crew data and generation | 7 | 6 | 7 |
| Life aboard | 1 | 7 | 9 |
| Body and surgeon | 4 | 1 | 8 |
| Psyche, discipline, morale | 0 | 0 | 15 |
| Gunnery | 14 | 7 | 9 |
| Damage, fire, structures, items | 3 | 6 | 17 |
| Boarding and contact | 2 | 0 | 8 |
| Captains, AI, signals, fleet | 3 | 6 | 26 |
| Sight and knowledge | 9 | 2 | 9 |
| Interface | 11 | 12 | 10 |
| Tutorial, scenarios, sandbox | 1 | 3 | 12 |
| World, campaign, economy | 0 | 2 | 25 |
| Architecture and engine | 10 | 2 | 2 |
| **Total (341 rows)** | **86** | **66** | **189** |

Headline: the single-ship action (hull with real decks, crew as creatures, drill, laying, shot, holes, AI captains, grounding, glass) is ported. Everything above one ship's deck (signals, squadron command, campaign, world, economy), everything about the people's inner life (psyche, discipline, mutiny), the surgeon, boarding, fire, anchoring and the tutorial are missing. The sea itself (waves, tide, currents) is better in Tachyon than it ever was in the legacy game.

---

## 1. Environment and sea

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| ENV-01 | Wind: one global vector with drift | 09 s1 (Today), 02 s1 | partial | game | | `Game.wind` is a constant (2.0, -8.5); no drift or noise |
| ENV-02 | Wind field varying over space and time, sampled bilinearly | 09 s1, 02 s1 | missing | engine | ENV-01 | `tachyon::weather` exists (wind and rain) but `game.rs` does not use it |
| ENV-03 | Apparent wind (true wind minus ship velocity) | 09 s1 | ported | engine | | `Craft::step` feels apparent wind in her own frame |
| ENV-04 | Gusts and squalls (dangerous with too much sail up) | 09 s1, 18 s2 | missing | both | ENV-02, SAIL-12 | engine weather for the field; the over-canvassed-ship consequence is naval |
| ENV-05 | Wind shadow of islands and ships (blanketing) | 09 s1 | missing | engine | ENV-02 | reuse sight obstruction; no code in either repo |
| ENV-06 | Funnelling, coastal calms, land and sea breeze | 09 s1 | missing | engine | ENV-02, WLD-01 | |
| ENV-07 | Regional named winds (Mistral, Meltemi, Sirocco...) | 09 s1, 04 | missing | game | ENV-02, WLD-01 | needs a generated world to attach to |
| ENV-08 | Veering and backing as systems pass | 09 s1 | missing | engine | ENV-02 | |
| ENV-09 | Wind-sea and swell as a modelled spectrum (fetch, duration) | 09 s2, 24 s"A sea" | ported | engine | | `tachyon::sea::field` directional spectrum, JONSWAP, shelter, shoaling. Legacy had only a render texture |
| ENV-10 | Ship motion in the sea (heave, pitch, roll from waves; heel from wind) | 09 s2, 24 | ported | engine | ENV-09 | `Craft::step` |
| ENV-11 | Gun captain fires on the roll (down-roll hulls, up-roll rigs) | 09 s2, 10 s4 | partial | game | ENV-10 | `Fire::AtWill` documented "on the roll"; no up/down-roll doctrine per nation, no skill effect on timing |
| ENV-12 | Tides: height, almost nil in the Mediterranean | 09 s3 | ported | engine | | `Sea::tide`, M2+S2 harmonics, spring/neap |
| ENV-13 | Tidal streams in straits, Gibraltar inflow, Dardanelles outflow | 09 s3 | partial | engine | WLD-01 | stream and potential-flow currents exist; the named straits need a world |
| ENV-14 | Currents carry the ship (set and drift) | 09 s4 | ported | engine | | `Sea::current` fed into `Craft::step` |
| ENV-15 | Whirlpools, eddies at headlands | 24 | ported | engine | | `tachyon::sea::field` (not in legacy); game places none |
| ENV-16 | Depth from terrain compared with draught; grounding | 09 s5 | ported | engine | | `Sea::water_depth`, `CraftEvent::Grounded`, AI avoids shoals in `ai::sailable` |
| ENV-17 | Bottom type and holding ground | 09 s5 | missing | both | ENV-16, SEA-ANCH | |
| ENV-18 | Lead line: depth as knowledge, sung out by a leadsman | 09 s5, 08 | missing | game | ENV-16, CRW-09 | |
| ENV-19 | Day and night, light level, season calendar | 02 s1 | partial | engine | | `Clock`/`Daylight` in engine; game uses `glass::daylight(time)` only for the glass. No seasons |
| ENV-20 | Weather as a field: cloud, cloud shadow, rain, fog, damp quarters | 09 s6, 18 s2 | missing | engine | ENV-02 | `tachyon::weather` has rain; not wired into `Game` |
| ENV-21 | Rain wets men, spoils powder and slow match | 18 s2 | missing | both | ENV-20, LIF-03 | |
| ENV-22 | Fog banks and visibility in Koschmieder terms | 07, 09 s6 | partial | engine | | `sight::Air.visibility` and `Murk` exist; game passes a constant 25 km |
| ENV-23 | Barometer, seeing a blow coming | 09 s6 | missing | game | ENV-20 | |
| ENV-24 | Fish, birds, whales (shoals and gulls as sightings) | 24 | missing | engine | | |

## 2. Ship, hull and sailing

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| SHP-01 | Ship classes from data (cutter, gunboat, sloop, brig, frigate, 74, first rate) | 10 s1, 00 | ported | game | | `data/ships/*.yaml`, `src/data.rs` |
| SHP-02 | Rig types: ship, brig, fore-and-aft | 10 s1 | ported | game | SHP-01 | `data::Rig` |
| SHP-03 | Rates and which ships fight in the line | 10 s1 | partial | game | SHP-01 | classes exist; no rate concept, no line-of-battle rule |
| SHP-04 | Deck plan at 1 m: hull narrowing to keel, bulwarks, planking | 07, 13 | ported | game | | `hull::build`, tapered waterlines |
| SHP-05 | Real internal levels: hold, orlop, gundecks, weather deck | 16 s7, ST s6.1 | ported | game | SHP-04 | `hull.rs` builds one level per covered gundeck plus the hold; legacy never had this |
| SHP-06 | Hatches and ladders between levels | 16 s7 | ported | game | SHP-05 | `hull.rs`, `movement::climb` on `<` `>` |
| SHP-07 | Gunports as openings; lower ports shut at sea, opened for action | 09 s1, 10 s1 | ported | game | SHP-05 | `Ship::assign` toggles port tiles |
| SHP-08 | Lower ports taking water when heeled in a blow | 09 s1 | partial | engine | ENV-10 | engine floods over a low rail/port; no deliberate "shut the lee ports" order |
| SHP-09 | Fittings: wheel, capstan, bowsprit, lanterns, hammocks, masts | 07, 13 | ported | game | SHP-04 | `hull::Kinds` |
| SHP-10 | Captain's cabin, wardroom, cockpit, galley, sick berth as rooms | 24 s"Captain mode", 10 s1 | missing | game | SHP-05 | only a `captain` post and berths are laid out |
| SHP-11 | Stores in the hold, powder in the magazine as items | 13 s"Items" | partial | game | SHP-05 | casks spawn in `hull.rs`; gun-side `powder`/`shot` are plain counters on `Ship`, not drawn from the casks |
| SHP-12 | Derived characteristics: displacement, metacentric height, canvas | 10 s6 | ported | game | SHP-01 | `ShipClass::displacement/gm/canvas` |
| SHP-13 | Stores capacity, crew required, roll period derived from design | 10 s6 | partial | game | SHP-12 | roll period is emergent from engine; stores not derived |
| SHP-14 | Refit/shipyard (re-arm, re-rig, re-copper), free ship designer | 10 s6 | missing | game | SHP-12, ECO-02 | |
| SHP-15 | Copper sheathing and fouling affecting speed | 10 s6 | missing | game | SHP-14 | |
| SHP-16 | Hull integrity as holes, below-waterline leaks, flooding by Torricelli | 02 s2, 15 limits | ported | engine | | `Craft` holes; `CraftEvent::Holed`; `water_inside`, foundering |
| SHP-17 | Pumps manned by crew, opposing flooding | 02 s2 | missing | both | SHP-16, CRW-10 | |
| SHP-18 | Carpenter plugs shot holes | 10 s3, 18 | missing | both | SHP-16, CRW-10 | engine `Craft::plug` exists; no crew job drives it |
| SHP-19 | Careening and beaching for repair | 02 s2 | missing | both | SHP-16, ENV-16 | |
| SHP-20 | Ship's boats: launch, cutter, jolly; towing, landing, abandoning | 02 s2 | missing | both | SHP-05 | |
| SAIL-01 | Sailing from sail and rudder forces rather than a polar | 00, 10 s2 | ported | engine | | `Foil` model in `Craft`; irons, leeway, inertia emerge. Replaces legacy polar curve |
| SAIL-02 | Helm with rudder needing way; way gathered and lost slowly | 08 pacing | ported | engine | SAIL-01 | |
| SAIL-03 | Quartermaster steers the ordered course; dead QM = nobody steers | ST s5 | ported | game | CRW-01 | `Ship::steer` |
| SAIL-04 | Sail ordered, then set by topmen at the speed they work | 08 pacing | ported | game | CRW-01 | `Ship::make_sail`, `Orders.sail`, `Ship.set` |
| SAIL-05 | Named sails (course, topsail, topgallant, royal, jibs, spanker) individually trimmed | 02 s2, 10 s1 | partial | game | SAIL-04 | one 0..1 plain-sail value mapped to canvas; fore-and-aft vs square foils exist |
| SAIL-06 | Fighting sail (clewing up courses) | 07, 08 | partial | game | SAIL-05 | `w`/`s` steps in quarters; no named fighting-sail setting or its sight benefit (SGT-09) |
| SAIL-07 | Yards braced to the wind | 07 | missing | game | SAIL-05 | foils trimmed, yards not shown braced |
| SAIL-08 | Tacking as a timed evolution that can fail (miss stays, in irons) | 10 s2, P1 | missing | game | SAIL-03, CRW-10 | irons arise physically; no "ready about" crew evolution |
| SAIL-09 | Wearing ship | 10 s2 | missing | game | SAIL-08 | |
| SAIL-10 | Heaving to | 10 s2 | missing | game | SAIL-05 | |
| SAIL-11 | Reefing topsails | 10 s2, 18 s2 | missing | game | SAIL-05 | |
| SAIL-12 | Over-canvassing: sprung masts, split sails, capsize | 09 q1, 10 s6 | missing | both | ENV-04, SAIL-05 | open design question 09 q1 |
| SAIL-13 | Sail handling aloft as acted work (loosing, furling, topmen can fall) | ST s6.3 | missing | game | SAIL-05, CRW-10 | |
| SAIL-14 | Standing and running rigging as damageable objects; dismasting | 02 s2, 10 s1 | missing | game | SAIL-05, DMG-08 | |
| SAIL-15 | Boxhauling, club-hauling off a lee shore | 10 s2 | missing | game | SAIL-08, SEA-ANCH | |
| SAIL-16 | Lee shore and sea room as a danger | 10 s2 | partial | game | ENV-16 | grounding exists; AI avoids shoals; no lee-shore warning or master's advice |
| SAIL-17 | Hull speed, hull drag, wave-making resistance | 10 s6 | ported | engine | | `Craft::step` |
| SEA-ANCH | Anchor: order, 14 s to let go, 75 s to weigh, will not hold under sail | 22 s"The anchor" | missing | both | SHP-09, CRW-10 | |
| SEA-MOOR | Docking as anchoring within a boat's pull of the mole | 22 | missing | game | SEA-ANCH, WLD-04 | |
| SEA-SPRING | Springs on the cable to turn a ship at anchor | 09 s5 | missing | game | SEA-ANCH | |
| SEA-DRAG | Dragging anchor in a gale | 09 s5 | missing | game | SEA-ANCH, ENV-17 | |

## 3. Crew data and generation

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| CRW-01 | Every man a creature with body, needs, station | 11 s"Who is aboard", ST s1 | ported | both | | `crew::embark`; engine `life` supplies creatures |
| CRW-02 | Whole establishment generated; only some embarked (cap 220 / 130) | 11, ST s5 | partial | game | CRW-01 | generated but not embarked above the cap; the legacy kept the rest as simulated `Below` |
| CRW-03 | Backgrounds driving skill, age, devotion (10 + officer) | 11 s"Generation" | partial | game | | `crew::BACKGROUNDS`: skills and age only; devotion, drink and traits missing |
| CRW-04 | Fifteen skills incl. the ones for every role | 11 | ported | game | | `crew::SKILLS` |
| CRW-05 | Roles assigned by skill in quarter-bill proportions | 11 | ported | game | CRW-04 | `crew::company` |
| CRW-06 | Generated names with meanings (people, ships) | 14 | ported | engine | | `tachyon::lang::Culture`; `Person.meaning`, `Ship.meaning` |
| CRW-07 | Generated language blending, mutation, lexicon, families | 14 | ported | engine | | `tachyon::lang` |
| CRW-08 | Place and nation names from the language | 14, 12 | partial | engine | WLD-01 | engine can; the game names no places |
| CRW-09 | Rank and role set: master, boatswain, gunner, carpenter, purser, surgeon, cook, lookout, master's mates, captains of the tops | 10 s3 | partial | game | CRW-05 | roles in code: captain, lieutenant, midshipman, gun captain, gunner, topman, quartermaster, bosun's mate, carpenter's mate, marine, boy, waister. No surgeon, master, cook, purser, boatswain |
| CRW-10 | Task and job scheduling (auto-routed repair jobs to free hands) | 00, 02 s3 | missing | both | CRW-01 | engine `life::mind::Task` is a base; no naval job board (pump, plug, splice) |
| CRW-11 | Personality traits (bravery, temper, sociability, discipline, ambition, honesty, optimism, resilience) | 11 s"The data" | partial | game | CRW-03 | only `bravery` and `discipline` on `Person` |
| CRW-12 | Allegiance (nation, cause, captain, ship) | 11 | missing | game | CRW-03 | |
| CRW-13 | Cravings (drink dependence, tobacco) | 11, 18 | missing | game | CRW-03 | |
| CRW-14 | Biography: dated events from history and from the sim | 11, 12 s"History" | partial | game | WLD-05 | `Person::story()` is one line |
| CRW-15 | Nicknames from extreme traits | 11 | missing | game | CRW-11 | |
| CRW-16 | Crew mix of 70% home culture and 30% others | 14 | ported | game | CRW-06 | `crew::company` takes a `Culture` (verify exact mix) |
| CRW-17 | Skill growth with practice | 02 s3 | missing | game | CRW-04 | |
| CRW-18 | Roles by trade glyph; you are the only `@` | 08 | ported | game | CRW-05 | `Role::glyph` |
| CRW-19 | Women and non-combatants aboard | ST s7, 11 q3 | missing | game | | open design question, undecided |
| CRW-20 | Superstition as a light trait | ST s7, 11 q2 | missing | game | CRW-11 | open question |

## 4. Life aboard

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| LIF-01 | Two watches, watch below really below and asleep | 18 s1 | partial | game | CRW-01 | `Ship::assign` flips on four-hour blocks; watch below goes to hammocks (`Task::Sleep`). Core and idlers always on deck |
| LIF-02 | Dog watches and bells (eight bells, half-hour glass) | 18 s1, 08 | missing | engine | LIF-01 | engine `Clock` has hours; no bell or dog-watch rotation |
| LIF-03 | Sleep paying off fatigue ~6x; day rest a third | 18 s1 | partial | engine | LIF-01 | engine `life::needs` has fatigue/sleep; rates not tuned to legacy |
| LIF-04 | Beat to quarters overrides sleep; owed sleep after | 18 s1 | ported | game | LIF-03 | `assign(true)` wakes everyone |
| LIF-05 | Meals at fixed hours from the real casks | 18 s1 | missing | game | SHP-11, LIF-03 | stores spawn but nobody eats them |
| LIF-06 | Short commons felt as grievance | 18 s1, 22 | missing | game | LIF-05, PSY-01 | |
| LIF-07 | Grog at dinner and supper; rum from the puncheon | 11, 18 | missing | game | LIF-05, CRW-13 | |
| LIF-08 | Short allowance (`r`) and splicing the mainbrace (`G`) | 22 | missing | game | LIF-07 | |
| LIF-09 | Hunger, thirst, fatigue as decaying needs | 02 s3, 11 | partial | engine | | engine `life::needs` supplies them; drill reads fatigue; no ship-side feeding |
| LIF-10 | Station bills per evolution (tack, reef, anchor, fire, boarding) | 10 s3 | partial | game | CRW-05 | quarter bill only |
| LIF-11 | Hammocks piped up and stowed in the netting | 18 s1 more | partial | game | | hammock kind exists as the bed; no stowing |
| LIF-12 | Galley and cook actually cooking; galley fire put out at quarters | 18 s1 more, 10 s3 | missing | game | CRW-09 | |
| LIF-13 | Idlers' own work; officers' routine | 18 s1 more | missing | game | CRW-09 | |
| LIF-14 | Watch-and-watch as punishment | 18 s1 more | missing | game | LIF-01, DIS-01 | |
| LIF-15 | Sick list and surgeon's rounds | 18 s1 more | missing | game | BOD-08 | |
| LIF-16 | Clearing for action (bulkheads down, sand, nets, boats streamed) | 10 s3 | partial | game | SHP-07 | quarters opens ports and mans stations; no bulkheads/sand/nets |
| LIF-17 | Time compression: sleeping as time skip, passage fast-forward | 24 s"Captain mode", 09 q3 | partial | game | | `, .` gives 0.5x..32x; no turn-in-until-morning |

## 5. Body and surgeon

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| BOD-01 | Body with parts, wounds, bleeding, death by blood loss | 11 s"Body", 18 s3 | ported | engine | | `tachyon::life::body` (tissue layers, organs, `fatal`); different model from legacy 12-part list |
| BOD-02 | Capabilities (grip, reach, stand, walk, see) taxed by pain and blood | 18 s3 | ported | engine | BOD-01 | `Body::capacities`; drill reads them in `Ship::physique` |
| BOD-03 | Shot and splinter wounds into bodies | 15, ST s1 | ported | game | BOD-01 | `game::wound`, `splinters` |
| BOD-04 | Fracture, splint, artery cut, tendon cut, tourniquet, infection per limb | 18 s3 | partial | engine | BOD-01 | wound kinds exist in engine; tourniquet/splint/infection as treatment states are not wired (CLAUDE: "engine work in `life/body`") |
| BOD-05 | Death on collapse (~33%) and heart stop (~45%) | 11 | ported | engine | BOD-01 | |
| BOD-06 | Bodies stay where they fell | 13 | missing | game | BOD-01 | check whether creatures remain as corpses in `Scene`; no handling code in `src/` |
| BOD-07 | Heart rate and pulse reported | 11 | missing | game | BOD-01 | |
| BOD-08 | Surgeon, cockpit, wounded carried below, queue | 18 s3 plan, ST s6.2 | missing | game | SHP-10, CRW-09, BOD-04 | |
| BOD-09 | Operations as timed work that can fail: tourniquet, binding, extraction, amputation | 18 s3 | missing | both | BOD-08, CRW-10 | |
| BOD-10 | Infection and fever over days; invalided home | 18 s3 | missing | engine | BOD-04 | |
| BOD-11 | Pain remedies (laudanum, rum) | 18 s3 | missing | game | BOD-08 | |
| BOD-12 | Permanent consequences, re-weighting skills after loss of a limb | 18 s3 | missing | game | BOD-01, CRW-04 | |
| BOD-13 | Scarring and recovery curves | 18 s3 | missing | engine | BOD-01 | `Body::step(heal)` exists; no long-term curves |

## 6. Psyche, discipline, morale

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| PSY-01 | Psyche state (morale, stress, anxiety, depression, confidence, fear, grievance) | 11 s"Psyche" | missing | both | CRW-01 | engine `mind` has a base; none of these on `Person` |
| PSY-02 | Fear from gunfire within 400 m, scaled by bravery | 11 | missing | game | PSY-01 | |
| PSY-03 | Feelings with fade times and diminishing returns | 18 s4 | missing | engine | PSY-01 | general, move to engine |
| PSY-04 | `appraise(event, weight)` through character | 18 s4 | missing | both | PSY-03 | |
| PSY-05 | Events hooked up: gunfire, struck, shipmate hurt, own broadside, shot home, fed, soaked, slept | 18 s4 | missing | game | PSY-04 | |
| PSY-06 | Ship morale aggregate and mutiny risk | 11 s"Ship morale" | missing | game | PSY-01 | |
| PSY-07 | Mutiny led by ringleaders, not a ship-wide number | 18 s4 plan | missing | game | PSY-06, CRW-11 | |
| PSY-08 | Desertion in port, sullen refusals | 11 s"What uses this" | missing | game | PSY-06, WLD-04 | |
| PSY-09 | Relationships: messmates, particular friends, hated officers | 18 s4 plan | missing | game | CRW-01 | |
| PSY-10 | Memory of events carried (famous action, flogged once) | 18 s4 plan | missing | game | PSY-04, CRW-14 | |
| PSY-11 | Expression: sullen work, cheering, flinching | 18 s4 plan | missing | game | PSY-01 | |
| DIS-01 | Flogging as an event with fear and anger edges | 02 s3, 18 s4 | missing | game | PSY-04 | |
| DIS-02 | Stopping grog, disrating, extra duty, promotion, prize shares | 02 s3, ST s7 | missing | game | PSY-04, LIF-07, ECO-04 | |
| DIS-03 | Drink as coping: theft from the spirit room, drunk at quarters | 11 q1, ST s7 | missing | game | CRW-13 | open question |
| DIS-04 | Courts martial | 05 P7 | missing | game | DIS-01 | |

## 7. Gunnery

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| GUN-01 | Guns typed by pounder, carronade flag, mass, muzzle speed, crew size | 10 s4, 02 s4 | ported | game | SHP-01 | `data::Battery` |
| GUN-02 | Nine-step drill by numbered stations | 17 s1 | ported | game | CRW-01 | `drill::DRILL`, `Ship::drill` |
| GUN-03 | Step time from skill, fatigue, physique, weight, hands | 17 s1 | ported | game | GUN-02, BOD-02 | `drill::step_time` |
| GUN-04 | Covering another man's station, 20% slower | 17 s1 | ported | game | GUN-02 | `own_station` flag |
| GUN-05 | Job dropped when its man falls; next man resumes the step | 17 s1 | ported | game | GUN-02 | |
| GUN-06 | Rate of fire emerges from the above (no constant) | 17 s1 | ported | game | GUN-03 | `tests/game.rs` `the_drill_sets_her_rate_of_fire` |
| GUN-07 | Reload on a timer for crewless or below-deck guns | 17 s1 | partial | game | SHP-05 | covered-deck guns have crews in the port; no timer path for far fleets (no LOD) |
| GUN-08 | Powder from the magazine, served out at quarters, deducted | 17 s2 | partial | game | SHP-11 | `Ship.powder`/`shot` counters decrement per step; no cartridges carried up, no charge by calibre |
| GUN-09 | Boys/powder monkeys carry cartridges as people who can be killed | 17 s2, ST s6.3 | missing | game | GUN-08, CRW-10 | |
| GUN-10 | Guns run dry and say so | 17 s2 | ported | game | GUN-08 | `GunState.waiting` ("no powder", "no shot") |
| GUN-11 | Gun captains lay their own pieces, solving elevation against real ballistics | 16 s6 | ported | both | GUN-02 | `Ship::lay` on `tachyon::ballistics` |
| GUN-12 | Range misjudged by skill; error re-rolled per lay | 16 s6 | ported | game | GUN-11 | `GunState.judged` |
| GUN-13 | Training arc ±12 deg, elevation limits | 16 s6 | ported | game | GUN-11 | `drill::MAX_TRAIN/MAX_ELEV/MIN_ELEV` |
| GUN-14 | Aim at the foot of walls, hull for ships | 16 s6 | partial | game | WLD-07 | ships only; no walls |
| GUN-15 | Named target (`x` on look cursor), obeyed after comprehension delay 6 s + 26 s x (1 - skill) | 16 s5 | partial | game | GUN-11 | `Orders.target` and `n` cycles the next enemy; no delay, no look-cursor targeting |
| GUN-16 | Gun that cannot bear lays on what it can | 16 s5 | partial | game | GUN-15 | |
| GUN-17 | Fire modes: hold, at will, broadside ripple | 02 s4, 08 | ported | game | GUN-02 | `Fire::{Hold,AtWill,Broadside}`; ripple bow to stern in `Ship.ripple` |
| GUN-18 | Round shot flying under gravity and drag, ricochet off water | 15 s"The ball" | ported | engine | | `tachyon::ballistics`, `projectile` |
| GUN-19 | Fall-of-shot preview (`p`) by the gun captain, precision by skill, arc in glass and track on chart | 21 s"fall of shot", 20 s2 | missing | both | GUN-11, SGT-01 | CLAUDE.md: "left from 21". Gated: only at quarters with a man at a loaded gun (22) |
| GUN-20 | Fall-of-shot reports after firing ("over, two cables") | 21 s"next time", 20 s2 | missing | game | GUN-18, CAP-02 | |
| GUN-21 | Solver for a given range with roll modelled; "lay for her waterline" | 21, 20 held back | missing | game | GUN-11, ENV-10 | |
| GUN-22 | Ammunition types: chain, bar, grape, canister, double shot | 10 s4, 02 s4 | missing | both | GUN-18, DMG-08 | `Shot`/`Battery` carry round shot only |
| GUN-23 | Heated shot (shore batteries) | 10 s4 | missing | game | GUN-22, FIR-01 | |
| GUN-24 | Raking: shot down the length of a ship | 10 s4, 02 s2 | partial | game | DMG-01 | emerges from hit cells on a real deck grid; no sectional hull accounting or doctrine |
| GUN-25 | Weather gage: smoke blinding the leeward ship, heel pointing guns | 10 s5 | partial | game | ENV-10, SGT-07 | smoke murks are in; no heel doctrine |
| GUN-26 | Dismounted guns | ST s1 | ported | game | DMG-01 | `game::hits` marks `GunState.disabled` |
| GUN-27 | Bow and stern chasers, guns firing ahead | 10 s5 | missing | game | GUN-13 | no fore/aft arcs beyond ±12 deg |
| GUN-28 | Hold fire, fire on the roll, choice of ammunition per gun | 17 s6, ST s8 | missing | game | GUN-22 | |
| GUN-29 | Gun smoke puffs with muzzle momentum drifting downwind | 07 | ported | engine | | `Game.smoke` murks plus engine gas/projectile |
| GUN-30 | Crews working one gun by hand (player does every step) | 15 s"Working the gun" | missing | game | GUN-02, UI-07 | legacy `sim/actions.py` |

## 8. Damage, fire, structures

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| DMG-01 | Hull hits resolved per cell against material, with energy | 13, 15 | ported | engine | | `Craft::take_hits`, `ShotEvent` |
| DMG-02 | Materials with toughness, flammability, splinter tendency, density | 13 s"Structure" | partial | both | DMG-01 | `hull::materials()` has oak and deal (plus engine materials); copper, canvas, hemp, stone, earth to add |
| DMG-03 | Splinters from oak hits wound nearby men | 15, 02 s4 | ported | game | DMG-01, BOD-03 | `game::splinters` |
| DMG-04 | Integrity per tile shown (damaged planks, holes) | 13 | ported | engine | DMG-01 | |
| DMG-05 | Look cursor reports "pine planking, splintered (43%)" | 13 | partial | game | DMG-04 | `screen::look_at` |
| DMG-06 | Hull sectioned (bow/waist/stern, port/starboard) integrity | 02 s2 | partial | game | DMG-01 | emergent from the grid, not tabulated |
| DMG-07 | Material connections: a struck timber drags its neighbours | 16 s8, ST s6.5 | missing | engine | DMG-01 | |
| DMG-08 | Rigging and spar hits (chain shot, shot-away lines, torn sails) | 10 s1, 02 s2 | missing | both | SAIL-14, GUN-22 | |
| DMG-09 | Object skeletons: named parts ("left curtain wall", "foremast") | 16 s4, ST s6.7 | missing | engine | DMG-01 | generic part graph is engine work; naval part names are game |
| DMG-10 | Orders and reports in terms of parts ("attack the magazine") | 16 s5, ST s6.7 | missing | game | DMG-09, GUN-15 | |
| DMG-11 | Ship reports her own damage ("hurt" 0..1 from water, men, guns) | 19 s3 (signal 8) | partial | game | DMG-06 | `ai::hurt` exists, not reported by signal |
| FIR-01 | Fire on a ship: spreading by flammability, burning | 13 s"Next", ST s6.6 | missing | both | DMG-02 | `tachyon::flames`/`heat` exist; no ignition source in game |
| FIR-02 | Fire-fighting (buckets, pumps, flooding the magazine) | 10 s3 | missing | game | FIR-01 | |
| FIR-03 | Magazine explosion | ST s6.6 | missing | both | FIR-01 | `projectile::explode` ready in engine |
| FIR-04 | Fire ships | 09 s1 | missing | game | FIR-01 | |
| STR-01 | Voxel walls of 0.5 m blocks: energy penetration, cracks, arching, crushing, collapse, rubble | 15 s"The wall" | missing | engine | | engine cells are 1 m; half-metre blocks are an engine decision |
| STR-02 | Dust, rubble, spall as atmosphere kinds | 15 s"Dust and smoke" | missing | engine | STR-01 | |
| STR-03 | Fortresses and batteries as garrisoned structures | 13 s"Fortresses", 02 s4 | missing | both | STR-01, WLD-04 | |
| STR-04 | "A ship is a fool to fight a fort" falling out of the numbers | 02 s4 | missing | game | STR-03 | |
| STR-05 | Collapse toppling rather than dropping | 15 limits | missing | engine | STR-01 | |
| STR-06 | Shot bouncing along a deck; splinter cone from masonry | 15 limits | missing | engine | | |
| ITM-01 | Items as entities with contents, stowage, condition | 13 s"Items" | partial | engine | SHP-11 | engine `things` supports it; ship stores are a few kinds, no contents |
| ITM-02 | Period ration scales and victualling from complement and cruise | 13 | missing | game | ITM-01 | |
| ITM-03 | Consumption, spoilage, theft, resupply | 13 s"Next" | missing | game | ITM-02, LIF-05 | |
| ITM-04 | Shot garlands emptied by firing, refilled from lockers | 13, 17 s2 | partial | game | GUN-08 | counters only |
| ITM-05 | Look cursor reports a cask's contents | 13 | missing | game | ITM-01 | |

## 9. Boarding and contact

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| BRD-01 | Tile-exact collision between hulls, damage by closing speed | 13 s"Collision" | ported | engine | | `craft::collide`, `game::collide_ships` |
| BRD-02 | Fouling: ships locked until cut free | 13, ST s8 | missing | both | BRD-01 | collisions knock ships apart instead |
| BRD-03 | Cutting free | ST s8 | missing | game | BRD-02 | |
| BRD-04 | Gangways between rails; boarders cross | 13 | missing | game | BRD-02 | |
| BRD-05 | "Boarders away" picking best fighters; marines' musketry | 13, 10 s5 | missing | game | BRD-04, CRW-04 | |
| BRD-06 | Melee by skill and fear, wounding real body parts | 13 | missing | game | BRD-04, BOD-01 | creatures can attack in engine (`Species::Attack`); no boarding logic |
| BRD-07 | Defenders turning out | 13 | missing | game | BRD-06 | |
| BRD-08 | Striking colours | 10 s5 | ported | game | | AI `Mission::Struck` and `S S` for the player |
| BRD-09 | Prize crews, prizes sailed to port, prize money | 02 s6, 10 s5 | missing | game | BRD-08, ECO-04 | |
| BRD-10 | Home ship memory for crossing men | 13 | missing | game | BRD-04 | |

## 10. Captains, AI, signals, fleet

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| CAP-01 | Captain mind from his own person: skill, wit, aggression, caution | 19 s2 | ported | game | CRW-04 | `ai::Captain::from` |
| CAP-02 | Discipline parameter: obeying disliked signals, order expiry | 19 s2 | missing | game | CAP-01, SIG-03 | no discipline in `Captain` |
| CAP-03 | Wit sets how often he thinks (3 s to 17 s) | 19 s2 | ported | game | CAP-01 | `ai::command` |
| CAP-04 | Missions: hold, station, engage, chase, withdraw, close, heave to | 19 s2 | partial | game | CAP-01 | `Mission::{Hold,Engage,Flee,Struck}` |
| CAP-05 | Decision order: signal, haul-off check, admiral's order, odds, engage/chase/station | 19 s2 | partial | game | CAP-04 | haul-off and odds yes; signal and admiral steps no |
| CAP-06 | Laying course: closing on a slant, taking the weather gage, holding the chosen range | 19 s2 | partial | game | CAP-04, ENV-01 | engage at a range; no deliberate weather gage |
| CAP-07 | Captain knows only what his own contacts show | 19 s2 | missing | game | SGT-02 | `game::tick` builds contacts from true positions |
| CAP-08 | Orders only through the player's own controls | 19 s2 | ported | game | CAP-01 | AI sets `Orders` |
| CAP-09 | Breaking off when beaten (hull, casualties, morale) | 19 s2 | partial | game | CAP-04, PSY-06 | `ai::hurt` without morale |
| CAP-10 | Station keeping, line ahead | 19, 10 s5 | missing | game | CAP-04 | |
| CAP-11 | Chase, stern chase, lightening ship | 10 s5 | missing | game | CAP-04 | |
| CAP-12 | Cutting out, doubling, breaking the line | 19 s5, 10 s5 | missing | game | CAP-10 | |
| CAP-13 | Captains with names, records, favourites | 19 s5 | missing | game | CRW-14 | |
| SIG-01 | Code book of numbered signals | 17 s3, 19 s3 | missing | game | | the whole signalling system is unported |
| SIG-02 | Hoisting takes a hand and 8-20 s | 17, 19 | missing | game | SIG-01, CRW-09 | |
| SIG-03 | Signals mean orders (1-12 table) | 19 s3 | missing | game | SIG-01, CAP-05 | |
| SIG-04 | Addressed to one ship or the squadron | 19 s3 | missing | game | SIG-01 | |
| SIG-05 | Read after a delay set by lookout skill and range | 17 s3 | missing | game | SIG-01, SGT-02 | |
| SIG-06 | Legibility through fog and smoke | 17 s3 | missing | game | SIG-05, ENV-22 | `sight::Murk` exists in engine |
| SIG-07 | Misreading by dull signal midshipmen | 19 s3 | missing | game | SIG-05 | |
| SIG-08 | Refusal by bold, undisciplined captains | 19 s3 | missing | game | SIG-03, CAP-02 | |
| SIG-09 | Orders expire after 60-360 s | 19 s3 | missing | game | CAP-02 | |
| SIG-10 | Report damage answered from the ship's state | 19 s3 | missing | game | SIG-03, DMG-11 | |
| SIG-11 | Enemy can read flags but does not obey | 19 s3 | missing | game | SIG-01 | |
| SIG-12 | Flags visible at the masthead; enemy hoists readable through the glass | 20 s4 | missing | game | SIG-01, SGT-01 | |
| SIG-13 | Popham's telegraphic code and compound signals | 19 s5, 10 s5 | missing | game | SIG-01 | |
| SIG-14 | Repeating frigates relaying down the line | 10 s5, 00 | missing | game | SIG-05 | |
| SIG-15 | Semaphore as the only remote channel; orders take time to arrive | 00, 02 s5 | missing | game | SIG-01 | |
| FLT-01 | Squadron: consorts under AI captains | 19, P3 | partial | game | CAP-01 | `odds` scenario has a consort; nothing to command it |
| FLT-02 | Switching which ship you are aboard | P3 | missing | game | FLT-01 | |
| FLT-03 | Fleet command hierarchy (divisions, flag officers) | 04 s"Rank", 19 s5 | missing | game | FLT-01 | |
| FLT-04 | Full-fidelity simulation of off-screen ships | 00, 02 s5 | partial | engine | | every ship in a `Game` ticks fully; no world-scale LOD |
| FLT-05 | Admiralty orders as missions | 19 s5 | missing | game | CAM-01 | |
| FLT-06 | Simulation LOD for far fleets | 13 s"Performance" | missing | engine | FLT-04 | |
| FLT-07 | Line of battle, rating rules (ships of the line do not fire on frigates) | 10 s1, s5 | missing | game | CAP-10 | |

## 11. Sight and knowledge

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| SGT-01 | The glass (`t`): first-person view along a bearing, x10, 7 deg | 16 s2, 21 | ported | both | | `glass.rs` over `tachyon::sight` |
| SGT-02 | Contact records: seen, topsails, lost, last-known position | 07 s"Contacts" | missing | game | SGT-01 | no records; AI uses true positions |
| SGT-03 | The eye (`T`): 70 deg, no magnification | 16 s2 | ported | game | SGT-01 | |
| SGT-04 | Glass held relative to her head, tilting, reticle, TAB holds a ship, `f` ahead | 21 s"glass", ST | ported | game | SGT-01 | |
| SGT-05 | Bearings in points, aspect words, range in cables | 21 s"The words" | ported | game | SGT-01 | `glass::relative_words`, `aspect_words`, `range_words` |
| SGT-06 | Identification report "a brig, hull up, bearing NNE, about 150 m" | 16 s2 | ported | game | SGT-01 | `glass::report` |
| SGT-07 | Smoke, fog, haze as extinction; hull down by earth curvature | 07 | ported | engine | | `sight::Air`, `Murk`, horizon |
| SGT-08 | Two-height target test: masts seen over a low islet | 07 | ported | engine | SGT-07 | `sight::look` |
| SGT-09 | Own canvas blinds the forward view; fighting sail clears it | 07 s"What blocks" | missing | both | SAIL-06 | |
| SGT-10 | Own ship exempt from glass and deck-view occlusion | 16 s2, 23 | ported | game | SGT-01 | glass omits own ship |
| SGT-11 | Raising the glass takes time; walk mode put down | 16 s2 | partial | game | SGT-01 | `t` leaves walk mode; no raise delay (noted in `glass.rs`) |
| SGT-12 | Masthead lookout (`o`), first call after ~6 s | 07 | missing | game | SGT-02, CRW-09 | |
| SGT-13 | Lookout reports with accuracy by skill; asking the lookout or master | 16 s2, ST s6.6 | missing | game | SGT-12 | |
| SGT-14 | Telescope tells weather coming to windward | 24 s"Telescope" | missing | game | ENV-20 | |
| SGT-15 | Map memory (seen/unseen/remembered) | 07 s"Views" | missing | engine | | |
| SGT-16 | Charted vs seen coasts; charts that can be wrong | 07, 12 s"Next" | missing | game | WLD-01 | |
| SGT-17 | Dead reckoning, noon sights, navigator/master reckoning | 08 s"How a captain knew" | missing | game | WLD-01, CRW-09 | |
| SGT-18 | Fall-of-shot report from the spotter | 16 s2 | missing | game | GUN-20 | |
| SGT-19 | Sight tracing no finer than 1 m, cached | 08 pacing | ported | engine | | engine-side concern |
| SGT-20 | Bodies obstruct the near view but not distant sighting | ST s5 | partial | engine | | |

## 12. Interface

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| UI-01 | Command screen: ship pane, chart, status strip, panel, footer | 08 s"Layout" | ported | game | | `screen::draw` |
| UI-02 | Ship pane bow-up with auto-fit zoom | 08 | partial | game | UI-01 | bow-up; zoom is the engine's `MapView`, no 2x2 sub-cell fit logic confirmed |
| UI-03 | Chart pane, north-up, ships from knowledge | 08, 07 | partial | game | SGT-02 | chart drawn from true positions |
| UI-04 | Status strip: time, heading in points, wind in Beaufort and relative, sail, quarters | 08 | ported | game | | `screen::points`, `beaufort`, `wind_on`, `sail_words` |
| UI-05 | Panels: LOG, CREW, ORDERS, SHIP, KEYS | 08 | ported | game | UI-01 | `Panel` |
| UI-06 | SIGNALS panel | 08, 19 s4 | missing | game | SIG-01 | |
| UI-07 | Walk mode: be the captain, `e` actions | 08 | partial | game | CRW-01 | walk, look, climb ladders implemented; no `e` contextual action list |
| UI-08 | Look cursor: person, tile, cask details | 08 | partial | game | UI-01 | `look_at` for place and person |
| UI-09 | CREW roster with 15-skill grid and person sheet | 08 | partial | game | CRW-04 | roster with find-him; skill grid and full sheet limited |
| UI-10 | Roster sorting, filtering, picking a man to order | 08 still | missing | game | UI-09 | |
| UI-11 | Z levels: PgUp/PgDn slices; time-stopped free scroll, walk when live | 16 s7 | partial | game | SHP-05 | levels exist and are viewable; the stopped/live rule not enforced |
| UI-12 | Deck view as a slice at the standing level | 23 | ported | engine | UI-11 | |
| UI-13 | Pause (planning mode); pause also stops the captain | 23, 07 | partial | game | | `space` pauses; planning-mode "reveal everything" has no equivalent |
| UI-14 | Time speed control | 08 | ported | game | | `, .` |
| UI-15 | Binnacle strip, dog-vane, masthead pennant, log-line, bell, sail-plan table | 08 s"How a captain knew" | partial | game | UI-04 | heading in points and wind words only; no card, log-line, bells or sail table |
| UI-16 | Instruments as crew reports with delay and error | 08 | missing | game | UI-15, SGT-13 | |
| UI-17 | One-row instrument band in the ship view | 20 s3 | missing | game | UI-15 | |
| UI-18 | Relative-bearing ring, fore-and-aft line and beams on chart; line of fire with aspect | 21 s"The chart" | missing | game | SGT-05 | `glass::chart_field` marks the field only |
| UI-19 | Guns-on line in status strip "guns on Vigilante stbd beam, 480 m, broadside (port)" | 21 | partial | game | SGT-05 | ORDERS panel shows the mark's bearing, range, angle |
| UI-20 | Orders menu in period language ("Hands to make sail", "Wear ship") | 08 still, 10 s3 | missing | game | SAIL-08 | |
| UI-21 | Two logs: immediate log and the ship's journal as a document in the cabin | 24 s"Two logs" | partial | game | SHP-10 | LOG panel only |
| UI-22 | Charts as documents on the table | 24 | missing | game | SHP-10, WLD-01 | |
| UI-23 | Three named modes (master, captain, telescope), mode shown on screen | 24 s"three modes" | partial | game | | `Mode::{Command,Walk,Look,...}` exists; master-mode inspector missing |
| UI-24 | Level-view cursor that opens a man's sheet | 24 | missing | game | UI-11, UI-09 | |
| UI-25 | Talking to a man as an activity | 24 | missing | game | PSY-01 | |
| UI-26 | Front-door menu, scenario list, help generated from the key table | 22 s"front door" | ported | game | | `main_menu`, `screen::KEYS` |
| UI-27 | Terminal diffed renderer, palette, layout | 03 | ported | engine | | `tachyon::draw`, `backend::term` |
| UI-28 | Sea rendering from the model (waves, shading) | 20 s5, 09 | ported | engine | ENV-09 | |
| UI-29 | Sub-tile art at 1, 2, 3+ cells per metre | 24 s"What was broken" | partial | engine | | |
| UI-30 | Sub-metre lattice lock to her grid (no bulwark shimmer) | 20 s0, 24 | ported | engine | | her grid never turns in the engine ("bow-up view never shimmers" per `craft.rs`) |
| UI-31 | Sea and ship drawn with weather: cloud shadow, rain streaks | 20, 09 | missing | engine | ENV-20 | |
| UI-32 | Fixed ticks locked to clock; uncapped draw | 08 pacing | ported | engine | | `tachyon::app::run` |
| UI-33 | Text and HTML snapshots, headless bench | 07 | ported | engine | | `--snapshot`, `--bench` |

## 13. Tutorial, scenarios, sandbox

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| TUT-01 | Tutor: lessons that pass on the ship's own state | 22 | missing | game | | |
| TUT-02 | Mission 1: handling (wheel, binnacle, sail, points, anchor, port) | 22 | missing | game | TUT-01, SEA-ANCH, WLD-04 | |
| TUT-03 | Mission 2: squadron and signals | 22 | missing | game | TUT-01, SIG-03 | |
| TUT-04 | Mission 3: ship against ship (identify, beam, quarters, word, fall of shot) | 22 | missing | game | TUT-01, GUN-19 | |
| TUT-05 | Mission 4: squadron in action from a distance | 22 | missing | game | TUT-03, FLT-01 | |
| TUT-06 | Mission 5: stores and the state of your people | 22 | missing | game | TUT-01, LIF-08 | |
| TUT-07 | Scripted student proving each course finishable | 22, 17 s5 | missing | game | TUT-01 | |
| TUT-08 | Eleven-lesson original course | 17 s5 | missing | game | TUT-01 | |
| SCN-01 | Scenario library with captions and machine-checked checkpoints (29) | 07, ST | partial | game | | 5 scenarios, no checkpoint harness; Rust tests instead |
| SCN-02 | Duels and fleets: action, frigates, odds, line, free | ST | ported | game | SHP-01 | `game::Scenario` |
| SCN-03 | Sandbox with casks, scuttlebutt, hulk and wall to shoot | 17 s4 | missing | game | ITM-05, STR-01 | |
| SCN-04 | `gun_vs_wall` and demo | 15 | missing | game | STR-01, GUN-30 | |
| SCN-05 | HTML replay export of scenarios | 07 | partial | engine | | `--snapshot` for one frame |
| SCN-06 | Boarding, fog, hull-down, night, strait, squall, fleet scenarios | 07, 09 | missing | game | various | listed in doc 07 table |
| SCN-07 | Generated home port scenario | 12 | missing | game | WLD-04 | |
| SCN-08 | Tests playing scenarios through | ST s4 | partial | game | | `tests/game.rs` (6), `tests/glass.rs` (3) |

## 14. World and campaign

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| WLD-01 | Generated geography: basin, strait, peninsulas, islands, archipelago | 12, 04 | missing | both | | `tachyon::make::{atlas,worldgen}` exist; the Mediterranean-specific shape is a game recipe |
| WLD-02 | Bridge from a world map to scenes at any zoom | 12 | missing | engine | WLD-01 | |
| WLD-03 | Depth field with shelf and shoal noise | 04 s3 | partial | engine | WLD-01 | scenarios use a hand-written `depth()` |
| WLD-04 | Ports placed by harbour quality, sized, some fortified | 12, 04 | missing | game | WLD-01 | |
| WLD-05 | Nations, cultures per region, territory, governments | 12 | missing | game | WLD-04, CRW-07 | |
| WLD-06 | 155-year history: wars, treaties, battles, sieges, admirals, plague | 12 | missing | game | WLD-05 | |
| WLD-07 | Fortresses on the coast | 13, 12 | missing | both | STR-03 | |
| WLD-08 | Player nation as an outside sea power with few bases | 12, ST s5 | missing | game | WLD-05 | |
| WLD-09 | Naming your captain, ship and nation | 11, 12 | missing | game | | |
| WLD-10 | Biographies from world history (veteran of this world's battles) | 12, 11 | missing | game | WLD-06, CRW-14 | |
| WLD-11 | Settlement histories | 12 | missing | game | WLD-06 | |
| CAM-01 | Campaign structure: start in a sloop, patrol and escort, open campaign | 04 s"Campaign" | missing | game | WLD-08 | |
| CAM-02 | Rank and widening command scope | 04 | missing | game | CAM-01 | |
| CAM-03 | Succession on death: next officer takes over | 04 | missing | game | CRW-14 | |
| CAM-04 | Loss condition when no officer is left | 04 | missing | game | CAM-03 | |
| CAM-05 | Strategic AI moving enemy fleets and reinforcing ports | 04 s"Notes" | missing | game | WLD-06 | |
| CAM-06 | Campaign chart pane at 10-40 km per cell | 12 s"Next" | missing | game | WLD-01 | |
| CAM-07 | Time compression for passages | 09 q3, ST s7 | partial | game | LIF-17 | |
| CAM-08 | Navigation across open water, courses plotted by wind | P4 | missing | game | WLD-01, SGT-17 | |
| ECO-01 | Port resupply of food, water, powder, shot, cordage, sailcloth | 02 s6 | missing | game | WLD-04, ITM-02 | |
| ECO-02 | Repair tiers: careen vs dockyard | 02 s6 | missing | game | SHP-19 | |
| ECO-03 | Crew replacement: volunteers, press gangs | 02 s6 | missing | game | WLD-04 | |
| ECO-04 | Prize money and trade goods | 02 s6 | missing | game | BRD-09 | |
| ECO-05 | Supply as real stock, consumed by crew and combat | 02 s6 | missing | game | ITM-03 | |
| ECO-06 | Climate and seasons over the world | 12 s"Next" | missing | engine | WLD-01 | |
| ECO-07 | Deeper history: rulers, dynasties, living famous captains | 12 | missing | game | WLD-06 | |
| ECO-08 | Language families, dialects, interpreters | 14 s"Next" | missing | engine | CRW-07 | |

## 15. Architecture and engine

These belong to Tachyon or are decisions already taken; listed for completeness.

| id | mechanic | source | status | side | depends on | where / note |
|---|---|---|---|---|---|---|
| ARC-01 | Data-oriented entities and systems (ECS) | 01 | ported | engine | | replaced by Tachyon `Things`/`Scene` |
| ARC-02 | Fixed-step clock, seeded named RNG streams, determinism | 01 | ported | engine | | `tachyon::rng`, `clock`, `SECS = 0.5` per tick |
| ARC-03 | Event bus | 01 | ported | engine | | `SceneEvent`, `CraftEvent`, `LifeEvent` |
| ARC-04 | Two coordinate spaces: sea space and ship grid | 00, 01 | ported | engine | | `Craft` grid never turns |
| ARC-05 | One spatial query seam | 07 | partial | engine | | `sight::look` and `Scene`, not one unified query |
| ARC-06 | Systems read, views never mutate; headless sim | 01 | ported | engine | | |
| ARC-07 | Ship data in YAML with sources noted | 00 | ported | game | | flat subset parser in `data.rs` |
| ARC-08 | Save and load | 01 s"Save format", 04 | missing | engine | | not started in either repo |
| ARC-09 | Compiled hot-path escape hatch | 01 | ported | engine | | whole stack is Rust |
| ARC-10 | Every ship simulated to the same fidelity as the player's | 00, 02 s5 | ported | game | | one `Ship` type for all |
| ARC-11 | Simulation LOD for far entities | 13 s"Performance" | missing | engine | FLT-06 | |
| ARC-12 | Orders not puppetry; rate of fire not a number; honest "not simulated yet" | CLAUDE.md, 17 | ported | game | | design rule, upheld in `ship.rs` |
| ARC-13 | Terminal-native renderer; web or native backends possible | 03 | ported | engine | | `backend/` split |
| ARC-14 | Legacy Python tree to be deleted once ported | CLAUDE.md | partial | game | this ledger | `legacy/` still present; nothing removed here |

---

## Notes for whoever picks this up

- **Check first**: rows marked "verify" or with a hedge (CRW-16, BOD-06, UI-02, UI-30) were judged from code skim, not a run. Confirm before relying on them.
- **Biggest unported cluster**: signals, squadron command, tutorials (SIG-*, FLT-*, TUT-*), because they hang off knowledge records (SGT-02) that do not exist yet. SGT-02 is the keystone; AI, chart and signals all read true positions today.
- **Engine already ahead of the legacy**: sea state, tide, currents, whirlpools, ship motion, below-deck levels with ladders, flooding. Do not re-implement these in Broadside; ENV-09/10/12/14 are done.
- **Engine-side work to hand to Tachyon** (noted only): ENV-02/05/06/08/20 (wind field, wind shadow, weather in `Game`), PSY-03 (feelings), BOD-04/10/13 (limb treatment, infection, recovery), DMG-07/09 (material connections, part graphs), STR-01/02/05/06 (half-metre voxel walls and collapse), FIR-01/03 hooks, SGT-15 (map memory), LIF-02 (bells), WLD-02/03, ECO-06, ARC-08 (save/load), ARC-11/FLT-06 (LOD).
- **Open design questions carried from legacy** (not mechanics until answered): seamanship severity (SAIL-12), women aboard (CRW-19), superstition (CRW-20), how deep rigging goes (SAIL-14), curated vs free ship designer (SHP-14), whether the chart shows currents and wind shadow.
