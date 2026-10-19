# Views, Observation, Object Skeletons and Named Targets

Design decisions taken 2026-09-23 and 2026-09-26, with what is built so far
and what is still a note. The drill and the teaching side of it have their
own document: `17_drill_signals_and_tutorial.md`.

## 1. The two views are one world at two zooms

There is no "ship view" model and "macro view" model. There is one world,
and two windows onto it:

- **The ship view** is a zoomed-in rectangle around your own ship, rotated
  so the bow stays up. Every cell is a metre or half a metre: you see people
  walking, single objects, single blocks. Anything that comes inside that
  rectangle is drawn at that detail, whether it is your deck, another ship
  alongside, a rock, or the corner of a fort.
- **The macro view** is the same world zoomed out: your ship small, and the
  other ships, islands and structures around her.

So a wall 120 m off does not need a rule to keep it out of the ship view -
it is simply outside the window. As you close with it, it comes in, and it
is drawn block by block because that is what the zoom is. *(This corrects an
earlier note that proposed banning distant objects from the ship pane.)*

## 2. Observation is something the captain does - built

`t` takes up the glass, `T` looks out over the rail. The ship pane is given
over to a **first-person picture** of what lies along that bearing
(`view/firstperson.py`), the arrows sweep it, and `+`/`-` change the field.

- Raising the glass is an `Action`: the captain is occupied with it for a
  couple of seconds, and while it is up he is looking one way only.
- The field is the trade: about 70 degrees by eye, 7 with the glass, and
  the narrower it is the larger things appear - which is what a telescope
  actually does.
- The picture is a **heightfield raycast**. For each column a ray is marched
  outward; every time it clears the top of something further off than
  anything nearer, that band of rows is filled with whatever the thing is
  made of, shaded by haze and the light. So you see the *face* of a thing:
  a hull as a dark band on the sea with her canvas above it, a wall's front,
  a hillside, a tree line, sky. It is one scene query for the whole fan, and
  costs about 15-20 ms.
- Materials are told apart, which was the requirement: sea, surf, sand,
  rock, grass, forest, snow, masonry, rubble, hull, deck, gun iron, mast,
  canvas. Nothing has a separate "front texture" - the material of the
  surface the ray meets is what is drawn (see sec. 3).
- **Your own ship is left out of the picture.** A captain with a glass
  moves his head, steps to the rail, or sends a midshipman to the
  crosstrees; what he does not do is spend five minutes looking at his own
  bulwark. So the look ignores your own hull, masts and canvas - and
  nothing else: fog, smoke, islands and other ships obstruct as ever.
- **The chart marks the field**, as two dotted edges and the bearing down
  the middle, so sweeping the glass is legible on the macro view.
- **The glass is held relative to her head**, tilts up and down with the
  other two arrows, carries a reticle, and will hold a ship in the field
  with `TAB`; `p` lays the gun captain's estimate of the shot over it. All
  of that is in `21_bearings_and_the_fall_of_shot.md`.
- **Raising the glass puts you down out of walk mode**, so the arrows are
  unambiguously the glass's. You cannot walk the deck and study the horizon
  at the same time, and trying to do both left the arrows attached to
  walking while the glass sat still.
- **It tells you as well as shows you.** A look reports what it finds - "a
  brig, hull up, bearing NNE, about 150 m" - which is how a captain told a
  brig from a frigate. Still to come: the report's *accuracy* depending on
  the looker, asking the lookout or the navigator instead of looking
  yourself, and fall-of-shot reports.

## 3. One appearance per thing, taken from above

Do **not** author a separate look for each face of a block or part. A
material or part has one appearance - the top-down one - and every other
projection (the elevation pane, a distant silhouette) reuses it, with
shading if it helps. A new material must stay a single line of data.

## 4. Object skeletons

Still a note; the natural next structural job.

Generated objects - fortresses, ships, batteries, towers - want a **named
part graph** over their geometry:

- A **part** has a name (`left curtain wall`, `magazine`, `sally port`,
  `foremast`, `rudder`, `larboard bow`), a region (voxel span or deck-tile
  span), links to neighbouring parts, and a role (structural, explosive,
  propulsive, steering, crew space).
- Parts are what damage, orders, reports and the look cursor all speak in:
  "the foremast is wounded", "they have a gun disabled on the larboard bow".
- Links give knock-on collapse for free, and the magazine's role says what
  happens when shot reaches it.
- Skeletons are generated with the object, so a procedural fort names its
  own walls and bastions.

## 5. Named targets - first cut built

The captain does not lay guns; he says what to fire at, and his gun captains
obey when they have understood him.

Built now (`sim/gundrill.py`, `ui/app.py`):

- `ShipOrders.gun_target` names an entity, with the time it was named.
- A gun captain adopts the named mark only after
  `6 s + 26 s x (1 - his skill)`: a crack hand shifts in a few seconds, a
  green one is still firing at the old mark half a minute later. Until then
  he goes on with what he was doing. This is the mechanism the user asked
  for - experience decides how fast an order is understood.
- A gun that cannot bear on the named mark lays on whatever she *can* bear
  on, which is why a ship is manoeuvred to bring her guns to bear.
- In play: `l` to put the look cursor on something, `x` to order the guns
  onto it. The order and the delay are both visible in the log and the
  DETAILS panel.

Still a note: **orders in terms of parts** - "attack the left wall", "focus
on the magazine" - which needs §4 first, and reports back when the crew have
misunderstood.

## 6. Laying the gun - built

A gun captain now solves his own aiming problem (`gundrill.solve_elevation`,
`gundrill.lay_gun`):

- He picks the nearest thing his gun can bear on within her arc (+/-12 deg of
  training), preferring a mark the captain has named.
- He estimates the range, misjudging it by however green he is, and the
  elevation is then *solved against the real trajectory* - the same drag and
  gravity the ball will fly under - by bisection. A 24-pounder comes out at
  about level for point-blank work and a degree or so for 600 m, which is
  what the period gunnery tables say.
- Structures are aimed at the **foot** of the wall, which is how a breach is
  made; ships at the hull.
- His error is re-rolled every time he lays her, so shot-to-shot dispersion
  is a property of the man, not a magic number.

## 7. The z axis - built for the world, pending for her decks

`z` cuts the world into horizontal levels and PgUp/PgDn walks up and down
them (`view/levels.py`), Dwarf-Fortress fashion: a cell that is solid at
this level is drawn as its cross-section, a cell that is open shows whatever
is below it, dimmed by how far down. Everything in the world already knew
its own height, so everything appears at the right level:

- **the sea** - level 0 is her surface; below it the water column and the
  bottom coming up (`TerrainSample.seabed`: a nominal bottom by water type
  until real soundings exist);
- **land and hills** - rock below you, the ground where you would stand,
  open air above;
- **trees** - a trunk at ground level and a canopy above it;
- **ships** - the hull from her draught to her rail, the weather deck at
  freeboard, the sails as bands, then bare masts;
- **fortifications** - read straight out of their voxels, which are already
  true 3D.

What is *not* there yet is the inside of a ship: below her deck you see her
hull section and her hold as one undivided space, because the gundeck, orlop
and hold are not modelled. That is the next structural job, and the rule for
it stands:

- **Time stopped (planning) - no restriction.** Scroll freely up and down
  through the decks and look at the whole ship. A captain knows his own ship.
- **Time running, as the captain - you must walk.** No free z scrolling: to
  see the gundeck you go below, which costs time and puts you out of touch
  with the quarterdeck.
- **The macro view is a masthead view.** Treat it as what the lookout in the
  crosstrees can see, which is why it shows more of the world and less of the
  detail.

## 8. Physics of materials - next

Blocks currently break by spending the ball's energy, fall when unsupported,
and slide into rubble. What is missing is what the user asked for: **a
block's connections**. A ball striking a piece of timber should drag its
neighbours with it - beams, knees and planking pulling on each other, so a
hit near a joint tears a whole section away rather than punching a neat hole.
That is a force-and-link model over the voxels, and it is the natural
successor to the present energy model.

## 9. Not now

Fortresses as garrisoned places, and the campaign chart, are set aside on
purpose. The near work is the crew, their actions, and sailing.
