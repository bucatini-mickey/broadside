# 22 - The game, and the course of instruction

*Round 10. Until now Broadside was a library of scenes you launched from a
command line. This is the front door: one program, a menu, and five
tutorial missions that teach the whole of what is built by making you do
it.*

## The front door

    python -m broadside.game        (or just python -m broadside.main)

A plain menu drawn with the same buffer and renderer as the ship, so it
looks like part of the same thing:

- **Five tutorial missions**, in the order a man would learn them.
- **Free sailing** - the sandbox.
- **The scenario library** - every test scene in the game, as a submenu.
- **Help** - every control, taken from the same table the in-game KEYS
  panel uses, so the two can never disagree.
- **Quit.**

Arrows choose, `ENTER` plays, the digits jump straight to a mission, `h`
is help and `q` quits (or backs out of a submenu). `q` aboard ship leaves
the mission and comes back to the menu, so nothing is a dead end. Every
state the menu can be in is a value in `MenuState`, which is what the
tests drive; a scene that will not build reports itself on the menu's
message line instead of taking the program down with it.

## The five missions

Each is a `Tutor` with its own list of lessons (`scenarios/courses.py`,
running on the machinery built for the original course in
`scenarios/tutorial.py`). A lesson announces itself in the log, hints
after a minute, and **passes only when the ship's own state says it is
done** - nothing is scripted and nothing is taken on trust.

### 1. Handling your ship - *tutorial_1_handling*

A cutter: one mast, eight 4-pounders, thirty hands, and nobody to fight.
Walk to the wheel; steer by the binnacle; make sail; find the point of
sailing; lay a course with the cursor; then the whole business of a port -
come in under short canvas, get the way off her, let go the anchor, lie to
it within a boat's pull of the mole, and weigh again and stand out to sea.

### 2. Commanding a squadron - *tutorial_2_squadron*

A brig and two cutters. The signal book; form line of battle and watch a
consort take station; lay a destination for the whole force; make all sail
by signal. The two consort captains are deliberately unalike - Swift's is
steady and obedient, Hazard's a fire-eater with poor discipline - so that
obedience is visibly a number in the panel and not an assumption.

### 3. Ship against ship - *tutorial_3_duel*

Two equal brigs meeting on opposite courses. Identify her through the
glass; con her onto your beam (nothing fires ahead); beat to quarters;
pass the word to the gun captains so they lay for her range; ask one of
them where his shot would go; give the word; keep firing until her
timbers start. Her captain is working for the same position you are.

### 4. A squadron in action - *tutorial_4_fleet_action*

A frigate and two brigs against two Frenchmen, with the weather gage and
one rule: **you are not to be in the thick of it.** Report the enemy,
order the squadron in, keep more than six cables off so that you can see
and be seen, call a consort off by name, and watch what captains of
different discipline make of your flags.

### 5. Stores, and the state of your people - *tutorial_5_supplies*

Nine weeks out, fourteen days of provisions, a sullen company. Read the
hold and the company; put her on two-thirds allowance and watch the days
remaining lengthen; watch the grievance that buys you; splice the
mainbrace to buy some of it back; and give them a full ration again when
you can.

Each mission has a test that plays it through with a scripted student
doing what a player would do, and passes only when the tutor itself
declares the course complete (`tests/test_courses.py`). That is the proof
that every lesson is reachable - and it caught two of my own lessons being
impossible as first written.

Missions are marked `interactive=True` in the registry. They are checked
headless with everything else, but left out of the HTML replay export: a
tutorial mission with nobody at the wheel is twenty megabytes of a ship
drifting. Export one by name if you ever want it.

## What had to be built for them

### The anchor

There was no anchoring at all. There is now, in
`sim/systems/seamanship.py`, as an order and a condition with real work
between them:

- `ShipOrders.anchor` is the order; `anchored` is her condition.
- **She will not lie to her anchor under sail**, and you cannot let go
  while she is still running down on it: over about a fifth of her canvas
  or two and a half knots and the order is refused, with the reason.
- **Letting go takes 14 seconds; weighing takes 75**, scaled by how many
  hands she has - it is the heaviest routine work in the ship.
- Riding to it she makes no way whatever her canvas.

Docking, in these seas, is anchoring in the roads within a boat's pull of
the quay, which is what `moored_to` reports. The tutorial's port is a
generated headland with a stone mole on it.

### Short allowance, and the mainbrace

- `r` puts her on **two-thirds allowance**: the provisions last half again
  as long (`days_of_victuals` accounts for it, and so does the SHIP panel)
  and the men mind it - grievance creeps up and they appraise it as short
  commons, which is the same machinery that handles being shot at.
- `G` **splices the mainbrace**: an extra issue of grog, half a pint a
  man, taken out of the rum actually in the hold, appraised exactly as the
  daily issue is. Once an hour at most, and it fails honestly when the
  hold is dry.

### A cutter

`cutter_8` - 20 m, eight 4-pounders, 34 men. The teaching ship: few enough
guns that you can follow every one of them by eye.

## One change to the shot preview

The estimate (`p`, from round 9) is now only to be had **when there is
somebody to ask**: she must be at quarters with a man at a loaded gun. Ask
with her guns housed and you are told to beat to quarters first; if the
men leave the guns, the estimate goes with them. It was always meant to be
the gun captain's opinion rather than a readout, and now it behaves like
one.
