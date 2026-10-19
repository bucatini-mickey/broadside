# 24 - Three modes, two logs, and a sea that is actually there

*Round 12. The player's own design, written down, with what already exists
underneath each part of it and what each missing piece would cost. Nothing
in the second half of this document is built yet; the first half is the
regression work that came with it.*

## What was broken (and is fixed)

Three faults in one report - *"ship is broken, menu not displaying"*:

1. **The ship was drawn as her plain glyphs doubled.** Auto-fit opens a
   small ship at **two cells to the metre**, but the sub-cell tile art
   (`view/style.subtile`) only switched on at three. So the default view -
   the one every player sees first - drew each tile's single glyph into a
   2x2 block: `##` bulwarks, two-by-two wheels, doubled gratings. Blocky,
   and nothing like a ship. Every tile now has a two-cell form: a solid
   bulwark, a gun with her muzzle outboard and her carriage inboard, a
   grating, a mast, the wheel. She reads as a ship at the zoom she opens
   at.
2. **The chart's bearing cross was a web of dots across the whole sea**,
   and it painted over the legend row - which is what made the picture look
   corrupted. It is now a short cross about a third of the pane, marked
   sparsely, labelled *ahead / astern / port / stbd*, and it never writes
   on the legend.
3. **"Menu not displaying" was real.** The menu held `term.fullscreen()`
   while a mission entered `term.fullscreen()` again; leaving the inner one
   dropped out of the alternate screen altogether, so afterwards the menu
   was painting onto a screen nobody was looking at. The menu now owns one
   fullscreen context per visit, entered and left around each mission. It
   also goes one line per item when the terminal is short, so *help* and
   *quit* are never below the fold, and says so plainly when the window is
   too small to draw at all.

All three have tests that drive the real paths - including one that runs
`game.run()` against a blessed terminal writing into a buffer, so a menu
that does not paint fails the suite.

## The three modes

The design, as given: three ways of being aboard, each with its own job.

### Master (god) view - mostly built; needs naming and an inspector

Observe the whole ship, live or paused; scroll through every level; inspect
the progress and the mood of every hand. The micromanaging half of the
game: watching your orders being carried out.

**What exists:** the level view (`z`, PgUp/PgDn) is exactly this, and works
live as well as paused - a slice per metre, with her canvas above the deck,
her people on it, her hull and the seabed below. The CREW panel already
gives a DFHack-style sheet per man: skills, needs, mood, wounds.

**What it needs:** a cursor in the level view that steps from man to man
and opens his sheet (the plan view has the look cursor; the level view does
not), and the mode named on screen so the player knows which of the three
he is in.

### Captain mode - built, and the most unfinished

Live, immersive, the main way to play: walk, talk, order, read. Sleep as
the way to let time run.

**What exists:** walk mode (`m`) with the captain as a man on a deck, `e`
for what can be done where he stands, the whole gun drill as acted work,
and the deck as a proper slice since round 11.

**What it needs, cheapest last:**

- **Below-deck levels.** The one real blocker. His quarters, the hold, the
  magazine, the orlop: internal levels with their own tiles, which both the
  level view and walk mode are already built to display. Until they exist
  there is nowhere to walk to and no cabin to keep documents in.
- **Talking to a man.** A conversation is an `Activity` like any other, and
  the people model already has mood, grievance, allegiance and a history
  worth asking about. Cheap, once there is a reason to stand beside
  someone.
- **Sleeping as time compression.** Almost free: `<` and `>` already
  compress time, so a cot that offers *turn in until the morning watch* is
  a wrapper round them, with the watch bill deciding who wakes him and why.

## Two logs, and taking the interface out of the panel

The player's own point, and a good one: **walking to a thing and reading it
is better than a panel that always knows everything.** That splits the log
in two:

- **The immediate log** - "a ball struck the mainmast", "Tomas Vieri is
  down" - belongs in the control panel, bottom right, where it is now. It
  is what the captain can hear and see from where he stands.
- **The ship's journal** - made port here, supplies short, a man flogged, a
  prize taken - is a *document*. It should live on the table in his
  quarters and be read by walking to it. It does not exist yet; what does
  exist is the raw event log that everything is drawn from, which is most
  of the work.

The same principle applies to the charts: the macro map stays in the corner
for what he can see from the deck, and the campaign chart - coasts and
ports he has not visited - is a document on the same table.

### Telescope mode - built; could do more with the weather

**What exists:** the glass (`t`), held relative to her head, tilting,
holding a ship with `TAB`, with a reticle and the gun captain's estimate of
the fall of shot (rounds 9 and 11).

**What it needs:** the weather is already a continuous field over space and
time at three scales, so a squall line, a rain shaft or a patch of calm
*is* in the model. The renderer reads cloud and rain per cell, but the
glass does not yet tell you there is weather coming up to windward, which
is half of what a glass was for.

## A sea that is actually modelled

*"We just need to ensure that the whole world, including the water, is
being modelled; waves, currents, fish, etc are physically modelled."*

The honest state of it, because this is the gap between what the sea looks
like and what the sea *is*:

| | modelled | drawn | affects the ship |
|---|---|---|---|
| wind | yes - a field over space and time, gusts, squalls | yes | yes: her speed, her heel, her point of sail |
| waves | **no** - a travelling-wave *texture* for the renderer | yes | **no** |
| swell | no | partly | no |
| currents | **no** | no | no |
| tide | no | no | no |
| depth and seabed | yes - bathymetry, shoals, grounding | yes, in the z levels | yes |
| fish, birds, life | **no** | no | no |

So the water is a surface pattern with correct physics *of the pattern* -
wavelength, phase speed, running with the wind - and nothing underneath it.
What it would take, in the order I would do it:

1. **One sea-state field** in place of a render-time texture: significant
   wave height, period and direction, driven by the wind field's fetch and
   duration and varying over kilometres. The renderer samples it; so does
   everything else. This is the keystone, and everything below depends on
   it.
2. **Her motion in it:** heave, pitch and roll from the wave field at her
   position and heading. Three systems are already waiting for this - the
   gun drill (laying on the roll), sighting (an eye 1.7 m up that rises and
   falls), and boat work alongside.
3. **Currents:** a slow vector field, strongest in straits and round
   headlands, added to her way through the water by the movement system.
   This is the one that turns navigation from arithmetic into seamanship:
   a current across a strait means laying a course you would otherwise call
   wrong.
4. **Tide**, as a slow scalar over the whole chart: the depth under her
   keel, and whether a harbour can be entered at all.
5. **Life:** fish, birds, a whale. Cheap, and worth doing last rather than
   first - a shoal breaking the surface is a *sighting*, and gulls working
   over a shoal are information.

1 and 2 are one piece of work and pay for themselves immediately in gunnery
and sighting. Each stage is testable the way the rest of this engine is
tested: a number that must move the right way when the wind has blown
across a hundred miles for a day.

## Still open from earlier rounds

- **The sub-metre lattice lock** (item 0 of
  `20_sighting_and_instruments_plan.md`): the sampling grid is rotated to
  her heading while her tile grid is axis-aligned in her own frame, so
  about a tenth of her bulwark cells still move at a metre a cell. The
  cask-per-cell zoom waits on it.
- **Below-deck interiors**, as above - now the blocker for captain mode
  rather than just a missing view.
