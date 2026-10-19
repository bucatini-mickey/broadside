# 21 - Bearings, aspect and the fall of shot

*Round 9. "I found a big issue for aiming to be understanding where we are
facing in relation to the enemy" - and the answer to it, which turned out
to be three separate things: the words, the chart, and the shot.*

## The glass takes the arrows properly now

Two faults, both reported from play:

- **Up and down scrolled the log.** The look handler only claimed left and
  right, so the other two arrows fell through to the panel underneath. They
  now **tilt the glass**, -20 to +40 degrees, which is a real thing a man
  does with a glass and which the first-person view already had the
  geometry for: the pitch simply moves the top of the field, so the horizon
  slides down the picture as you look up.
- **Left and right swept a compass bearing.** So every movement of the helm
  swung the view off whatever you were watching. The glass is now held
  **relative to her head**: you are a man standing on her deck facing three
  points off the starboard bow, and if she comes round, so do you. The
  title line gives that relative bearing first and the compass bearing
  second, because the first is the one that matters when laying guns.

The sweep step is a quarter of the field rather than a fixed two degrees,
so a strong glass no longer flings the world past you.

`TAB` **takes the next ship in sight into the glass and holds her there**,
nearest first: the view then tracks her as she moves and as we turn, and
reports her name, her bearing, her range and her aspect. Sweeping by hand
lets her go. `f` returns the glass dead ahead and level.

## The words

`view/orientation.py`, which has no state and no opinions:

- **Relative bearing** in points, the way a lookout called it: *dead
  ahead*, *three points on the starboard bow*, *on the port beam*, *two
  points on the port quarter*, *right astern*. A point is 11.25 degrees;
  the forward quadrants are counted from ahead and the after quadrants from
  astern, which is how it was done.
- **Aspect** - what of her we can see, which is the number that decides
  whether a broadside will tell or glance off two feet of oak end-on:
  *bows on*, *her starboard bow to us*, *broadside on, her port side to
  us*, *her port quarter to us*, *stern on*. It is her heading seen from
  our bearing, so it changes as either ship turns.
- **Range** in metres close to, cables further off.

## The chart knows which way she is pointed

A north-up chart cannot tell you how you lie to the enemy, which was the
complaint. It now draws, dotted out from the ship herself:

- her **fore-and-aft line** ahead (brighter, marked `ahead`) and astern,
- her **beams**, port and starboard,
- the **four-point diagonals** between them, fainter.

A contact sitting on the starboard beam line will take the whole broadside;
one on the bow line will not, and now you can see which it is at a glance.
None of it is ever painted over a ship, a coast or a contact - the dots
only fill water and unknown sea.

When the guns are laid on something, a **line of fire** runs out to her in
`+`, with her bearing, range and aspect written at her end of it, and the
status strip carries the same thing in words: `guns on Vigilante stbd beam,
480 m, broadside (port)`. It sits immediately after the helm, because the
strip is cut off from the right on a narrow pane and this is the part you
cannot do without.

## The fall of shot, before the word is given

`p` asks the gun captain where his shot would go.

- `sim/systems/ballistics.predict_shot` is a **dry run of the model that
  actually fires the ball**: same drag coefficient, same muzzle velocity
  for the gun's weight of metal, same elevation it is laid at. It creates
  nothing and touches nothing - verified by a test that counts projectiles
  and her position before and after.
- `gun_to_bear` picks the gun that *can* be laid on the mark, training it
  within its port with the existing `train_for`/`bears` rules, rather than
  the gun that happens to be pointing that way.
- The result carries the **track over the water**, the **first graze**, the
  **apex**, the **time of flight**, and a verdict against the target which
  is about height at her range rather than where the ball lands: *falls
  70 m short of her*, *would strike her hull*, *would pass 8 m up - her
  rigging, not her hull*.
- **It is his estimate, so its precision is his.** The spread reported with
  it is a quarter of the range for a raw crew and a twentieth for a crack
  one, drawn as `480 m +-24`. A green gun captain's preview is honestly
  vague, which is the point: the preview is not a cheat, it is the man at
  the breech telling you what he thinks.

Drawn in two places at once, the same prediction:

- **On the chart**, the track in dots (`-` where the ball is skimming, `.`
  where it is up), a `x` at the splash, and the range, spread and verdict
  beside it.
- **Through the glass**, the arc as the gun captain would see it rise out
  of the muzzle, flatten and come down - projected into the same angular
  frame as everything else in that view, so it lies over the sea properly
  and ends at the splash. At very close quarters the arc can fall outside a
  seven-degree field: the gun is eight metres from your eye, and at a
  hundred yards that parallax is real. The chart still shows it.

A **reticle** marks the centre of the field on the horizontal, with what it
is laid on written under it. A glass without a mark is a picture; with one
it is an instrument.

## What this leaves for next time

- Fall-of-shot *reports* after firing ("over, two cables"), which the AI
  captains can use as well as the player.
- A solver rather than a preview: the elevation for a given range, with her
  roll modelled, so `x` could mean "lay for her waterline".
- The sub-metre rendering lock, which is still the first item in
  `20_sighting_and_instruments_plan.md`, and the instrument band and signal
  flags from the same plan.
