# Broadside: the game itself.
#
#   python -m broadside.game
#
# A front door with a menu. The five tutorial missions are meant to be
# taken in order - each teaches one whole part of command and checks that
# you have actually done it - and after them the sandbox and the scenario
# library are open for anything you like.
#
# The menu is deliberately plain. It is drawn with the same ScreenBuffer
# and renderer as everything else, so it looks like the rest of the ship
# rather than like a separate program, and every state it can be in is a
# value in MenuState - which is what the tests drive.

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass, field

from broadside.render.buffer import ScreenBuffer
from broadside.render.terminal import TerminalRenderer

TITLE = "BROADSIDE"
SUBTITLE = "A Napoleonic naval command simulation"

BG = (11, 13, 18)
FRAME = (70, 86, 110)
HEAD = (236, 222, 180)
TEXT = (206, 206, 212)
DIM = (126, 132, 146)
PICK_BG = (34, 48, 70)
PICK_FG = (255, 240, 190)

QUIT = "quit"
HELP = "help"
LIBRARY = "library"
BACK = "back"


@dataclass
class Item:
    key: str  # a scenario key, or QUIT / HELP / LIBRARY / BACK
    title: str
    note: str = ""


def _courses() -> list:
    from broadside.scenarios.courses import COURSES

    return [Item(key, title, note) for key, title, note in COURSES]


def main_items() -> list:
    return _courses() + [
        Item("sandbox", "Free sailing", "A ship, a sea, and nobody telling you what to do."),
        Item(LIBRARY, "The scenario library", "Every test scene in the game, with captions and checks."),
        Item(HELP, "Help: every control", "What each key does, and the few worth remembering."),
        Item(QUIT, "Quit", "Leave the ship."),
    ]


def library_items() -> list:
    from broadside.scenarios.base import all_scenarios

    out = [Item(BACK, "Back to the main menu")]
    for scn in all_scenarios():
        if scn.key.startswith("tutorial_") and scn.key != "tutorial_demo":
            continue
        out.append(Item(scn.key, scn.key, scn.title))
    return out


@dataclass
class MenuState:
    """Everything the menu is, as a value. `choose` is the only way out."""

    items: list = field(default_factory=main_items)
    i: int = 0
    where: str = "main"  # "main" | "library" | "help"
    message: str = ""

    def move(self, delta: int) -> None:
        if not self.items:
            return
        self.i = (self.i + delta) % len(self.items)

    @property
    def current(self) -> Item:
        return self.items[self.i]

    def _open(self, where: str) -> None:
        self.where = where
        self.items = {"main": main_items, "library": library_items}.get(where, main_items)()
        self.i = 0

    def handle(self, k: str):
        """A keystroke. Returns a scenario key to play, QUIT, or None."""
        if k in ("KEY_UP", "k"):
            self.move(-1)
            return None
        if k in ("KEY_DOWN", "j"):
            self.move(1)
            return None
        if k in ("KEY_PGUP",):
            self.move(-10)
            return None
        if k in ("KEY_PGDOWN",):
            self.move(10)
            return None
        if k in ("q", "Q"):
            if self.where != "main":
                self._open("main")
                return None
            return QUIT
        if k in ("h", "H", "?"):
            if self.where == "help":
                self._open("main")
            else:
                self.where = "help"
            return None
        if k in ("KEY_ESCAPE", "KEY_BACKSPACE"):
            self._open("main")
            return None
        if k and k.isdigit() and self.where == "main":
            n = int(k)
            if 1 <= n <= len(self.items):
                self.i = n - 1
                return self.handle("KEY_ENTER")
            return None
        if k in ("KEY_ENTER", "\n", "\r", " "):
            if self.where == "help":
                self._open("main")
                return None
            item = self.current
            if item.key == QUIT:
                return QUIT
            if item.key == HELP:
                self.where = "help"
                return None
            if item.key == LIBRARY:
                self._open("library")
                return None
            if item.key == BACK:
                self._open("main")
                return None
            return item.key
        return None


# --- drawing ---------------------------------------------------------------


def _frame(buf: ScreenBuffer, x: int, y: int, w: int, h: int) -> None:
    for xx in range(x, x + w):
        for yy in range(y, y + h):
            buf.set(xx, yy, " ", fg=TEXT, bg=BG)
    for xx in range(x + 1, x + w - 1):
        buf.set(xx, y, "─", fg=FRAME, bg=BG)
        buf.set(xx, y + h - 1, "─", fg=FRAME, bg=BG)
    for yy in range(y + 1, y + h - 1):
        buf.set(x, yy, "│", fg=FRAME, bg=BG)
        buf.set(x + w - 1, yy, "│", fg=FRAME, bg=BG)
    for xx, yy, ch in ((x, y, "┌"), (x + w - 1, y, "┐"), (x, y + h - 1, "└"), (x + w - 1, y + h - 1, "┘")):
        buf.set(xx, yy, ch, fg=FRAME, bg=BG)


def draw_menu(buf: ScreenBuffer, menu: MenuState) -> None:
    W, H = buf.width, buf.height
    for y in range(H):
        for x in range(W):
            buf.set(x, y, " ", fg=TEXT, bg=BG)
    buf.draw_text(2, 1, TITLE, fg=HEAD, bg=BG)
    buf.draw_text(2 + len(TITLE) + 2, 1, SUBTITLE, fg=DIM, bg=BG)
    if menu.where == "help":
        _draw_help(buf)
        return
    box_w = min(W - 4, 96)
    box_h = min(H - 6, len(menu.items) * 2 + 4)
    # Two lines an item while there is room for all of them; one line each
    # when there is not, so that the last items - help and quit - are on
    # the screen rather than below the fold on a short terminal.
    compact = len(menu.items) * 2 + 4 > box_h
    per = 1 if compact else 2
    rows = max(1, (box_h - 4) // per)
    _frame(buf, 2, 3, box_w, box_h)
    head = ("Missions, in the order a man would learn them - and everything else"
            if menu.where == "main" else "The scenario library")
    buf.draw_text(4, 4, head, fg=HEAD, bg=BG)
    # A window onto the list, so a long library scrolls instead of being cut.
    start = 0 if len(menu.items) <= rows else max(0, min(menu.i - rows // 2, len(menu.items) - rows))
    y = 6
    for n in range(start, min(len(menu.items), start + rows)):
        item = menu.items[n]
        on = n == menu.i
        label = f" {n + 1}. {item.title.split('. ', 1)[-1]} " if menu.where == "main" else f" {item.title} "
        if compact and item.note:
            label = f"{label}  - {item.note}"
        buf.draw_text(4, y, label.ljust(box_w - 6)[: box_w - 6], fg=PICK_FG if on else TEXT, bg=PICK_BG if on else BG)
        if item.note and not compact:
            buf.draw_text(6, y + 1, item.note[: box_w - 8], fg=DIM, bg=BG)
        y += per
    if start + rows < len(menu.items):
        buf.draw_text(4, 3 + box_h - 2, f"... {len(menu.items) - start - rows} more below", fg=DIM, bg=BG)
    foot = "arrows choose   ENTER plays   1-9 jump   h help   q quit"
    if menu.where != "main":
        foot = "arrows choose   ENTER plays   q back to the main menu"
    buf.draw_text(2, min(H - 2, 3 + box_h + 1), foot, fg=DIM, bg=BG)
    if menu.message:
        buf.draw_text(2, min(H - 1, 3 + box_h + 2), menu.message[: W - 4], fg=HEAD, bg=BG)


def _draw_help(buf: ScreenBuffer) -> None:
    from broadside.view.panels import KEY_HELP

    W, H = buf.width, buf.height
    buf.draw_text(2, 3, "Every control. The footer in the game keeps the few worth remembering.", fg=HEAD, bg=BG)
    y = 5
    keyw = 16
    for key, what in KEY_HELP:
        if y >= H - 3:
            buf.draw_text(2, y, "(more in the KEYS panel aboard: press 6 while playing)", fg=DIM, bg=BG)
            break
        for i, line in enumerate(textwrap.wrap(what, max(24, W - keyw - 8)) or [""]):
            if y >= H - 3:
                break
            buf.draw_text(2, y, (key if i == 0 else "").ljust(keyw)[:keyw], fg=HEAD, bg=BG)
            buf.draw_text(2 + keyw, y, line, fg=TEXT, bg=BG)
            y += 1
    buf.draw_text(2, H - 2, "q or ENTER returns to the menu", fg=DIM, bg=BG)


# --- the loop --------------------------------------------------------------


def play(key: str) -> None:
    """Build a scenario and hand it to the interactive app."""
    from broadside.scenarios.base import get
    from broadside.ui.app import run_interactive

    scn = get(key)
    run_interactive(scn.build(), scn)


def run(term=None) -> int:
    if term is None:
        from blessed import Terminal

        term = Terminal()
    if not sys.stdout.isatty():
        print("broadside: stdout is not a terminal - run in a real terminal.", file=sys.stderr)
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    menu = MenuState()
    while True:
        # One fullscreen context per visit to the menu, entered and left
        # around each mission rather than wrapped about the whole program.
        # Nesting it inside the app's own fullscreen left the alternate
        # screen on the inner exit, after which the menu was painting onto
        # a screen nobody was looking at - which is what "menu not
        # displaying" turned out to be.
        got = _menu_loop(term, menu)
        if got == QUIT:
            return 0
        if got:
            menu.message = ""
            try:
                play(got)
            except Exception as exc:  # a broken scene must not take the menu with it
                menu.message = f"{got} would not run: {exc!r}"


def _menu_loop(term, menu: MenuState):
    """Draw and drive the menu until the player chooses something. Returns
    a scenario key, QUIT, or None."""
    renderer = TerminalRenderer(term)
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            if term.width < 60 or term.height < 12:
                buf = ScreenBuffer(max(20, term.width), max(3, term.height))
                buf.draw_text(0, 0, f"Terminal too small: {term.width}x{term.height}."[: max(20, term.width)], fg=HEAD, bg=BG)
                buf.draw_text(0, 1, "Please enlarge it to at least 60x12."[: max(20, term.width)], fg=TEXT, bg=BG)
                renderer.render(buf)
            else:
                buf = ScreenBuffer(term.width, term.height)
                draw_menu(buf, menu)
                renderer.render(buf)
            key = term.inkey(timeout=5.0)
            if not key and not getattr(key, "name", None):
                continue
            k = key.name if getattr(key, "is_sequence", False) else str(key)
            got = menu.handle(k)
            if got:
                return got


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
