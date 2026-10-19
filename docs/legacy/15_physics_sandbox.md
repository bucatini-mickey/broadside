# Physics Sandbox: Shot, Structures and Destruction

The first real physics: a gun you work yourself, a ball that flies, a wall built of blocks that crack, break, collapse and throw up dust. Code: `sim/systems/ballistics.py`, `sim/voxels.py`, `sim/actions.py`, `view/elevation.py`. Try it:

```bash
python -m broadside.scenarios run gun_vs_wall        # you work the gun
python -m broadside.scenarios run gun_vs_wall_demo   # scripted: one man, ten rounds, a breach
```

## The sandbox

A gunboat with one 24-pounder lies about 120 m off a stone curtain wall (20 m long, 2 m thick, 5 m high) on an islet. You are the captain. Press `m` to **walk** the deck yourself, `e` to see what you can do where you stand, and a number key to do it.

The right-hand pane switches from the chart to an **elevation view**: the wall seen face-on, one 0.5 m block per two columns, showing cracks, craters, holes right through, rubble and the dust hanging over it.

## Working the gun (`sim/actions.py`)

Actions are a general mechanism: a person can act on an object he's next to, the action takes time, and while it runs he's busy. The player and any script (and, later, the crew's own task system) use the same functions, so the player is one more person acting in the world.

The gun is worked through the period drill, and it consumes real stores:

| Action | Time | Effect |
|---|---|---|
| Sponge out | 5 s | required after firing, before loading |
| Load a powder cartridge | 6 s | takes a cartridge from the cartridge box beside the gun |
| Load round shot and ram home | 6 s | takes a ball from the shot garland |
| Prime | 3 s | ready to fire |
| Train forward/aft 0.5° | 1.5 s | at 120 m, half a degree moves the fall of shot about a metre |
| Elevate/depress 0.5° | 1.5 s | the quoin |
| FIRE | — | the ball, the flash, the smoke |

One man alone manages a round every 20–25 s, which is why guns had crews of a dozen.

## The ball (`sim/systems/ballistics.py`)

Mass comes from the pounder rating (a 24-pounder ball is 10.9 kg), diameter from iron's density (~0.14 m), muzzle velocity from the gun type (~460 m/s for a long gun, ~250 for a carronade). The ball flies under gravity and quadratic drag, sub-stepped a quarter-metre at a time so it can't skip through anything thin, and each step asks what it has run into:

- **A wall:** it spends kinetic energy breaking blocks and carries on if it has energy left (see below).
- **A ship:** the planks of that deck tile take damage scaled by the ball's energy, and anyone standing there is wounded — splinters, through the same body model as boarding (`11_people.md`).
- **Water:** a splash; at a grazing angle (under 7°) and enough speed it **skips**, up to four times. Ricochet fire was a real tactic.
- **Land:** it buries itself in a puff of sand.

Every broadside in the game now fires real projectiles, so gunnery has physical consequences everywhere, not just in the sandbox.

## The wall (`sim/voxels.py`)

A ship's hull is modelled per 1 m deck tile because a ship is essentially one deck seen from above. A fortification needs the third dimension, so walls are grids of **0.5 m blocks**, each with a material and an integrity:

- **Impact.** Breaking a block costs energy (material toughness × 120 kJ per 0.5 m block: masonry 360 kJ, solid rock 480 kJ, oak 66 kJ). A 24-pounder at short range carries about 1.1 MJ, so it drives roughly 1.5 m into masonry and lodges — which matches period accounts of what it took to breach a wall. Neighbouring blocks are cracked by spalling, worst behind the impact.
- **Support.** A block stands if the block under it stands. Masonry can arch over a gap of one block; anything wider is unsupported.
- **Crushing.** Badly cracked blocks carrying a tall column above them give way.
- **Falling.** Unsupported blocks drop a block per tick, become loose rubble, and land on whatever is below. Loose rubble slides off steep piles toward its angle of repose, so a breach grows a rubble ramp in front of it — exactly what a storming party wanted.
- **Dust.** Every impact and every landing throws up dust.

In the demo, one man firing ten rounds smashes about 30 blocks, opens a breach through the full thickness and brings a dozen more blocks down as rubble.

## Dust and smoke

Atmosphere puffs now have a **kind**: `smoke` (powder smoke, lingers, drifts and rises), `dust` (stone and sand, settles in ~15 s, hugs the ground) and `spray` (a splash, gone in seconds). All of them obscure sight through the same extinction model (`07_vision_and_views.md`), so a dusty breach is genuinely hard to see through, and the views tint them differently: grey for smoke, sandy for dust.

## What this is groundwork for

- **Phase 2 combat:** the same ball, hull damage and splinter wounds, with aiming from the roll, ammunition types (chain for rigging, grape for men) and carronades at close range.
- **Fortresses:** the wall is already the fort. Add gun platforms, magazines and a garrison of full people, and "a ship's a fool to fight a fort" falls out of the numbers.
- **Ship damage in three dimensions:** hulls could grow voxel sides (planking, frames, the waterline) so shot holes flood by depth.
- **Fire:** materials already carry flammability.

## Known limits

- One ball is one impact line: no splinter cone from masonry, no shot bouncing along a deck.
- Hull damage is per deck tile; below-water holes and flooding aren't modelled.
- Collapse drops blocks straight down rather than toppling them.
- The gunboat carries no crew to help: gun crews still work guns abstractly at quarters; hand-working a gun is the player's (or a script's) job for now.
