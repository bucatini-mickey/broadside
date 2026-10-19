# Commanding a Squadron: Signals, and the Captains Who Read Them

Built 2026-10-03. Code: `sim/systems/captain_ai.py`,
`sim/systems/signals.py`, `view/panels.py` (the SIGNALS panel),
`scenarios/fleet.py`. Try it:

```bash
python -m broadside.scenarios run fleet_orders
```

## 1. How advanced was the AI before this? It wasn't.

Worth saying plainly, because it was the question. Before this round there
was **no captain AI at all**. An enemy or consort did exactly three things:

- followed a list of waypoints laid down by the scenario, with the helm
  system beating to windward when a waypoint lay inside the no-go zone;
- fired if a scenario had set `fire_at_will`;
- worked her guns through the drill, if she had a crew (and on a timer if
  she did not).

Nothing chose a target, judged the odds, closed, hauled off, kept station or
reacted to being hit. Every "tactic" in every scenario was a waypoint list
written by hand.

## 2. A captain is a parameter, not a difficulty setting

Every ship that is not yours now carries a `ShipCaptainAI` - his mind -
built from the person already generated for her captain, so his tactics come
out of the same skills and character as everything else aboard:

| Parameter | Built from | What it does |
|---|---|---|
| **skill** | navigation, seamanship, gunlaying | how well he handles her: the station he keeps (slack of 40 m at 1.0, 160 m at 0.0), whether he thinks to take the weather gage |
| **intelligence** | leadership, navigation, discipline | **how often he thinks at all**: his whole decision loop runs every 3 s at 1.0 and every 17 s at 0.0, so a dull captain is permanently a few seconds behind the action |
| **aggression** | bravery, ambition | how readily he closes, and the range he fights at: 420 m at 0.0, 90 m - yardarm to yardarm - at 1.0 |
| **caution** | timidity, lack of ambition | when he breaks off: how much damage and how many casualties he will take, and what odds he needs before he will fight at all |
| **discipline** | discipline | whether he obeys a signal he dislikes, and how long an order holds him before he reverts to his own judgement (60 s at 0.0, 360 s at 1.0) |

He thinks in terms of a **mission** - hold, station, engage, chase,
withdraw, close, heave to - and the mission is then carried out by setting
*the same orders a player sets*: helm, sail, quarters, fire at will, named
gun target. Nothing in here can do anything you could not do yourself.

What he knows comes from his own ship's `Contacts` - knowledge, not truth -
so he hunts the enemy he has actually seen, at the position he last saw her.

### His decisions, in order

1. A signal he has read, if any (see below).
2. Is he beaten about enough to haul off? Hull, casualties and the ship's
   morale, weighted by his caution and his dash.
3. Is an admiral's order still in force? Then hold to it.
4. What are the odds? `his guns x hull / hers`, against a threshold set by
   caution minus aggression. If they are against him and she is near, he
   withdraws.
5. Otherwise: engage what he can see; chase her if she is far off and he has
   any dash; else keep station.

### Carrying it out

Engaging is the interesting one. He steers for a **laying course** that
brings his broadside to bear at the range he likes: closing on a slant while
he is far off (on the weather side of her, if his skill is up to thinking of
it), edging away if he finds himself closer than he wanted, and lying
parallel when he is at his chosen range. Then fighting sail, quarters, fire
as they bear, and his guns given her as their named target.

## 3. Signals carry real orders

The signal book was already there - numbered flags, hoisting time,
legibility through fog and smoke, a reading delay set by the other ship's
best lookout. Now the numbers **mean** something to the captain who reads
them:

| No. | Signal | What her captain does |
|---|---|---|
| 1 | Engage the enemy more closely | +0.25 aggression, engage the nearest enemy he knows of |
| 2 | Form line of battle | take station 200 m astern of whoever made the signal |
| 3 | Make all sail | order every stitch set |
| 4 | Enemy in sight | nothing: his own lookouts will find her |
| 5 / 6 | Tack in succession / wear together | put the helm over the right way for the wind |
| 7 | Come within hail | close the signalling ship and stay there |
| 8 | Report your damage | **answers**, in the log, with her hull and her casualties, and hoists 12 or 8 in reply |
| 9 | Discontinue the action | haul off - if he will (see below) |
| 10 | Anchor | lie quiet |
| 11 | Prepare to board | +0.3 aggression, quarters, engage |
| 12 | Well done | the company feels it (an appraised event, `18` sec. 4) |

And the things that make it a *signalling* system rather than a menu:

- **It takes a man.** "Make signal number two" sends a hand - a midshipman
  for choice - to the locker; he bends the flags on and hoists them, and
  that takes him eight to twenty seconds depending on who he is.
- **It can be addressed** to one ship or to the squadron.
- **It can be misread.** The receiving ship's signal midshipman may read the
  number next to the right one - more often the duller he is and the thicker
  the day - and then her captain does the wrong thing, promptly and in good
  faith. This lost real battles.
- **It can be ignored.** A bold captain with a weak sense of discipline, in
  the thick of an action, will not answer the signal to discontinue: *"She
  does not answer the signal to discontinue."*
- **Orders expire.** An order holds a captain for a minute to six minutes
  depending on his discipline; after that he returns to his own judgement.
- **Only your own side answers.** The enemy can read your flags - he simply
  has no reason to obey them.

## 4. The player's side: the SIGNALS panel

`4` opens it; `TAB` to focus it; the arrows choose a signal, `a` changes who
it is addressed to, and `ENTER` makes it. The panel shows the book, what is
flying, who has answered, and - usefully - **your squadron with each
captain's parameters** (skill, wit, dash, obedience), what mission he is on,
and how long your last order still holds him.

The old way still works: walk to the signal locker yourself and use the
action menu.

## 5. What this is groundwork for

- **Fleet actions as the campaign's centrepiece:** line of battle, breaking
  the line, divisions with their own flag officers, repeating frigates.
- **A proper tactical vocabulary:** Popham's telegraphic code rather than
  twelve numbers, and compound signals ("No. 16, engage the enemy's rear").
- **Captains as people you know:** names, records, favourites and
  disappointments; a captain who has disobeyed before, and one you can trust
  with a detached squadron.
- **Admiralty orders** to you - a mission with a signal of its own.
- **Deeper tactics:** the weather gage as a deliberate choice, doubling on a
  ship, raking, cutting out, and knowing when to strike.
