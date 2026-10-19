# A Naval Primer for Broadside

A tutorial on the Napoleonic sailing warship: how she's built, how she sails, how she's commanded, and how she fights. Each section ends with **→ In the game**: what we simulate now and what's planned. It is written for designing the game, so it favours the mechanisms that matter over naval trivia. Figures are typical Royal Navy values c. 1795–1815. Refine specific numbers against sources when a system is built (`06_research_references.md`).

---

## 1. The ship

### Hull and decks

From the waterline up, a ship of the line has:

- **Hold** and **orlop:** stores, water, powder magazines (below the waterline, safe from shot), cables. The orlop is also the surgeon's **cockpit** in action.
- **Gundecks:** one (frigate), two (74s and most ships of the line), or three (first and second rates). They are covered decks with a row of gunports down each side. The **lower gundeck** carries the heaviest guns, because weight low keeps the ship stable. Its ports sit only ~1.5–2 m above the water, so in a heavy sea or a steep heel they may have to stay shut.
- **Weather deck:** open to the sky. It includes the **quarterdeck** aft (the captain's domain, with the wheel, lighter guns and carronades), the **forecastle** forward, and between them the **waist** (open over a big ship's upper gundeck, crossed by gangways).
- **Poop:** a short raised deck right aft on larger ships (signal flags, marines).

The **bow** faces forward and the **stern** aft. Facing forward, **starboard** is right and **larboard** (renamed "port" officially in 1844) is left. **Windward** is the side the wind comes from; **leeward** is the side it goes to.

### Rates

The Royal Navy classed ships by guns carried:

| Rate | Guns | Decks | Crew | Role |
|---|---|---|---|---|
| First | 100+ | 3 | ~850 | fleet flagship (HMS *Victory*) |
| Second | 90–98 | 3 | ~750 | line of battle |
| Third | 64–80 (mostly **74s**) | 2 | ~600 | backbone of the battle line |
| Fourth | 50–60 | 2 | ~350 | obsolescent; convoy, flagship on distant stations |
| Fifth | 32–44 (**frigates**) | 1 | ~250–300 | scouts, cruisers, commerce raiders, "eyes of the fleet" |
| Sixth | 20–28 | 1 | ~150–200 | small frigates, post ships |
| Unrated | sloops, brigs, cutters | 1 | 50–130 | dispatch, escort, patrol, a commander's first ship |

First to third rates were "fit to lie in the line of battle", hence **ship of the line**. Frigates didn't fight in the line; by convention a ship of the line didn't fire on a frigate in fleet action unless fired on first.

### Masts, sails and rigging

A **ship-rigged** vessel has three masts (**fore**, **main**, **mizzen**), each built in sections: lower mast, topmast, topgallant mast. Each carries square sails on **yards**, bottom to top:

- **course** (the big lowest sail: fore course, main course; the mizzen's, the *crossjack*, was rarely set),
- **topsail** (the working sail, set in nearly all weather and reefed as wind rises),
- **topgallant**,
- **royal** (light weather).

There are also **fore-and-aft** sails: **jibs** and **staysails** on the stays forward and between masts, and the **spanker** (driver) on the mizzen, which helps steering. A **brig** has two masts (no mizzen). A **cutter** or **schooner** is fore-and-aft rigged: more weatherly, but needs more skill per sail and is less powerful downwind.

**Standing rigging** (shrouds, stays, backstays) holds the masts up. Shoot it away and masts fall. **Running rigging** works the sails: **braces** swing the yards round, **sheets** and **tacks** hold the sail's lower corners, **halyards** hoist the yards, **clewlines** and **buntlines** gather a sail up to furl it. Shot-away running rigging means sails flap uselessly until spliced.

**→ In the game.** Ships are generated from class data (`sim/data/ships/*.yaml`) into 1 m weather-deck plans. Covered gundecks exist as abstract batteries: they fire and smoke, but their crews aren't drawn. Rigs: ship (3 masts) and brig (2). The sail setting is a single value mapped to named sails: topsails, then courses, topgallants, royals. Classes so far: sloop, brig, frigate, 74, first rate. **Planned (Phase 1):** each sail and each piece of rigging as its own damageable, repairable object; multiple decks.

---

## 2. How a square-rigger sails

### Points of sail

The angle between the wind and the ship's head is everything:

- **In irons / taken aback:** heading into the wind. Sails flatten or press backward, the ship stops, even gathers sternway, and won't steer. It's a real danger mid-manoeuvre.
- **Close-hauled ("on a wind", "by the wind"):** as close as she'll go. For a square-rigger that is about **6 points (67°)** off the wind, with considerable **leeway** (sideways slip).
- **Wind abeam / reaching:** fast and comfortable.
- **Large / wind on the quarter:** usually the fastest point for a square-rigger.
- **Before the wind / running:** dead downwind. Surprisingly not the fastest, because the after sails blanket the forward ones, and the ship rolls heavily.

### Changing tack

To get to windward you zigzag, **tacking** from one tack to the other. There are two ways to turn:

- **Tacking ("going about"):** turn the bow *through* the wind. It is quick and loses little ground, but needs way on and a practised crew. Misjudge it and she **misses stays** and falls back, or hangs **in irons**. Orders: *"Ready about!" – "Helm's a-lee!" – "Rise tacks and sheets!" – "Mainsail haul!"* (the main and mizzen yards swung round as she passes head to wind) *– "Let go and haul!"* (the fore yards follow).
- **Wearing:** turn the *stern* through the wind, the long way round. It is slower and loses ground to leeward, but it is safe in heavy weather or with damaged rigging, and it never fails.

Other manoeuvres worth modelling: **heaving to** (back the main topsail against the fore so the ship lies nearly stopped: waiting, lowering boats, speaking another ship); **reefing** (shortening a topsail by tying down a band of it as wind rises); **boxhauling** and **club-hauling** (emergency turns using backed sails or an anchor off a lee shore).

### The lee shore

Wind blowing toward land, and you can't point high enough to claw off. It was the sailing navy's great killer, more lethal than enemy fleets. A captain's first seamanship duty was **sea room**.

**→ In the game.** A polar speed curve with an irons zone, and speed inertia so a tack costs way. The helm turns at a rate that depends on speed. Waypoint steering beats to windward automatically. Yards are braced to the wind, with the leeward yardarm aft. **Tuning note:** the helm's close-hauled limit is 55°, generous against the historical ~67°. **Planned (Phase 1):** tacking and wearing as timed crew evolutions that can fail (missing stays, in irons); leeway; heave-to; reefing.

---

## 3. Command: who's who and how orders flow

### The people

- **Captain:** absolute authority. Handles the ship in action from the quarterdeck.
- **Lieutenants:** the first lieutenant runs the ship day to day (discipline, the station bills). Others keep watches and command gun decks in action.
- **Master:** the navigation and sailing expert, a warrant officer. Our "navigator" to question later.
- **Midshipmen:** officers in training. They carry orders, command gun sections, lead boats.
- **Warrant officers:** the **boatswain** (rigging, sails, anchors, discipline "pipes"), **gunner** (guns, powder), **carpenter** (hull, masts, pumps, shot-plugs in action), **purser** (stores), **surgeon**.
- **Petty officers:** **quartermasters** (helm and conning), **boatswain's mates**, **gun captains**, **captains of the tops**.
- **Seamen:** able seamen (can "hand, reef and steer"), ordinary seamen, landsmen (new hands, often pressed), boys. Plus **Royal Marines** (musketry, boarding, sentries, hauling).

### The organisation

- **Watches:** the crew is split into two watches, **larboard** and **starboard**, alternating four-hour watches. The **dog watches** (16–18, 18–20) shift the cycle each day. Bells mark each half hour.
- **Divisions:** groups under a lieutenant, for welfare and inspection.
- **The station bills:** every man has an assigned place for every evolution: tacking, reefing, anchoring, fire, boarding, and **quarters** (his gun or post in action). This is exactly what makes a practised crew fast: nobody wonders where to go.

### Orders

Orders flow captain → officer of the watch → boatswain's call and mates → the men. Typical helm and sail orders:

- **Helm orders** referred to the **tiller**, the reverse of modern usage. "Port the helm" (tiller to larboard) turned the ship to starboard. "Up helm" (tiller to windward) bore away from the wind, "down helm" / "helm a-lee" luffed toward it. *"Steady"* and *"Nothing off"* held her. *"Keep her full"* or *"Full and by"* meant sail as close as possible with the sails still drawing.
- **Sail orders:** *"Hands to make sail", "Let fall", "Sheet home", "Hoist away", "Brace up/in/round", "Square the yards", "Clew up", "Furl", "Reef topsails", "Shorten sail"*.
- **Action:** *"Beat to quarters"* (drums; the ship **clears for action**: bulkheads struck down, sand scattered for grip, nets rigged against falling spars, boats streamed astern, the galley fire put out). Then *"Run out the guns", "Fire as they bear"*, or a full broadside on command, *"Cease fire"*, *"Boarders away!"*, *"Strike the colours"* (surrender).

**→ In the game.** Crew entities with names and roles; the captain and masthead lookout as observers; watches and bells in the clock. **Beat to quarters** assigns stations from a quarter bill (gun crews, helm, sail posts) and hands walk there along real deck paths, so clearing for action takes time. Planning mode lets you give orders with time stopped. **Planned (Phase 1):** officers and warrant officers as real people with skills; watches deciding who's on deck; station bills per evolution; orders given in period language through an orders menu, and executed at a speed and reliability set by the crew.

---

## 4. Gunnery

### The guns

- **Long guns**, rated by shot weight: 32-pounders on the lower gundeck of a ship of the line; 24s and 18s on upper decks and on frigates; 12s and 9s on quarterdecks. A 32-pounder weighs ~2.75 tons, needs a crew of **~12–14 men** (often shared between opposite guns when only one side is engaged), and is effective to ~1,000 m, decisive at a few hundred.
- **Carronades:** short, light, large-bore "smashers" (18- to 68-pounders), needing few crew. They are devastating at close range and useless at long range. Ships armed mostly with carronades (like our 18-gun sloop) had to close to fight.

### The drill

Worm (clear debris) → **sponge** (put out embers) → **cartridge** (powder bag) → wad → **shot** → wad → **ram** → **run out** (haul the gun up to the port) → **prime** (by the late 1790s often a flintlock gunlock) → **point** (train with handspikes, elevate with the quoin) → **fire** → the gun recoils inboard against its breeching. A well-drilled British crew managed about **one round every 90 seconds** in sustained action, faster in the first rounds. Green crews were far slower. That rate difference won battles.

### Shot

- **Round shot:** smashes hulls, dismounts guns, and throws **splinters**, the main killer on a gundeck.
- **Double-shotting:** two balls at close range for heavy damage; hard on the gun.
- **Chain and bar shot:** spinning pairs that cut rigging and sails, to disable a ship or stop her escaping.
- **Grape and canister:** clusters of small balls against men on open decks, for anti-boarding and clearing a quarterdeck.
- **Heated shot:** shore batteries only; sets ships on fire. It is why "a ship is a fool to fight a fort".

### Aiming and the roll

A ship rolls, and gunners timed their shots to it. On the **down-roll** the shot goes low, into the hull. On the **up-roll** it goes high, into the rigging. British doctrine favoured hulling: kill men, dismount guns, force a surrender. French practice is often characterised as aiming high to cripple the enemy's rigging and escape or manoeuvre.

**Raking** is firing through the enemy's bow or stern along her length. Every shot travels the whole deck, and she can't reply because her guns point sideways. The **stern** is the weakest point: glass windows and light timbers. Crossing an enemy's stern and raking her was the single most decisive move in a ship duel.

**→ In the game.** Guns with deck positions and outboard aim, reloading only while manned (2–4 crew in our simplification), rippling broadsides, muzzle flashes and real drifting smoke. No shot yet. **Planned (Phase 2):** ballistic shot with calibre, range, spread and roll timing; ammunition types; hull, rigging and crew damage resolved against the actual deck plan and the actual sailors standing there; splinters; raking geometry emerging naturally from where the ships actually are.

---

## 5. Tactics

### Single-ship actions (frigate duels)

- **The gage.** From the **weather gage** (to windward) you choose when to close and how. Your smoke blows onto the enemy, blinding her (you can watch this in `broadside_smoke`), and your heel toward her points your guns down into her hull. From the **lee gage** you can always run away downwind, your heel points your guns high (rigging shots), and your lee lower ports may stay shut in a breeze.
- **Manoeuvre to rake**, avoid being raked, and cripple her rigging so she can't manoeuvre.
- **Close action.** Nelson: *"No captain can do very wrong if he places his ship alongside that of an enemy."* British crews' rate of fire told best at short range.
- **Chasing.** "A stern chase is a long chase". Bow and stern chaser guns, lightening ship (pumping water, jettisoning stores) to gain speed, chasing into the night.
- **Boarding.** Grapnels, "Boarders away!", marines' musketry from the tops, cutlass and pike. Usually decided by numbers and morale.
- **Striking colours.** A beaten ship surrendered by hauling down her flag. The victor put a **prize crew** aboard, and prizes meant **prize money**, a huge motive.

### Fleet actions

- **The line of battle.** Ships in line ahead, one behind the other, so every broadside bears and none masks another. The Admiralty's *Fighting Instructions* long made it doctrine, which often produced indecisive parallel fights.
- **Breaking the line.** Cutting through the enemy line lets you rake ships as you pass and fight part of their fleet with all of yours (the Saintes 1782, the Glorious First of June 1794, Camperdown 1797). **Trafalgar** (1805) did it with two columns driving perpendicular into the Franco-Spanish line: very risky while approaching (you can't reply bow-on), decisive once in.
- **Signals.** Flags, with **Popham's** telegraphic code (1803) allowing whole words. "England expects..." was sent in Popham's code. **Repeating frigates** stood out of the line to relay the admiral's signals down it, because smoke and distance hid the flagship. The fleet channel, and the constraint behind Phase 3.

**→ In the game.** The vision and smoke model already gives the weather gage its real bite: smoke drifts downwind onto the leeward ship. The `fleet_action` scenario sets up two lines and a repeating frigate. **Planned:** AI captains with gage-aware goals (Phase 2); semaphore with real range, weather and smoke limits over the same line-of-sight engine (Phase 3).

---

## 6. Designing a ship

What naval architects of the period traded against each other. It is also the menu for a ship-design system in the game.

| Choice | Buys | Costs |
|---|---|---|
| **Length** | More guns per deck, higher top speed (hull speed ∝ √length), steadier | Wooden hulls **hog** (sag at the ends) beyond ~60 m; slower to turn and tack; costlier; needs more crew |
| **Beam** | Stability ("stiffness") to carry sail and heavy guns high; room inboard for guns to recoil and be worked | Drag; wider = slower for the same length |
| **Depth of hold / draught** | Stores (months of provisions and water), grip on the water (less leeway, more weatherly) | Can't enter shallow harbours or approach coasts; grounds sooner |
| **Freeboard / lower-port height** | Lower gundeck usable in a seaway; drier | Weight and windage high up |
| **Armament** | Weight of broadside; long guns for range, carronades for close punch | Gun weight high up reduces stability; each long gun needs ~12 men who must be fed |
| **Rig** | Ship: power, redundancy, handles well in all conditions. Brig: cheaper, fewer men. Fore-and-aft: closer-winded | Handiness vs power vs crew vs repairability far from a dockyard |
| **Scantlings** (hull thickness) | Resistance to shot (a 74's sides stopped much 18-pounder fire) | Weight, cost, speed |
| **Copper sheathing** (standard from the 1780s) | Keeps weed and worm off: much faster over a long commission | Cost; needs dockyard work to maintain |

**The core triangle is firepower vs speed vs endurance**, with stability as the hidden constraint that ties them together. A ship that carries too much weight high is **crank**: she heels too far, can't open her lee ports, and may capsize in a squall. A very **stiff** ship rolls fast and violently, which is bad for gunnery and strains the masts. French designs were often faster and finer-lined; British ships were more heavily built, tougher and slower. Both navies prized captured ships and often copied them.

A useful period quantity is **Builder's Old Measurement tonnage** (a volume estimate, not weight): `(L − 3/5·B) × B × B/2 / 94`, with length L and beam B in feet. It already appears in our data files.

**→ In the game.** The parametric deck-plan generator (length, beam, guns, rig → 1 m plan) is the seed of a designer. Proposed direction, for discussion:

1. **Historical classes first** (as now), each a data file. The generator makes the deck, and hand-authored ASCII plans can override it where a famous ship deserves it.
2. **Derived characteristics** computed from the parameters rather than typed in: hull speed, stability/stiffness (from beam, freeboard and gun weight aloft), roll period, gunport height, stores capacity, crew required.
3. **A shipyard/refit screen** later in the campaign: re-arm (swap long guns for carronades), change rig, re-copper. Every change feeds back through the same derived numbers, so a refit has real trade-offs you *feel* at sea.
4. **Full ship design** (draw your own hull) only if you want it. It's big, and the historical classes may carry the fantasy better.

---

## Questions for you on ship design

1. **Curated or free-form?** Historical classes with refit choices, or a full designer where you set length, beam, decks, rig and guns?
2. **Multiple decks in the ship pane?** Should the view let you step down to the gundecks (DF z-levels: see the lower-deck gun crews in action, the orlop and the surgeon), or stay on the weather deck?
3. **How deep for rigging?** Individual named sails and lines that part and get spliced, or "sails & rigging" per mast?
4. **Crew scale.** A first rate has ~820 men. We can simulate all of them (performance is fine with care). Should every one of them be a named, individual person?
