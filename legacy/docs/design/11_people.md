# People

Every sailor, officer and marine on every ship, friendly, enemy and neutral, is an individual with the same depth of data, Dwarf-Fortress style. This covers what that data is, how it's generated so each person has a story, and how it drives behaviour. Code: `src/broadside/sim/people/`.

**Status: groundwork.** The data model, generation, the body/blood model, the psyche model and ship morale are built and run in every scene. Behaviours that *use* them are partly built: skill already decides roles and melee, blood and wounds decide death, fear comes from nearby gunfire. Much more is to come (see the end).

## Who is aboard

A ship's **whole establishment** is generated, not just the hands on deck: a sloop's 121, a 74's 590, a first rate's 821. People on the weather deck are placed on tiles, pathfind and work. Everyone else carries a `Below` marker: fully simulated (needs, psyche, body, story), just not drawn until the lower decks get their own view. The fleet scenario holds ~23,700 entities (twelve 74s' companies plus their stores) and still simulates ~8× faster than real time.

## The data (components)

| Component | Holds | Notes |
|---|---|---|
| `Identity` | given and family name, nickname, **culture**, **nation**, birth year, **birthplace**, background, rank | The nation's culture supplies ~70% of a crew; the rest is a period-typical mix (Celtic, Nordic, Italic, Iberian, Hellenic, Gallic) |
| `Personality` | bravery, temper, sociability, discipline, ambition, honesty, optimism, resilience | Stable traits, 0..1 around 0.5, shifted by background |
| `Psyche` | **morale**, **stress**, **anxiety**, **depression**, **confidence**, **fear**, **grievance** | Move over seconds (fear) to weeks (grievance) |
| `Allegiance` | devotion to **nation**, **cause** (the war), **captain**, **ship** | Foreign-born and pressed men start low |
| `Cravings` | **drink dependence** (trait), current drink need, tobacco | The grog ration (dinner and supper) relieves it |
| `Skills` | proficiency 0..1 in **every shipboard role**: seamanship, topwork, helm, gunnery, gunlaying, musketry, melee, carpentry, sailmaking, rigging, cooking, medicine, navigation, leadership, lookout | Grow with years at sea along the lines his life used, plus one specialism |
| `Body` | 12 parts (head, neck, chest, abdomen, arms, hands, legs, feet), each with health, bleeding, fracture, missing, infection, wounds; **blood volume**, **heart rate**, pain, consciousness | See *Body and death* |
| `Biography` | dated events, from birth to now | Written at generation (including **battles from world history**) and by the simulation (wounds, death) |

Presentation: the look cursor shows a two-line brief (origin, background, condition, pulse, state of mind). `view/people_view.person_sheet()` produces the full sheet (character, devotion, drink, best skills, wounds, story), ready for a roster screen.

## Generation: giving each man a story

A person is generated from a **background**, which drives everything else coherently:

| Background | Typically | Why he's here |
|---|---|---|
| career man-of-war's man | skilled, disciplined, loyal to ship | volunteered for the navy |
| merchant seaman | expert seaman, low devotion to the cause | pressed out of a merchantman |
| pressed landsman | green, anxious, resentful | taken by the press gang |
| volunteer landsman | green, keen | the bounty |
| fisherman | handy, sharp-eyed | pressed from the fishing fleet |
| quota man | green, light-fingered, resentful, drinks | sent by the magistrates in lieu of gaol |
| ship's boy, marine, tradesman, foreign seaman, officer | ... | ... |

The mix follows a period ship's company. Age sets years at sea, which sets skill. Traits are drawn around background means. Devotion follows background, discipline and nationality. Drink dependence follows background. The biography records birth, first going to sea, how he came aboard, old wounds, floggings for drunkenness, and **battles he fought in**, drawn from the generated world's actual history if his years at sea cover them. Nicknames come from extreme traits ("Grog" Winlock, "Lionheart" Dray). **Roles are then assigned by skill**, in period quarter-bill proportions: the best gun-layers become gun captains, the best helmsmen quartermaster's mates, and so on.

You name your captain, ship and nation (`CampaignSetup`). Everyone else is generated.

## Body and death

Death is measured by **blood** and the **heartbeat**, as you suggested:

- An adult has ~5 litres (boys less). Each wound bleeds at a rate set by the part (neck and chest fast, hands slow) and its severity. Minor bleeding **clots** within minutes; arterial bleeding barely slows.
- The heart rate rises as blood is lost (the body fighting to keep pressure up), and with fear and pain.
- **~33% loss: collapse** (unconscious). **~45%: the heart stops.** Destroying a vital part (head, neck, chest) kills outright. A limb can be carried away.
- Only people with an `Injured` marker are ticked, so a healthy crew costs nothing.
- A surgeon (Phase 1) will act on these same numbers: tourniquets stop bleeding, amputation trades a limb for a life, infection sets in over days.

## Psyche

Each state relaxes toward a target set by circumstances and character, at its own pace:

- **Fear**, in seconds: gunfire within 400 m, scaled by bravery and confidence.
- **Stress**, over minutes: fatigue, hunger, drink craving × dependence, fear, grievance, pain. Resilience changes how fast it builds.
- **Anxiety**, over the hour: sustained stress in a brittle man.
- **Depression**, over days: stress, grievance, pessimism.
- **Morale**: devotion, optimism and confidence, against stress, depression and grievance.
- **The grog ration** at dinner and supper relieves drink need and lifts morale. Stopping grog is a real lever, and a gamble.

The existing Phase 0 `Mood` is now driven by the psyche for these people.

## Ship morale and mutiny

`ShipMorale` aggregates the company every second: morale, stress, grievance, devotion to the captain, drink need, living, dead and injured, and a **mutiny risk** (0..1) that rises with grievance, low morale, low devotion to the captain and unmet drink. It isn't a scripted trigger. It's a pressure for Phase 1's discipline system (flogging, stopping grog, promotions, prize money, the captain's leadership skill) and for crew agents (ringleaders, sullen refusals, desertion in port) to act on.

## What uses this now, and next

- **Now:** roles by skill; melee skill decides blows in boarding fights; wounds, bleeding and death; fear from gunfire; grog; morale; the look readout.
- **Next (Phase 1):** skill sets task speed and quality (reload speed from gunnery, sail-handling speed from topwork, the lookout's *eyesight* setting how far he sees); watches and fatigue with sleep; the surgeon; discipline actions and their morale effects; relationships (messmates, grudges); memories of events feeding back into psyche (seeing a messmate killed); desertion and mutiny events; promotion and succession (the next captain is a simulated officer).

## Questions

1. **Drink as coping:** should heavily dependent men sneak drink (theft from the spirit room, drunk at quarters) when their need is high? This is period-accurate and a nice emergent source of trouble.
2. **Faith:** you said religion isn't needed. The period had chaplains aboard larger ships, and superstition was universal at sea (Friday sailings, whistling up a wind). Should it be a light *superstition* trait instead of faith?
3. **Women and non-combatants:** some ships carried a few (warrant officers' wives, powder carriers in action). Include them?
