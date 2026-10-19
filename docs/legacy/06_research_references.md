# Research References

Two kinds of research feed this project: the historical/nautical material that gives the numbers and mechanisms their period accuracy, and the game-design/technical precedent that de-risks the architecture. Neither list is exhaustive — treat this as a starting bibliography to expand as each subsystem is actually built, and cite the specific source used for a stat block in the relevant `sim/data/ships/*.yaml` comment when you do.

## Nautical & historical

- **Seamanship & points of sail**: any standard "how a square-rigged ship actually sails" reference — the core facts (can't sail directly into the wind, the run of points of sail from close-hauled to running, tacking vs wearing, why a ship goes "in irons") are well documented in sail-training and maritime-museum material and are the right level of detail for the polar-curve model in `02_simulation_systems.md`.
- **Ship rating system**: the Royal Navy's rate classification (First through Sixth Rate, plus unrated sloops/brigs) by gun count, and typical crew complements per rate — the direct source for the `sim/data/ships/*.yaml` stat blocks (dimensions, tonnage, gun count/type, crew size) and for the roadmap's "sloop first, ship of the line eventually" command-scope progression.
- **The ship's watch and bell system**: the four-hour watch cycle and half-hourly bells — directly implemented in `engine/clock.py` and the basis for crew scheduling in `02_simulation_systems.md` §3.
- **Popham's Telegraphic Signals of Marine Vocabulary (1803)** and the broader history of Royal Navy flag signalling: the direct real-world model for the semaphore system in `02_simulation_systems.md` §5 — a numbered-flag-hoist vocabulary with real range/weather/night limits, not free text.
- **Gunnery practice**: period gun types and calibres, typical rates of fire and their dependence on crew size/training, and ammunition types (round/chain/grape/canister) and their distinct battlefield roles — feeds the Phase 2 combat model.
- **Naval mutiny and discipline history** (e.g. the 1797 Spithead and Nore mutinies): grounding for the discipline/morale system in `02_simulation_systems.md` §3 — evidence that crew morale collapse was a real, structural risk worth simulating, not melodrama.
- **Mediterranean regional winds**: the Mistral, Meltemi, and Sirocco as recognisable, learnable regional weather patterns — the model for the named regional wind systems in `04_world_campaign.md`.
- **Historical Mediterranean campaigns of the period** (e.g. the Royal Navy's Mediterranean Fleet operations, 1793–1815) as flavour and scenario inspiration once the campaign layer needs concrete texture, without needing to be reproduced literally (the brief asks for a Mediterranean-*like* world, not the historical one).

## Game design & technical precedent

- **Dwarf Fortress**: the direct inspiration named in the brief — specifically its philosophy of simulating mechanism over outcome, its fortress-mode/adventure-mode split (echoed here by the deck-view/chart-view and "ship you're aboard vs. ship you command by signal" split), and its practice of always keeping something playable across a very long, undead-lined development timeline — the model for this project's own phased roadmap.
- **RimWorld**: a cleaner, smaller-scale reference for a needs → mood → behaviour pipeline per simulated individual than Dwarf Fortress's own (considerably more opaque) implementation — a reasonable model for `sim/components.py`'s `Needs`/`Mood` design.
- **Cataclysm: Dark Days Ahead**: a large, long-lived, ECS-influenced roguelike codebase (in C++, but architecturally instructive) demonstrating that a data-oriented entity/component/system-shaped design scales to years of open-ended feature growth by many contributors — relevant precedent for keeping this project's own architecture disciplined as it grows solo, over years.
- **Sid Meier's Pirates!** and modern sailing/naval sims (e.g. *Naval Action*): precedent for the polar-performance-curve approach to sail physics — "mechanically accurate, not a fluid-dynamics simulation" is a deliberate, well-precedented simplification, not a shortcut unique to this project.
- **Terminal roguelike rendering technique**: the diffed-cell-buffer approach in `03_rendering_ui.md` is the same principle underlying curses' internal `refresh()` optimisation and is visible in the source of many terminal roguelikes; useful to study if `render/terminal.py`'s diffing ever needs to get smarter (dirty-rectangle tracking, partial-line writes) than the skeleton's straightforward per-cell diff.
- **`esper` (ECS library)** and **`blessed` (terminal control library)**: both used directly by this codebase; their own documentation/source are the first place to look when extending `engine/` or `render/` respectively.

## How to use this document going forward

When a new subsystem from `02_simulation_systems.md` moves from "designed" to "being built" (per the roadmap), that's the point to do a focused research pass on it specifically — pull actual period figures (a real 38-gun frigate's dimensions and complement, real period gun weights and rates of fire) rather than working from memory, and record the source alongside the resulting data file or constant. Treat this file as the index of *where to look*, not as the final source of truth for any specific number.
