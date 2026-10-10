# Life Aboard: the Day, the Weather, the Body and the Heart

Built 2026-10-01. Code: `sim/people/life.py` (watches, sleep, meals),
`sim/world/atmosphere.py` (rain and squalls), `sim/people/components.py` +
`sim/people/health.py` (the limb model), `sim/people/psyche.py` (feelings
and appraisal). Try it:

```bash
python -m broadside.scenarios run night_watch
```

## 1. The day aboard - built

A warship's company is divided into two watches, starboard and larboard,
and the day into four-hour watches with the two short dog watches that stop
the rotation repeating (`engine/clock.py`). That is now how the ship lives:

- **The watch bill.** Every hand is entered in one watch or the other; the
  idlers - the captain, the surgeon, the cook, the carpenter, the marines,
  the lookout - are left out of it, because they turn out when wanted
  rather than by rotation.
- **The watch below really goes below.** Off-watch men leave the weather
  deck entirely (they lose their `DeckPosition` and carry `Below`), and come
  up again when their watch is called. So the deck is thin at night and
  crowded at a change of watch, and if you want men at the guns in the
  middle watch you must turn them out.
- **Sleep.** Below in the dark, a man turns in. Sleeping pays off fatigue
  about six times as fast as working accrues it, which is what makes a
  four-and-four rotation survivable. By day, below, he rests at a third of
  that rate.
- **Beating to quarters overrides everything.** Every man turns out, asleep
  or not, at any hour - and then owes the sleep he did not get, which is why
  a night action ruined a crew for days.
- **Meals** are served at the proper hours - breakfast at eight, dinner at
  noon, supper at five - and they eat **real provisions out of the real
  casks** (`sim/people/life.serve_meal`). A well-found ship relieves her
  people's hunger and thirst and gains a little in spirits; a ship whose
  stores have run down serves short commons, and her people feel it as
  grievance. An empty ship cannot feed them at all.
- **Grog** at dinner and supper was already in; it now registers as
  contentment rather than a direct nudge to morale (see §4).

### Still to come

Hammocks as objects (piped up and stowed in the netting), the galley and
the cook actually cooking, watch-and-watch as a punishment, idlers' own
work, sick list and the surgeon's rounds, and the officers' own routine.

## 2. Weather - first cut

`Atmosphere` now carries `rain` and a squall:

- A squall comes up a few times a day at sea, lasts four to fifteen minutes,
  and brings a gust of 8-22 knots which the wind runs up to (`WindField.tick`
  takes the gust as a target, so it builds and falls away rather than
  jumping).
- Rain thickens the air: a downpour cuts visibility by three quarters. A
  squall can take you from a fifteen-mile horizon to half a mile.
- Men on deck in rain get wet: they tire faster and sour slightly.

### Still to come

Sea state and heel (`09_environment.md`), rain putting out slow match and
spoiling powder, reefing topsails before a squall strikes, a real wind field
rather than one global wind, and fog as weather rather than as placed banks.

## 3. The limb system

What is built now is the *skeleton* of it - deliberately, because the
surgeon is the next system and he needs something to work on.

A `BodyPart` is no longer one number. It carries:

| Field | Means | Consequence |
|---|---|---|
| `health` | tissue loss | the part's general usefulness |
| `fractured` | the bone is broken | almost no load (0.15) until `splinted` (0.45) |
| `artery_cut` | a vessel is open | it will **not** clot on its own; he bleeds out |
| `tendon_cut` | the tendons are severed | the limb holds but will not obey (0.25) |
| `tourniquet` | a ligature above the wound | bleeding stops in seconds; the limb's use falls to 0.3 and it begins to die |
| `splinted` | the bone held straight | it can knit |
| `missing` | carried away | nothing |
| `infection` | 0..1 | eats away at use; untreated it kills, days later |

`BodyPart.usable` folds those into one number, and **`Body.capability(what)`**
turns the parts into the six things a sailor actually does: `grip`, `reach`,
`stand`, `walk`, `see`, `speak`, taxed by pain and blood loss. Every task
asks for a capability rather than reading limbs itself - the gun drill's
`physique` is now three lines of `capability` calls, so a broken wrist, a cut
tendon and a tourniquet all slow a man down without the drill knowing what a
tendon is.

Wounds set the new fields: a deep wound in a well-supplied part opens an
artery; a deep wound in a limb has a good chance of cutting the tendons; a
severe one breaks the bone.

### The plan from here

1. **The surgeon as a person doing work.** The cockpit as a place, the
   wounded carried down, a queue, and operations that are `Activity`s with
   durations and failure: tourniquet (seconds), binding (a minute),
   extracting splinters, **amputation** (two minutes under three men
   holding him, and the stump either takes or does not).
2. **Infection and fever over days**, which is what actually killed people -
   with the surgeon's skill setting the odds, and a man who survives it
   either returning to duty, going on the sick list, or being invalided
   home.
3. **Pain and its remedies:** laudanum and rum dull pain and dull the man.
4. **Permanent consequences:** a man with one arm can still con a ship, be a
   cook, or be discharged. His `Biography` should say so, and his skills
   should be re-weighted to what he can still do.
5. **Scarring and recovery curves** rather than instant healing: bones knit
   in six weeks, tendons never quite.

## 4. Feelings, mood and morale

Three layers, deliberately separated, because they move at different speeds:

```
   events  ──appraise()──▶  feelings (seconds to an hour)
                                │
                                ▼
                            morale  (quarter-hour)  ──▶  mutiny risk
                                │
                                ▼
                 stress · anxiety · depression · grievance  (hours to weeks)
```

- **Feelings** (`Psyche.feelings`, with `EMOTIONS` giving each a fade time):
  fear fades in under a minute, anger in minutes, grief and pride over
  half an hour, hope and contentment over longer. They are added with
  **diminishing returns**, so the twentieth broadside does not make a man
  twenty times prouder.
- **`appraise(state, ent, event, weight)`** is the single way an event
  becomes a feeling, and **character decides how much**: a brave man fears
  less, a hot-tempered one angers faster, a resilient one shrugs off grief,
  an optimist takes more hope from the same event.
- **`Psyche.spirits`** is the balance of what a man feels now, and it feeds
  the morale target directly, so morale is moved *by feelings* rather than
  by events reaching in and nudging a number.

Hooked up so far: gunfire nearby, being struck by shot, a shipmate killed or
hurt in sight of you, your own broadside, your shot striking home, grog,
being fed, short commons, a soaking, a good sleep. Defined and waiting for
their systems: a flogging witnessed, a prize taken.

### The plan from here

1. **Discipline**: flogging, stopping grog, promotion - each an event with
   two edges (fear and order on one side, anger and grievance on the other).
2. **Relationships**: messmates, a particular friend, a hated officer, so
   "a shipmate killed" means *that* shipmate and the grief is not uniform.
3. **Memory**: events a man carries (he was at a famous action; he was
   flogged once; he saw a ship burn), which colour his appraisals.
4. **Ringleaders**: mutiny from the men with grievance, courage and
   leadership, not from a ship-wide number crossing a line.
5. **Expression**: what the player sees - men working sullenly, cheering a
   broadside, flinching, going quiet.
