# 20 - Sighting, instruments and the look of the sea (round 9 plan)

*A plan, not a build. Written 2026-10-03 against seven notes from play.
Ordered by what each costs against what it fixes, so the cheap and decisive
work happens first and the expensive work waits for its turn.*

## Done in this round (cheap, and the notes asked plainly for them)

### Cloud shadow as a dimming, not a stain

The cloud field is kilometres wide, so across 100 m of deck it is near
enough uniform - and the tint was strong enough (up to 42% toward a dark
blue) that on deck it read as a wash of wrong colour over the whole picture
rather than as weather. The tint is now less blue, less than half as strong,
and does not begin until the light is actually down a few per cent. The
shadows still drift visibly on the chart, which is the scale at which a
cloud shadow is a *shape*.

### Auto-fit decides the cell size before the camera is snapped

The camera is snapped to the ship's own grid so her deck holds still; the
pane's auto-fit then overrode the cell size *after* the snap, so the snap
was to the wrong lattice whenever the two disagreed. The fit now happens
inside `ViewState.camera(state, rows=...)`, before the snap, and reckons in
rows rather than metres (a square cell covers `aspect` metres a row).

## Attempted, and held back with a diagnosis: the deck at a cell to a cask

The note is right about the ratio. The ship view is 1 m a column on a
terminal character twice as tall as it is wide, so a 30 m sloop is drawn 30
rows tall and 8 columns across: slender out of all proportion, and only
eight cells of detail across her beam. That is what reads as "zoomed out"
even though a cell is a whole metre. **Half a metre a column and a metre a
row - square on screen - is the ratio to aim for:** she keeps her height in
rows, is twice as wide across the beam, is in her true proportions, and a
cell is about a cask across.

It was tried as the default and taken back out, because **below a metre a
cell her bulwarks shimmer.** Measured on a ship alone, steady helm, frozen
wind, five frames over 1.2 s, counting how many of her bulwark cells move:

| cells | 1 m x 1 m | 0.5 x 1 m | 0.5 x 0.5 m |
|---|---|---|---|
| bulwark cells moving | 9.7% | 36.8% | 35.7% |

So this is not about the aspect: it is that **below a metre the screen
lattice is not locked to the ship's tile grid.** Two pieces of evidence
worth keeping:

- Quantising the rendered heading coarsely enough to land the view
  axis-aligned (a 3 degree step, which here rounded a heading of ~1.5 deg to
  0) drops the shimmer to **0%**. Rounding to 1 degree changes nothing. So
  it is the *rotation* of the lattice, not the translation, that breaks the
  lock - the translation snap puts the camera on the ship's grid along her
  own axes, but a rotated sampling lattice does not stay in phase with her
  axis-aligned tile grid.
- Snapping to the world's 1 m raster instead, or following her rounded to
  whole metres, is far worse (120%+): the camera then stops following her.

**The fix to try first:** derive the per-cell sub-tile phase from the
ship's own hull grid (`spatial.Content.fu`/`fv` are already ship-local -
the question is whether the *cell centres* are placed on her grid), and
make the camera snap and the sampling rotation use one shared set of axes
rather than each deriving its own from the heading. Until that holds, `-`
zooms to half a metre by hand and the shimmer is visible, which is the
honest state of it.

## Next, in order

### 0. Lock the lattice to her grid below a metre a cell

Diagnosed above, and first because the zoom ratio the note asks for waits on
it - and because a shimmering deck is the complaint that keeps coming back.

### 1. Orientation: knowing where you are pointing (the aiming note) - DONE

**Built in round 9; see `21_bearings_and_the_fall_of_shot.md`.** What
follows is what was proposed, and all three parts of it were done.

- **A relative-bearing ring on the chart.** The compass rose is absolute;
  what a gunnery officer needs is *where he bears from us*. Draw the chart
  with her bow marked and ticks every 45 deg of **relative** bearing, with
  the beams emphasised, so "two points forward of the starboard beam" is
  readable at a glance.
- **A contact line.** From own ship to the current target or cursor: a
  dotted line with the bearing, range and *her* aspect (bow on, quarter,
  broadside) at the far end. Aspect is the number that decides whether a
  broadside will tell.
- **An orientation strip** on the ship view: our heading, the wind's
  quarter relative to us, and the target's relative bearing, in one line.

### 2. Targeting in the glass, and the fall of shot - DONE except the reports

**Built in round 9**, apart from fall-of-shot reports after firing, which
stay on the list.

- **The glass carries a mark**: a reticle at the centre of the fan with the
  bearing and the ranged distance under it, and a nearest-contact lock
  (`tab` through what is in the field).
- **A trajectory preview before `fire`.** The physics is already there, so
  this is a dry run of the existing ballistics: fire a shot with the gun's
  present elevation, charge and the ship's roll held still, and draw where
  it passes - as a dotted arc on the glass with its apex and its first
  graze, and as a fall-of-shot ellipse on the chart (short, over, and the
  spread from roll). It must read as an *estimate by the gun captain*, so
  its accuracy should come from his gunlaying skill: a poor crew's preview
  is honestly vague.
- **Fall of shot reported** after firing - "over, two cables", "short and
  wide" - which the AI captain can use as well as the player.

### 3. Instruments in the ship view, without clutter

A one-row band at the top of the ship pane, not a panel: compass card with
the bow, the wind arrow, sail set as a short glyph per mast (courses /
topsails / topgallants, furled or set), speed, and the helm. Everything
else stays in the panels. Test the character count against the pane width
before it goes in.

### 4. Flags you can see

Signals should be visible as colour, not only as text: a hoist drawn beside
the SIGNALS panel as stacked coloured blocks (one per flag of the number),
and - the better half - **flags drawn at the mastheads in the ship view**
while a hoist is flying, with the enemy's hoists readable through the glass
at a distance his flags can actually be made out at. This makes reading
another ship's signal a *sighting* problem, which is what it was.

### 5. Waves with more in them, still answering the wind

Two travelling trains is better than noise cut at a threshold, but it is
still regular. Add, roughly in this order of value:
- **Three trains at slightly different headings**, the third a slow swell
  from the prevailing quarter rather than the present wind - so a shifting
  wind leaves the old swell behind, as it does.
- **A wider sea state** carried in the weather field: the fetch and the
  hours the wind has blown, slowly varying over kilometres, driving wave
  height and steepness. Waves then build and die with the region, which is
  the "wider wind pattern" the note asks for.
- **More glyphs in the ramp** with the steepness: glassy, ripple, chop,
  crest, breaking, and spindrift down-wind of a breaking crest.
- **Wind streaks**: faint lines along the wind in the smooth patches, which
  is how a real sea tells you the wind's direction at a glance.

## Held back (expensive, and nothing is blocked on them)

- A full ballistics *solver* (elevation for a given range, with the roll
  modelled) rather than a preview of the present lay.
- Flag imagery per nation, and a signal book large enough to need searching.
- Below decks, which is a larger piece of work (see `STATUS_REPORT` 6).
