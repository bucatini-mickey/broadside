# The right-hand panels: one thing at a time, chosen with 1-5.
#
# Everything that used to be crammed into the bottom right - instruments,
# sight, contacts, battery, orders, the log - now lives in five panels with
# the whole width to themselves, above a single always-on status strip:
#
#   1 LOG      the log, wrapped, and the look/actions readout
#   2 CREW     the ship's company as a roster with a skill grid, and the
#              full sheet for whoever is selected (arrows when the panel
#              has focus)
#   3 ORDERS   what you have ordered, what the guns are doing, contacts
#   4 SHIP     binnacle, pennant, log-line, bell, sail plan, hull, stores
#   5 KEYS     every control, in two columns, wrapped
#
# See docs/design/08_interface.md.

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass, field

from broadside.render.buffer import ScreenBuffer
from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.sailplan import beaufort, compass_32, point_of_sail, relative_bearing_words, sail_setting_name
from broadside.view import style as S
from broadside.view.hud import DIM, HEAD, KIND_COLORS, TEXT, _Writer
from broadside.view.instruments import draw_instruments
from broadside.view.people_view import person_sheet

BG = (12, 13, 18)
TAB_ON_BG = (44, 46, 62)
TAB_OFF_FG = (130, 132, 145)
STRIP_BG = (20, 22, 30)
SEL_BG = (58, 52, 24)

PANELS = ("log", "crew", "orders", "signals", "ship", "keys")
PANEL_TITLES = {"log": "LOG", "crew": "CREW", "orders": "ORDERS", "signals": "SIGNALS", "ship": "SHIP", "keys": "KEYS"}

# Short headers for the roster's skill grid, in SKILLS order.
SKILL_ABBR = {
    "seamanship": "sm", "topwork": "tp", "helm": "hm", "gunnery": "gn", "gunlaying": "gl",
    "musketry": "mk", "melee": "ml", "carpentry": "cp", "sailmaking": "sl", "rigging": "rg",
    "cooking": "ck", "medicine": "md", "navigation": "nv", "leadership": "ld", "lookout": "lk",
}

KEY_HELP = [
    ("SPACE", "pause / resume (paused = planning: your whole ship revealed)"),
    ("TAB", "move focus: ship pane -> chart -> panel"),
    ("1 - 6", "choose a panel: log, crew, orders, signals, ship, keys"),
    ("", "  in SIGNALS (TAB to it): arrows choose, ENTER makes the signal, a changes who it is for"),
    ("m", "WALK: be the captain. The view follows him, close in"),
    ("arrows / hjkl", "walk (in walk mode), else move the look cursor or pan"),
    ("e  then 1-9", "what can I do here (walk mode): the next order of a drill, casks, signals"),
    ("+ / -", "zoom the focused pane"),
    ("r / c", "rotation / cell shape of the focused pane"),
    ("o", "look through the captain's eyes or the masthead lookout's"),
    ("a / d", "helm five degrees to larboard / starboard (A / D: thirty)"),
    ("w / s", "make / shorten sail"),
    ("b", "beat to quarters, or stand down"),
    ("[ / ]", "fire the larboard / starboard battery on your word"),
    ("F", "fire as they bear: each gun captain fires when his gun is ready"),
    ("l", "look cursor on / off"),
    ("x", "tell the guns to fire at what the cursor is on"),
    ("o", "let go the anchor, or weigh it: she must be under short canvas and nearly stopped "
          "to let go, and weighing is the heaviest routine work in the ship"),
    ("r", "two-thirds allowance on or off: the stores last half again as long and the men mind it"),
    ("G", "splice the mainbrace - an extra issue of grog out of your own goodwill"),
    ("p", "the gun captain's estimate of where the shot would fall: his arc through "
          "the glass, its track and splash on the chart, and how far out he may be"),
    ("t / T", "take up the glass / look out by eye: a first-person view of what is around you"),
    ("", "  while looking: left/right sweep, up/down tilt the glass, TAB takes the next"),
    ("", "  ship into it and holds her there, f returns it dead ahead, +/- change the"),
    ("", "  field, t lowers it. The bearing is held relative to her head, so the view"),
    ("", "  stays on what you are watching when the helm moves"),
    ("z", "levels: cut the world into horizontal slices (PgUp/PgDn to go up and down)"),
    ("g", "steer for the cursor"),
    ("f", "re-centre the view"),
    ("< / >", "slow down / speed up time"),
    ("v", "reveal everything (debug: ignore line of sight)"),
    ("q", "quit"),
]


@dataclass
class UIState:
    """What the player has the interface set to. Presentation only."""

    panel: str = "log"
    fps: float = 0.0
    signal_i: int = 0  # which signal in the book is selected
    signal_to: int = -1  # addressed to one ship, or -1 for the squadron
    crew_i: int = 0
    crew_scroll: int = 0
    log_scroll: int = 0
    look: list = field(default_factory=list)

    def select_panel(self, key: str) -> bool:
        idx = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5}.get(key)
        if idx is None:
            return False
        self.panel = PANELS[idx]
        return True

    def move(self, delta: int, count: int) -> None:
        if self.panel == "crew":
            self.crew_i = max(0, min(max(0, count - 1), self.crew_i + delta))
        elif self.panel == "signals":
            self.signal_i = max(0, min(max(0, count - 1), self.signal_i + delta))
        else:
            self.log_scroll = max(0, self.log_scroll + delta)


# --- the always-on strip and the tab bar ---------------------------------


def draw_status_strip(buf: ScreenBuffer, x0: int, y0: int, width: int, state, ui=None) -> None:
    world = state.world
    ship = state.player_ship
    heading = world.component_for_entity(ship, c.Heading).degrees
    speed = world.component_for_entity(ship, c.Speed).knots
    trim = world.component_for_entity(ship, c.SailPlan).trim
    orders = world.try_component(ship, c.ShipOrders)
    wind = state.wind.current
    _force, name = beaufort(wind.speed_knots)
    rel_wind = (wind.direction_degrees - heading) % 360.0
    parts = [
        (state.clock_text(), TEXT),
        ("  helm ", DIM), (f"{compass_32(heading)} {heading:03.0f}", HEAD),
        ("  log ", DIM), (f"{speed:.1f} kn", TEXT),
    ]
    # How the enemy bears from *us*, before anything else but the helm: it
    # is the one thing a north-up chart cannot tell you, and the strip is
    # cut off from the right when the pane is narrow.
    if orders is not None and orders.gun_target >= 0:
        from broadside.view.orientation import aspect_short, range_short, relative_short

        her = world.try_component(orders.gun_target, c.WorldPosition)
        mine = world.try_component(ship, c.WorldPosition)
        her_name = world.try_component(orders.gun_target, c.Name)
        her_head = world.try_component(orders.gun_target, c.Heading)
        if her is not None and mine is not None:
            dx, dy = her.x_m - mine.x_m, her.y_m - mine.y_m
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            rel = (bearing - heading + 180.0) % 360.0 - 180.0
            words = f"{her_name.full if her_name is not None else 'target'} {relative_short(rel)}, {range_short(math.hypot(dx, dy))}"
            if her_head is not None:
                words += f", {aspect_short(her_head.degrees, bearing)}"
            parts += [("  guns on ", DIM), (words, (245, 150, 110))]
    parts += [
        ("  wind ", DIM), (f"{name}, {relative_bearing_words(rel_wind)}", TEXT),
        ("  ", DIM), (sail_setting_name(trim), TEXT),
    ]
    weather = state.atmosphere.words()
    if weather != "clear":
        parts += [("  ", DIM), (weather, (160, 180, 205))]
    if orders is not None and orders.quarters:
        parts += [("  ", DIM), ("QUARTERS", (245, 170, 110))]
    if orders is not None and (orders.anchored or orders.anchor_work_s > 0):
        word = "ANCHORED" if orders.anchored else "ANCHOR WORKING"
        parts += [("  ", DIM), (word, (150, 200, 230))]
    if orders is not None and orders.short_allowance:
        parts += [("  ", DIM), ("SHORT ALLOWANCE", (220, 190, 120))]
    if ui is not None and ui.fps:
        parts += [("   ", DIM), (f"{ui.fps:.0f} fps", (110, 130, 150))]
    for xx in range(width):
        buf.set(x0 + xx, y0, " ", fg=TEXT, bg=STRIP_BG)
    x = x0 + 1
    for text, fg in parts:
        room = x0 + width - 1 - x
        if room <= 0:
            break
        buf.draw_text(x, y0, text[:room], fg=fg, bg=STRIP_BG)
        x += len(text[:room])


def draw_tab_bar(buf: ScreenBuffer, x0: int, y0: int, width: int, ui: UIState, focused: bool) -> None:
    for xx in range(width):
        buf.set(x0 + xx, y0, " ", fg=TEXT, bg=BG)
    x = x0 + 1
    for i, key in enumerate(PANELS):
        label = f" {i + 1} {PANEL_TITLES[key]} "
        on = key == ui.panel
        bg = TAB_ON_BG if on else BG
        fg = HEAD if on else TAB_OFF_FG
        if x + len(label) >= x0 + width:
            break
        buf.draw_text(x, y0, label, fg=fg, bg=bg)
        x += len(label) + 1
    if focused:
        hint = "arrows: move"
        if x + len(hint) + 2 < x0 + width:
            buf.draw_text(x0 + width - len(hint) - 1, y0, hint, fg=(235, 200, 120), bg=BG)


def draw_panel(buf: ScreenBuffer, x0: int, y0: int, width: int, height: int, state, view, ui: UIState, *, info=None, scenario=None, focused: bool = False) -> None:
    for yy in range(height):
        for xx in range(width):
            buf.set(x0 + xx, y0 + yy, " ", fg=TEXT, bg=BG)
    if ui.panel == "crew":
        _crew_panel(buf, x0, y0, width, height, state, ui, focused)
    elif ui.panel == "orders":
        _orders_panel(buf, x0, y0, width, height, state)
    elif ui.panel == "signals":
        _signals_panel(buf, x0, y0, width, height, state, ui, focused)
    elif ui.panel == "ship":
        _ship_panel(buf, x0, y0, width, height, state, view, info)
    elif ui.panel == "keys":
        _keys_panel(buf, x0, y0, width, height)
    else:
        _log_panel(buf, x0, y0, width, height, state, ui, scenario)


# --- 1 LOG ----------------------------------------------------------------


def draw_log(w: _Writer, state, scroll: int = 0) -> None:
    """The log, newest at the bottom, wrapped rather than clipped - the
    tutor and the gun crews both speak through here."""
    room = max(0, w.h - w.row)
    rows: list = []
    indent = 6
    for e in reversed(state.log):
        body = textwrap.wrap(e.text, max(12, w.w - indent - 3)) or [""]
        fg = KIND_COLORS.get(e.kind, TEXT)
        stamp = f"{int(e.time_s // 60):02d}:{int(e.time_s % 60):02d} "
        block = [[(stamp, DIM), (body[0], fg)]] + [[(" " * indent, DIM), (ln, fg)] for ln in body[1:]]
        if len(rows) + len(block) > room + scroll:
            break
        rows[:0] = block
    if scroll:
        rows = rows[: max(0, len(rows) - scroll)]
    for spans in rows[-room:]:
        w.spans(spans)


def _log_panel(buf, x0, y0, width, height, state, ui: UIState, scenario) -> None:
    w = _Writer(buf, x0, y0, width, height)
    world = state.world
    ship = state.player_ship
    name = world.component_for_entity(ship, c.Name).full
    light = state.atmosphere.light
    light_txt = "day" if light > 0.7 else ("dusk" if light > 0.25 else "night")
    w.spans([(name, HEAD), ("  ", DIM), (state.clock_text(), TEXT), (f"  {light_txt}", DIM)])
    if scenario is not None:
        for ln in textwrap.wrap(f"Scenario: {scenario.title}", max(20, width - 3))[:2]:
            w.line(ln, fg=DIM)
    if ui.look:
        w.rule(ui.look[0] if ui.look[0].startswith("Actions") else "Look")
        body = ui.look[1:] if ui.look[0].startswith("Actions") else ui.look
        for ln in body[: max(0, (height - w.row) // 2)]:
            for part in textwrap.wrap(ln, max(20, width - 3), subsequent_indent="    ") or [""]:
                w.line(part, fg=(230, 230, 180))
    w.rule("Log")
    draw_log(w, state, ui.log_scroll)


# --- 2 CREW ---------------------------------------------------------------


def company(state, ship: int) -> list:
    """The ship's company, officers first, then by role - a stable order so
    the roster does not shuffle under the cursor."""
    world = state.world
    out = []
    for ent, crew in world.get_component(c.CrewMember):
        if crew.ship != ship and crew.home_ship != ship:
            continue
        role = world.try_component(ent, c.Role)
        title = role.title if role else ""
        rank = 0 if title == "Captain" else (1 if title in ("Lookout", "Gun Captain", "Bosun's Mate") else 2)
        name = world.try_component(ent, c.Name)
        out.append((rank, title, name.full if name else "?", ent))
    out.sort(key=lambda r: (r[0], r[1], r[2]))
    return [(r[3], r[1], r[2]) for r in out]


def _station_word(world, ent: int) -> str:
    task = world.try_component(ent, c.CrewTask)
    if world.has_component(ent, c.Below):
        return "below"
    if world.has_component(ent, c.Aloft):
        return "aloft"
    if task is None:
        return "-"
    if task.station_kind == "gun":
        return f"gun {task.gun_index}.{task.station_no}"
    if task.station_kind:
        return task.station_kind
    return task.kind


def _state_word(world, ent: int) -> tuple:
    from broadside.sim.actions import Activity
    from broadside.sim.people.health import condition_words

    body = world.try_component(ent, pc.Body)
    if body is not None and not body.alive:
        return "dead", (150, 90, 90)
    act = world.try_component(ent, Activity)
    if act is not None:
        return act.label.split("(")[0].strip().lower()[:18], (220, 200, 140)
    if body is not None and not body.conscious:
        return "senseless", (200, 140, 120)
    if body is not None:
        words = condition_words(body)
        if words and words != "unhurt":
            return words[:18], (215, 150, 130)
    psy = world.try_component(ent, pc.Psyche)
    if psy is not None and psy.morale < -0.2:
        return "sullen", (170, 170, 200)
    return "-", DIM


def _crew_panel(buf, x0, y0, width, height, state, ui: UIState, focused: bool) -> None:
    world = state.world
    ship = state.player_ship
    people = company(state, ship)
    if not people:
        _Writer(buf, x0, y0, width, height).line("No crew aboard.", fg=DIM)
        return
    ui.crew_i = max(0, min(len(people) - 1, ui.crew_i))
    sheet_h = min(12, max(6, height // 3))
    rows_h = height - sheet_h - 2
    w = _Writer(buf, x0, y0, width, height)
    skills = [s for s in pc.SKILLS]
    grid_w = 3 * len(skills)
    wide = width >= 78
    name_w = min(24, max(12, width - (grid_w + 26) if wide else width - 30))
    header = f"{'NAME':<{name_w}} {'ROLE':<12} {'STATION':<10} "
    if wide:
        header += " ".join(f"{SKILL_ABBR.get(s, s[:2]):>2}" for s in skills)
    else:
        header += "STATE"
    w.spans([(f"{len(people)} of the company", HEAD), ("   morale, skills, and what each man is at", DIM)])
    w.line(header[: width - 2], fg=DIM)
    # Keep the selected man on screen.
    if ui.crew_i < ui.crew_scroll:
        ui.crew_scroll = ui.crew_i
    if ui.crew_i >= ui.crew_scroll + rows_h:
        ui.crew_scroll = ui.crew_i - rows_h + 1
    ui.crew_scroll = max(0, min(max(0, len(people) - rows_h), ui.crew_scroll))
    for i in range(ui.crew_scroll, min(len(people), ui.crew_scroll + rows_h)):
        ent, title, name = people[i]
        sel = i == ui.crew_i
        bg = SEL_BG if sel else BG
        state_txt, state_fg = _state_word(world, ent)
        line = f"{name[:name_w]:<{name_w}} {title[:12]:<12} {_station_word(world, ent)[:10]:<10} "
        row = y0 + w.row
        if row >= y0 + height:
            break
        for xx in range(width):
            buf.set(x0 + xx, row, " ", fg=TEXT, bg=bg)
        buf.draw_text(x0 + 1, row, line[: width - 2], fg=(235, 235, 240) if sel else TEXT, bg=bg)
        if wide:
            sk = world.try_component(ent, pc.Skills)
            x = x0 + 1 + len(line)
            for s in skills:
                v = sk.get(s) if sk is not None else 0.0
                ch = "." if v < 0.05 else str(min(9, int(v * 9.99)))
                fg = DIM if v < 0.3 else ((210, 210, 160) if v < 0.6 else (245, 215, 120))
                if x + 2 < x0 + width:
                    buf.draw_text(x, row, f"{ch:>2}", fg=fg, bg=bg)
                x += 3
        else:
            x = x0 + 1 + len(line)
            if x + 6 < x0 + width:
                buf.draw_text(x, row, state_txt[: x0 + width - x - 1], fg=state_fg, bg=bg)
        w.row += 1
    w.rule("The man")
    ent = people[ui.crew_i][0]
    year = 1805
    lines: list = []
    for ln in person_sheet(world, ent, year):
        lines.extend(textwrap.wrap(ln, max(20, width - 3), subsequent_indent="    ") or [""])
    for ln in lines[: max(0, height - w.row)]:
        w.line(ln, fg=TEXT if not ln.startswith("    ") else DIM)


# --- 4 SIGNALS ------------------------------------------------------------


def signal_targets(state) -> list:
    """(entity, name) of the ships you might address, your own excepted."""
    world = state.world
    out = [(-1, "the squadron")]
    for ent, (_pos, _body) in world.get_components(c.WorldPosition, c.ShipBody):
        if ent == state.player_ship:
            continue
        nm = world.try_component(ent, c.Name)
        fac = world.try_component(ent, c.Faction)
        mine = world.try_component(state.player_ship, c.Faction)
        if fac is not None and mine is not None and fac.name != mine.name:
            continue  # you do not give orders to the enemy
        out.append((ent, nm.full if nm is not None else "a consort"))
    return out


def _signals_panel(buf, x0, y0, width, height, state, ui: UIState, focused: bool) -> None:
    from broadside.sim.systems.captain_ai import ShipCaptainAI
    from broadside.sim.systems.signals import SIGNAL_BOOK, Signals

    world = state.world
    ship = state.player_ship
    w = _Writer(buf, x0, y0, width, height)
    sig = world.try_component(ship, Signals)
    book = sorted(SIGNAL_BOOK.items())
    ui.signal_i = max(0, min(len(book) - 1, ui.signal_i))
    targets = signal_targets(state)
    to_name = next((nm for ent, nm in targets if ent == ui.signal_to), "the squadron")

    w.spans([("The signal book", HEAD), ("   arrows choose, ENTER makes the signal, a changes who it is for", DIM)])
    w.spans([("Addressed to ", DIM), (to_name, TEXT)])
    if sig is not None and sig.hoisted:
        flying = f"No. {sig.hoisted} \"{sig.text}\""
        w.spans([("Flying ", DIM), (flying, (245, 200, 120))])
        answered = []
        for ent in sig.acknowledged:
            nm = world.try_component(ent, c.Name)
            answered.append(nm.full if nm is not None else "one")
        w.line("  answered by " + (", ".join(answered) if answered else "nobody yet"), fg=DIM)
    else:
        w.line("Nothing flying.", fg=DIM)
    w.rule("Book")
    rows = max(1, height - w.row - 6)
    start = max(0, min(len(book) - rows, ui.signal_i - rows // 2))
    for i in range(start, min(len(book), start + rows)):
        number, text = book[i]
        sel = i == ui.signal_i
        row = y0 + w.row
        if row >= y0 + height:
            break
        bg = SEL_BG if sel else BG
        for xx in range(width):
            buf.set(x0 + xx, row, " ", fg=TEXT, bg=bg)
        buf.draw_text(x0 + 1, row, f"{number:>3}  {text}"[: width - 2], fg=(235, 235, 240) if sel else TEXT, bg=bg)
        w.row += 1
    w.rule("Your squadron")
    for ent, nm in targets[1:]:
        if w.full:
            break
        ai = world.try_component(ent, ShipCaptainAI)
        if ai is None:
            w.line(f"{nm}  (no captain of her own)", fg=DIM)
            continue
        held = max(0.0, ai.ordered_until_s - state.now_s)
        w.spans([
            (f"{nm[:22]:<22}", TEXT),
            (f"{ai.mission:<9}", (200, 220, 140)),
            (f"skill {ai.skill:.2f} wit {ai.intelligence:.2f} dash {ai.aggression:.2f} obedience {ai.discipline:.2f}", DIM),
            (f"  order holds {held:.0f}s" if held else "", DIM),
        ])


# --- 3 ORDERS -------------------------------------------------------------


def _orders_panel(buf, x0, y0, width, height, state) -> None:
    from broadside.sim.gundrill import DRILL, next_step
    from broadside.sim.systems.crew_tasks import manned_counts
    from broadside.sim.systems.signals import Signals

    world = state.world
    ship = state.player_ship
    w = _Writer(buf, x0, y0, width, height)
    heading = world.component_for_entity(ship, c.Heading).degrees
    helm = world.try_component(ship, c.Helm)
    orders = world.try_component(ship, c.ShipOrders)
    trim = world.component_for_entity(ship, c.SailPlan).trim
    w.rule("Standing orders")
    if helm is not None:
        want = helm.desired_heading
        off = abs(((want - heading + 180) % 360) - 180)
        w.spans([("Course  ", DIM), (f"{compass_32(want)} {want:03.0f}", TEXT), ("   coming round" if off > 2 else "   steady", DIM)])
        if helm.waypoints:
            w.spans([("        ", DIM), (f"steering for {len(helm.waypoints)} waypoint(s)  (g sets one)", DIM)])
        if helm.aground:
            w.line("        AGROUND", fg=(240, 120, 100))
    w.spans([("Sail    ", DIM), (sail_setting_name(trim), TEXT), (f"   {trim * 100:.0f}%   (w / s)", DIM)])
    w.spans([("Point   ", DIM), (point_of_sail(heading, state.wind.current.direction_degrees), TEXT)])
    if orders is not None:
        w.spans([("Quarters", DIM), ("  BEAT TO QUARTERS" if orders.quarters else "  no  (b)", (245, 170, 110) if orders.quarters else DIM)])
        w.spans([("Guns    ", DIM), ("  firing as they bear" if orders.fire_at_will else "  waiting for your word  (F, or [ / ])", (245, 170, 110) if orders.fire_at_will else DIM)])
        if orders.gun_target >= 0:
            nm = world.try_component(orders.gun_target, c.Name)
            since = state.now_s - orders.gun_target_since_s
            w.spans([("Target  ", DIM), (nm.full if nm else "named", TEXT), ("   word still passing along the deck" if since < 6 else "", DIM)])
        else:
            w.spans([("Target  ", DIM), ("whatever bears   (l, then x)", DIM)])
    sig = world.try_component(ship, Signals)
    if sig is not None and sig.hoisted:
        w.spans([("Signal  ", DIM), (f"No. {sig.hoisted} \"{sig.text}\"", TEXT)])
        w.line(f"        answered by {len(sig.acknowledged)}", fg=DIM)

    battery = world.try_component(ship, c.Battery)
    body = world.try_component(ship, c.ShipBody)
    if battery is not None and body is not None and battery.guns:
        w.rule("Battery")
        manned = manned_counts(state, ship)
        for side, label in ((-1, "Larboard"), (1, "Starboard")):
            guns = [g for g in battery.guns if body.layout.guns[g.index].side == side]
            deck = [g for g in guns if body.layout.guns[g.index].on_deck]
            ready = sum(1 for g in guns if g.loaded)
            crewed = sum(1 for g in deck if manned.get(g.index, 0) >= 2)
            key = "[" if side < 0 else "]"
            w.spans([(f"{label:<10}", DIM), (f"{ready}/{len(guns)} loaded  {crewed}/{len(deck)} manned", TEXT), (f"   {key}", DIM)])
        busy: dict = {}
        for g in battery.guns:
            if not body.layout.guns[g.index].on_deck:
                continue
            step = next_step(g)
            busy["ready" if step is None else step.label.lower()] = busy.get("ready" if step is None else step.label.lower(), 0) + 1
        order = ["ready"] + [st.label.lower() for st in DRILL]
        w.line("At the guns: " + ", ".join(f"{busy[k]} {k}" for k in order if k in busy), fg=DIM)

    w.rule("Contacts")
    contacts = world.try_component(ship, c.Contacts)
    shown = 0
    if contacts is not None:
        for ent, rec in sorted(contacts.records.items(), key=lambda kv: kv[1].last_seen_s, reverse=True):
            if w.full or shown > 8:
                break
            nm = world.try_component(ent, c.Name)
            fac = world.try_component(ent, c.Faction)
            age = state.now_s - rec.last_seen_s if rec.last_seen_s >= 0 else -1
            when = "in sight" if rec.status in ("hull", "topsails") else (f"{age:.0f} s ago" if age >= 0 else "reported")
            w.spans([(f"{nm.full if nm else '?':<22}", TEXT), (f"{rec.status:<9}", DIM), (when, DIM), (f"  {fac.name if fac else ''}", S.faction_color(fac.name) if fac else DIM)])
            shown += 1
    if shown == 0:
        w.line("nothing in sight", fg=DIM)


# --- 4 SHIP ---------------------------------------------------------------


def _ship_panel(buf, x0, y0, width, height, state, view, info) -> None:
    from broadside.sim.items import stores_summary

    inst_w = min(48, max(30, width // 2))
    draw_instruments(buf, x0, y0, inst_w, height, state)
    for yy in range(height):
        buf.set(x0 + inst_w, y0 + yy, "│", fg=(70, 70, 84), bg=BG)
    rx = x0 + inst_w + 1
    rw = width - inst_w - 1
    w = _Writer(buf, rx, y0, rw, height)
    world = state.world
    ship = state.player_ship
    nm = world.component_for_entity(ship, c.Name).full
    klass = world.component_for_entity(ship, c.ShipTag).ship_class
    hull = world.try_component(ship, c.Hull)
    w.spans([(nm, HEAD), (f"  {klass}", DIM)])
    if hull is not None:
        w.spans([("Hull  ", DIM), (f"{hull.length_m:.0f} x {hull.beam_m:.0f} m", TEXT), (f"   integrity {hull.integrity * 100:.0f}%", DIM)])
    company_n = sum(1 for _e, crew in world.get_component(c.CrewMember) if crew.ship == ship)
    on_deck = sum(1 for _e, (crew, _p) in world.get_components(c.CrewMember, c.DeckPosition) if crew.ship == ship)
    w.spans([("Crew  ", DIM), (f"{company_n} aboard", TEXT), (f"   {on_deck} on the weather deck", DIM)])
    w.rule("Stores")
    tot = stores_summary(world, ship)
    per_day = {"fresh water": 4.5 * company_n, "ship's biscuit": 1.0 * company_n, "rum": 0.5 * company_n}
    for k in ("fresh water", "ship's biscuit", "salt beef", "salt pork", "rum", "gunpowder", "powder cartridge"):
        if k not in tot or w.full:
            continue
        days = tot[k] / per_day[k] if k in per_day and per_day[k] > 0 else None
        w.spans([(f"{k:<17}", DIM), (f"{tot[k]:>8.0f}", TEXT), (f"  ~{days:.0f} days" if days else "", DIM)])
    shot = sum(v for k, v in tot.items() if "shot" in k)
    if shot:
        w.spans([(f"{'round shot':<17}", DIM), (f"{shot:>8.0f}", TEXT), ("  at the garlands", DIM)])
    w.rule("Sight")
    atm = state.atmosphere
    w.spans([("Visibility ", DIM), (f"{atm.effective_visibility_m() / 1000.0:.1f} km", TEXT)])
    if info is not None and info.eye is not None:
        w.spans([("Eye        ", DIM), (f"{info.eye.h:.1f} m above the water", TEXT)])
    w.spans([("Light      ", DIM), (f"{atm.light * 100:.0f}%", TEXT)])


# --- 5 KEYS ---------------------------------------------------------------


def _keys_panel(buf, x0, y0, width, height) -> None:
    w = _Writer(buf, x0, y0, width, height)
    w.spans([("Every control", HEAD), ("   the footer keeps only the few you need most", DIM)])
    keyw = max(10, min(16, max(len(k) for k, _ in KEY_HELP) + 1))
    for key, what in KEY_HELP:
        if w.full:
            break
        for i, ln in enumerate(textwrap.wrap(what, max(20, width - keyw - 4)) or [""]):
            if w.full:
                break
            w.spans([(f"{key if i == 0 else '':<{keyw}}", HEAD if i == 0 else DIM), (ln, TEXT)])
