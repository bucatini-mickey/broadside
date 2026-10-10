# Non-blocking keyboard input -> Command. Polled once per render frame so
# the sim loop is never blocked waiting on a keypress. See
# docs/design/03_rendering_ui.md, "Input and interaction model".
#
# The skeleton implements a single flat keymap (movement only). Later
# phases add the full modal scheme described in that doc (orders mode,
# signal-composition mode, ...) as separate Command-producing functions
# selected by the active mode, rather than growing this one function
# indefinitely.

from __future__ import annotations

from dataclasses import dataclass

from blessed import Terminal

TURN_STEP_DEGREES = 5.0
TRIM_STEP = 0.1


@dataclass
class Command:
    turn_delta_degrees: float = 0.0
    trim_delta: float = 0.0
    quit: bool = False


def poll_command(term: Terminal, timeout: float = 0.0) -> Command:
    """Read at most one keypress (non-blocking if timeout=0) and translate
    it to a Command. Call within `with term.cbreak():` (see main.py)."""
    key = term.inkey(timeout=timeout)
    if not key:
        return Command()

    if key.lower() == "q":
        return Command(quit=True)
    if key.lower() == "a":
        return Command(turn_delta_degrees=-TURN_STEP_DEGREES)
    if key.lower() == "d":
        return Command(turn_delta_degrees=TURN_STEP_DEGREES)
    if key.lower() == "w":
        return Command(trim_delta=TRIM_STEP)
    if key.lower() == "s":
        return Command(trim_delta=-TRIM_STEP)
    return Command()
