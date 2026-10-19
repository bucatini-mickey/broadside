# World Generation

A procedurally generated, **fictional Mediterranean**, with its coasts, islands, straits, ports, nations and cultures, and a simulated history that produces the present day and a store of legends. Code: `src/broadside/worldgen/`. Try it:

```bash
python -m broadside.worldgen --seed 1805 --captain "Thomas Hardy" --ship Dauntless --nation Albion --out world
```

This prints a summary and writes `world/map.html` (political and terrain maps) and `world/chronicle.md` (the history). The `generated_home_port` scenario sets a ship off the generated home port.

**Status: groundwork.** Geography, settlements, nations, territory, history and player naming are built and deterministic from the seed. The generated coast feeds real scenes at any zoom. Economy, climate and the campaign map UI are still to come.

## Geography (`geography.py`)

Not the real map. A generated sea with the **structure** that made the Mediterranean what it was for sailing ships:

- a long east-west basin between a northern and a southern continent;
- a **narrow strait** at the west, between two headlands, to an outer ocean (the Gibraltar analogue), guaranteed open;
- a closed eastern end (the Levant analogue);
- 2–3 **peninsulas** hanging from the northern shore, bent part-way (the Iberia, Italy and Greece analogues), plus sometimes a cape from the south;
- 4–6 **large islands**, and an **archipelago** of 18–32 small ones off the easternmost peninsula (the Aegean analogue);
- a **narrow passage in the north-east to an inland sea** (the Bosporus/Black Sea analogue).

Each piece is a "landness" field. They're combined, roughened with fractal noise, and thresholded at sea level. Heights and depths come from distance to the coast plus ridged noise, so peninsulas have mountain spines and the sea shelves into deep basins. Default size is 360 × 150 cells of 10 km: a 3,600 × 1,500 km world, close to the real sea's scale. Generation takes ~0.3 s.

**Bridge to scenes:** `sim/world/terrain.WorldHeightmap` samples the map bilinearly and adds local detail noise, so a scene set anywhere in the world gets the *same* coast at 1 m, 20 m and 300 m per cell (the one-world-any-resolution rule from `07`).

## Settlements, nations and territory (`polity.py`)

- **Ports** go where real ports went: on the coast, in bays (sea around to anchor, land on several sides for shelter), on low ground, spaced out. There are ~70 by default, rated for harbour quality, with some fortified.
- **Nations** grow from regional capitals, each region's culture fixed by where it lies: an Iberian people in the west, Gallic and Italic in the north, Hellenic in the north-east and archipelago, Levantine in the east, and two Maghrebi powers in the south. Territory spreads over land from each capital (mountains slow it). Islands go to the nearest capital. Governments suit the culture (merchant republics, regencies, sultanates, kingdoms, a league of city-states).
- **The player's nation** is by default an **outside sea power** (Anglic culture, named by you) holding only a few bases: the strait fortress and the best island harbours. This is exactly Britain's position in the Mediterranean of the period: a strong navy, few ports, every base precious.

Names of people, places, nations and ships come from each culture's naming tradition (`sim/people/cultures.py`): recognisable in flavour ("Porto Veriello", "Saint-Marbonne", "Ras Tlalaane"), invented in fact.

## History (`history.py`)

155 years (1650 → 1805 by default) simulated year by year, Dwarf-Fortress "legends" at a naval scale:

- relations between nations drift, with more friction between different cultures;
- **wars** are declared when relations sour, and end in **treaties** as exhaustion grows;
- in war: **sea battles** (named for a nearby port, cape or shoal; won in proportion to navy strength; ships lost; admirals killed) and **sieges** (ports change hands, which redraws the map);
- navies rebuild toward what their ports can support;
- **admirals** rise, **famous ships** are launched and wrecked, **plague** strikes towns;
- the present: your nation enters a **great war** against its worst enemies, which is where the campaign begins.

The result isn't decoration. It's the present-day state (who owns which port, who's at war, navy sizes) plus a store of named battles, ships and admirals that **people are generated from**. A veteran's biography reads "Fought at the Battle of Cape Varon" because that battle happened in this world's history, while he was at sea. Settlements keep their own histories too (captured in 1744, plague in 1790).

## Next steps

- **Climate and winds:** regional prevailing winds and seasonal patterns (`09_environment.md`) laid over the generated geography: a Mistral analogue down the gap north of a peninsula, Etesians through the archipelago.
- **Economy:** what each port produces and needs, trade routes, convoys and privateers (Phase 5).
- **Fortresses:** batteries and forts at the fortified ports, built as structures with the same per-tile detail as ships (see `13_structures_and_items.md`).
- **A campaign chart** in the game: the generated world as the chart pane at 10–40 km per cell, with the same knowledge rules (your charts can be wrong or incomplete; coasts you haven't seen may be misdrawn).
- **Deeper history:** dynasties and rulers, alliances, colonies, famous captains still alive (and possibly at sea against you), rivalries and family feuds that can land in your crew list.

## Questions

1. **How big a world?** 3,600 × 1,500 km at 10 km cells is Mediterranean scale, and a passage across it takes weeks. Smaller makes for a tighter campaign.
2. **Playable nations:** always the outside sea power, or could you pick a regional nation (a Gallic empire's frigate captain, a Maghrebi corsair)?
3. **How much history?** 155 years gives legends without swamping. Should it go back further, with ruins, ancient wrecks and old grudges?
