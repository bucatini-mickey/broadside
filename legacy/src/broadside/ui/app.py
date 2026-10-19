# The interactive terminal app: runs a scenario (or any ScenarioRun) with
# the full engine - live captain's-eye view, planning mode, both scales,
# orders, a look cursor.
#
# Time model, Dwarf-Fortress style: SPACE stops time and enters planning
# mode, where your own ship is shown in its entirety and orders can be
# given (they take effect in the sim immediately, but nothing moves until
# time runs again). SPACE again resumes the captain's-eye live view.

from __future__ import annotations

import math
import sys
import time

from blessed import Terminal

from broadside.render.buffer import ScreenBuffer
from broadside.render.terminal import TerminalRenderer
from broadside.sim import components as c
from broadside.sim.entities import find_observer
from broadside.sim.systems.sighting import observer_eye
from broadside.view.hud import describe_point
from broadside.view.panels import UIState, company
from broadside.view.screen import compose_screen

KEYS_HELP = (
    "SPC pause  TAB focus  1-5 panels (5 = all keys)  m WALK as the captain  "
    "a/d helm  w/s sail  b quarters  [ ] fire  F at-will  l look  x target  p shot  t GLASS  o anchor  z levels  < > time  q quit"
)
WALK_HELP = (
    "WALKING: arrows/hjkl step  e what can I do here (then 1-9)  m stop walking  "
    "SPC pause  TAB focus  q quit"
)

SPEEDS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
MIN_W, MIN_H = 120, 40
ROTATIONS = {"local": ["ship", "north", "bow"], "macro": ["north", "ship"]}
FOCUS_ORDER = ["deck", "chart", "panel"]
# Walking the deck: three cells to the metre, so a man is a glyph in a
# world of half-metre planks, and the view goes with him.
WALK_SUBCELL = 5
# Draw as fast as the machine will go, up to this. Simulated time is fixed
# at clock.tick_seconds a step and accumulated against real elapsed time, so
# a faster screen never means a faster ship - it only means smoother
# motion. (tests/test_panels.py holds that to be true.)
MAX_FPS = 120.0


class App:
    def __init__(self, run, scenario=None, term: Terminal | None = None):
        self.run = run
        self.sim = run.sim
        self.state = run.sim.state
        self.deck = run.deck
        self.chart = run.chart
        self.chart.memory = self.deck.memory
        self.focus = "deck"
        self.scenario = scenario
        self.term = term or Terminal()
        self.renderer = TerminalRenderer(self.term)
        self.look = False
        self.walk = False
        self.ui = UIState()
        self._walk_saved = None
        self.menu: list = []
        self.speed_i = SPEEDS.index(1.0)
        self.state.clock.time_scale = 1.0
        self._acc = 0.0
        self._last_info = None
        self.message = ""
        self.fps = 0.0
        self._frame_times: list = []
        self.look_out = None  # a Look while the captain is looking out
        # Show the gun captain's estimate of where the shot would fall,
        # before the word to fire is given.
        self.preview = False

    @property
    def view(self):
        """The scene pane the view keys act on. With the panel focused they
        still act on the ship pane, which is what you are looking at."""
        return self.chart if self.focus == "chart" else self.deck

    def _both(self, **kw) -> None:
        for v in (self.deck, self.chart):
            for k, val in kw.items():
                setattr(v, k, val)

    # --- input ------------------------------------------------------------

    def handle(self, key) -> bool:
        """Apply one keypress. Returns False to quit."""
        # A Keystroke is a str subclass: a named key (an arrow) can have an
        # empty string body, so test the name too before dismissing it.
        if key is None or (not key and not getattr(key, "name", None)):
            return True
        k = key.name if getattr(key, "is_sequence", False) else str(key)
        st, view, world = self.state, self.view, self.state.world
        ship = st.player_ship
        if k in ("q", "Q"):
            return False
        if self.look_out is not None and self._look_key(k):
            return True
        if self.walk and self._walk_key(k):
            return True
        if not self.walk and self.ui.select_panel(k):
            return True
        if self.focus == "panel" and self.ui.panel == "signals" and self._signal_key(k):
            return True
        if self.focus == "panel" and k in ("KEY_UP", "KEY_DOWN", "KEY_PGUP", "KEY_PGDOWN", "k", "j"):
            n = len(company(st, ship)) if self.ui.panel == "crew" else 999
            step = {"KEY_UP": -1, "k": -1, "KEY_DOWN": 1, "j": 1, "KEY_PGUP": -10, "KEY_PGDOWN": 10}[k]
            self.ui.move(step, n)
            return True
        if k == " ":
            self._both(paused=not self.deck.paused)
            self.message = "PLANNING - time stopped. Orders take effect when you resume." if self.deck.paused else ""
        elif k in ("\t", "KEY_TAB"):
            if self.look:
                view.cursor = None
            self.focus = FOCUS_ORDER[(FOCUS_ORDER.index(self.focus) + 1) % len(FOCUS_ORDER)]
            if self.look:
                self._cursor_to_ship()
        elif k in ("+", "="):
            view.zoom(-1)
        elif k in ("-", "_"):
            view.zoom(1)
        elif k == "r":
            opts = ROTATIONS[view.scale]
            view.rotation = opts[(opts.index(view.rotation) + 1) % len(opts)] if view.rotation in opts else opts[0]
        elif k == "c":
            if view.scale == "local":
                view.square_local = not view.square_local
            else:
                view.square_macro = not view.square_macro
        elif k == "o":
            self._both(observer="lookout" if self.deck.observer == "captain" else "captain")
        elif k == "v":
            self._both(reveal=not self.deck.reveal)
        elif k in ("a", "d", "A", "D"):
            helm = world.component_for_entity(ship, c.Helm)
            step = {"a": -5, "d": 5, "A": -30, "D": 30}[k]
            helm.waypoints = []
            helm.desired_heading = (helm.desired_heading + step) % 360.0
        elif k in ("w", "s"):
            sail = world.component_for_entity(ship, c.SailPlan)
            now = sail.ordered if sail.ordered >= 0 else sail.trim
            sail.ordered = max(0.0, min(1.0, round(now + (0.1 if k == "w" else -0.1), 2)))
            self.message = "Make sail!" if k == "w" else "Shorten sail!"
        elif k == "b":
            orders = world.component_for_entity(ship, c.ShipOrders)
            orders.quarters = not orders.quarters
            self.message = "Beat to quarters!" if orders.quarters else "Stand down."
        elif k in ("[", "]"):
            orders = world.component_for_entity(ship, c.ShipOrders)
            orders.fire_side = -1 if k == "[" else 1
            self.message = "Fire larboard battery!" if k == "[" else "Fire starboard battery!"
        elif k == "F":
            # Hand the guns over to their captains: each fires as she comes
            # ready and bears, instead of waiting for your word.
            orders = world.component_for_entity(ship, c.ShipOrders)
            orders.fire_at_will = not orders.fire_at_will
            self.message = "Fire as they bear!" if orders.fire_at_will else "Cease fire - wait for my word."
            st.say(self.message, "order")
        elif k in ("<", ",", ">", "."):
            self.speed_i = max(0, min(len(SPEEDS) - 1, self.speed_i + (-1 if k in ("<", ",") else 1)))
            st.clock.time_scale = SPEEDS[self.speed_i]
        elif k == "m":
            self._toggle_walk()
        elif k == "l":
            self.look = not self.look
            if self.look and view.cursor is None:
                self._cursor_to_ship()
            if not self.look:
                view.cursor = None
        elif k == "f":
            view.pan = (0.0, 0.0)
            if view.cursor is not None:
                self._cursor_to_ship()
        elif k in ("t", "T"):
            self._take_up_glass(glass=k == "t")
        elif k == "z":
            self._toggle_levels()
        elif k in ("KEY_PGUP", "KEY_PGDOWN") and self.deck.z_m is not None:
            from broadside.view.levels import LEVEL_STEP_M, clamp_level, level_label

            step = LEVEL_STEP_M if k == "KEY_PGUP" else -LEVEL_STEP_M
            self.deck.z_m = clamp_level(self.deck.z_m + step)
            self._note_level(self.deck.z_m)
            self.message = f"Level: {level_label(self.deck.z_m)}."
        elif k == "x":
            self._name_target()
        elif k == "p":
            if not self.preview and not self._ready_to_fire():
                # Nobody to ask: the guns are housed and the deck is clear.
                self.message = "There is no one at the guns to ask. Beat to quarters first (b)."
            else:
                self.preview = not self.preview
                if self.preview:
                    st.note("estimate")
                self.message = ("Your gun captain squints along the barrel and gives you his estimate."
                                if self.preview else "You leave the gun captains to it.")
            self._update_preview()
        elif k == "o":
            self._anchor()
        elif k == "r":
            orders = world.component_for_entity(ship, c.ShipOrders)
            orders.short_allowance = not orders.short_allowance
            from broadside.sim.systems.seamanship import days_of_victuals

            if orders.short_allowance:
                st.say("The purser is told to serve two-thirds allowance. The word goes round the messes.", "order")
                self.message = f"Short allowance: the stores will last {days_of_victuals(st, ship):.0f} days, and the men will mind it."
            else:
                st.say("Full allowance again.", "order")
                self.message = f"Full allowance: {days_of_victuals(st, ship):.0f} days of provisions."
        elif k == "G":
            from broadside.sim.systems.seamanship import splice_the_mainbrace

            self.message = splice_the_mainbrace(st, ship)
        elif k == "g":
            if view.cursor is not None:
                helm = world.component_for_entity(ship, c.Helm)
                helm.waypoints = [tuple(view.cursor)]
                self.message = f"Steering for the cursor ({view.cursor[0]:.0f}, {view.cursor[1]:.0f})."
        elif k in ("KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT", "h", "j", "k", "H", "J", "K", "L"):
            self._move(k)
        return True

    # --- walking the deck as the captain ---------------------------------

    def _me(self):
        from broadside.sim.entities import find_observer

        return find_observer(self.state.world, self.state.player_ship, "captain")

    # --- signalling the squadron ------------------------------------------

    def _signal_key(self, k: str) -> bool:
        """Keys inside the signal book: choose a signal, choose who it is
        for, and send a hand to make it."""
        from broadside.sim.systems.signals import SIGNAL_BOOK, make_signal
        from broadside.view.panels import signal_targets

        st = self.state
        book = sorted(SIGNAL_BOOK)
        if k in ("KEY_UP", "k", "KEY_DOWN", "j", "KEY_PGUP", "KEY_PGDOWN"):
            step = {"KEY_UP": -1, "k": -1, "KEY_DOWN": 1, "j": 1, "KEY_PGUP": -5, "KEY_PGDOWN": 5}[k]
            self.ui.move(step, len(book))
            return True
        if k == "a":
            targets = [ent for ent, _nm in signal_targets(st)]
            i = targets.index(self.ui.signal_to) if self.ui.signal_to in targets else 0
            self.ui.signal_to = targets[(i + 1) % len(targets)]
            nm = next(nm for ent, nm in signal_targets(st) if ent == self.ui.signal_to)
            self.message = f"Signals addressed to {nm}."
            return True
        if k in ("KEY_ENTER", chr(10), chr(13)):
            number = book[max(0, min(len(book) - 1, self.ui.signal_i))]
            self.message = make_signal(st, st.player_ship, number, self.ui.signal_to)
            return True
        return False

    # --- looking out ------------------------------------------------------

    def _take_up_glass(self, glass: bool = True) -> None:
        """Raise the glass (or just look out). Raising a glass is work: the
        captain is occupied with it, and sees a few degrees of the world
        instead of all of it."""
        from broadside.sim.actions import Activity
        from broadside.view.firstperson import GLASS_FOV_DEG, NAKED_FOV_DEG, Look

        st = self.state
        if self.look_out is not None:
            self.look_out = None
            self.chart.look_sector = None
            self.message = "You lower the glass."
            return
        if self.walk:
            # You cannot walk the deck and study the horizon at the same
            # time: the arrows belong to the glass while it is up.
            self._toggle_walk()
        heading = st.world.component_for_entity(st.player_ship, c.Heading).degrees
        bearing = heading
        if self.view.cursor is not None:
            from broadside.sim.units import bearing_degrees

            pos = st.world.component_for_entity(st.player_ship, c.WorldPosition)
            bearing = bearing_degrees(self.view.cursor[0] - pos.x_m, self.view.cursor[1] - pos.y_m)
        from broadside.view.orientation import relative_bearing

        self.look_out = Look(bearing_deg=bearing % 360.0, fov_deg=GLASS_FOV_DEG if glass else NAKED_FOV_DEG, glass=glass)
        self.look_out.relative_deg = relative_bearing(heading, bearing)
        # The chart marks where you are looking and how wide the field is.
        self._sync_look()
        me = self._me()
        if glass and me is not None and not st.world.has_component(me, Activity):
            st.world.add_component(me, Activity("Take up the glass", 2.5, 2.5, lambda s: None))
        self.message = ("You put the glass to your eye." if glass else "You look out over the rail.") + " Left/right sweep, up/down tilt, TAB takes the next ship, +/- the glass, t to lower."
        self._report_what_is_seen()

    def _sync_look(self) -> None:
        """Point the glass. The bearing you hold is relative to her head,
        so the view stays on what you were watching when the helm moves;
        and if you have a ship in the glass, it follows her."""
        look = self.look_out
        if look is None:
            return
        st = self.state
        heading = st.world.component_for_entity(st.player_ship, c.Heading).degrees
        if look.target >= 0:
            from broadside.view.orientation import bearing_and_range, relative_bearing

            her = st.world.try_component(look.target, c.WorldPosition)
            # From the eye, not from her centre: a glass is held at a man's
            # face, and at close quarters the two differ by degrees - enough
            # to put the ship you are watching outside a 7 degree field.
            obs = find_observer(st.world, st.player_ship, self.view.observer) or find_observer(st.world, st.player_ship, "captain")
            eye = observer_eye(st, obs) if obs is not None else None
            mine = st.world.try_component(st.player_ship, c.WorldPosition)
            here = (eye.x, eye.y) if eye is not None else (None if mine is None else (mine.x_m, mine.y_m))
            if her is None or here is None:
                look.target = -1
            else:
                bearing, _rng = bearing_and_range(here, (her.x_m, her.y_m))
                look.relative_deg = relative_bearing(heading, bearing)
        look.bearing_deg = (heading + look.relative_deg) % 360.0
        self.chart.look_sector = (look.bearing_deg, look.fov_deg)

    def _look_key(self, k: str) -> bool:
        from broadside.view.firstperson import GLASS_FOV_DEG, NAKED_FOV_DEG

        look = self.look_out
        # A sweep of a quarter of the field, whatever the glass: a strong
        # glass should not fling the world past you.
        fine = max(1.0, look.fov_deg / 8.0)
        sweep = {"KEY_LEFT": -fine, "h": -fine, "H": -fine * 6.0,
                 "KEY_RIGHT": fine, "l": fine, "L": fine * 6.0}
        tilt = {"KEY_UP": fine, "k": fine, "K": fine * 4.0,
                "KEY_DOWN": -fine, "j": -fine, "J": -fine * 4.0}
        if k in sweep:
            # Relative to her head, not to the compass.
            look.relative_deg = (look.relative_deg + sweep[k] + 180.0) % 360.0 - 180.0
            look.target = -1
            self._sync_look()
            self._report_what_is_seen()
            return True
        if k in tilt:
            # Up and down: the arrows belong to the glass while it is up,
            # which is why they no longer scroll the log underneath it.
            look.pitch_deg = max(-20.0, min(40.0, look.pitch_deg + tilt[k]))
            self.message = ("Glass level." if abs(look.pitch_deg) < 0.5
                            else f"Glass {abs(look.pitch_deg):.0f} deg {'up' if look.pitch_deg > 0 else 'down'}.")
            return True
        if k in ("	", "KEY_TAB"):
            self._next_in_glass()
            return True
        if k in ("+", "="):
            look.glass = True
            look.fov_deg = max(2.0, look.fov_deg / 2.0)
            self.chart.look_sector = (look.bearing_deg, look.fov_deg)
            self.message = f"Field of view {look.fov_deg:.0f} degrees."
            return True
        if k in ("-", "_"):
            look.fov_deg = min(NAKED_FOV_DEG, look.fov_deg * 2.0)
            look.glass = look.fov_deg < 30.0
            self.chart.look_sector = (look.bearing_deg, look.fov_deg)
            self.message = f"Field of view {look.fov_deg:.0f} degrees."
            return True
        if k == "f":
            look.relative_deg = 0.0
            look.pitch_deg = 0.0
            look.target = -1
            self._sync_look()
            self.message = "Glass dead ahead."
            return True
        return False

    def _next_in_glass(self) -> None:
        """Take the next ship in sight into the glass and hold her there."""
        from broadside.sim.systems.sighting import sight_ship
        from broadside.view.orientation import bearing_and_range, relative_bearing

        st, world = self.state, self.state.world
        look = self.look_out
        mine = world.component_for_entity(st.player_ship, c.WorldPosition)
        heading = world.component_for_entity(st.player_ship, c.Heading).degrees
        seen = []
        for ent, pos in world.get_component(c.WorldPosition):
            if ent == st.player_ship or not world.has_component(ent, c.ShipBody):
                continue
            if sight_ship(st, st.player_ship, ent) is None:
                continue
            bearing, rng = bearing_and_range((mine.x_m, mine.y_m), (pos.x_m, pos.y_m))
            seen.append((rng, ent, relative_bearing(heading, bearing)))
        if not seen:
            self.message = "Nothing in sight to take into the glass."
            return
        seen.sort()
        order = [ent for _d, ent, _r in seen]
        nxt = order[(order.index(look.target) + 1) % len(order)] if look.target in order else order[0]
        look.target = nxt
        st.note("glass_on", nxt)
        self._sync_look()
        name = world.try_component(nxt, c.Name)
        rng = next(d for d, ent, _r in seen if ent == nxt)
        rel = next(r for _d, ent, r in seen if ent == nxt)
        from broadside.view.orientation import aspect_words, range_words, relative_words

        her_heading = world.component_for_entity(nxt, c.Heading).degrees
        bearing = (heading + rel) % 360.0
        self.message = (f"In the glass: {name.full if name else 'a ship'}, {relative_words(rel)}, "
                        f"{range_words(rng)} - {aspect_words(her_heading, bearing)}.")

    def _report_what_is_seen(self) -> None:
        """What a look tells you, as opposed to what it draws: a glass is
        how a captain told a brig from a frigate, and at what distance."""
        from broadside.sim.systems.sighting import sight_ship
        from broadside.view.firstperson import ships_in_view

        st = self.state
        look = self.look_out
        me = self._me()
        if look is None or me is None:
            return
        eye = observer_eye(st, me)
        if eye is None:
            return
        from broadside.sim.sailplan import compass_32

        seen = 0
        for dist, ent, _off in ships_in_view(st, eye, look, st.world):
            if ent == st.player_ship:
                continue
            what = sight_ship(st, me, ent)
            if what == "none":
                continue
            nm = st.world.try_component(ent, c.Name)
            klass = st.world.try_component(ent, c.ShipTag)
            fac = st.world.try_component(ent, c.Faction)
            kind = (klass.ship_class.replace("_", " ") if klass else "sail")
            if look.glass:
                text = f"Through the glass: {nm.full if nm else 'a sail'}, a {kind}, {'hull up' if what == 'hull' else 'topsails only'}, bearing {compass_32(look.bearing_deg)}, about {dist:.0f} m."
            else:
                text = f"A {'hull' if what == 'hull' else 'sail'} in sight bearing {compass_32(look.bearing_deg)}, perhaps {dist / 100:.0f} cables off."
            st.say(text, "sight")
            seen += 1
            if seen >= 3:
                break

    def _note_level(self, z: float) -> None:
        """Record that he has looked at a level above the deck or below it:
        the z axis is the one thing a tutorial cannot check from the ship's
        own state, because looking is not doing."""
        body = self.state.world.try_component(self.state.player_ship, c.ShipBody)
        deck_h = 1.5 if body is None else float(body.layout.freeboard_m)
        if z > deck_h + 1.5:
            self.state.note("level_above", int(round(z)))
        elif z < deck_h - 1.0:
            self.state.note("level_below", int(round(z)))

    def _toggle_levels(self) -> None:
        """Cut the world into horizontal levels and scroll through them, or
        go back to the captain's-eye view. While time is stopped this is the
        plan of his own ship and the ground about her; with time running it
        is what he knows, not what he can see this instant."""
        from broadside.view.levels import deck_level_of, level_label

        if self.deck.z_m is None:
            self.deck.z_m = deck_level_of(self.state, self.state.player_ship)
            self.message = f"Levels: {level_label(self.deck.z_m)}. PgUp/PgDn to go up and down, z to leave."
        else:
            self.deck.z_m = None
            self.message = "Back to the captain's eye."

    def _toggle_walk(self) -> None:
        """Take the captain in hand, or let him be. Walking zooms the ship
        pane right in and pins it to him: he stays in the middle of the view
        and it goes where he goes, with only what he can see drawn."""
        deck = self.deck
        self.menu = []
        if not self.walk:
            me = self._me()
            if me is None:
                self.message = "There is no captain aboard to walk."
                return
            self._walk_saved = (deck.fit, deck.subcell, deck.local_zoom, deck.pan, deck.rotation, deck.square_local)
            deck.follow = me
            deck.fit = False
            deck.local_zoom = 0
            deck.subcell = WALK_SUBCELL
            deck.pan = (0.0, 0.0)
            deck.rotation = "ship"
            # True proportions this close in: a terminal cell is about twice
            # as tall as it is wide, so square cells mean a metre of deck
            # looks like a metre.
            deck.square_local = True
            self.walk = True
            self.focus = "deck"
            self.ui.panel = "log"
            self.message = "You take the deck yourself: arrows to walk, e for what you can do here."
            return
        deck.follow = -1
        if self._walk_saved is not None:
            deck.fit, deck.subcell, deck.local_zoom, deck.pan, deck.rotation, deck.square_local = self._walk_saved
            self._walk_saved = None
        self.walk = False
        self.message = "You return to conning the ship."

    def _walk_key(self, k: str) -> bool:
        from broadside.sim.actions import available_actions, start_action, step_actor

        me = self._me()
        if me is None:
            return False
        steps = {"KEY_UP": (0, -1), "k": (0, -1), "KEY_DOWN": (0, 1), "j": (0, 1),
                 "KEY_LEFT": (-1, 0), "h": (-1, 0), "KEY_RIGHT": (1, 0), "l": (1, 0),
                 "y": (-1, -1), "u": (1, -1), "b": (-1, 1), "n": (1, 1)}
        if k in steps:
            if self.deck.paused:
                # Planning mode stops time. Walking takes time, so it is
                # one of the things that stops: it was possible to pause
                # the ship and still stroll her deck, which made the pause
                # look broken.
                self.message = "Time is stopped. SPACE to let it run."
                return True
            # Screen is bow-up: up the screen is forward (+x on the deck
            # grid, which runs stern to bow), right is starboard (+y).
            dx, dy = steps[k]
            if not step_actor(self.state, me, -dy, dx):
                self.message = "Blocked."
            else:
                self.menu = []
            return True
        if k == "e":
            self.menu = available_actions(self.state, me)
            self.message = "Nothing to do here." if not self.menu else ""
            return True
        if k.isdigit() and self.menu:
            i = int(k) - 1
            if 0 <= i < len(self.menu):
                act = self.menu[i]
                if start_action(self.state, me, act):
                    self.message = f"{act.label}..."
                else:
                    self.message = "Can't do that now."
                self.menu = []
            return True
        return False

    def _menu_lines(self) -> list:
        from broadside.sim.actions import Activity

        me = self._me()
        if me is None:
            return []
        busy = self.state.world.try_component(me, Activity)
        if busy is not None:
            return ["Actions", f"{busy.label} ({busy.remaining_s:.1f} s left)"]
        if not self.menu:
            return ["Actions", "e: what can I do here?"]
        return ["Actions"] + [f"{i + 1}) {a.label}" + (f"  [{a.duration_s:.0f} s]" if a.duration_s else "") for i, a in enumerate(self.menu[:9])]

    def _name_target(self) -> None:
        """Tell the guns what to fire at: whatever the look cursor is over.
        Your gun captains take a while to take it in - the greener they are,
        the longer - and a gun that cannot bear on it lays on what she can."""
        from broadside.sim.voxels import VoxelStructure

        st, world = self.state, self.state.world
        if self.view.cursor is None:
            self.message = "Press l and put the cursor on what you want fired at."
            return
        cx, cy = self.view.cursor
        best, bd = -1, 1e18
        for ent, pos in world.get_component(c.WorldPosition):
            if ent == st.player_ship or not (world.has_component(ent, c.ShipBody) or world.has_component(ent, VoxelStructure)):
                continue
            d = (pos.x_m - cx) ** 2 + (pos.y_m - cy) ** 2
            if d < bd:
                best, bd = ent, d
        orders = world.component_for_entity(st.player_ship, c.ShipOrders)
        if best < 0 or bd > 400.0 ** 2:
            orders.gun_target = -1
            self.message = "Guns: fire at what bears."
            return
        orders.gun_target = best
        orders.gun_target_since_s = st.now_s
        name = world.try_component(best, c.Name)
        self.message = f"Guns to fire at {name.full if name else 'that'} - passing the word along the deck."
        st.say(f"'Fire at {name.full if name else 'her'}!' - the word is passed to the gun captains.", "order")

    def _ready_to_fire(self) -> bool:
        """Is anybody in a state to give you an estimate? A gun captain at
        a loaded gun with his crew about him is; a ship with her guns
        housed and her decks lumbered is not."""
        from broadside.sim.gundrill import crew_at_guns

        st, world = self.state, self.state.world
        orders = world.try_component(st.player_ship, c.ShipOrders)
        battery = world.try_component(st.player_ship, c.Battery)
        if orders is None or battery is None or not orders.quarters:
            return False
        if battery.abstract_crew:
            return any(g.loaded for g in battery.guns)
        crews = crew_at_guns(st, st.player_ship)
        specs = world.component_for_entity(st.player_ship, c.ShipBody).layout.guns
        for gs in battery.guns:
            if not gs.loaded:
                continue
            if not specs[gs.index].on_deck or crews.get(gs.index):
                return True
        return False

    def _anchor(self) -> None:
        """Let go, or weigh. The work itself is the sim's (systems/seamanship.py)."""
        st, world = self.state, self.state.world
        orders = world.component_for_entity(st.player_ship, c.ShipOrders)
        if orders.anchor_work_s > 0.0:
            self.message = f"They are at it now - {orders.anchor_work_s:.0f} seconds more."
            return
        orders.anchor = not orders.anchored
        self.message = "Let go the anchor." if orders.anchor else "Weigh anchor - hands to the capstan."

    def _update_preview(self) -> None:
        """Ask the gun captain where his shot would go. Cheap enough to do
        every frame: it is one ball integrated for a second or two, with no
        randomness - the scatter is reported as a figure instead."""
        from broadside.sim.gundrill import crew_at_guns
        from broadside.sim.people import components as pc
        from broadside.sim.systems.ballistics import gun_to_bear, predict_shot
        st, world = self.state, self.state.world
        if self.preview and not self._ready_to_fire():
            # The men have left their guns: the estimate goes with them.
            self.preview = False
        if not self.preview:
            self.chart.shot = None
            if self.look_out is not None:
                self.look_out.shot = None
            return
        orders = world.try_component(st.player_ship, c.ShipOrders)
        target = -1 if orders is None else orders.gun_target
        if target < 0 and self.look_out is not None:
            target = self.look_out.target
        mine = world.try_component(st.player_ship, c.WorldPosition)
        aim = None
        if target >= 0:
            hers = world.try_component(target, c.WorldPosition)
            if hers is not None:
                aim = (hers.x_m, hers.y_m)
        if aim is None and self.look_out is not None:
            # Nothing named: lay on the middle of the field, half a mile out.
            b = math.radians(self.look_out.bearing_deg)
            aim = (mine.x_m + math.sin(b) * 800.0, mine.y_m + math.cos(b) * 800.0)
        if aim is None:
            self.chart.shot = None
            return
        gi, train = gun_to_bear(st, st.player_ship, aim[0], aim[1])
        if gi < 0:
            self.chart.shot = None
            if self.look_out is not None:
                self.look_out.shot = None
            self.message = "No gun will bear that way."
            return
        # Whose estimate it is: the man at the breech, if there is one.
        skill = 0.4
        men = crew_at_guns(st, st.player_ship).get(gi) or []
        if men:
            sk = world.try_component(men[0][0], pc.Skills)
            if sk is not None:
                skill = sk.get("gunlaying")
        shot = predict_shot(st, st.player_ship, gi, train_deg=train, target=target, skill=skill)
        self.chart.shot = shot
        if self.look_out is not None:
            self.look_out.shot = shot

    def _cursor_to_ship(self) -> None:
        pos = self.state.world.component_for_entity(self.state.player_ship, c.WorldPosition)
        self.view.cursor = (pos.x_m, pos.y_m)

    def _move(self, k: str) -> None:
        info = self._last_info
        pane = None if info is None else (info.deck if self.focus == "deck" else info.chart)
        cam = pane.camera if pane is not None else None
        cell = cam.cell_m if cam else 1.0
        aspect = cam.aspect if cam else 1.0
        big = 10 if k in ("H", "J", "K", "L") else 1
        dcol, drow = {
            "KEY_LEFT": (-1, 0), "h": (-1, 0), "H": (-1, 0),
            "KEY_RIGHT": (1, 0), "L": (1, 0),
            "KEY_UP": (0, -1), "k": (0, -1), "K": (0, -1),
            "KEY_DOWN": (0, 1), "j": (0, 1), "J": (0, 1),
        }[k]
        import math

        rot = math.radians(cam.rotation if cam else 0.0)
        rx, ry = math.cos(rot), -math.sin(rot)
        ux, uy = math.sin(rot), math.cos(rot)
        dx = (dcol * rx - drow * aspect * ux) * cell * big
        dy = (dcol * ry - drow * aspect * uy) * cell * big
        if self.look and self.view.cursor is not None:
            cx, cy = self.view.cursor
            self.view.cursor = (cx + dx, cy + dy)
        else:
            px, py = self.view.pan
            self.view.pan = (px + dx, py + dy)

    # --- loop -------------------------------------------------------------

    def frame(self) -> None:
        term = self.term
        W, H = term.width, term.height
        buf = ScreenBuffer(W, H)
        if W < MIN_W or H < MIN_H:
            buf.draw_text(1, 1, f"Terminal too small: {W}x{H}. Please enlarge to at least {MIN_W}x{MIN_H}.", fg=(240, 200, 120))
            self.renderer.render(buf)
            return
        if self.look_out is not None:
            self._sync_look()
        # The chart runs a line of fire to whatever the guns are laid on.
        orders = self.state.world.try_component(self.state.player_ship, c.ShipOrders)
        self.chart.contact = -1 if orders is None else orders.gun_target
        self._update_preview()
        look_lines = self._menu_lines() if self.walk else None
        if self.look and self.view.cursor is not None:
            obs = find_observer(self.state.world, self.state.player_ship, self.view.observer)
            eye = observer_eye(self.state, obs) if obs is not None else None
            look_lines = describe_point(self.state, self.view, self.view.cursor[0], self.view.cursor[1], eye)
        keys = WALK_HELP if self.walk else KEYS_HELP
        footer = f"{self.message}   |  {keys}" if self.message else keys
        self.ui.fps = self.fps
        self._last_info = compose_screen(
            buf, self.state, self.deck, self.chart, scenario=self.scenario,
            look=look_lines, focus=self.focus, footer=footer, ui=self.ui,
            look_out=self.look_out,
        )
        self.renderer.render(buf)
        now = time.perf_counter()
        self._frame_times.append(now)
        if len(self._frame_times) > 20:
            del self._frame_times[:-20]
        if len(self._frame_times) > 2:
            span = self._frame_times[-1] - self._frame_times[0]
            self.fps = (len(self._frame_times) - 1) / span if span > 1e-6 else 0.0

    def advance(self, wall_dt: float) -> None:
        if self.deck.paused:
            self._acc = 0.0
            return
        tick = self.state.clock.tick_seconds
        self._acc += wall_dt * self.state.clock.time_scale
        # Don't spiral: if rendering is slow at high speed, drop time rather
        # than trying to catch up forever.
        self._acc = min(self._acc, tick * 60)
        while self._acc >= tick:
            self.sim.step()
            self._acc -= tick

    def main(self) -> None:
        term = self.term
        with term.fullscreen(), term.hidden_cursor(), term.cbreak():
            last = time.perf_counter()
            drawn = 0.0
            dims = (term.width, term.height)
            self.frame()
            while True:
                timeout = 0.25 if self.deck.paused else 0.001
                key = term.inkey(timeout=timeout)
                redraw = bool(key)
                while key:
                    if not self.handle(key):
                        return
                    key = term.inkey(timeout=0)
                now = time.perf_counter()
                self.advance(now - last)
                last = now
                if (term.width, term.height) != dims:
                    dims = (term.width, term.height)
                    self.renderer.force_full_redraw_next_frame()
                    redraw = True
                # Draw as often as the machine can, capped only so a fast
                # terminal doesn't spin for nothing. Simulated time does not
                # depend on this in any way.
                if redraw or (not self.deck.paused and now - drawn >= 1.0 / MAX_FPS):
                    drawn = now
                    self.frame()


def run_interactive(run, scenario=None) -> int:
    if not sys.stdout.isatty():
        print("broadside: stdout is not a terminal - run in a real terminal, or use the headless tools.", file=sys.stderr)
        return 1
    # Windows consoles may default to a legacy code page; the scene is full
    # of box-drawing and block glyphs.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    App(run, scenario).main()
    return 0
