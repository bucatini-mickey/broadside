# The playable demo: one scene with everything in it that works.
#
#   python -m broadside.main
#   python -m broadside.scenarios run demo
#
# Your brig is under way with her company aboard, a consort astern to
# signal, a hostile corvette standing toward you, and a fort's sea wall on
# an islet to leeward. Nothing is scripted except the enemy's course and
# her willingness to fight: everything you do is done with the ordinary
# controls, and everything your people do is the ordinary simulation.
#
# The opening lines in the log say what is worth trying, and a few hints
# fire the first time you do something (walk, beat to quarters, open fire),
# so the demo teaches its own interface without being a tutorial.

from __future__ import annotations

from dataclasses import dataclass, field

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.scenarios.sandbox import _stow_on_deck
from broadside.sim import components as c

OPENING = [
    ("Your brig stands to the eastward under topsails, the wind on the larboard beam.", "order"),
    ("A strange brig holds station a cable and a half off your larboard beam, her ports open. There is a fort's sea wall on the islet to starboard.", "sight"),
    ("Try this, in any order:", "info"),
    ("  m  - take the deck yourself. The view closes in and follows you; arrows walk, e shows what you can do where you stand.", "info"),
    ("  1-5 - the panels: this log, the crew roster and their skills, your orders, the ship's instruments, and every key.", "info"),
    ("  b  - beat to quarters, then watch the log: every man walks to his station and the gun crews start the drill.", "info"),
    ("  l then x - put the cursor on the enemy brig and tell the guns to fire at her; F lets each gun captain fire as he bears.", "info"),
    ("  a/d steer, w/s call for sail - she is slow to answer either, as she should be.", "info"),
]


@dataclass
class Guide:
    """A few hints, each fired once, the first time it is relevant."""

    enemy: int
    said: list = field(default_factory=list)

    def once(self, state, key: str, text: str, kind: str = "info") -> None:
        if key not in self.said:
            self.said.append(key)
            state.say(text, kind)

    def tick(self, state) -> None:
        world = state.world
        me = state.player_ship
        orders = world.component_for_entity(me, c.ShipOrders)
        # She holds her fire until you clear for action, or until her
        # captain's patience runs out - so you have a few minutes to look
        # about you before anyone is killed.
        eo = world.component_for_entity(self.enemy, c.ShipOrders)
        if not eo.fire_at_will and (orders.quarters or state.now_s > 150.0):
            eo.fire_at_will = True
            nm = world.try_component(self.enemy, c.Name)
            state.say(f"{nm.full if nm else 'The stranger'} is running her guns out.", "alert")
        if orders.quarters:
            self.once(state, "quarters", "Cleared for action. Panel 3 shows what every gun's crew is at; panel 2 is the company, man by man.", "order")
        if orders.fire_at_will:
            self.once(state, "at_will", "The gun captains have her now - each fires as his gun comes to bear, and lays her himself.", "order")
        if orders.gun_target >= 0:
            nm = world.try_component(orders.gun_target, c.Name)
            self.once(state, "target", f"The word is going along the deck: fire at {nm.full if nm else 'her'}. A green gun captain takes half a minute to take it in.", "order")
        hull = world.try_component(me, c.Hull)
        if hull is not None and hull.integrity < 0.995:
            self.once(state, "hit", "We are hit. Panel 2 will show who is hurt, and panel 4 what she has left.", "alert")
        if any("boarders" in e.text.lower() for e in state.log[-6:]):
            self.once(state, "board", "Hulls fouled. Every man who crosses fights man to man.", "alert")


def _demo_scene(seed: int):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=9.0, start_hour=9.0)
    me = b.player("brig_14", name="Kestrel", heading_degrees=90.0, trim=0.45, crew=46, victual_days=40)
    b.set_speed(me, 4.5)
    consort = b.ship("sloop_18", name="Swift", faction="british", x_m=-450.0, y_m=60.0, heading_degrees=90.0, trim=0.5, observers=True)
    b.set_speed(consort, 4.5)
    # An enemy who means it. She works round a box that crosses your track,
    # so she comes within gunshot on your larboard side and keeps coming
    # back for more - no AI captain yet, just a course and the will to fight.
    # A cable and a half off your larboard beam, on the same course and the
    # same canvas, so she holds station there: parallel courses, broadside
    # to broadside, which is how these actions were really fought. Haul off
    # if you would rather not - she has no captain to follow you yet.
    enemy = b.ship("brig_14", name="Vigilante", faction="french", x_m=30.0, y_m=150.0, heading_degrees=90.0, trim=0.45, crew=0)
    b.set_speed(enemy, 4.5)
    eo = b.world.component_for_entity(enemy, c.ShipOrders)
    eo.quarters = True  # cleared for action, but holding her fire (see Guide)
    # A fort's sea wall on the islet to starboard (we steer east, so
    # starboard is southward): something to breach if you would rather.
    b.island(330.0, -620.0, 120.0, peak_m=18.0, wooded=True, shoal_m=30.0)
    b.wall(300.0, -505.0, 90.0, length_m=26.0, thickness_m=2.0, height_m=6.0, name="sea wall")
    w = b.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    w.component_for_entity(me, c.Battery).verbose_drill = True
    _stow_on_deck(w, me, layout)
    run = b.build(duration_s=600, checkpoints=[])
    run.enemy = enemy
    run.consort = consort
    run.captain = next(e for e, o in w.get_component(c.Observer) if o.ship == me and o.post == "captain")
    guide = Guide(enemy=enemy)
    run.guide = guide

    def opening(st):
        for text, kind in OPENING:
            st.say(text, kind)

    run.sim.at(0.5, opening)
    run.sim.every(1.0, guide.tick)
    return run


def _closes_to(run, metres: float):
    def fn(state):
        a = state.world.component_for_entity(state.player_ship, c.WorldPosition)
        b_ = state.world.component_for_entity(run.enemy, c.WorldPosition)
        d = ((a.x_m - b_.x_m) ** 2 + (a.y_m - b_.y_m) ** 2) ** 0.5
        return d <= metres, f"{d:.0f} m apart"

    return fn


def _enemy_has_fired(state):
    n = sum(1 for e in state.log if "vigilante" in e.text.lower() and "fire" in e.text.lower())
    return n > 0, f"{n} enemy salvoes in the log"


@scenario(
    "demo",
    "Demo: your brig, a consort, an enemy and a fort",
    "The playable demo. Your brig is under way with her whole company; a consort astern to signal; an enemy "
    "brig holding station a cable and a half off your larboard beam, cleared for action but holding her fire; "
    "and a fort's sea wall on the islet to starboard. Walk the deck as the captain, con the ship, beat to "
    "quarters, name a target and let the gun captains fight her - all with the ordinary controls, in real "
    "time. She opens fire when you do, or when her captain tires of waiting.",
    look_for=[
        "The log opens with a list of things to try; hints follow as you do them.",
        "m: walk mode - three cells to the metre, the view following you, only what you can see drawn.",
        "1-5: the panels. 2 is the roster with every man's skills; 3 shows what each gun's crew is doing this second.",
        "l then x names a target; F lets the gun captains fire as they bear. Watch the shot fall, and the answer come back.",
        "She fights on a parallel course, broadside to broadside: expect casualties on deck, and look at who they are.",
    ],
    duration_s=600,
)
def demo(seed: int = 1805):
    run = _demo_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "The opening: your brig under topsails, the company about their work.", {"paused": True}),
        Checkpoint(40, "Walk mode: the captain in the middle of his own view, three cells to the metre.", {"follow": run.captain, "subcell": 5, "fit": False, "square_local": True}),
        Checkpoint(90, "The macro view: the consort astern, the corvette closing, the islet to starboard.", {"scale": "macro", "macro_zoom": 4}),
        Checkpoint(300, "Half an hour out - the corvette should be within range by now.", {}, [expect("she closes", _closes_to(run, 900.0))]),
        Checkpoint(595, "The end of the run.", {}, [expect("she came within gunshot", _closes_to(run, 700.0))]),
    ]
    return run


@scenario(
    "demo_fight",
    "Demo, fought through",
    "The same scene with your side ordered to fight from the start: quarters beaten, the guns firing as they "
    "bear, and the enemy corvette doing the same. Everything that follows - laying, the drill, shot in the "
    "hull, wounded men - is the simulation running on its own.",
    look_for=[
        "Both ships at quarters, both firing as their guns bear.",
        "Log: the drill by name, then shot striking home, then the surgeon's work waiting to be written.",
        "Panel 2 (crew) after ten minutes: who is hurt, who is dead, who is still at his gun.",
    ],
    duration_s=600,
)
def demo_fight(seed: int = 1805):
    run = _demo_scene(seed)

    def fight(st):
        o = st.world.component_for_entity(st.player_ship, c.ShipOrders)
        o.quarters = True
        o.fire_at_will = True

    run.sim.at(5.0, fight, "Beat to quarters - and fire as they bear!")
    run.checkpoints = [
        Checkpoint(60, "Quarters: the crews at their guns, the drill under way.", {"paused": True}),
        Checkpoint(300, "Closing, with both sides firing as their guns bear.", {}, [expect("she closes", _closes_to(run, 900.0))]),
        Checkpoint(595, "After ten minutes of it.", {}, [expect("the enemy has opened fire", _enemy_has_fired)]),
    ]
    return run
