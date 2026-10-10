# The Drill, Signals, the Sandbox and the Tutorial

Built 2026-09-26. Code: `sim/gundrill.py`, `sim/actions.py`,
`sim/systems/signals.py`, `sim/items.py`, `scenarios/sandbox.py`,
`scenarios/tutorial.py`. Try it:

```bash
python -m broadside.scenarios run tutorial      # eleven lessons, played
python -m broadside.scenarios run sandbox       # a deck to walk, things to try
python -m broadside.scenarios run gun_vs_wall   # you, one gun, one wall
python -m broadside.scenarios check gun_vs_wall_demo tutorial_demo
```

## 1. Nothing loads behind a progress bar

The principle: **every interaction that can be acted out, is.** A gun is not
a cooldown with men standing beside it. It is nine separate jobs, each done
by a named man, each taking the time that man needs:

| # | Order | Whose job | Skill | Physically |
|---|---|---|---|---|
| 1 | Sponge out | 2 rammer/sponger | gunnery | light |
| 2 | Load a powder cartridge | 3 loader | gunnery | light; takes a cartridge from the box |
| 3 | Ram the cartridge home | 2 | gunnery | moderate |
| 4 | Wad the charge | 3 | gunnery | light |
| 5 | Load round shot | 3 | gunnery | **the ball's weight** - takes one from the garland |
| 6 | Ram the shot home | 2 | gunnery | **the ball's weight** |
| 7 | Run the gun out | 4 tackle men | seamanship | **the gun's weight over the number of hands** |
| 8 | Prime the vent | 1 gun captain | gunnery | light |
| 9 | Lay the gun | 1 gun captain | gunlaying | judgement (see `16` §6) |

Each step's duration comes from:

- **skill** - `base x (0.6 + (1 - skill))`, so a green hand is about twice an
  expert;
- **fatigue** - work tires men, and tired men are slower, which is the tie
  into food, drink and morale;
- **physique** - arms, hands and pain from `sim/people`: a man with a hand
  gone is much slower at the rammer, and this is not special-cased anywhere;
- **the weight of the thing** - a 32-pounder ball is a heavier lift than a
  9-pounder's; a gun of 2.5 tonnes with one man on the tackles takes 27 s to
  run out and 8 s with four, which is why crews were what they were;
- **whose job it is** - a man covering another man's station is 20% slower,
  in his way.

If the man doing a job is killed or called away, the job is dropped and the
next man picks it up from the beginning of that step.

**What falls out of it.** Rate of fire is nobody's constant. Measured: a
brig's 9-pounders with three men each fire about one round a minute; a
24-pounder worked by the captain alone takes about a minute and a half, most
of it running her out. Shorthanded guns get slower; wounded crews get much
slower; a gun with nobody left at it stops.

The same table drives the player (`sim/actions.py` offers the *next* order in
the drill, with the time it will cost him) and the crews
(`gundrill.gun_drill_system`). There is exactly one definition of the drill.

Guns below decks and ships simulated without crew entities still reload on a
timer - a fleet of thirty ships cannot afford a hundred individual men per
ship yet.

## 2. Powder comes from the magazine

A gap the drill exposed at once: shot garlands sit beside each gun, but
powder lives in the magazine, so the guns could never be charged. Now
**clearing for action serves out cartridges**: when quarters is beaten, the
boys carry cartridges up and fill the box beside each gun on deck, and the
powder is *deducted from the magazine's barrels* at the service charge for
that calibre (a third of the shot's weight for a long gun, a quarter for a
carronade). Ten cartridges a gun. A ship can run out of powder, and a gun
with nothing to load says so once and stands idle.

Since round 6 the boys **keep** the boxes and the garlands filled while the
ship is at quarters - every forty seconds, from the magazine and from the
shot lockers below (sixty rounds a gun, the period establishment). Powder
monkeys as *people* running up and down with salt boxes are the next step;
the bookkeeping is already right, and a ship can still be fought dry.

## 3. Signals

A captain cannot hail a ship a mile off, so `sim/systems/signals.py` gives
him the signal locker on the quarterdeck:

- A **code book** of numbered signals, the ones that mattered in action
  ("Engage the enemy more closely", "Come within hail", "Report your
  damage"...).
- **Hoisting takes time** - the flags must be bent on and run up, faster for
  a practised hand.
- The other ship must **see it and read it**: legibility comes from her own
  contact record of you, so fog and powder smoke stop signals dead; then her
  best lookout's skill and the range set how long before she answers.
- What is flying, and how many ships have answered, shows on the
  QUARTERDECK panel.

Semaphore proper was the shore telegraph; at sea this was how it was done.

## 4. The sandbox

`python -m broadside.scenarios run sandbox` - a brig at sea with her company
aboard and nothing required of you:

- walk the deck (`m`, arrows), and look into the casks, bags and the rum
  puncheon struck up in the waist - each one's contents are recorded;
- drink from the scuttlebutt;
- read the signal book at the locker and hoist a signal to be answered;
- beat to quarters (`b`) and watch every gun's crew work through the drill,
  named man by named man, in the log;
- fire into the derelict hulk 120 m to starboard, or at the stone wall on the
  islet beyond her - `l` and `x` to tell the guns which.

`gun_vs_wall` remains the one-gun version where you do every step yourself,
and `gun_vs_wall_demo` is its crew-worked counterpart: ten rounds in ten
minutes opens a breach through 2 m of masonry and brings a dozen blocks down.

## 5. The tutorial

`python -m broadside.scenarios run tutorial` - eleven lessons, each passed
only when the ship's own state says it has been done:

1. **The captain is a man on a deck** - walk to the wheel.
2. **The binnacle** - heading in points, not degrees; steer east.
3. **Points of sail** - in irons, close-hauled, abeam, running; put the wind
   on the quarter.
4. **Making sail** - and why she gathers way slowly.
5. **Fighting sail** - why royals and topgallants come in before action.
6. **Signals** - hoist No. 1 and wait to be answered.
7. **Laying her alongside** - guns fire out of the sides, so the enemy must
   be brought abeam.
8. **Beat to quarters** - and how long it takes men to walk there.
9. **The drill** - take a hand at a gun yourself.
10. **Giving the word** - you choose the moment; the gun captains lay.
11. **The fall of shot** - what a ball does when it arrives.

The lesson text explains the seamanship as it goes, so the tutorial doubles
as the primer (`10_naval_primer.md` is the longer read). A hint appears if
you are stuck for more than a minute.

`tutorial_demo` drives the same eleven lessons with a scripted student who
uses only the controls a player has - proof that the course can be finished,
and an HTML replay of it.

## 6. Known limits

- The gun's crew work their piece as fast as they can whenever quarters is
  beaten; they do not yet hold fire, fire on the roll, or choose ammunition.
- Cartridges are served out in one act at quarters rather than carried up
  continuously by boys.
- One weather deck is drawn, so below-deck batteries are still abstract.
- The tutorial teaches nothing about tacking, wearing, anchoring or
  boarding yet.
- Signals are read by ships, not by named signal midshipmen with their own
  skill.
