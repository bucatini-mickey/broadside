# Centralised colour constants. Extending the palette is meant to be "add a
# constant here," never "hunt down a magic RGB tuple in a system." See
# docs/design/03_rendering_ui.md, "Colour palette".
#
# Colour choices avoid relying on pure red vs. pure green as the only
# differentiator for good/bad state (a common colourblind-accessibility
# pitfall) - status colour pairs below are also distinguishable by relative
# brightness, and status text in render/ pairs colour with a glyph/label
# rather than colour alone.

from __future__ import annotations

Color = tuple[int, int, int]

# --- Sea & sky ---
SEA_DEEP: Color = (10, 40, 80)
SEA_SHALLOW: Color = (60, 120, 160)
SEA_FOAM: Color = (210, 230, 235)
SKY: Color = (25, 30, 45)

# --- Ship structure ---
HULL_TIMBER: Color = (110, 75, 45)
DECK_PLANK: Color = (150, 120, 80)
SAIL_FULL: Color = (235, 232, 220)
SAIL_REEFED: Color = (170, 165, 150)
SAIL_DAMAGED: Color = (120, 100, 90)
RIGGING: Color = (90, 70, 50)

# --- Crew, by broad role group (see sim/entities.py ROLES) ---
CREW_HAND: Color = (225, 200, 170)  # ordinary seamen, landsmen, waisters
CREW_GUNNER: Color = (220, 140, 90)
CREW_PETTY_OFFICER: Color = (150, 200, 230)
CREW_OFFICER: Color = (235, 220, 90)
CREW_BOY: Color = (180, 220, 150)

ROLE_COLORS: dict[str, Color] = {
    "Gun Captain": CREW_GUNNER,
    "Bosun's Mate": CREW_PETTY_OFFICER,
    "Quartermaster's Mate": CREW_PETTY_OFFICER,
    "Carpenter's Mate": CREW_PETTY_OFFICER,
    "Ship's Boy": CREW_BOY,
    "Marine": (225, 90, 80),
    "Lieutenant": CREW_OFFICER,
    "Midshipman": CREW_OFFICER,
    "Topman": (200, 215, 235),
    "Sailmaker's Mate": CREW_PETTY_OFFICER,
}


def role_color(role_title: str) -> Color:
    return ROLE_COLORS.get(role_title, CREW_HAND)


# --- Status / UI ---
STATUS_GOOD: Color = (110, 200, 140)
STATUS_WARN: Color = (230, 190, 90)
STATUS_BAD: Color = (220, 100, 90)
TEXT_PRIMARY: Color = (225, 225, 225)
TEXT_DIM: Color = (140, 140, 145)
PANEL_DIVIDER: Color = (70, 70, 80)


def mood_color(mood_value: float) -> Color:
    """mood_value in [-1, 1] -> a status colour. Paired with Mood.label
    (text) in the UI so colour is never the only signal."""
    if mood_value > 0.3:
        return STATUS_GOOD
    if mood_value > -0.3:
        return STATUS_WARN
    return STATUS_BAD
