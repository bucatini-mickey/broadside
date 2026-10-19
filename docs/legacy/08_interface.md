# Interface: the Command Screen

How the terminal is laid out, and how the player learns what a period captain would learn: heading, wind, speed, time and sail. Implementation: `view/screen.py` (layout), `view/panels.py` (the status strip and the five panels), `view/instruments.py` (the quarterdeck instruments), `view/hud.py` (the look readout), `ui/app.py` (input). This builds on the view engine in `07_vision_and_views.md`.

## Layout

```
┌─ SHIP ──────────────────────┬─ CHART ────────────────────────┐
│                            │  the macro view: fleet, contacts,   │
│  Half a metre to two metres │  terrain, fog and smoke, north up   │
│  a cell, bow up, full       │  (redrawn a few times a second)     │
│  height. Crew about their   ├───────────────────────────────────┤
│  work, guns, canvas,        │ 09:31  helm N 000  log 4.2 kn  wind │
│  smoke, and what the        │ gentle breeze, on the quarter  ...  │
│  captain can and cannot     ├───────────────────────────────────┤
│  see. In walk mode it       │ 1 LOG  2 CREW  3 ORDERS  4 SHIP  5 K│
│  closes in and follows      │                                     │
│  the captain himself.       │   one panel, the full width         │
├───────────────────────────┴───────────────────────────────────┤
│ footer: the message, then the few keys worth keeping in front of  │
│ you - wrapped over two lines, never cut off                        │
└────────────────────────────────────────────────────────────┘
```

- **Ship pane (left half).** Where the detail lives, so it gets the most room and the full height. The camera is centred on the ship and rotates with her, so **the bow always points up the screen**. A ship is as many cells wide as she is metres in beam: a sloop is 9 x 30, a 74 is 15 x 51 (65 with bowsprit), a first rate 17 x 57. **A first rate needs about 75 rows to show bowsprit to taffrail**; at less than that the hull is centred and the bowsprit runs off the edge.
- **Auto-fit zoom.** The pane picks the largest whole number of cells per metre at which the hull still roughly fits, up to two. On a 64-row screen a sloop is drawn **2x2 cells per metre**, a frigate or first rate 1x1. `+`/`-` override it.
- **Walk mode (`m`).** Taking the captain in hand zooms the ship pane right in - **five cells to the metre, in true proportions** - and pins it to him: he stays in the middle and the view goes where he goes, with his own eyes deciding what is drawn. Stepping out puts the pane back as it was. Close in, a square metre of ship is drawn as *what it is*: planking with its seams, a gun's barrel and carriage, the round of a mast, the bars of a grating (`style.subtile`).
- **Who is who.** You are the only `@` aboard. Everyone else reads by his trade - `&` officers, `g` gun captains, `t` topmen and lookouts, `x` marines, `b` bosun's mates, `,` boys, `o` the rest - so the captain is findable at a glance on a crowded deck.
- **Men are obstructions.** A body blocks the view of what is behind it from the chest up, so a crowd is something to see round or move through, and walking the deck feels occluded. (A body is *not* an obstruction to spotting a ship on the horizon: one deck level is drawn, so everyone stands at the captain's own height, and letting a man at the rail hide a frigate would be the worse lie.)
- **Levels (`z`).** The world cut into horizontal slices, PgUp/PgDn to go up and down: the hold under your feet, the deck, the sails, the mastheads; and ashore, rock, ground, trunks and canopy. See `16_observation_and_targeting.md` sec. 7.
- **Looking out (`t`, `T`).** The pane is given over to a first-person picture along one bearing - the glass or the naked eye - and **the chart marks the field of view**: two dotted edges and the bearing down the middle, so you always know which way you are looking and how much of the world is in it. See `16` sec. 2.
- **Your own ship is veiled, never erased.** In live mode the captain cannot see most of his own deck - his canvas and his powder smoke are in the way - but he knows where his guns, hatches and masts are, so they are drawn dim and grey rather than blanked to black. His people are another matter: a man you cannot see is not drawn at all. Water alongside that your own rail hides is drawn as remembered sea for the same reason: a captain knows the sea is there. (This was a real complaint: in action the ship pane became a field of black holes.)
- **Smoke looks like smoke.** Air that is hidden by powder smoke or fog is drawn in its own colour - grey, or sandy where there is dust in it - rather than in the black of the unknown.
- **Chart pane (top right).** The macro view (`07` sec. Views): ships as glyph clusters drawn from what you *know* (contact records), plus terrain, fog and smoke, north up. It is recomposed a few times a second rather than every frame: nothing in it moves a whole 12 m column in that time, and the saving is what lets the ship pane be smooth.
- **Status strip.** One line, always there: the time, the heading in points, the log reading, the wind in Beaufort's words and relative to the ship, the sail setting, and whether the ship is at quarters. Whatever panel you are in, you can always con the ship.
- **One panel at a time (`1`-`6`).** Four things at once was clutter, so the bottom right shows one:
  - **1 LOG** - the log, wrapped and given room, plus the look readout and the walk-mode action menu.
  - **2 CREW** - the ship's company as a roster: name, role, station, and a grid of all fifteen skills as digits, Dwarf-Fortress fashion, with the selected man's full sheet (character, devotion, drink, wounds, story) below it. Focus the panel with `TAB` and the arrow keys move down the roster.
  - **3 ORDERS** - what you have ordered and what is being done about it: course and waypoints, sail, point of sail, quarters, the named gun target, the signal flying, each battery's loaded and manned counts, what every gun's crew is at this second, and the contacts.
  - **4 SIGNALS** - the signal book, who the signal is addressed to, what is flying and who has answered, and your squadron with each captain's skill, wit, dash and obedience (see `19_fleet_and_captains.md`). Arrows choose, `a` changes the addressee, `ENTER` makes the signal.
  - **5 SHIP** - the quarterdeck instruments in full, with hull, company, stores and sight conditions.
  - **6 KEYS** - every control, wrapped. The footer keeps only the few worth remembering.
- **Focus.** `TAB` cycles ship pane -> chart -> panel. The focused pane's title is highlighted; zoom, rotation, pan and the look cursor act on the scene panes, the arrows on the panel when it has focus.

Recommended terminal: **190 × 64 or larger**; the minimum is 120 × 40. On Windows, Windows Terminal full-screen (`F11`) at a slightly reduced font size (`Ctrl -`) gives plenty.

## How a captain knew heading, wind, speed and time

The question is what the officer on the quarterdeck actually had. The instruments panel shows exactly that, in his vocabulary, rather than an all-knowing north arrow and wind vector.

| Need | Period source | In the game |
|---|---|---|
| **Heading** | The **binnacle** beside the wheel: a boxed compass, lit by lamp at night, read in *points* (32 to the circle), e.g. "NE by E". The quartermaster conned the helmsman by it. | `Binnacle NE by E 056°` plus a strip of the compass card centred under a lubber mark `▼`. North only appears as a letter on the card, as it would. |
| **Wind direction** | Felt on the cheek, and read from the **masthead pennant** (the commissioning pennant or a wind vane at the truck) and the **dog-vane**, a string of cork and feathers on a pole at the weather rail for the helmsman. It was always spoken of *relative to the ship*: "two points abaft the beam", "on the larboard bow". | `Pennant gentle breeze (force 3) / broad on the larboard bow / close-hauled, larboard tack`. |
| **Wind strength** | Judged by sea and sails. **Beaufort's scale (1805/06) is exactly period**, and was originally defined by how much sail a man-of-war could carry. | Beaufort force and Beaufort's own wording ("fresh breeze", "moderate gale"). |
| **True wind (for the record)** | The officer of the watch chalked wind and course each hour on the **log-board** for the master to enter in the log. | `Log-board: wind NW` (dim: it's a record, not a live instrument). |
| **Speed** | The **log-line**: a weighted chip streamed astern with a 28-second sand-glass; the knots that ran out gave the speed in knots and fathoms (eighths). It was heaved every hour, or on demand. | `Log 5 knots 2 fathoms`. |
| **Time** | The **half-hour glass** turned by the ship's boy, and the **bell** struck each half hour: eight bells to a four-hour watch. | `Bell 5 bells, forenoon watch` (from `engine/clock.py`). |
| **Sails** | Seen by looking up, and known because the captain ordered them. | A sail-plan table: royal / topgallant / topsail / course on each mast, plus jib and spanker. `█` set, `·` furled, blank where the rig doesn't carry that sail. It is labelled with the setting's name ("fighting sail (topsails)", "all plain sail"). |
| **Position** | Dead reckoning (course, speed and time on the traverse board), noon sun sights for latitude, and bearings of landmarks. Longitude came from chronometers, rare and expensive before ~1800, or lunar distances. | Not yet. It belongs with world generation and navigation (Phase 4). It could go through **asking the master or navigator** for a reckoning, as you suggested. |
| **Depth** | The **lead line**, heaved by a leadsman in the chains and sung out ("by the mark, seven"). | Not yet. See `09_environment.md`. |

You were right that in action much of this mattered less. The captain fought by eye and by relative bearings: "she's two points on our starboard bow". Heading in points and wind relative to the ship are exactly what he needed, so that's what the panel emphasises. Exact compass degrees are shown small, for our convenience.

**Later, to make it more immersive:** instruments could become *crew reports*. The quartermaster sings out the course, the leadsman the depth, the lookout the sails. They would then carry the same delays and errors as masthead reports: a green or frightened hand misjudges, and a dead quartermaster stops reporting. Hooks for this exist already (lookout reports are delayed, Phase 1 adds skills).

## Controls (current)

| Key | Action |
|---|---|
| `SPACE` | pause / resume; paused = **planning mode** (your whole ship shown; orders apply when time runs) |
| `TAB` | move focus: ship pane -> chart -> panel (arrows then move within the panel) |
| `1`-`5` | choose the panel: log, crew, orders, ship, keys |
| `m` | **walk mode**: be the captain. The view closes in to three cells a metre and follows him; `e` lists what he can do where he stands, `1`-`9` does it |
| `+` `-` | zoom the focused pane |
| `r` | rotation of the focused pane (ship: bow-up / north-up / bow-right; chart: north-up / ship-up) |
| `c` | cell shape of the focused pane (1 m × 1 m or 1 m × 2 m) |
| `o` | captain's eyes / masthead lookout's eyes |
| `a` `d` (`A` `D`) | helm 5° (30°) to larboard / starboard |
| `w` `s` | call for more / less sail. The order is given at once; the canvas follows as fast as hands can set or take it in (about half a minute for the whole plan) |
| `b` | beat to quarters / stand down |
| `[` `]` | fire larboard / starboard broadside |
| `l`, arrows / `hjk`, `HJKL` | look cursor in the focused pane (who a man is, where he's from, his condition and pulse, state of mind; the plank's material and condition; what's in the cask); arrows pan when not looking |
| `x` | tell the guns to fire at whatever the look cursor is on; the gun captains take time to understand it |
| `g` | steer for the cursor; `f` recentre |
| `<` `>` | time slower / faster |
| `v` | reveal everything (debug) |
| `q` | quit |

Planned: a real **orders menu** in period language instead of raw keys ("Hands to make sail", "Brace up", "Wear ship", "Clear for action"). This fits once Phase 1 gives each order a crew evolution that takes time and can fail. See `10_naval_primer.md` §Commands for the vocabulary.

## Pacing: slow ship, smooth screen

A sailing ship should feel heavy, and the screen should not. The two were the wrong way round at first - motion was quick and the picture stuttered at five frames a second - so both were changed:

- **The ship is slower to answer.** The rudder needs water flowing past it, so a ship with no way on hardly answers her helm at all; way is gathered and lost over about half a minute; and sail is now *ordered* rather than set, the yards following at the speed men can work them. Setting a course is a decision you then live with.
- **The ship holds still.** Her position is continuous, so the sampling grid used to slide under her deck and every plank, gun and hatch shimmered a cell back and forth as she made way - worst in walk mode, where the camera rides on the captain, who rides on a moving ship. The camera is now snapped to the ship's own grid (and offset half a cell, so no sampled point lands exactly on a tile's edge, where the last bit of floating point decides which plank it is). Measured: 31% of her fabric moving between frames, down to 0.6%. The sea slides past her instead, which is the way round it should be.
- **The sea runs in waves.** It was a noise field cut at a threshold, which popped on and off in blotches. It is now two trains of travelling waves running with the wind at the speed deep-water waves of their length actually run (c = sqrt(gL/2pi)), modulated by slow noise so the crests are not corduroy, with wavelength scaled to the zoom - wind waves on the deck, long swell on the chart. Crests march; cells do not blink.
- **The chart says which way she is pointed.** A north-up chart could not
  tell you how you lay to the enemy, so it now dots out her fore-and-aft
  line, her beams and the four-point diagonals from the ship herself, and
  runs a line of fire to whatever the guns are laid on with that ship's
  bearing, range and aspect written at her end of it. The status strip
  carries the same in words, immediately after the helm.
- **There is a front door now.** `python -m broadside.game` opens a menu
  with the five tutorial missions, free sailing, the scenario library,
  help and quit; `q` aboard ship comes back to it. See
  `22_the_game_and_the_course.md`.
- **The screen is quicker, and uncapped.** A 190 x 64 frame went from about 180 ms to about 40 ms, and the draw rate is now limited only by a 120 fps ceiling. Simulated time is fixed ticks accumulated against real elapsed time, so **a faster screen never means a faster ship** - it only means smoother motion (and the strip shows the frame rate, so you can see it):
  - sight lines are traced on a **1 m grid**, never finer, because the world is modelled at a metre - so zooming in to three cells a metre no longer costs nine times as much;
  - the **chart is cached** for 0.4 s at a time;
  - map memory stopped sorting twelve thousand coordinates a frame;
  - the screen cell became a `NamedTuple`, and the per-cell loop reads plain Python lists instead of indexing numpy twelve thousand times;
  - the traced **sight field is reused for a tenth of a second** - what is visible does not change in that time, while the people, the water and the ship's position are redrawn every frame;
  - the app draws as fast as it can, to a 120 fps ceiling. Measured at 190x56: the ship view about 20 fps, walk mode 24, the levels 28, the glass 130.

## Still to come

- **Below decks.** Walking down a hatch to the gundeck, the orlop and the hold, with the z rule from `16` sec. 7: free to scroll while time is stopped, walked when it is running.
- **An orders menu** in period language instead of raw keys ("Hands to make sail", "Brace up", "Wear ship", "Clear for action"), once each order is a crew evolution that takes time and can fail.
- **Roster sorting and filtering** (by skill, by station, by condition), and picking a man to give an order to.
