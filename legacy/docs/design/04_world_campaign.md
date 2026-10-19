# World Generation & Campaign

## World generation: a Mediterranean-like theatre

The brief asks for "a variation of a Mediterranean-like area" rather than the real, exact Mediterranean — so generation should produce a plausible sea of similar character (many indented shorelines, islands, straits, and a mix of deep basins and shallow coastal shelves) without needing to be historically literal.

**Pipeline (each stage a swappable module, so any one can be improved independently):**

1. **Base heightmap.** Layered simplex/Perlin noise (domain-warped, so coastlines look organic rather than like raw noise contours) produces a continuous elevation field over the campaign area. A tunable sea-level threshold splits land from sea.
2. **Coastline extraction & cleanup.** Contour the land/sea boundary, then clean up (remove single-cell islands/lakes below a size threshold, or deliberately keep some as tiny reefs/skerries — a period hazard) to get a coherent coastline suitable for gameplay.
3. **Depth field.** Depth is derived from how far below sea level the underlying heightmap is, smoothed, and separately seeded with a small amount of shelf/shoal noise near coasts, because gameplay cares more about "is this a dangerous shoal near a headland" than about abyssal depth.
4. **Currents & regional wind bias.** A coarse current field (mostly relevant near straits and coastlines) and the named regional wind systems from `02_simulation_systems.md` (Mistral, Meltemi, Sirocco, land/sea breeze) are assigned to regions based on coastline geometry (e.g. a Mistral-analogue channelled through a generated mountain-flanked gulf).
5. **Settlement placement.** Ports/cities are placed at coastline sites scored by natural-harbour quality (sheltered inlets score higher than exposed straight coast) and strategic value (control of a strait, proximity to trade routes), then sized/typed (fishing village up to a major naval dockyard) partly by that score and partly by a controlling faction's investment.
6. **Political layer.** The generated coastline is divided among a small number of factions (analogous to the real theatre's major and minor Mediterranean naval powers of the period) with territory, home ports, and a relationship state (war/peace/uneasy) to the player's nation — this is what actually produces "enemy fleets" and "enemy fortresses" to encounter, rather than those being scripted per-scenario.
7. **Seeded and deterministic.** The whole pipeline takes a single integer seed (via `engine/rng.py`) and is reproducible from it — a campaign is, at the storage level, mostly "the seed plus the log of what's happened since."

This is intentionally the most deferred subsystem in the roadmap (Phase 4+) because everything else — ship, crew, combat — can be built and validated on one or two small hand-authored maps first; procedural generation is worth doing once the thing it's generating content *for* already works.

## The campaign layer

**Structure.** The player starts in command of a single small vessel (a sloop or similar) under a home-nation flag within the generated theatre, with orders, a home port, and a small set of nearby objectives (patrol, escort, a specific enemy vessel or fortress reported in the area) that expand into a looser open campaign as the player's rank and command grow — deliberately not a fixed mission list, since the underlying simulation (weather, enemy movement, economy) is what should generate most of what happens.

**Rank and command scope.** As the player's career advances (successful actions, prize money, survival), rank increases and command scope widens: a lieutenant given their first command, up through post-captain of a frigate or ship of the line, up to commodore/admiral commanding a small squadron or fleet. Command scope directly gates what the player can do hands-on (a captain is aboard and directly controlling one ship) versus what they must do via semaphore (an admiral is aboard their flagship, commanding consorts by signal) — this is the mechanic from `02_simulation_systems.md` §5 made structural to the whole game, not just a battle feature.

**Succession on death — the core "who is the player" mechanic.** Per the brief: the player controls a captain/admiral, and death transfers control rather than ending the campaign. Concretely: the currently-controlled character entity, on death (or incapacitation — capture, invaliding out from severe injury), hands control to the senior surviving officer the game can plausibly justify — the flagship's first lieutenant, or the next-senior captain in the squadron, following period succession norms. Because every officer is already a fully simulated named individual (per `02_simulation_systems.md` §3), this requires no special-casing: the game always has a bench of real candidates because it was never *not* simulating them. This is the single mechanic that most directly justifies "simulate everyone, always" as a technical investment rather than an aesthetic choice — it only pays off narratively if the officer you're handed off to already has a service record, a personality shaped by mood/events, and relationships (rivalry, mentorship) with the crew, all of which only exist if they were being simulated the whole time.

**Loss condition.** The campaign ends only if there is no plausible officer left to inherit command (the entire chain of command aboard is dead/incapacitated and no consort is close enough to send a replacement) — a rare, appropriately dramatic "the fleet is lost" state, rather than a single character death ending the run.

**Victory/progress framing.** Open-ended rather than a fixed win condition initially: rank, reputation, and the state of the theatre's political/military balance (territory held, enemy fleets broken) are the running scoreboard. A defined "campaign arc" (a specific historical-flavoured war to prosecute to a conclusion) is a reasonable later addition once the open sandbox loop is proven fun on its own.

## Notes for future work

- Faction AI at the strategic layer (where do enemy fleets sail, which ports get reinforced) is a separate, coarser-grained simulation from per-ship captain AI (`02_simulation_systems.md` §5) and should be designed as its own system once there's a world for it to operate on — not conflated with ship-level AI now.
- Save/load (noted in `01_architecture.md`) becomes load-bearing once campaigns are meant to span real play sessions over months; get the component schema reasonably stable before investing in it.
