# Environment: Wind, Water and Weather

This is the proposal for the next major piece of work: the physical environment ships sail in. For each element it covers what it is and why it mattered to a Napoleonic captain, what we simulate today, and what to build, in what order. The Mediterranean specifics are noted because they differ sharply from the Atlantic and Channel of most naval fiction.

**The organising idea** is one environment query, the same shape as the vision engine's `SceneQuery`: `environment.sample(xs, ys, t)` returns wind, current, depth, tide and sea state at any points and any time. Every system (sailing, drift, grounding, smoke, gunnery, crew comfort) asks it, and every view can draw it. Whatever the resolution, the answer agrees with itself.

## 1. Wind

**Why it matters.** Wind is the engine, the steering constraint and the battlefield geometry all at once. A square-rigger can point no closer than about **6 points (67°)** to the true wind. She has to tack or wear to make ground to windward, and she is fastest with the wind on the quarter. Whoever is to windward (the **weather gage**) chooses whether and how to engage.

**Today.** A single global wind (`sim/systems/wind.py`) that wanders around a mean by a drift-and-noise process. Sailing uses a polar curve. Smoke and fog drift with it. Yards are braced to it.

**To build:**

| Feature | What it adds | Notes |
|---|---|---|
| **Wind field** | Direction and speed vary across the map: a coarse grid (≈2–5 km cells) evolving smoothly, sampled bilinearly. | `WindField.sample(x, y)`; the docstring already anticipates it. |
| **Apparent wind** | The wind the ship feels is true wind minus her own velocity. It drives the pennant, sail trim and the smoke's drift relative to the deck. | Cheap; improves realism of the pennant and the fire-ship/smoke tactics. |
| **Gusts and squalls** | Short, local high-wind cells, visible as dark patches on the water and a rain curtain. They are dangerous with too much sail set: sails split, spars carry away, a ship can be laid on her beam ends. | A real seamanship test: shorten sail when a squall is sighted. Squalls also cut visibility, which ties to vision. |
| **Wind shadow** | Islands, cliffs and **other ships** block the wind downwind of them. A ship to windward "takes the wind out of" one close to leeward, a real close-action tactic. | Reuse the vision engine's obstruction fields: sample upwind along the wind vector. The same code, pointed another way. |
| **Funnelling and coastal effects** | Straits and valleys accelerate wind (the Levanter and Poniente at Gibraltar; the Mistral out of the Rhône valley). There are calms under high coasts, and land and sea breezes on a daily cycle (onshore by day, offshore by night) near coasts. | Terrain-aware modifier on the field. |
| **Regional winds** | Named Mediterranean winds as recurring weather patterns (`04_world_campaign.md`): the **Mistral** (N/NW, cold, violent, Gulf of Lion), **Tramontane**, **Bora** (NE, Adriatic, sudden and violent), **Sirocco** (SE/S off Africa, hot, humid, hazy: reduces visibility!), **Levanter** (E, Strait of Gibraltar, often with cloud and fog), **Meltemi/Etesians** (N, Aegean, summer, steady and strong), **Libeccio** (SW), **Gregale** (NE, winter). | Each is a pattern that biases the field for days. The Sirocco's haze and the Levanter's fog feed straight into the vision engine. |
| **Veering and backing** | Wind shifts clockwise (veering) or anticlockwise (backing) as weather systems pass. A shift can turn a lee position into a weather gage mid-battle. | Emerges from the field's evolution. |

**Gameplay hooks:** heel angle from wind pressure and sail area. In strong winds (about force 6+) the **lee lower-deck gunports can't be opened** without shipping water, so a heavily heeled ship may lose her lowest battery on one side. This is a real, decisive factor, and it follows directly from wind + sail + hull (freeboard of the lower ports; see ship design).

## 2. Sea state

**Why it matters.** Waves make a ship roll and pitch, and that is what decides gunnery accuracy. British practice favoured firing on the *down-roll* into the hull; the French are often described as firing on the *up-roll* into the rigging. Motion also affects boat work, boarding, seasickness among green hands, water shipped through ports, and structural strain.

**To build:**
- **Wind-sea** grows with wind speed, duration and **fetch** (open water upwind). It is short and steep in the enclosed Mediterranean compared with the Atlantic, and dies quickly when the wind drops. **Swell** is long-period and outlasts the wind that raised it, and can come from a different direction.
- **Ship motion:** roll period depends on beam and stability (a "stiff" ship snaps back quickly, a "crank" one rolls slowly and deeply), pitch on length. The phase of the roll is simulated, so a gun captain can wait for the roll, and a skilled one fires at the right moment. This feeds Phase 2 gunnery directly.
- **Rendering:** wave glyph density and animation driven by sea state and direction. The sea already animates with the wind; it becomes honest.

## 3. Tides

**The Mediterranean is almost tideless.** The range is typically only 20–40 cm, because the narrow Strait of Gibraltar throttles the Atlantic tide. The exceptions are the **Gulf of Gabès** (Tunisia, up to ~2 m) and the **northern Adriatic** (~1 m at Venice). Tidal *height* matters to us only for running aground in those places and for entering shallow harbours.

What *does* matter are **tidal streams in straits**:
- **Strait of Messina:** strong reversing tidal currents (a few knots) and eddies, the origin of Scylla and Charybdis. It is a genuine navigational hazard for a sailing ship.
- **Strait of Gibraltar:** a permanent **eastward surface inflow** of Atlantic water (~1–2 knots) with tidal streams on top. Beating out of the Mediterranean westward against wind and current was notoriously hard.
- **Dardanelles and Bosporus:** a steady **outflow** toward the Aegean (1–3 knots and more in the narrows), which made entering the Dardanelles under sail a real problem. The British forced it only in 1807, with a fair wind.

**To build:** a tide model (lunar semidiurnal cycle, M2 ≈ 12.42 h) scaled by a per-region amplitude map for heights, plus tidal-stream components on the current field in the few straits where they matter. If the game ever leaves the Mediterranean, the same model scales up to the Channel's 6–12 m tides.

## 4. Currents

**Why it matters.** Current carries a ship bodily. Her course and speed through the water differ from her track over the ground (**set and drift**), which is what makes dead reckoning drift from reality and leads ships onto shoals at night. It also changes who can reach whom in a chase.

**The Mediterranean circulation** is weak (generally ≤ 0.5 knot) and broadly anticlockwise along the coasts: the Atlantic inflow runs east along North Africa, then north and west around the basin's rim. It is stronger in the straits (above).

**To build:** a current field (static background + tidal components) added to ship velocity in `movement_system`, and to smoke and fog drift near the surface. It is invisible in the ship pane (the water "looks the same"), but the chart can show set and drift once navigation exists: the ship's reckoning versus her true position.

## 5. Depth, bottom and anchoring

**Why it matters.** Running aground is the classic catastrophe (a **lee shore**, with wind blowing onto rocks and no room to claw off, killed more ships than enemies did). Anchoring holds position for blockade, repairs, or waiting out a foul wind. Depth also decides where a battle can happen: Nelson's attack at the Nile (1798) went *inshore* of the anchored French line, where they hadn't expected water deep enough.

**Today.** Terrain has shoal, reef and rock codes and grounding stops a ship. There is no true depth number.

**To build:**
- A **depth** value from terrain (continuous: shelf and slope away from coasts), compared against each ship's **draught** from its class data.
- **Bottom type** (sand, mud, rock, weed) → **holding ground** for anchors.
- **Anchoring:** depth-limited by cable (a ship of the line's cable was ~100–120 fathoms / ~200 m; you want roughly 3–5× the depth in scope). An anchored ship swings to wind and tide, can drag in a gale, and **springs on the cable** to turn her broadside at anchor (Nile, Copenhagen).
- **The lead line** as the crew's sounding report (see `08_interface.md`): depth becomes knowledge, not truth, just like contacts.

## 6. Visibility, light and weather - a field, built

Weather is **a field over the sea**, not a dice roll (`sim/world/weather.py`).
It is a continuous function of place and time, so the same patch of sea
behaves the same way tomorrow, and bad weather is something you can see
coming. Three scales lie over each other:

| Scale | What it is | What it does |
|---|---|---|
| ~70 km | how **unsettled** this stretch of sea is, and how **damp** the quarter | a stormy region; a quarter that holds mist |
| ~3 km | the **clouds**, drifting downwind a little faster than you can sail | cover, their shadows, and rain under the thick ones |
| ~500 m | the **puffs** inside a breeze | gusts and lulls |

- **Cloud shadows** are drawn: the view asks `Atmosphere.light_at(xs, ys)`
  per cell, so patches of shade drift over the water on the chart and on
  the deck. It is a slight drop in light - about a quarter at most - never
  a blackout.
- **Rain** forms where the cloud is thick and the air unsettled, and cuts
  visibility by up to three quarters. A downpour takes you from a
  fifteen-mile horizon to under a mile.
- **Fog** forms in damp quarters when the wind is light, and a breeze blows
  it away: at sea it shows as a shortening horizon on the chart and a
  general haziness on the deck. (Discrete, drifting `FogBank`s remain for
  scenarios that want a wall of it rolling down on you.)
- **Squalls** can still be put on deliberately by a scenario, and then
  override the background: wind up, rain on, horizon in.
- The log tells you: "It comes on to rain", "Mist gathering - the horizon
  is closing in", "The mist thins and lifts", and the status strip and the
  log-board carry the weather in the officer of the watch's own words
  ("fair, some cloud", "overcast", "heavy rain", "thick fog").

Still to come here: the wind *field* proper (so the weather pattern and the
wind agree, and there is a lee under the land), sea state and spray, rain
spoiling powder and slow match, and the barometer - which a captain had, and
which is how he saw a blow coming.

## Data model sketch

```python
@dataclass
class EnvSample:            # all arrays, one entry per sample point
    wind_from: ndarray      # degrees
    wind_kn: ndarray        # including gusts
    current_vx: ndarray     # m/s, east
    current_vy: ndarray     # m/s, north
    depth_m: ndarray        # at current tide
    bottom: ndarray         # code: sand / mud / rock / weed
    wave_h_m: ndarray       # significant wave height (wind-sea + swell)
    wave_period_s: ndarray
    wave_from: ndarray

class Environment:
    def sample(self, xs, ys, t) -> EnvSample: ...
    def tick(self, dt): ...  # evolve wind field, squalls, weather systems
```

It lives beside `Terrain` and `Atmosphere` in `sim/world/`, and is deterministic from the campaign seed.

## Proposed order

1. **Wind field + apparent wind + squalls.** This has the biggest gameplay effect and reuses the existing drift machinery.
2. **Wind shadow** of islands and ships (reuses the vision obstruction fields).
3. **Heel + sea state + ship roll.** This unlocks gunnery accuracy and lower-port closure for Phase 2.
4. **Depth & anchoring** (+ lead line).
5. **Currents + tidal streams in straits** (pairs with navigation in Phase 4).
6. **Sun, moon, seasons and weather systems.**

Each lands with its own test scenarios, as in engine v1: e.g. "a squall line comes down on an over-canvassed frigate", "blanketed by the enemy to windward", "beating out of the Strait against the inflow".

## Questions for you

1. **How hard should seamanship be?** Realistically, carrying too much sail into a squall springs masts and can capsize. Should that be possible (Dwarf-Fortress "losing is fun"), or should the crew or first lieutenant warn and act?
2. **How visible should the invisible be?** Currents and wind shadows can't be seen. Should the chart show them (as a navigator's knowledge), or should you only infer them from the ship's behaviour and the log?
3. **Time compression.** Tides and weather work on hours and days. Are you comfortable with passages being fast-forwarded (up to 16× now, more later), with battles in real time?
