# Draws the two split-screen panels from current ECS state: the deck view
# (left) and the ship/crew status readout (right). This is where render/
# actually reads sim components - see docs/design/03_rendering_ui.md.
#
# Both draw_* functions only read the esper.World; they never call
# world.add_component / create_entity / etc. That's the one rule this
# module exists to respect (docs/design/01_architecture.md, "systems
# mutate the ECS world; renderers only read it").

from __future__ import annotations

import esper

from broadside.engine.clock import SimClock
from broadside.render import palette
from broadside.render.buffer import ScreenBuffer
from broadside.render.layout import Panel
from broadside.render.viewport import Viewport
from broadside.sim import components as c
from broadside.sim.systems.wind import WindField

# Compass-direction arrow glyphs at 45-degree steps, index 0 = north,
# going clockwise - used for the wind indicator.
_WIND_ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


def _wind_arrow(direction_from_degrees: float) -> str:
    # An arrow pointing the direction the wind is blowing TOWARD (i.e. the
    # reverse of "from") reads more intuitively on screen than one pointing
    # at its source.
    blowing_to = (direction_from_degrees + 180.0) % 360.0
    idx = int((blowing_to + 22.5) // 45) % 8
    return _WIND_ARROWS[idx]


def draw_deck_panel(
    buffer: ScreenBuffer,
    panel: Panel,
    world: esper.World,
    ship: int,
) -> None:
    sub = ScreenBuffer(panel.width, panel.height)

    grid = world.component_for_entity(ship, c.DeckGrid)
    sail = world.component_for_entity(ship, c.SailPlan)

    viewport = Viewport.fitting(grid.width, grid.height, panel.width, panel.height)

    # Hull outline.
    for gy in range(grid.height):
        for gx in range(grid.width):
            on_border = gx in (0, grid.width - 1) or gy in (0, grid.height - 1)
            screen = viewport.to_screen(gx, gy)
            if screen is None:
                continue
            sx, sy = screen
            if on_border:
                sub.set(sx, sy, "#", fg=palette.HULL_TIMBER)
            else:
                sub.set(sx, sy, ".", fg=palette.DECK_PLANK)

    # Sails, drawn schematically as a row near the top of the hull, shaded
    # by how much sail is set - a placeholder for the per-sail rendering
    # described in docs/design/02_simulation_systems.md.
    sail_glyph = "█" if sail.trim > 0.66 else ("▓" if sail.trim > 0.33 else ("░" if sail.trim > 0.0 else " "))
    sail_color = palette.SAIL_FULL if sail.trim > 0.5 else palette.SAIL_REEFED
    mast_y = 1
    screen = viewport.to_screen(grid.width // 2, mast_y)
    if screen is not None and sail.trim > 0:
        sx, sy = screen
        sub.set(sx, sy, sail_glyph, fg=sail_color)

    # Crew, coloured by role.
    for _entity, (pos, renderable, crew) in world.get_components(
        c.DeckPosition, c.Renderable, c.CrewMember
    ):
        if crew.ship != ship:
            continue
        screen = viewport.to_screen(pos.x, pos.y)
        if screen is None:
            continue
        sx, sy = screen
        role = world.try_component(_entity, c.Role)
        fg = palette.role_color(role.title) if role else renderable.fg
        sub.set(sx, sy, renderable.glyph, fg=fg)

    buffer.blit(sub, panel.x, panel.y)


def draw_status_panel(
    buffer: ScreenBuffer,
    panel: Panel,
    world: esper.World,
    ship: int,
    wind_field: WindField,
    clock: SimClock,
) -> None:
    sub = ScreenBuffer(panel.width, panel.height)

    name = world.component_for_entity(ship, c.Name)
    heading = world.component_for_entity(ship, c.Heading)
    speed = world.component_for_entity(ship, c.Speed)
    sail = world.component_for_entity(ship, c.SailPlan)
    wind = wind_field.current

    row = 0
    sub.draw_text(1, row, name.full, fg=palette.TEXT_PRIMARY)
    row += 1
    sub.draw_text(1, row, clock.clock_display(), fg=palette.TEXT_DIM)
    row += 2
    sub.draw_text(1, row, f"Heading  {heading.degrees:5.1f} deg", fg=palette.TEXT_PRIMARY)
    row += 1
    sub.draw_text(1, row, f"Speed    {speed.knots:5.1f} kn", fg=palette.TEXT_PRIMARY)
    row += 1
    sub.draw_text(1, row, f"Sail     {sail.trim * 100:5.0f} %", fg=palette.TEXT_PRIMARY)
    row += 2
    arrow = _wind_arrow(wind.direction_degrees)
    sub.draw_text(
        1, row,
        f"Wind     {arrow} {wind.speed_knots:4.1f} kn  (from {wind.direction_degrees:5.1f} deg)",
        fg=palette.TEXT_PRIMARY,
    )
    row += 2

    sub.draw_text(1, row, "Crew", fg=palette.TEXT_PRIMARY)
    row += 1
    sub.draw_hline(1, row, min(panel.width - 2, 24), glyph="-", fg=palette.PANEL_DIVIDER)
    row += 1

    roster = [
        (world.component_for_entity(e, c.Name).full, world.component_for_entity(e, c.Role).title, mood)
        for e, (crew, mood) in world.get_components(c.CrewMember, c.Mood)
        if crew.ship == ship
    ]
    for shown, (name_str, role_title, mood) in enumerate(roster):
        if row >= panel.height - 1:
            sub.draw_text(1, row, f"... and {len(roster) - shown} more", fg=palette.TEXT_DIM)
            break
        line = f"{name_str:<16} {role_title:<18} {mood.label}"
        sub.draw_text(1, row, line[: panel.width - 2], fg=palette.mood_color(mood.value))
        row += 1

    buffer.blit(sub, panel.x, panel.y)
