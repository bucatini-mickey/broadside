# The five tutorial missions, in the order a man would actually learn them.
#
#   1  Ship handling: the wheel, the canvas, a course to steer, and coming
#      to an anchor off a port - and getting under way again.
#   2  A squadron of small craft: the signal book, a destination for the
#      whole force, and a line of battle.
#   3  Ship against ship: the approach, to arms, the guns laid, the word
#      given, and the fall of shot.
#   4  A squadron in action while you keep your distance and command it.
#   5  Stores and the state of the men: short allowance, grievance, and
#      what a captain can do about it.
#
# Every lesson passes on the ship's own state - nothing is scripted and
# nothing is taken on trust. They all run on the same Tutor as the original
# course (scenarios/tutorial.py), which is also what the menu launches
# (broadside/game.py).

from __future__ import annotations

import math

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.scenarios.tutorial import (
    Lesson,
    Tutor,
    _abeam,
    _at_the_wheel,
    _guns_manned,
    _heading,
    _lesson_at_least,
    _relative_bearing,
    _relative_wind,
    _signal_flying,
)
from broadside.sim import components as c
from broadside.sim.systems.captain_ai import ENGAGE, STATION, WITHDRAW, ShipCaptainAI
from broadside.sim.systems.seamanship import days_of_victuals, moored_to

QUAY_X, QUAY_Y = 0.0, 1500.0


def _orders(state):
    return state.world.component_for_entity(state.player_ship, c.ShipOrders)


def _speed(state) -> float:
    return state.world.component_for_entity(state.player_ship, c.Speed).knots


def _trim(state) -> float:
    return state.world.component_for_entity(state.player_ship, c.SailPlan).trim


def _pos(state):
    return state.world.component_for_entity(state.player_ship, c.WorldPosition)


def _range_to(state, other: int) -> float:
    a, b = _pos(state), state.world.component_for_entity(other, c.WorldPosition)
    return math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)


def _quay_range(state) -> float:
    p = _pos(state)
    return math.hypot(QUAY_X - p.x_m, QUAY_Y - p.y_m)


def _consorts(run) -> list:
    return list(run.squadron)


def _mission(state, ship: int) -> str:
    ai = state.world.try_component(ship, ShipCaptainAI)
    return "" if ai is None else ai.mission


def _course(run, lessons, done_text: str) -> None:
    run.tutor = Tutor(lessons=lessons, done_text=done_text)
    run.sim.every(0.5, run.tutor.tick)


# --- 1: ship handling, and a port ----------------------------------------


HANDLING = [
    Lesson(
        "walk",
        "You are a man on a deck",
        [
            "This is a cutter: one mast, eight guns, thirty hands. Everything larger works the same way, with more men to do it.",
            "Press m to take yourself in hand - the view closes in and follows you about. Walk with the arrow keys.",
            "Go to the wheel: right aft on the centreline. It is drawn as a wheel - a rim of dots round a hub.",
        ],
        _at_the_wheel,
        "That is your quarterdeck. From here you con the ship.",
        hint="Press m first; the wheel is aft - down the screen, since the bow is up.",
    ),
    Lesson(
        "levels",
        "Her levels: the ship is a stack of slices",
        [
            "What you are looking at is one level - the weather deck you are standing on. Her canvas is above it, so it is not in this picture; her hold is below it.",
            "Press z to cut the world into levels, then PgUp and PgDn to go up and down a metre at a time.",
            "Go up to her masthead and you will find her sails, and nothing else - like the leaves of a tree with the trunk far below. Go down and you are in the water, looking at her hull and the seabed.",
            "Look at one level above her deck and one below it, then press z to come back to the captain's eye.",
        ],
        lambda st, t: "level_above" in st.did and "level_below" in st.did,
        "That is how she is built: levels, one at a time, each showing only what is at that height. Her masts are in every one of them, as a tree's trunk is.",
        hint="z, then PgUp a few times to find the canvas, then PgDn past the deck into the hold.",
    ),
    Lesson(
        "steer",
        "The helm, and the binnacle",
        [
            "a and d put the helm over five degrees; A and D thirty. Her head comes round slowly - she is heavy and the water has to be pushed.",
            "The binnacle is on the strip above the panels, and in full on panel 5, SHIP.",
            "Bring her head to due north: 000, with the quay somewhere ahead of you.",
        ],
        lambda st, t: abs(((_heading(st) + 180.0) % 360.0) - 180.0) <= 12.0,
        "Steady as she goes.",
        hint="a turns to larboard, d to starboard. Watch the compass on the strip.",
    ),
    Lesson(
        "canvas",
        "Making sail",
        [
            "w sets more canvas, s takes it in. Her speed is the wind, her canvas and her heading together - you cannot sail into the wind's eye.",
            "Make all plain sail (w until she is at full) and get way on her: four knots will do.",
        ],
        lambda st, t: _trim(st) > 0.85 and _speed(st) >= 4.0,
        "Four knots and drawing well.",
        hint="Press w a few times and give her a moment - she takes time to gather way.",
    ),
    Lesson(
        "point_of_sail",
        "Points of sail",
        [
            "The pennant at the masthead gives the wind relative to the ship, which is what the sails care about.",
            "Put the wind on the quarter - abaft the beam, the fastest point of sailing. Use the helm, not the sails.",
        ],
        lambda st, t: 110.0 <= _relative_wind(st) <= 250.0 and _speed(st) >= 3.0,
        "That is her best point of sailing, and the way to make a passage.",
        hint="Turn until the wind is coming over one quarter - behind the beam but not dead astern.",
    ),
    Lesson(
        "course",
        "A course to steer",
        [
            "You need not stand at the wheel for every mile. Press l for the look cursor, put it where you want to be, and press g: the quartermaster will steer for it.",
            "Lay a course for the quay to the north of you, and close to within six cables.",
        ],
        lambda st, t: _quay_range(st) < 1100.0,
        "Well laid. She will hold that course while you see to other things.",
        hint="Press l, move the cursor onto the mole ahead with the arrows, then g. TAB switches panes if you want the chart.",
    ),
    Lesson(
        "approach",
        "The approach: take the way off her",
        [
            "You do not sail into a harbour under all plain sail. Carry canvas until you are nearly there, then shorten right in (s) and let her way carry her the rest.",
            "Come within two cables of the quay, under short canvas, with the way nearly off her: less than three knots.",
        ],
        lambda st, t: _quay_range(st) < 420.0 and _trim(st) <= 0.3 and _speed(st) <= 3.0,
        "Handsomely done - she has barely a ripple at the stem.",
        hint="s shortens sail. Mind that she carries her way for a long time with no canvas on her.",
    ),
    Lesson(
        "anchor",
        "Coming to an anchor",
        [
            "Press o to let go. She must be under short canvas and nearly stopped, or the anchor will not hold and you will drag.",
            "Let go, and lie to it.",
        ],
        lambda st, t: _orders(st).anchored and moored_to(st, st.player_ship, 600.0) is not None,
        "Brought up, and within a boat's pull of the mole. That is what docking is in these seas: you lie in the roads and the boats do the rest.",
        hint="o lets go the anchor. If she refuses, you still have too much canvas or too much way on her.",
    ),
    Lesson(
        "weigh",
        "Getting under way again",
        [
            "Weighing is the heaviest routine work in the ship: the whole watch at the capstan, a minute or more of it.",
            "Press o again to weigh, then make sail and stand out to sea - a mile off the quay.",
        ],
        lambda st, t: not _orders(st).anchored and _quay_range(st) > 1000.0 and _speed(st) >= 3.0,
        "Standing out, and you have handled her from the wheel to the anchor and back. That is the whole of ship handling.",
        hint="o weighs the anchor; then w for canvas and the helm to take you out.",
    ),
]


def _handling_scene(seed: int):
    b = SceneBuilder(seed, wind_from=250.0, wind_knots=11.0, start_hour=8.0)
    me = b.player("cutter_8", name="Wasp", heading_degrees=60.0, trim=0.25, crew=30, victual_days=20)
    b.set_speed(me, 2.0)
    # A port: a headland with a stone mole, to anchor in the roads of.
    b.island(QUAY_X + 260.0, QUAY_Y + 120.0, 190.0, peak_m=40.0, wooded=True, shoal_m=30.0)
    b.wall(QUAY_X, QUAY_Y, 90.0, length_m=70.0, thickness_m=4.0, height_m=4.0, name="the mole")
    run = b.build(duration_s=1800, checkpoints=[])
    _course(run, HANDLING, "That is ship handling. Mission 2 next: a squadron to command.")
    return run


@scenario(
    "tutorial_1_handling",
    "Tutorial 1: handling your ship",
    "A cutter, eight guns, and nobody to fight. The wheel, her levels, the binnacle, making and shortening "
    "sail, the points of sailing, laying a course by the cursor, and then the whole business of coming to "
    "an anchor off a port and weighing again. Nine lessons, each passed on the ship's own state.",
    look_for=[
        "Panel 1, LOG, is your tutor.",
        "o lets go the anchor and weighs it - she must be under short canvas and nearly stopped to let go.",
        "The mole is a stone wall on a generated headland; anchoring within a boat's pull of it is what docking means here.",
        "z cuts her into levels: the deck you stand on, her canvas above it, her hold and the seabed below.",
    ],
    duration_s=1800,
    interactive=True,
)
def tutorial_1_handling(seed: int = 1831):
    run = _handling_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Mission 1: handling her. Press m and walk to the wheel.", {"paused": True},
                   [expect("the course opens", _lesson_at_least(run, 0))]),
        Checkpoint(6, "The port to the north: a headland and a stone mole to anchor off.",
                   {"scale": "macro", "macro_zoom": 6}),
    ]
    return run


# --- 2: a squadron of small craft ----------------------------------------


SQUADRON = [
    Lesson(
        "book",
        "The signal book",
        [
            "You have two consorts, each with a captain of her own who can neither hear you nor read your mind. The only way to tell them anything is the signal book.",
            "Press 4 for the SIGNALS panel. The arrows choose a number, a changes who it is addressed to, ENTER makes the signal.",
            "The panel also shows each captain's skill, wit, dash and obedience - they are not alike, and it matters.",
            "Hoist anything at all to begin with: a hand must be sent to the locker, and it takes him time.",
        ],
        lambda st, t: _signal_flying(st) > 0,
        "Flying. Their lookouts must see it and their signal midshipmen must read it - which they may do wrong.",
        hint="Press 4, then ENTER on any number in the book.",
    ),
    Lesson(
        "line",
        "Form line of battle",
        [
            "A line of battle is not pageantry: it keeps every ship's broadside clear of her own friends.",
            "Signal No. 2, form line of battle, to the squadron. Then watch a consort take station astern of you.",
        ],
        lambda st, t: any(_mission(st, s) == STATION for s in t.squadron),
        "She is taking her station. Each captain holds it as well as his seamanship allows.",
        hint="Panel 4, choose 'No. 2 - Form line of battle', addressed to the squadron, and press ENTER.",
    ),
    Lesson(
        "station",
        "In her station",
        [
            "Hold your own course and let her close. A sloop two cables astern of her senior officer is in line of battle.",
            "Give her time: she is working up on you with the canvas she has.",
        ],
        lambda st, t: any(
            _mission(st, s) == STATION and _range_to(st, s) < 420.0 for s in t.squadron
        ),
        "That is a line. Now the whole force moves as one.",
        hint="Keep a steady course and watch her come up on the chart. Signalling again only confuses her.",
    ),
    Lesson(
        "destination",
        "A destination for the force",
        [
            "Your own course is the squadron's course while they are in your wake: lay one and they follow.",
            "Press l, put the cursor well to the eastward, press g - and make all plain sail (w) so the force moves.",
        ],
        lambda st, t: _trim(st) > 0.8 and _speed(st) >= 4.0 and bool(
            st.world.component_for_entity(st.player_ship, c.Helm).waypoints
        ),
        "Standing east with your squadron in your wake. That is a force under way.",
        hint="l for the cursor, arrows to move it east, g to steer for it, w for canvas.",
    ),
    Lesson(
        "all_sail",
        "Make all sail - the whole squadron",
        [
            "A signal can tell them to do what you have just done. No. 5, make all sail, to the squadron.",
            "A dull or wilful captain may be slow about it. Obedience is a number in the panel, not an assumption.",
        ],
        lambda st, t: all(_trim_of(st, s) > 0.7 for s in t.squadron),
        "The whole force under all plain sail. You have commanded a squadron with flags and nothing else.",
        hint="Panel 4, 'No. 5 - Make all sail', addressed to the squadron.",
    ),
]


def _trim_of(state, ship: int) -> float:
    sp = state.world.try_component(ship, c.SailPlan)
    return 0.0 if sp is None else sp.trim


def _squadron_scene(seed: int):
    b = SceneBuilder(seed, wind_from=20.0, wind_knots=11.0, start_hour=9.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=90.0, trim=0.45, crew=44, victual_days=30)
    b.set_speed(me, 4.0)
    swift = b.ship("cutter_8", name="Swift", faction="british", x_m=-900.0, y_m=260.0,
                   heading_degrees=90.0, trim=0.5, crew=24, observers=True)
    hazard = b.ship("cutter_8", name="Hazard", faction="british", x_m=-1400.0, y_m=-180.0,
                    heading_degrees=90.0, trim=0.5, crew=24, observers=True)
    for s in (swift, hazard):
        b.set_speed(s, 4.0)
    run = b.build(duration_s=1800, checkpoints=[])
    run.squadron = [swift, hazard]
    _course(run, SQUADRON, "That is a squadron. Mission 3 next: ship against ship.")
    run.tutor.squadron = [swift, hazard]
    # Two captains who are not alike, so obedience is visibly a number.
    w = run.state.world
    a = w.component_for_entity(swift, ShipCaptainAI)
    a.skill, a.intelligence, a.discipline, a.aggression = 0.7, 0.75, 0.9, 0.3
    b2 = w.component_for_entity(hazard, ShipCaptainAI)
    b2.skill, b2.intelligence, b2.discipline, b2.aggression = 0.45, 0.4, 0.45, 0.8
    return run


@scenario(
    "tutorial_2_squadron",
    "Tutorial 2: commanding a squadron",
    "A brig and two cutters, and no enemy. The signal book, forming a line of battle, keeping station, "
    "laying a destination for the whole force, and making sail by signal - with two consort captains who "
    "are deliberately unalike, so that obedience is a number you can see rather than an assumption.",
    look_for=[
        "Panel 4, SIGNALS: the book, the addressee, what is flying, who has answered, and each captain's parameters.",
        "A signal takes a hand to the locker, time to be seen, and may be misread.",
        "Hazard's captain is a fire-eater with poor obedience; Swift's is steady. Watch the difference.",
    ],
    duration_s=1800,
    interactive=True,
)
def tutorial_2_squadron(seed: int = 1832):
    run = _squadron_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Mission 2: a squadron. Panel 4 is the signal book.", {"paused": True},
                   [expect("the course opens", _lesson_at_least(run, 0))]),
        Checkpoint(8, "Your two consorts astern and to leeward, waiting on your flags.",
                   {"scale": "macro", "macro_zoom": 6}),
    ]
    return run


# --- 3: ship against ship -------------------------------------------------


DUEL = [
    Lesson(
        "sight",
        "Know what you are looking at",
        [
            "A sail to the eastward. Before anything else, find out what she is: press t for the glass, then TAB to take the nearest ship into it and hold her there.",
            "The glass is held relative to your own head: left and right sweep, up and down tilt.",
        ],
        lambda st, t: st.did.get("glass_on", (0, -1))[1] == t.foe,
        "A brig, French colours, much your own force. This will be a fair fight.",
        hint="t raises the glass, TAB takes her into it. t again lowers it.",
    ),
    Lesson(
        "approach",
        "The approach: lay her abeam",
        [
            "Your guns point out of her sides. Nothing fires ahead, so a bow-on approach is a ship that cannot hurt anybody.",
            "Con her round until the enemy is on your beam - the chart draws your own beam lines to steer by.",
            "Close to within four cables as you do it.",
        ],
        lambda st, t: _abeam(_relative_bearing(st, t.foe), 28.0) and _range_to(st, t.foe) < 800.0,
        "She is abeam and within range. That is the position the whole approach is for.",
        hint="Use the helm. The dotted lines out from your ship on the chart are her beams.",
    ),
    Lesson(
        "quarters",
        "Beat to quarters",
        [
            "Press b. The drums beat, the messes are struck below, the bulkheads come down and the people run to their stations.",
            "It takes a minute or two in a well-worked ship, and nothing about a gun can be done until it is done.",
        ],
        lambda st, t: _orders(st).quarters and _guns_manned(st, 2) >= 2,
        "Cleared for action, and men at the guns.",
        hint="b beats to quarters. Panel 2, CREW, shows them running to their stations.",
    ),
    Lesson(
        "lay",
        "Tell the guns what to fire at",
        [
            "Press l, put the cursor on her, and press x: the word is passed along the deck and the gun captains lay their pieces for her range.",
            "A gun nobody has laid is still at point blank, whatever the range - which is how an unaimed opening broadside goes into the sea.",
        ],
        lambda st, t: _orders(st).gun_target == t.foe,
        "The word is passed. Quoins under the breeches, handspikes to train.",
        hint="l for the cursor, move it onto her, then x.",
    ),
    Lesson(
        "estimate",
        "Ask the gun captain what he thinks",
        [
            "Now that there is a man at the gun, you can ask him: press p.",
            "You get his arc through the glass, his splash on the chart, and his own doubt as a figure. A green crew's estimate is honestly vague - it is his opinion, not the truth.",
        ],
        lambda st, t: "estimate" in st.did,
        "That is what he believes. Whether he is right is another matter.",
        hint="p - but only once she is at quarters with men at the guns.",
    ),
    Lesson(
        "fire",
        "Give the word",
        [
            "] fires the starboard broadside, [ the larboard. The guns go off in a ripple down the side, not together.",
            "Give the word, and watch the fall of shot.",
        ],
        lambda st, t: t.rounds_fired(st) >= 1,
        "Well fired. Each gun must now be sponged, charged, wadded, shotted, rammed, run out, primed and laid again before it will speak.",
        hint="] for starboard, [ for larboard - whichever side she is on.",
    ),
    Lesson(
        "hurt",
        "Hurt her",
        [
            "Keep her abeam, keep the guns served, and keep firing. F gives the batteries leave to fire as they bear, which is what you want in a close action.",
            "Break her timbers.",
        ],
        lambda st, t: _hurt(st, t.foe) or t.rounds_fired(st) >= 12,
        "That is ship against ship: the approach, the position, the word, and the iron.",
        hint="F for fire at will, and hold your position on her beam.",
    ),
]


def _hurt(state, ship: int) -> bool:
    from broadside.sim.structure import StructureState

    ss = state.world.try_component(ship, StructureState)
    if ss is None:
        return False
    return bool((ss.integrity < 0.999)[ss.material >= 0].any())


class DuelTutor(Tutor):
    """The duel needs two facts the ship's state does not record - that you
    took her into the glass, and that you asked a gun captain for his
    estimate. Both are noted on the state by the app (`state.did`)."""

    def __init__(self, foe: int, **kw):
        super().__init__(**kw)
        self.foe = foe


def _duel_scene(seed: int):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=10.0, start_hour=10.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=80.0, trim=0.5, crew=44, victual_days=30)
    b.set_speed(me, 4.5)
    foe = b.ship("brig_14", name="Vigilante", faction="french", x_m=1500.0, y_m=250.0,
                 heading_degrees=260.0, trim=0.5, crew=40, observers=True)
    b.set_speed(foe, 4.0)
    w = b.world
    w.component_for_entity(me, c.Battery).verbose_drill = True
    run = b.build(duration_s=2400, checkpoints=[])
    run.foe = foe
    run.tutor = DuelTutor(foe=foe, lessons=DUEL,
                          done_text="That is a single-ship action. Mission 4 next: a squadron in action.")
    run.sim.every(0.5, run.tutor.tick)
    ai = w.component_for_entity(foe, ShipCaptainAI)
    ai.skill, ai.intelligence, ai.aggression, ai.caution = 0.55, 0.6, 0.6, 0.45
    return run


@scenario(
    "tutorial_3_duel",
    "Tutorial 3: ship against ship",
    "Your brig against an equal French brig, met on opposite courses. Identify her through the glass, con "
    "her onto your beam, beat to quarters, pass the word to the gun captains, ask one of them where his "
    "shot would go, and then give the word to fire - and keep firing until her timbers start.",
    look_for=[
        "Nothing fires ahead: the approach exists to put her on your beam.",
        "p is only to be had at quarters, with a man at a loaded gun - it is his estimate, not the game's.",
        "Her captain has a mind of his own and will be working for the same position you are.",
    ],
    duration_s=2400,
    interactive=True,
)
def tutorial_3_duel(seed: int = 1833):
    run = _duel_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Mission 3: a sail to the eastward. Raise the glass (t) and TAB her into it.", {"paused": True},
                   [expect("the course opens", _lesson_at_least(run, 0))]),
        Checkpoint(10, "Both brigs closing on opposite courses.", {"scale": "macro", "macro_zoom": 6}),
    ]
    return run


# --- 4: a squadron in action ----------------------------------------------


FLEET = [
    Lesson(
        "report",
        "Tell them what you see",
        [
            "You are to windward with two consorts, and there are two Frenchmen to leeward. You will fight this one with flags.",
            "Signal No. 4, enemy in sight, to the squadron: every captain should know what you know.",
        ],
        lambda st, t: _signal_flying(st) > 0 or t.signals_made >= 1,
        "Made. Their lookouts have it.",
        hint="Panel 4, 'No. 4 - Enemy in sight', to the squadron, ENTER.",
    ),
    Lesson(
        "engage",
        "Order them in",
        [
            "Signal No. 1, engage the enemy more closely. Then let them. A captain who is being commanded at every minute is no use to anybody.",
            "Watch a consort bear down on the enemy on her own account.",
        ],
        lambda st, t: any(_mission(st, s) in (ENGAGE,) for s in t.squadron),
        "She is going in. Her captain chooses his own range, his own side and his own moment.",
        hint="Panel 4, 'No. 1 - Engage the enemy more closely', to the squadron.",
    ),
    Lesson(
        "stand_off",
        "Keep your own distance",
        [
            "A senior officer who lays his own ship alongside can see nothing and command nobody. Stay out of it: more than six cables from either Frenchman.",
            "Shorten sail if you must. Hold off while your consorts fight.",
        ],
        lambda st, t: t.stood_off_s >= 45.0,
        "That is command rather than fighting: you can see the whole action and they can see your flags.",
        hint="Put the helm over and shorten sail (s) to stay back. The chart shows the ranges.",
    ),
    Lesson(
        "recall",
        "Call her off",
        [
            "A consort too far gone to fight is worth more afloat than sunk. Signal No. 9, discontinue the action - to one ship, by name.",
            "Press a in the SIGNALS panel to change the addressee until it names a ship instead of the squadron.",
        ],
        lambda st, t: t.recalled,
        "Made to her alone. Whether she obeys is a question of her captain's discipline, which you can read in the panel.",
        hint="Panel 4, 'No. 9 - Discontinue the action', then a to address it to one ship.",
    ),
    Lesson(
        "outcome",
        "The action, and what came of it",
        [
            "Let it play out. Watch the log: hits, hurts, a captain breaking off, a ship hauling out of the line.",
            "This is what fleet command is - judgement, flags, and waiting.",
        ],
        lambda st, t: any(_mission(st, s) in (WITHDRAW,) for s in t.squadron) or t.now_minus_start(st) > 240.0,
        "That is a squadron in action under your flags.",
        hint="Nothing to press. Watch the log and the chart.",
    ),
]


class FleetTutor(Tutor):
    def __init__(self, squadron: list, enemies: list, **kw):
        super().__init__(**kw)
        self.squadron = list(squadron)
        self.enemies = list(enemies)
        self.signals_made = 0
        self.recalled = False
        self.stood_off_s = 0.0
        self._start_s = None

    def now_minus_start(self, state) -> float:
        if self._start_s is None:
            self._start_s = state.now_s
        return state.now_s - self._start_s

    def tick(self, state) -> None:
        from broadside.sim.systems.signals import Signals

        sig = state.world.try_component(state.player_ship, Signals)
        if sig is not None and sig.hoisted:
            self.signals_made = max(self.signals_made, 1)
            # No. 9, discontinue the action, addressed to one ship by name.
            if sig.hoisted == 9 and sig.to_ship >= 0:
                self.recalled = True
        # Standing off is a thing you keep doing, not a thing you do once.
        if self.i >= 2:
            near = min((_range_to(state, e) for e in self.enemies), default=1e9)
            if near > 1100.0:
                self.stood_off_s += 0.5
            else:
                self.stood_off_s = max(0.0, self.stood_off_s - 0.5)
        super().tick(state)


def _fleet_scene(seed: int):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=12.0, start_hour=11.0)
    me = b.player("frigate_38", name="Kestrel", heading_degrees=135.0, trim=0.5, crew=120, victual_days=40)
    b.set_speed(me, 5.0)
    swift = b.ship("brig_14", name="Swift", faction="british", x_m=-300.0, y_m=-500.0,
                   heading_degrees=135.0, trim=0.55, crew=44, observers=True)
    hazard = b.ship("brig_14", name="Hazard", faction="british", x_m=-700.0, y_m=-900.0,
                    heading_degrees=135.0, trim=0.55, crew=44, observers=True)
    for s in (swift, hazard):
        b.set_speed(s, 5.0)
    foe1 = b.ship("brig_14", name="Vigilante", faction="french", x_m=1800.0, y_m=1500.0,
                  heading_degrees=300.0, trim=0.5, crew=40, observers=True)
    foe2 = b.ship("cutter_8", name="Guepe", faction="french", x_m=2200.0, y_m=1900.0,
                  heading_degrees=300.0, trim=0.5, crew=24, observers=True)
    run = b.build(duration_s=2400, checkpoints=[])
    run.squadron = [swift, hazard]
    run.enemies = [foe1, foe2]
    run.tutor = FleetTutor(squadron=run.squadron, enemies=run.enemies, lessons=FLEET,
                           done_text="That is fleet command. Mission 5 next: the state of your ship and her people.")
    run.sim.every(0.5, run.tutor.tick)
    w = run.state.world
    for ship, (skill, wit, dash, disc) in ((swift, (0.7, 0.7, 0.55, 0.85)), (hazard, (0.5, 0.45, 0.85, 0.4))):
        ai = w.component_for_entity(ship, ShipCaptainAI)
        ai.skill, ai.intelligence, ai.aggression, ai.discipline = skill, wit, dash, disc
    return run


@scenario(
    "tutorial_4_fleet_action",
    "Tutorial 4: a squadron in action",
    "A frigate and two brigs against two Frenchmen, and your own ship is not to be in the thick of it. "
    "Report the enemy, order the squadron in, keep your distance so that you can see and be seen, call a "
    "consort off by name, and watch what captains with different discipline make of your flags.",
    look_for=[
        "Keeping out of it is the lesson: a senior officer alongside the enemy commands nobody.",
        "Signals can be addressed to one ship (a) or to the whole squadron.",
        "Hazard's captain has poor discipline; a recall may not be obeyed at once.",
    ],
    duration_s=2400,
    interactive=True,
)
def tutorial_4_fleet_action(seed: int = 1834):
    run = _fleet_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Mission 4: your squadron to windward, two Frenchmen to leeward.", {"paused": True},
                   [expect("the course opens", _lesson_at_least(run, 0))]),
        Checkpoint(10, "The two forces, and the weather gage in your hands.",
                   {"scale": "macro", "macro_zoom": 7}),
    ]
    return run


# --- 5: stores and the state of the men ----------------------------------


SUPPLIES = [
    Lesson(
        "stores",
        "What is in the hold",
        [
            "Nine weeks out, no port within reach, and the bread is going. Panel 5, SHIP, gives the stores and the days remaining.",
            "Panel 2, CREW, gives the men: their morale, their grievances, who is sick and who is sullen.",
            "Put her on two-thirds allowance - press r. The stores go half again as far, and the men will mind it.",
        ],
        lambda st, t: _orders(st).short_allowance,
        "Short allowance it is. The purser is content and nobody else is.",
        hint="r puts her on short allowance and takes her off again.",
    ),
    Lesson(
        "stretch",
        "Stretching the stores",
        [
            "Watch the days remaining in panel 5 lengthen. That is the whole of it: hunger now against starvation later.",
            "Hold her on short allowance until the provisions will see you to twenty days.",
        ],
        lambda st, t: days_of_victuals(st, st.player_ship) >= 20.0,
        "Twenty days in hand. That is a passage you can make.",
        hint="Keep her on short allowance (r) - the figure in panel 5 includes the allowance you have set.",
    ),
    Lesson(
        "grievance",
        "The men mind it",
        [
            "Grievance is not a mood, it is an account they keep. Watch the company's temper in panel 2 while they are on short commons.",
            "Let it run. You will see the grumbling in the log.",
        ],
        lambda st, t: t.grievance_rose(st),
        "That is what a sullen ship's company looks like in the numbers.",
        hint="Nothing to press. Give it a few minutes of ship's time - or press > to run time faster.",
    ),
    Lesson(
        "mainbrace",
        "What a captain can do about it",
        [
            "You cannot conjure beef out of the sea. You can give them a drink, and be seen to do it.",
            "Press G: splice the mainbrace, an extra issue of grog out of your own goodwill. It costs rum out of the hold.",
        ],
        lambda st, t: _orders(st).spliced_at_s > 0.0,
        "A cheer, and a different ship's company for the rest of the day. It will not last, and you cannot do it every hour.",
        hint="G splices the mainbrace. There must be rum left in the hold.",
    ),
    Lesson(
        "full",
        "And when you can, feed them",
        [
            "Short allowance is a thing you do because you must, not because it is clever. The day you can give them a full ration, give it.",
            "Press r again and take her off short allowance.",
        ],
        lambda st, t: not _orders(st).short_allowance,
        "Full allowance. That is the last of the lessons: her stores and her people are as much your command as her guns.",
        hint="r takes her off short allowance.",
    ),
]


class SuppliesTutor(Tutor):
    base_grievance = None

    def grievance_rose(self, state) -> bool:
        """Not a threshold but a rise: whatever this company started at,
        short commons must be seen to be making it worse."""
        if self.base_grievance is None:
            self.base_grievance = self.grievance(state)
        return self.grievance(state) > self.base_grievance + 0.008

    def grievance(self, state) -> float:
        from broadside.sim.people import components as pc

        vals = [
            psy.grievance
            for _e, (psy, crew) in state.world.get_components(pc.Psyche, c.CrewMember)
            if crew.ship == state.player_ship
        ]
        return sum(vals) / len(vals) if vals else 0.0


def _supplies_scene(seed: int):
    b = SceneBuilder(seed, wind_from=200.0, wind_knots=9.0, start_hour=14.0)
    # Nine weeks out: victualled thin to begin with, and a tired company.
    me = b.player("brig_14", name="Kestrel", heading_degrees=250.0, trim=0.45, crew=44, victual_days=14)
    b.set_speed(me, 4.0)
    run = b.build(duration_s=2400, checkpoints=[])
    w = run.state.world
    from broadside.sim.people import components as pc

    for _e, (psy, crew) in w.get_components(pc.Psyche, c.CrewMember):
        if crew.ship == me:
            psy.grievance = min(1.0, psy.grievance + 0.12)
            psy.morale = min(1.0, max(-1.0, psy.morale - 0.35))
    run.tutor = SuppliesTutor(lessons=SUPPLIES,
                              done_text="That is the course. Try the sandbox, or the scenario library, next.")
    run.sim.every(0.5, run.tutor.tick)
    return run


@scenario(
    "tutorial_5_supplies",
    "Tutorial 5: stores, and the state of your people",
    "Nine weeks out with thirteen days of provisions and a sullen company. Read the hold and the company, "
    "put her on two-thirds allowance to stretch the stores, watch the grievance that buys you, splice the "
    "mainbrace to buy some of it back, and give them a full ration again when you can.",
    look_for=[
        "r sets two-thirds allowance; the days remaining in panel 5 account for it.",
        "G splices the mainbrace: real rum out of the hold, and the same appraisal the daily issue makes.",
        "Grievance is an account the men keep, not a mood - it is what mutinies are made of.",
    ],
    duration_s=2400,
    interactive=True,
)
def tutorial_5_supplies(seed: int = 1835):
    run = _supplies_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Mission 5: thirteen days of provisions and a sullen company.", {"paused": True},
                   [expect("the course opens", _lesson_at_least(run, 0))]),
        Checkpoint(8, "Her people, in panel 2: morale, grievances, who is sick.",
                   {"paused": True}),
    ]
    return run


COURSES = [
    ("tutorial_1_handling", "1. Handling your ship", "The wheel, the canvas, a course to steer, and coming to an anchor off a port."),
    ("tutorial_2_squadron", "2. Commanding a squadron", "The signal book, a line of battle, and a destination for the whole force."),
    ("tutorial_3_duel", "3. Ship against ship", "The approach, to arms, the guns laid, the word given, and the fall of shot."),
    ("tutorial_4_fleet_action", "4. A squadron in action", "Order them in, keep your distance, and command with flags."),
    ("tutorial_5_supplies", "5. Stores and your people", "Short allowance, grievance, and what a captain can do about it."),
]
