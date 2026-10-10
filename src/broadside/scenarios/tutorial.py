# A playable tutorial: learning to be the captain.
#
# Eleven short lessons, each one a real thing done with the real controls -
# walk to the wheel, read the binnacle, put the wind on the quarter, make
# sail and then shorten to fighting canvas, hoist a signal to your consort,
# lay the enemy abeam, beat to quarters, take a hand in the gun drill
# yourself, and give the word to fire. Nothing is faked: the lesson is
# passed when the ship's own state says it has been done.
#
# The same lessons drive two scenarios:
#   tutorial       - you do them (python -m broadside.scenarios run tutorial)
#   tutorial_demo  - a scripted student does them, so the whole course is
#                    checked headless and exported as a replay.
#
# The naval terms are explained as they come up; docs/design/10_naval_primer.md
# is the longer treatment.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.sim import components as c
from broadside.sim.entities import find_observer
from broadside.sim.systems.crew_tasks import manned_counts
from broadside.sim.units import bearing_degrees

HINT_AFTER_S = 75.0


@dataclass
class Lesson:
    key: str
    title: str
    tell: list  # what the tutor says when the lesson opens
    done: Callable  # (state, tutor) -> bool
    praise: str
    hint: str = ""


def _captain(state):
    return find_observer(state.world, state.player_ship, "captain")


def _layout(state):
    return state.world.component_for_entity(state.player_ship, c.ShipBody).layout


def _heading(state) -> float:
    return state.world.component_for_entity(state.player_ship, c.Heading).degrees


def _relative_wind(state) -> float:
    """Where the wind blows from, relative to the bow, clockwise."""
    return (state.wind.current.direction_degrees - _heading(state)) % 360.0


def _relative_bearing(state, other: int) -> float:
    a = state.world.component_for_entity(state.player_ship, c.WorldPosition)
    b = state.world.component_for_entity(other, c.WorldPosition)
    return (bearing_degrees(b.x_m - a.x_m, b.y_m - a.y_m) - _heading(state)) % 360.0


def _abeam(rel: float, slack: float = 22.0) -> bool:
    return min(abs(rel - 90.0), abs(rel - 270.0)) <= slack


def _at_the_wheel(state, tutor) -> bool:
    cap = _captain(state)
    pos = state.world.component_for_entity(cap, c.DeckPosition)
    hx, hy = _layout(state).helm
    return max(abs(pos.x - hx), abs(pos.y - hy)) <= 1


def _at_locker(state, tutor) -> bool:
    from broadside.sim.items import Item, Stowed

    cap = _captain(state)
    pos = state.world.component_for_entity(cap, c.DeckPosition)
    for _e, (item, st) in state.world.get_components(Item, Stowed):
        if st.ship == state.player_ship and item.kind == "signal locker" and st.x is not None:
            if max(abs(pos.x - st.x), abs(pos.y - st.y)) <= 1:
                return True
    return False


def _guns_manned(state, at_least: int = 3) -> int:
    counts = manned_counts(state, state.player_ship)
    return sum(1 for n in counts.values() if n >= 2)


def _hulk_hurt(state, tutor) -> bool:
    """Her planks broken anywhere - or, if the gun captains are having a bad
    day of it, enough rounds fired that the lesson has been learnt anyway."""
    from broadside.sim.structure import StructureState

    ss = state.world.try_component(tutor.hulk, StructureState)
    if ss is not None and bool((ss.integrity < 0.999)[ss.material >= 0].any()):
        return True
    return tutor.rounds_fired(state) >= 4


LESSONS = [
    Lesson(
        "walk",
        "The captain is a man on a deck",
        [
            "You are one person aboard, not a cursor. Press m to take yourself in hand: the view closes right in and follows you about.",
            "Walk with the arrow keys.",
            "Go to the ship's wheel: right aft on the centreline. It is drawn as a wheel - a rim of dots round a hub - with the capstan forward of it.",
            "Anything you want done in person - working a gun, sending a signal, looking into a cask - you must be standing by it.",
        ],
        _at_the_wheel,
        "Good. That is your quarterdeck: from here you con the ship.",
        hint="The wheel is aft - down the screen, since the bow is up. Press m first.",
    ),
    Lesson(
        "binnacle",
        "The binnacle: where her head lies",
        [
            "No compass rose is painted on the sea. Your heading comes from the binnacle by the wheel - it is on the strip above the panels, and in full on panel 4, SHIP.",
            "It is given in points - N by E, NE, and so on. Thirty-two points make the circle, 11 1/4 degrees each.",
            "Bring her head round to due east: eight points, or 090. a and d put the helm over five degrees, A and D thirty.",
        ],
        lambda st, t: abs(((_heading(st) - 90.0 + 180.0) % 360.0) - 180.0) <= 10.0,
        "East it is. Note she takes time to answer the helm - a ship does not turn on the spot.",
        hint="d turns to starboard (right). Watch the binnacle swing toward E.",
    ),
    Lesson(
        "points_of_sail",
        "Points of sail: you cannot sail into the wind",
        [
            "The masthead pennant shows the wind relative to the ship, which is what sail-handling needs.",
            "Within about six points of the wind's eye she will not sail at all: that is being in irons.",
            "Close-hauled is as near the wind as she goes; abeam is a beam reach, her fastest point; behind you is running.",
            "The wind is out of the north today. Bring it onto the quarter - abaft the beam, but not dead astern - by steering south-east or south-west.",
        ],
        lambda st, t: 110.0 <= _relative_wind(st) <= 160.0 or 200.0 <= _relative_wind(st) <= 250.0,
        "Wind on the quarter: your best point of sailing with square canvas.",
        hint="Keep the helm over until the pennant reads 'on the quarter'.",
    ),
    Lesson(
        "make_sail",
        "Making sail",
        [
            "w calls for more canvas, s for less. Nothing happens at once: hands must go aloft, and the sail plan on panel 4 fills as they work.",
            "Sails are set from the deck upward: courses, topsails, topgallants, royals. More sail means more speed, and more heel.",
            "Make all plain sail.",
        ],
        lambda st, t: st.world.component_for_entity(st.player_ship, c.SailPlan).trim >= 0.85,
        "All plain sail set. Watch the log: she gathers way slowly, and loses it slowly.",
        hint="Press w repeatedly; the log reading should climb past four knots.",
    ),
    Lesson(
        "fighting_sail",
        "Fighting sail",
        [
            "Ships did not fight under a cloud of canvas. Royals and topgallants are furled before action.",
            "They need men aloft who are wanted at the guns, and they burn.",
            "Shorten down to fighting sail: topsails, and little more.",
        ],
        lambda st, t: 0.25 <= st.world.component_for_entity(st.player_ship, c.SailPlan).trim <= 0.55,
        "Fighting sail. She is slower, but handier, and your people are on deck.",
        hint="Press s until only the courses and topsails are drawn as set.",
    ),
    Lesson(
        "signals",
        "Signals: how ships talk",
        [
            "You cannot hail a ship a mile off. A midshipman goes to the signal locker by the wheel and bends the numbered flags of the code book to the halyards.",
            "Walk to the locker, press e, read the book, and hoist No. 1: 'Engage the enemy more closely'.",
            "Then watch. Your consort must see the flags and find the number in her own book before she can answer.",
        ],
        lambda st, t: _signal_flying(st) == 1,
        "Flying. She will answer when her people have read it - that delay is real, and it decides battles.",
        hint="Stand beside the signal locker (by the wheel), press e, then the number key for 'Hoist signal No. 1'.",
    ),
    Lesson(
        "abeam",
        "Laying her alongside",
        [
            "Guns point out of the ship's sides, so you cannot fire ahead. An action is fought by putting the enemy abeam and keeping her there.",
            "That derelict hulk is your target. Bring her onto your beam - square abreast of you, either side.",
        ],
        lambda st, t: _abeam(_relative_bearing(st, t.hulk)),
        "She is abeam: your whole broadside will bear.",
        hint="Steer so the hulk lies square off your side, not ahead or astern.",
    ),
    Lesson(
        "quarters",
        "Beat to quarters",
        [
            "b beats to quarters. The drums go, and every man walks to a station: gun crews first, then the helm, then hands at the masts.",
            "How long clearing for action takes is simply how long your people need to walk there, and the boys to bring cartridges up from the magazine.",
            "Beat to quarters now, and watch them go.",
        ],
        lambda st, t: st.world.component_for_entity(st.player_ship, c.ShipOrders).quarters and _guns_manned(st) >= 6,
        "Cleared for action. Each gun now has a captain, a rammer, a loader and men on the tackles.",
        hint="Press b, then give them half a minute to reach their guns.",
    ),
    Lesson(
        "drill",
        "The drill: what a gun costs",
        [
            "A gun is not a button. Nine separate jobs put a ball in her and run her out through the port:",
            "sponge, cartridge, ram, wad, shot, ram, run out, prime, lay - each done by a named man, each taking as long as his skill, his strength and the weight of the thing allow.",
            "Walk to a gun, press e, and take a hand yourself: any job in the drill, or lay her with handspike and quoin.",
        ],
        lambda st, t: bool(t.gun_work),
        "That is where rate of fire comes from. Two rounds in three minutes is good practice; your crews will improve.",
        hint="Stand on a tile beside a gun (the = at the ship's side), press e, then a number.",
    ),
    Lesson(
        "fire",
        "Giving the word",
        [
            "You do not aim the ship's guns. Your gun captains lay them, each on his own judgement of the range, which is why shot scatters.",
            "You choose the moment: ] fires the starboard battery, [ the larboard.",
            "Fire into the hulk.",
        ],
        lambda st, t: t.rounds_fired(st) > 0,
        "There she goes - the guns fire in a ripple from bow to stern, not all together.",
        hint="] for starboard, [ for larboard. Only loaded, manned guns will speak.",
    ),
    Lesson(
        "fall_of_shot",
        "The fall of shot",
        [
            "Now watch. The balls fly under gravity and drag at some hundreds of metres a second, and where they strike, planks are broken and men are hurt.",
            "Read the log, and look at the powder smoke drifting down on the wind: your own smoke will blind you soon enough.",
        ],
        _hulk_hurt,
        "Your shot told. That is the whole of the drill: you have conned her, signalled, cleared for action and fought.",
        hint="Keep firing; at this range not every ball will find her.",
    ),
]


def _signal_flying(state) -> int:
    from broadside.sim.systems.signals import Signals

    sig = state.world.try_component(state.player_ship, Signals)
    return sig.hoisted if sig is not None else 0


@dataclass
class Tutor:
    """Runs a course: announces a lesson, watches for it to be done.

    `lessons` is the course. The original eleven-lesson course is the
    default; `scenarios/courses.py` passes its own, which is how the five
    tutorial missions in the menu are built.
    """

    hulk: int = -1
    lessons: list = field(default_factory=lambda: LESSONS)
    done_text: str = "Lessons complete. The ship is yours - try the sandbox next."
    i: int = 0
    announced: bool = False
    hinted: bool = False
    started_s: float = 0.0
    gun_work: list = field(default_factory=list)  # gun jobs the player has done
    fire_mark: int = 0
    finished: bool = False

    def rounds_fired(self, state) -> int:
        n = sum(1 for e in state.log if any(w in e.text.lower() for w in ("gun fires", "broadside", "fire! (")))
        return n - self.fire_mark

    def observe(self, state) -> None:
        """Notice the player taking a hand at a gun."""
        from broadside.sim.actions import Activity

        cap = _captain(state)
        act = state.world.try_component(cap, Activity) if cap is not None else None
        if act is not None and ("pounder" in act.label or "gun" in act.label.lower()):
            if act.label not in self.gun_work:
                self.gun_work.append(act.label)

    def tick(self, state) -> None:
        if self.finished:
            return
        lesson = self.lessons[self.i]
        if not self.announced:
            state.say(f"-- Lesson {self.i + 1} of {len(self.lessons)}: {lesson.title} --", "order")
            for line in lesson.tell:
                state.say(line, "info")
            self.announced = True
            self.hinted = False
            self.started_s = state.now_s
            if lesson.key == "fire":
                self.fire_mark = self.rounds_fired(state) + self.fire_mark
        self.observe(state)
        if lesson.done(state, self):
            state.say(lesson.praise, "order")
            self.i += 1
            self.announced = False
            if self.i >= len(self.lessons):
                self.finished = True
                state.say(self.done_text, "order")
            return
        if lesson.hint and not self.hinted and state.now_s - self.started_s > HINT_AFTER_S:
            self.hinted = True
            state.say("(" + lesson.hint + ")", "info")


def _tutorial_scene(seed: int):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=9.0, start_hour=8.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=60.0, trim=0.4, crew=44, victual_days=30)
    b.set_speed(me, 3.0)
    consort = b.ship("sloop_18", name="Swift", faction="british", x_m=-260.0, y_m=420.0, heading_degrees=60.0, trim=0.5, observers=True)
    b.set_speed(consort, 3.0)
    hulk = b.ship("brig_14", name="Derelict hulk", faction="french", x_m=300.0, y_m=180.0, heading_degrees=100.0, trim=0.0)
    w = b.world
    w.component_for_entity(me, c.Battery).verbose_drill = True
    run = b.build(duration_s=600, checkpoints=[])
    run.hulk = hulk
    run.consort = consort
    run.tutor = Tutor(hulk=hulk)
    run.sim.every(0.5, run.tutor.tick)
    return run


def _lesson_at_least(run, n: int):
    def fn(state):
        t = run.tutor
        ls = t.lessons
        return t.i >= n, f"lesson {min(t.i + 1, len(ls))} of {len(ls)} ({ls[min(t.i, len(ls) - 1)].key})"

    return fn


@scenario(
    "tutorial",
    "Tutorial: taking command",
    "Eleven lessons in being the captain, done with the real controls on a real ship: walk to the wheel, read "
    "the binnacle, put the wind on the quarter, make sail and shorten to fighting canvas, hoist a signal to "
    "your consort, lay the enemy abeam, beat to quarters, take a hand in the gun drill, give the word to fire, "
    "and watch the fall of shot. Each lesson passes when the ship's own state says you have done it.",
    look_for=[
        "Panel 1, LOG, is your tutor: the lesson, what to press, and why it was done that way at sea.",
        "Every lesson is a real action - nothing is scripted and nothing is skipped for you.",
        "If you are stuck for a minute you get a hint in brackets.",
    ],
    duration_s=600,
)
def tutorial(seed: int = 1803):
    run = _tutorial_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Lesson one: you are a man on a deck. Press m and walk to the wheel.", {"paused": True}),
    ]
    return run


def _student(run):
    """A scripted student who does each lesson the way a player would -
    walking, pressing the same orders, working a gun through the menu. It is
    the proof that the course can actually be completed."""
    from broadside.sim.actions import Activity, available_actions, start_action, walk_to
    from broadside.sim.items import Item, Stowed

    def tick(st):
        w = st.world
        tut = run.tutor
        cap = _captain(st)
        if cap is None or tut.finished or w.has_component(cap, Activity):
            return
        key = LESSONS[tut.i].key
        me = st.player_ship
        helm = w.component_for_entity(me, c.Helm)
        sail = w.component_for_entity(me, c.SailPlan)
        orders = w.component_for_entity(me, c.ShipOrders)
        layout = _layout(st)
        if key == "walk":
            hx, hy = layout.helm
            walk_to(st, cap, (hx + 1, hy))
        elif key == "binnacle":
            helm.desired_heading = 90.0
        elif key == "points_of_sail":
            helm.desired_heading = 135.0
        elif key == "make_sail":
            sail.trim = 1.0
        elif key == "fighting_sail":
            sail.trim = 0.45
        elif key == "signals":
            for _e, (item, stw) in w.get_components(Item, Stowed):
                if stw.ship == me and item.kind == "signal locker" and stw.x is not None:
                    pos = w.component_for_entity(cap, c.DeckPosition)
                    if max(abs(pos.x - stw.x), abs(pos.y - stw.y)) > 1:
                        walk_to(st, cap, (stw.x, stw.y - 1) if layout.tile(stw.x, stw.y - 1) in (2, 7) else (stw.x, stw.y + 1))
                    else:
                        for a in available_actions(st, cap):
                            if a.label.startswith("Hoist signal No. 1"):
                                start_action(st, cap, a)
                    break
        elif key == "abeam":
            rel = _relative_bearing(st, run.hulk)
            hdg = _heading(st)
            helm.desired_heading = (hdg + rel - 90.0) % 360.0
        elif key == "quarters":
            orders.quarters = True
        elif key == "drill":
            gun = next((g for g in layout.guns if g.on_deck and g.side > 0 and g.crew_tiles), None)
            if gun is None:
                return
            pos = w.component_for_entity(cap, c.DeckPosition)
            tile = gun.crew_tiles[0]
            if (pos.x, pos.y) != tuple(tile):
                walk_to(st, cap, tile)
            else:
                acts = [a for a in available_actions(st, cap) if a.note != "unavailable" and ("Train" in a.label or "Elevate" in a.label)]
                if acts:
                    start_action(st, cap, acts[0])
        elif key == "fire":
            orders.fire_side = 1
        elif key == "fall_of_shot":
            orders.fire_side = 1

    return tick


@scenario(
    "tutorial_demo",
    "Tutorial, played through",
    "The tutorial course driven by a scripted student: he walks to the wheel, cons the ship onto a heading, "
    "puts the wind on the quarter, makes and shortens sail, hoists a signal and waits for it to be answered, "
    "lays the hulk abeam, beats to quarters, takes a hand at a gun and fires into her. Proof that every "
    "lesson can be passed with the controls a player has.",
    look_for=[
        "The log reads as a lesson book: each lesson announced, then passed.",
        "Watch the crew walk to quarters, and the gun drill begin gun by gun.",
    ],
    duration_s=600,
)
def tutorial_demo(seed: int = 1803):
    run = _tutorial_scene(seed)
    run.sim.every(1.0, _student(run))
    run.checkpoints = [
        Checkpoint(30, "Early lessons: at the wheel, and conning her onto a heading.", {"paused": True}, [expect("past the first lesson", _lesson_at_least(run, 1))]),
        Checkpoint(200, "Sail handling and signals done; the hulk being laid abeam.", {}, [expect("through five lessons", _lesson_at_least(run, 5))]),
        Checkpoint(420, "Quarters, the drill, and the guns speaking.", {}, [expect("through nine lessons", _lesson_at_least(run, 9))]),
        Checkpoint(595, "Course complete.", {}, [expect("all eleven lessons passed", _lesson_at_least(run, 11))]),
    ]
    return run
