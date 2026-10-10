# Broadside: Structural Report

*Status as of 2026-10-06 (round 12). Where the project stands, how it's built, what's been verified, and what comes next.*

## 1. Summary

Broadside is a terminal, Dwarf-Fortress-style simulation of Napoleonic naval command in a generated, fictional Mediterranean. Built so far:

1. **Phase 0 (skeleton):** ECS, fixed-step clock, seeded RNG, diffed terminal renderer, ship data, wind and polar sailing.
2. **Engine v1 (vision & views):** captain's-perspective line of sight (terrain, hulls, masts, sails, fog, smoke, darkness, earth curvature), planning mode, one camera at every scale, contact knowledge, 1 m deck plans, crew stations with pathfinding, gun smoke.
3. **The command screen:** the ship pane (bow up, full height, **auto-zoomed so small ships are drawn 2×2 per metre**), the chart, the quarterdeck instruments and details.
4. **Round 3, "everything is a point of data":**
   - **People:** every sailor on every ship is an individual (culture, nationality, birthplace, background, character, morale/stress/anxiety/depression/confidence/fear/grievance, devotion, drink dependence, skills for every role, a 12-part body with blood and a pulse, and a biography).
   - **Structures:** every deck tile has a material and a condition.
   - **Items:** every cask and shot garland has recorded contents.
   - **Contact:** ships collide, foul, and are boarded man by man.
   - **World generation:** a fictional Mediterranean with ports, nations and cultures, and 155 years of simulated history. You name your captain, ship and nation.

5. **Round 4:**
   - **Generated languages** replace the real-world culture labels: every people speaks a tongue built from blended, mutated sound systems, and names carry translations.
   - **Physics sandbox:** you can walk the deck as the captain and work a gun by hand; round shot flies ballistically and knocks a stone wall down block by block, with collapse, rubble and dust.

6. **Round 5, the drill and learning the ropes:**
   - **The gun drill as nine acted jobs**, each done by a named man at a numbered station, timed from his skill, his fatigue, his surviving limbs, and the weight of the ball and the gun. Rate of fire is no longer a number anywhere: it is the sum of what men do.
   - **Powder from the magazine:** clearing for action serves out cartridges gun by gun, deducting real powder.
   - **Gun captains lay their own pieces**, solving elevation against the real trajectory and misjudging the range by however green they are - which is where dispersion comes from.
   - **Named targets:** `x` tells the guns what to fire at, and the crews take time to understand the order, the greener the longer.
   - **Flag signals** with a code book, hoisting time, legibility through fog and smoke, and a reading delay.
   - **A sandbox** (a brig to walk, casks to open, a hulk and a wall to shoot) and an **eleven-lesson playable tutorial**.

7. **Round 6, how it feels to command:**
   - **Walk mode is a first-person view now:** taking the captain in hand closes the ship pane to three cells a metre and pins it to him - he stays in the middle, the view goes where he goes, and only what he can see is drawn.
   - **One panel at a time** instead of four things at once: log, crew, orders, ship, keys (`1`-`5`), under a status strip that always carries heading, wind, log and sail. The footer wraps, and every control is listed on its own panel.
   - **A crew roster** with the whole company, their stations, a grid of all fifteen skills, and the selected man's full sheet.
   - **A playable demo** (`python -m broadside.main`): brig, consort, an enemy holding station off the larboard beam, and a fort to starboard, with the log opening on what to try. Building it turned up four real faults, all fixed: spent shot was never deleted (esper defers deletions until `world.process()`, which this engine never calls) and was being stepped over for the whole action; a single-point atmosphere query cost more in numpy overhead than the whole battle's physics; shot flew *over* a deck because a hull was only solid where a fitting stood; and nobody brought powder or shot up from below once the ready supply was spent.
   - **Slow ship, smooth screen:** a frame went from ~180 ms to ~40 ms (5 fps to 25-30), while the ship herself became heavier - a rudder that needs way on, way gathered and lost over half a minute, and sail that is *ordered* and then set by hand over half a minute.

8. **Round 7, the third dimension and the day aboard:**
   - **Walking is close in now:** five cells to the metre in true proportions, the view pinned to the captain, sub-metre drawing of planks, guns, masts and gratings, every man reading by his trade (you are the only `@`), and bodies that block the view of other bodies.
   - **The z axis:** `z` cuts the world into horizontal levels - the sea and its bottom, hills in cross-section, trunks and canopy, a ship's hull, deck, canvas and mastheads, and voxel walls read straight out of their blocks.
   - **The glass:** a first-person heightfield raycast along any bearing, 70 degrees by eye or 7 through the glass, telling canvas from stone from hillside - and reporting what it finds.
   - **Life aboard:** two watches, the watch below really below and asleep at night, meals eaten out of the real casks, squalls with rain that shortens the horizon and wets the men.
   - **A limb is several things** (bone, artery, tendon, tourniquet, splint, infection) behind one `Body.capability()` question that every task asks.
   - **Feelings** between events and morale: appraised through character, fading at their own rates, with diminishing returns.
   - **Frame rate uncapped** to 120 fps, with simulated time locked to the clock, and the traced sight field reused for a tenth of a second so the ship pane can draw everything else every frame. Measured at 190x56: ship view ~20 fps, walk mode ~24, levels ~28, the glass ~130.
   - **Weather became a field** over the sea - stormy quarters and kindly ones, clouds that drift and cast shadows, rain and fog that follow from them - after the first version read as random black clouds over the ship.
   - **Your own ship is veiled, not erased** where your own canvas and smoke hide her, and smoke-hidden air is drawn grey rather than black. The ship pane no longer fills with holes in action.
   - **The glass looks past your own ship**, and the chart marks its field of view.

9. **Round 8, a squadron to command:**
   - **Captains**, at last, with parameters: skill, intelligence (how often he thinks at all), aggression, caution and discipline, all built from the person already generated for him. He chooses a mission from what his own lookouts have seen, and carries it out with the orders a player would use.
   - **Signals carry orders.** The numbered book now means something: form line of battle, engage more closely, come within hail, report your damage (she answers), discontinue the action - made by a hand sent to the locker, addressed to one ship or the squadron, read after a delay, sometimes misread, and sometimes refused.
   - **A SIGNALS panel** with the book, what is flying, who has answered, and your squadron's captains with their parameters on show.
   - **A steady ship and a moving sea:** the camera snapped to her own grid (31% of her fabric shifting between frames, down to 0.6%), and real travelling swell in place of noise cut at a threshold.
   - **The glass takes the arrows** from walk mode instead of fighting it for them.

10. **Round 9, laying the guns:**
   - **Bearings and aspect in the old words** (`view/orientation.py`): *three points on the starboard bow*, *broadside on, her port side to us*.
   - **The chart draws her own axes** - fore-and-aft line, both beams, the four-point diagonals - and a **line of fire** to whatever the guns are laid on, with her bearing, range and aspect at the end of it. The strip says the same in words.
   - **The glass is held relative to her head** instead of to the compass, **tilts** with the other two arrows (which used to scroll the log underneath it), carries a **reticle**, and holds a ship in the field with `TAB`.
   - **The fall of shot before the word is given** (`p`): a dry run of the real ballistics, drawn as an arc through the glass and a track and splash on the chart, with a verdict (*short*, *would strike her hull*, *her rigging, not her hull*) and a spread that is the gun captain's own doubt.
   - **A bug the preview found:** guns were never laid for range before their first shot, so the opening broadside of every action went out at point blank. Her gun captains now lay when the word changes and every half minute as the range runs off.

11. **Round 10, a game rather than a library:**
   - **A front door.** `python -m broadside.game` (or `broadside.main` with no arguments) opens a menu: five tutorial missions, free sailing, the scenario library, help drawn from the same key table as the in-game panel, and quit. `q` aboard ship returns to the menu.
   - **Five tutorial missions**, each a course of lessons that pass on the ship's own state: ship handling and a port; a squadron and the signal book; ship against ship; a squadron in action while you stand off and command; stores, grievance and what a captain can do about them. Every one has a test that plays it through with a scripted student.
   - **The anchor**, as an order with real work between order and condition: she will not lie to it under sail, letting go takes 14 seconds and weighing 75, and docking is anchoring in the roads within a boat's pull of the mole.
   - **Short allowance (`r`) and splicing the mainbrace (`G`)**: the stores stretch, the men mind it, and the grog comes out of the rum actually in the hold.
   - **A cutter** (`cutter_8`) - the teaching ship.
   - **The shot preview is gated**: the gun captain's estimate is only to be had at quarters with a man at a loaded gun.

12. **Round 11, the slice:**
   - **The captain's-eye view is a z slice**, Dwarf-Fortress fashion: you see the level you are standing on. Her canvas is above the deck, so it is not in the deck's picture; her masts are, as trunks. The chart keeps the sails. A lesson in mission 1 teaches the levels.
   - **The black shadows that jittered on the water were his own shipmates.** Thirty hands at 1.75 m against an eye at 1.7 m, cutting the view into wedges that swung as they walked. In her own deck view your own ship is now wholly out of the way - hull, guns, masts, canvas and company. Measured: the traced sight field went from 51-67% visible with 27% flipping per quarter second, to 100% visible and 0% flipping. The sighting system still counts her own canvas in full, so being blinded by your own courses is unchanged.
   - **Pause freezes the captain too** - with time stopped you could still walk the deck, which made the pause look broken.
   - **The wheel is drawn as a wheel** (rim, spokes, hub) and the lesson names the glyph that is actually on screen.
   - **Still missing:** below-deck rooms. The level view shows her hull and the void inside it, not a cabin or a hold with casks in it. That is the next real piece of work.

13. **Round 12, three rendering faults and a design written down:**
   - **The ship was drawn as her plain glyphs doubled.** Auto-fit opens a small ship at two cells to the metre; the sub-cell tile art only switched on at three. Every tile now has a two-cell form, so she reads as a ship at the zoom she opens at.
   - **The chart's bearing cross was a web of dots** across the whole sea, painting over the legend. It is a short labelled cross now, and never writes on the legend.
   - **"Menu not displaying" was real:** the menu held the alternate screen while a mission entered it again, so afterwards it painted onto a screen nobody was looking at. One fullscreen context per visit, and the list goes one line per item on a short terminal so help and quit are never below the fold.
   - **The player's three modes** (master view, captain mode, telescope) and a **modelled sea** are written up in `docs/design/24_three_modes_and_a_modelled_sea.md`, with what exists under each part and what the missing pieces cost. The honest headline: **waves are a render-time texture, not a model** - no sea state, no ship motion in it, no currents, no tide.

It runs with `python -m broadside.game` (the menu), `python -m broadside.scenarios run <key>` and `python -m broadside.worldgen`. **29 scenarios** have captions and checks. **162 tests pass**, including the slow ones.

Design docs: `07` vision & views · `08` interface · `09` environment · `10` naval primer · `11` people · `12` world generation · `13` structures, items & boarding · `14` languages · `15` physics sandbox · `16` views, observation & targeting · `17` the drill, signals & tutorial · `18` life aboard, the body & the heart · `19` fleet & captains · `20` sighting, instruments & the look of the sea (plan) · **`21` bearings, aspect & the fall of shot**.

## 2. Architecture

```
 worldgen/ ──────────────▶ geography · polity (ports, nations) · history · world (+ player naming)
     │ WorldHeightmap / places / battles
     ▼
 sim/ (state + systems, no I/O)
   shiplayout ─▶ ShipBody        structure (materials, per-tile condition)     items (casks, contents)
   people/ cultures · components · generate · health (blood, pulse) · psyche (morale, grog, mutiny risk)
   world/ terrain (analytic + WorldHeightmap) · atmosphere (haze, fog, smoke)
   state.Simulation pipeline:
     wind · helm · sailing · pin_fouled · movement · collision · atmosphere · crew_tasks · boarding ·
     activities · gun_drill · gunnery · ballistics · structures · health · sighting · signals · needs · mood · psyche
   spatial.SceneQuery ── the one seam: "what's here, how tall, what blocks?"
   vision.trace       ── 2.5D rays: solids, poles, sail walls, murk, curvature (+ people at head height)
     │ read-only
     ▼
 view/  camera · compose · memory · instruments · hud · people_view · screen · export
     ▼                                   ▼
 render/ + ui/app (terminal)        scenarios/ (library, runner, checks, CLI, HTML replays)
```

**Rules held:** systems mutate and views read. The sim runs headless. Randomness comes from named seeded streams. Every spatial question goes through `SceneQuery`. Every ship, friend or foe, uses the same data model.

**Size:** ~18,300 lines of Python in `src/`, ~2,800 in `tests/`. Ship classes: cutter, gunboat, sloop, brig, frigate, 74, first rate (Victory's dimensions).

## 3. What exists, by area

| Area | Built | Depth |
|---|---|---|
| **Captains (round 8)** | A mind per ship: skill, intelligence, aggression, caution, discipline from his own person; missions chosen from his contacts; laying courses, breaking off, keeping station | **First version** (was *nothing at all* before) |
| **Fleet signalling (round 8)** | Orders in the signal book, made by a hand, addressed, read late, misread, refused; a SIGNALS panel | **First version** |
| **Weather (round 7)** | A field over the sea at three scales: unsettled and damp quarters, drifting cloud with shadows, rain and fog that follow, forced squalls | **First version** |
| **The z axis (round 7)** | Horizontal levels through sea, seabed, hills, trees, hulls, decks, canvas, mastheads and voxel walls | **First version** (a ship's internal decks are still one space) |
| **Looking out (round 7)** | First-person heightfield raycast, naked eye or glass, materials told apart, haze and night, identification reports | **First version** |
| **Life aboard (round 7)** | Watch bill, the watch below going below and sleeping, fatigue paid off by sleep, meals from real stores, squalls and rain | **First version** |
| **The body (round 7)** | Bone, artery, tendon, tourniquet, splint, infection per part behind one `capability()` question | **Groundwork for the surgeon** |
| **Feelings (round 7)** | Appraisal of events through character into fading feelings that move morale | **First version** |
| **Views & interface (round 6)** | Walk mode follows the captain at three cells a metre; five panels with a permanent status strip; crew roster with skill grid and person sheet; wrapped footer and a keys panel | **Second version** |
| **Frame cost** | Sight traced on a 1 m grid however far you zoom in; chart cached 0.4 s; map memory and the per-cell loop rewritten; steady 30 fps draw | **Solid** |
| Line of sight | 2.5D rays; poles; sail walls; fog, smoke, haze, darkness; hull-down; people seen at head height | Solid |
| Knowledge | Contact records; captain vs masthead with report delay; map memory | Solid |
| Views & interface | Command screen; auto-fit ship zoom; focus; look cursor with person, tile and cask details | First version |
| **People** | Full person model; coherent generation with stories; roles by skill; blood/pulse/death; psyche; grog; ship morale and mutiny risk | **Groundwork**: data complete, behaviours partial |
| **Structures** | Material and integrity per tile; collision damage; damaged planks drawn | **Groundwork** |
| **Items** | Period-scale victualling; casks, powder, shot garlands, scuttlebutt; drawn and inspectable | **Groundwork** (no consumption yet) |
| **Collision & boarding** | Tile-exact collision, fouling, gangways, boarders crossing, defenders, skill-based melee wounding real bodies | **Groundwork, proven end to end** |
| **World generation** | Geography, ports, nations and cultures, territory, 155-year history, named player; bridge to scenes at any scale; map and chronicle export | **Groundwork** |
| **Languages** | Generated per people from blended sound systems; lexicons; names of people, places, nations and ships with translations | **Groundwork** |
| **Ballistics** | Real round shot: mass and velocity by calibre, gravity and drag, hull hits with splinter wounds, ricochet off water; every broadside fires balls | **First version** |
| **Destructible structures** | 0.5 m block walls: energy-based penetration, spalling cracks, arching support, crushing, collapse into rubble, dust | **First version** |
| **Acting on objects** | Timed actions on nearby things, used by the player in walk mode, by the crews, and by scripts | **First version** |
| **The gun drill** | Nine ordered jobs per round; numbered crew stations; duration from skill, fatigue, wounds, ball weight, gun weight and hands available; a job dropped when its man falls; cartridges served out of the magazine; guns that starve say so | **Built, proven end to end** |
| **Laying and targets** | Gun captains solve elevation against the real trajectory, misjudge the range by skill, and prefer a mark the captain has named once they have understood him | **First version** |
| **Signals** | Numbered code book, hoisting time, legibility through fog and smoke, reading delay by lookout skill, acknowledgement | **First version** |
| **Teaching** | Eleven-lesson playable tutorial, each lesson passed from the ship's own state; a scripted student proves the course | **First version** |
| Sailing | Polar curve, irons, inertia, helm, autopilot with tacking, grounding | Shallow |
| Gunnery | Manned reload, broadsides, smoke, and now real round shot with hull and structure damage | Growing |
| Environment | One global wind; a weather field with cloud, cloud shadows, rain and fog; forced squalls; light | **Growing** (`09`) |

## 4. Verification

- `pytest`: **131 passed** (vision maths; engine; interface; period vocabulary; people generation, bleeding to death versus clotting, psyche, stores, structure; world determinism, open strait, war at start, terrain bridge; ballistics, wall support and collapse, working a gun by hand, generated languages; every scenario's checkpoints).
- `python -m broadside.scenarios check`: **23/23** pass, including `boarding_action` (fouled with 9 crossings; 28 boarders across; casualties on both sides), `generated_home_port` (197 of the company born in the nation's towns) `gun_vs_wall_demo` (a three-man crew working one 24-pounder unaided: ten rounds in ten minutes, 32 blocks smashed, a breach through 2 m of masonry, 16 blocks down as rubble) and `tutorial_demo` (all eleven lessons passed using only a player's controls).
- Measured rates of fire, which nothing in the code sets: a brig's 9-pounders with three men each, about **one round a minute**; a 24-pounder worked by the captain **alone**, about **a minute and a half**, most of it spent running her out.
- Frames inspected as images throughout. The interactive app has been exercised on a simulated terminal; **the feel in your real terminal is still to confirm.**
- Performance: the fleet scenario holds ~23,700 entities and runs ~8× real time; a world generates in ~1.5 s.

## 5. Decisions made this round

| Decision | Why |
|---|---|
| Generate every ship's **full establishment** as people; only those on the weather deck are placed on tiles, the rest `Below` | Everyone has data (your requirement) without drawing decks we don't model yet |
| Death by **blood volume and heartbeat** (collapse ~33% loss, death ~45%), vital parts kill outright | Your suggestion; physiologically grounded; gives the surgeon real numbers to act on |
| Skills for **every role**, with roles **assigned by skill** | Performance and job come from the individual, not the job title |
| People visible at **head height** | You see men over a bulwark before you see the deck |
| Auto-fit ship zoom (2×2 cells per metre for small ships) | Your note that the first-rate view felt right; small ships now get the same detail |
| Player nation = an **outside sea power with few bases** by default | Mirrors Britain's Mediterranean position; every base precious |
| History **produces the present and feeds biographies** | Legends aren't decoration; a veteran fought in *this* world's battles |
| **Generated languages** instead of real-world culture labels (round 4) | Your note: "Iberian", "Gallic" point at the real world. Blended, mutated sound systems keep the familiarity without borrowing an identity |
| Walls as **0.5 m voxels**, ships as 1 m deck tiles (round 4) | A wall's damage is vertical (holes, arches, collapse); a ship's deck is essentially flat |
| Energy-based penetration tuned so a 24-pounder drives ~1.5 m into masonry | Matches period accounts of what breaching actually took |
| **One drill table** drives the player and the crews alike (round 5) | Your requirement that the captain acts exactly as the AI does - and one definition cannot drift from another |
| Step duration from skill x fatigue x physique x **weight** (round 5) | "Like an F1 pitstop": rate of fire has to come out of who is doing what, with how heavy a thing |
| Guns on deck with real crews **never** use the reload timer (round 5) | Two models of one thing is how a simulation rots; the timer stays only for below decks and crewless NPC ships |
| Cartridges **served out of the magazine** at quarters (round 5) | The drill exposed that deck guns had no powder at all; now the bookkeeping is honest and a ship can run dry |
| Named targets obeyed after a **comprehension delay** set by skill (round 5) | Your point that an order like "attack the left wall" should be understood at a speed that depends on the crew |
| The two views are **one world at two zooms**, not two models (round 5) | Your correction: it removes a rule instead of adding one |
| Bodies obstruct the near view but not distant sighting (round 7) | One deck level is drawn, so everyone stands at the captain's height; letting a man at the rail hide a frigate on the horizon would be a worse lie than ignoring him |
| One `Body.capability(what)` question, not limb arithmetic at call sites (round 7) | So a cut tendon or a tourniquet slows the gun drill without the gun drill knowing what a tendon is |
| Feelings sit **between** events and morale (round 7) | Events nudging morale directly made morale a scoreboard; feelings fade at their own rates and are coloured by character |
| Sight lines never traced finer than 1 m; the look fan sampled in **one** query (round 7) | Both are the same lesson: the cost is the number of queries, not the number of points |
| Never trace sight lines finer than the world's own 1 m grain (round 6) | The honest fix for zooming in: detail the model does not have costs nothing to skip, and it is what made walk mode affordable |
| The chart may be up to 0.4 s stale; the ship pane never is (round 6) | Nothing moves a 12 m column in that time, and the saving buys the ship pane its frame rate |
| A hull is solid from the waterline to the rail (round 6) | Shot was passing over the deck and hitting nothing but bulwark tiles; a ball below the rail now strikes her, and the splinters it tears out wound the men around it |
| Powder and shot are **served out continuously** while at quarters (round 6) | The guns fell silent after ten rounds. The boys are not people yet, but the powder and shot they carry are real and come out of the magazine and the lockers |
| Sail is **ordered**, not set (round 6) | "Set a course and it takes a while to get there": canvas should follow at the speed men can work, and this is where topmen's real work will hang |

## 6. What's next (proposed order)

Set by your direction of 2026-09-26: crew, actions and sailing first; fortresses and the campaign set aside.

1. **Below decks** (`16` sec. 7): the gundeck, orlop and hold as real levels with their own deck plans, walked down to by hatch and ladder. The level view and walk mode are both built and waiting for them; what is missing is the ship's *internal* geometry.
2. **The surgeon** (`18` sec. 3): the cockpit, the wounded carried down, tourniquet and amputation as timed work that can fail, infection and fever over days, and men invalided home. The limb model is built for him.
3. **More of the ship acted out, as the gun now is:** sail handling as real jobs aloft (loosing, reefing, furling, bracing the yards) with topmen who can fall; the helm; anchor and capstan; powder monkeys as boys who can be killed carrying up cartridges; the cook and the galley.
4. **Discipline, drink and morale as a loop** (`18` sec. 4): flogging and stopping grog as appraised events, messmates and particular friends so grief is not uniform, memory, and mutiny led by ringleaders rather than by a number.
5. **Materials with connections** (`16` sec. 8): a struck timber drags its neighbours, so a hit near a joint tears a section away instead of punching a neat hole. Wood first, then masonry bonding.
6. **Fall-of-shot reports and asking the lookout** (`16` sec. 2): the glass is in; what is missing is a report whose accuracy depends on the spotter and the state of the air, and asking the lookout or the navigator instead of looking yourself.
7. **Object skeletons** (`16` sec. 4) and orders in terms of named parts - "attack the left wall", "focus on the magazine" - building on the named-target order now in.
8. **Environment** (`09`): squalls and rain are in; what is left is a real wind field, wind shadow, heel, sea state and roll - what makes sailing a craft.
9. **Time compression and the campaign's distances**: a long campaign should let you feel the distance without living through it.
10. **Then** fortresses as garrisoned places, and the campaign chart.

## 7. Answers given, and what is still open

**Answered 2026-09-26:**

| Question | Your answer | What it means here |
|---|---|---|
| Drink | Yes, performance is affected. The aim is a healthy, high-morale crew - well trained, well fed, happy; unhappy men drink and slack, but a baseline ration keeps them content. Discipline is needed, and too much of it risks mutiny | A loop to build: `Cravings` and `Psyche` exist, the grog ration exists; wanted now are drunkenness at work, theft, and punishment with its two edges |
| Women and non-combatants aboard | Undecided; the focus is war, so non-navy people can be few | Left out for now, cheap to add later |
| World size | Representative distances, with proper time compression - the distance should be felt, not endured. The point is a long campaign of growth and exploration | Full Mediterranean scale stands; time compression becomes a real feature, not a debug key |
| Playable nations | Always the underdog, starting out | The outside sea power with few bases stays the default; growth is the arc |
| Depth of history | The deeper the better, but later | Kept as it is for now |

**Still open:** seamanship severity (can over-canvassing dismast or capsize?); drawing currents and wind shadows on the chart; curated ship classes versus a free designer; how deep to go on rigging; superstition as a light trait in place of religion.

## 8. Known limitations

- No fortresses yet. One deck level is *modelled*: the level view will show you the hold, but as one undivided space, because a ship has no internal decks yet.
- Provisions still aren't eaten (powder and shot now are); psyche has few event inputs yet (gunfire, grog, needs).
- Crews work their guns as fast as they can once at quarters: no holding fire, no firing on the roll, no choice of ammunition.
- Cartridges are served out in one act at quarters rather than carried up continuously by boys.
- Melee is simple: adjacency, skill, one blow at a time, no weapons or armour distinctions.
- Ship hulls take shot per deck tile only: no below-waterline holes or flooding yet.
- Collapse drops blocks straight down; masonry doesn't topple outward.
- Ships stay fouled forever once fouled (no cutting free yet).
- World history is plausible but shallow: no rulers, alliances or economy.
- Generated place names are sometimes clunky.
- The hand-built test scenarios still describe ships as "French" or "British" in their captions and faction labels, while the game world itself is fictional with generated peoples. Worth renaming them to generated nations for consistency - say the word.
