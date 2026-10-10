# Rendering & UI

## Rendering target: a real terminal, not a graphics window pretending to be one

Two approaches were weighed:

1. **A real terminal, driven via `blessed`** (cross-platform terminal control: cursor positioning, 24-bit colour where supported, input, terminal-capability detection including on Windows via `jinxed`), with a hand-rolled diffed cell buffer on top.
2. **`python-tcod`** (Python bindings for `libtcod`), the de facto standard for Python roguelikes. It's fast, gives full per-cell RGB colour, custom bitmap fonts, and is battle-tested for exactly this genre of game.

Both were installed and smoke-tested. **`blessed` is the recommendation and what the skeleton uses**, because the brief specifically asks for a *terminal* game — `tcod` (like Dwarf Fortress's own classic "ASCII" mode, in fact) actually opens its own SDL window with a bitmap font; it looks like a terminal but isn't one, doesn't run over SSH, and doesn't behave like the rest of a person's terminal environment (font, copy-paste, terminal multiplexers). `blessed` runs in the user's actual terminal emulator. The tradeoff is real: `tcod` gives more rendering headroom (custom tilesets, guaranteed full RGB, no dependence on the host terminal's quirks) and would be the better choice if the project ever pivots away from "must be a literal terminal app." That door is left open deliberately — `render/` is the only part of the codebase that would need to change, because `sim/` has no idea how it's being displayed.

## The screen buffer and diffed rendering

Full-screen redraws every frame are the classic terminal-app performance trap — writing the whole grid every frame causes visible flicker and wastes most of the write bandwidth re-sending cells that didn't change. `render/buffer.py`'s `ScreenBuffer` is a plain 2D array of `(glyph, fg_rgb, bg_rgb)` per cell. `render/terminal.py`'s `TerminalRenderer` keeps the *previous* frame's buffer and, each frame, only emits cursor-move + colour-set + character writes for cells that actually changed since last frame, then does a single flush. This is the same technique used by curses' `refresh()` internally and by most serious terminal UI libraries; the skeleton implements it explicitly (rather than relying on a library to do it invisibly) because it's simple, it's the main performance-critical piece of the render path, and understanding it matters once panels/animation are added.

## Coordinate spaces, cameras, and the split screen

Per `01_architecture.md`, `DeckPosition` (sailors on a ship) and `WorldPosition` (ships on the chart) are different spaces. `render/viewport.py`'s `Viewport` is a small camera abstraction: given an origin and a target rectangle of screen cells, it maps space-coordinates to screen-coordinates and clips anything outside the visible window. Two viewports exist at once:

- **Deck viewport (left pane)**: centred on the player's ship, rendering the deck tile grid — hull outline, sails (schematically, as a block of characters whose glyph/shading reflects trim and damage), guns, fittings, and every crew member as an individual coloured glyph (`@` by default, coloured by role — topmen, gun crew, officers, marines, etc. — exactly the "every terminal pixel is a person or wall" request from the brief).
- **Status/chart pane (right pane)**: ship status (heading, speed, wind), crew roster with need/mood indicators, and (later phases) the fleet/chart view and the semaphore message log. In the skeleton this is a live status readout; the chart view proper arrives with world generation (Phase 4 in the roadmap).

`render/layout.py` owns the split — a simple vertical divider whose position is a fraction of terminal width, recomputed if the terminal is resized (detected via `blessed`'s resize signal handling).

## Colour palette

`render/palette.py` centralises colour constants rather than scattering RGB literals through rendering code: sea (shading by depth), hull/deck timber tones, sail whites/greys (darkening as sails take damage or reef), a small set of role-colours for crew, and status colours (health/mood bars) chosen to remain distinguishable under red-green colourblindness (avoiding pure red/green as the only differentiator for good/bad state — pairing colour with a glyph or intensity change instead). Extending the palette is meant to be "add a constant here," not "hunt down a magic RGB tuple somewhere in a system."

## Input and interaction model

`ui/input.py` reads terminal input non-blocking (`blessed`'s `inkey(timeout=...)`, polled once per render frame so the sim loop is never blocked waiting on a keypress) and maps keys to commands. The skeleton implements a minimal command set (heading adjustment, sail trim, quit) as a placeholder for the fuller **modal command scheme** planned for later phases, in the Dwarf Fortress tradition of distinct modes rather than one flat keymap: a sailing/movement mode, an orders mode (assign crew tasks, set battle stations), and — once semaphore exists — a signal-composition mode for picking flag-hoists from the period signal book. Modes are a UI/state concern only; they read from and issue commands into the same `sim/` systems regardless of which mode is active.

## Performance budget

Target: a smooth 10 Hz simulation tick (matching `SimClock`'s default) and a render frame at or above that rate, on a terminal window in the range of roughly 120×40 to 200×60 cells — large enough for a legible split screen, small enough that even a naive full redraw would be tolerable as a fallback. The diffed renderer should make sustained higher frame rates easy; the harder cost, if any shows up under profiling, will be in `sim/` (large-crew AI/pathfinding), not `render/` — consistent with the performance strategy in `01_architecture.md`.
