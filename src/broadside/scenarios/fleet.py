# Commanding a squadron: signals, and the captains who read them.
#
# You are the senior officer of three. Your consorts have captains of their
# own - with their own skill, wit, dash and obedience - and the only way to
# tell them anything is the signal book. Hoist a number; their lookouts
# must see it, their signal midshipmen must read it (and may read it
# wrong), and their captains then do as they are told, or don't.
#
# See docs/design/19_fleet_and_captains.md.

from __future__ import annotations

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.sim import components as c
from broadside.sim.systems.captain_ai import ShipCaptainAI
from broadside.sim.systems.signals import SIGNAL_BOOK, make_signal


def _squadron_scene(seed: int):
    b = SceneBuilder(seed, wind_from=20.0, wind_knots=11.0, start_hour=7.5)
    me = b.player("frigate_38", name="Kestrel", heading_degrees=90.0, trim=0.55, crew=120, victual_days=60)
    b.set_speed(me, 5.5)
    # Two consorts, deliberately unalike: one steady, one a fire-eater.
    swift = b.ship("sloop_18", name="Swift", faction="british", x_m=-700.0, y_m=250.0, heading_degrees=90.0, trim=0.5, crew=40, observers=True)
    hazard = b.ship("brig_14", name="Hazard", faction="british", x_m=-1300.0, y_m=-150.0, heading_degrees=90.0, trim=0.5, crew=40, observers=True)
    for s in (swift, hazard):
        b.set_speed(s, 5.0)
    # The enemy: a frigate and a brig standing across your course.
    foe1 = b.ship("frigate_38", name="Vigilante", faction="french", x_m=3200.0, y_m=1500.0, heading_degrees=250.0, trim=0.6, crew=40, observers=True)
    foe2 = b.ship("brig_14", name="Guepe", faction="french", x_m=3600.0, y_m=1900.0, heading_degrees=250.0, trim=0.6, crew=30, observers=True)
    for s in (foe1, foe2):
        b.set_speed(s, 5.0)
    w = b.world
    # Give the two consorts their characters by hand, so the scenario shows
    # the difference between captains rather than whatever the seed rolled.
    steady = w.component_for_entity(swift, ShipCaptainAI)
    steady.skill, steady.intelligence, steady.aggression, steady.caution, steady.discipline = 0.72, 0.74, 0.35, 0.6, 0.88
    steady.leader = me
    fiery = w.component_for_entity(hazard, ShipCaptainAI)
    fiery.skill, fiery.intelligence, fiery.aggression, fiery.caution, fiery.discipline = 0.5, 0.42, 0.9, 0.2, 0.42
    fiery.leader = me
    w.component_for_entity(me, c.Battery).verbose_drill = False
    run = b.build(duration_s=900, checkpoints=[])
    run.swift, run.hazard, run.foe1, run.foe2 = swift, hazard, foe1, foe2
    run.captain = next(e for e, o in w.get_component(c.Observer) if o.ship == me and o.post == "captain")
    return run


def _mission_is(run, which: str, *missions):
    def fn(state):
        ai = state.world.component_for_entity(getattr(run, which), ShipCaptainAI)
        return ai.mission in missions, f"{which} is on '{ai.mission}'"

    return fn


def _in_station(run, metres: float):
    import math

    def fn(state):
        w = state.world
        ai = w.component_for_entity(run.swift, ShipCaptainAI)
        lead = w.component_for_entity(state.player_ship, c.WorldPosition)
        head = w.component_for_entity(state.player_ship, c.Heading).degrees
        brg = math.radians(head + ai.station_bearing)
        wx, wy = lead.x_m + math.sin(brg) * ai.station_m, lead.y_m + math.cos(brg) * ai.station_m
        her = w.component_for_entity(run.swift, c.WorldPosition)
        off = math.hypot(wx - her.x_m, wy - her.y_m)
        return off < metres, f"Swift is {off:.0f} m off her station"

    return fn


def _signalled(n: int):
    def fn(state):
        hoists = sum(1 for e in state.log if "Signal No." in e.text)
        answers = sum(1 for e in state.log if "answers the signal" in e.text)
        return hoists >= n and answers >= 1, f"{hoists} signals made, {answers} answered"

    return fn


@scenario(
    "fleet_orders",
    "Signals: giving orders to a squadron",
    "You are senior officer of three, standing east with a frigate and a brig in company, and two of the "
    "enemy coming down from the north-east. Your consorts have captains of their own - Swift's is steady and "
    "obedient, Hazard's is a fire-eater who holds an order about as long as it suits him - and the signal "
    "book is the only way to tell either of them anything. The signals here are made for you, on a timetable; "
    "in play you make them from the SIGNALS panel.",
    look_for=[
        "Panel 4 (SIGNALS): the book, who the signal is addressed to, what is flying, and who has answered.",
        "The same panel lists your squadron with each captain's skill, wit, dash and obedience, and what he is doing.",
        "Log: a signal made, then seen, then answered, then acknowledged - and sometimes misread.",
        "Hazard's captain breaks away to engage before he is told to; Swift's keeps her station.",
    ],
    duration_s=900,
    slow=True,
)
def fleet_orders(seed: int = 1806):
    run = _squadron_scene(seed)
    me = run.state.player_ship

    def signal(number, to=None):
        def fn(st):
            whom = -1 if to is None else getattr(run, to)
            st.say(make_signal(st, me, number, whom), "order")

        return fn

    run.sim.at(30.0, signal(2), "Make signal No. 2: form line of battle.")
    run.sim.at(240.0, signal(4), "Make signal No. 4: enemy in sight.")
    run.sim.at(420.0, signal(8, "swift"), "Make signal No. 8 to Swift: report your damage.")
    run.sim.at(540.0, signal(1), "Make signal No. 1: engage the enemy more closely.")
    run.sim.at(780.0, signal(9, "hazard"), "Make signal No. 9 to Hazard: discontinue the action.")
    run.checkpoints = [
        Checkpoint(20, "The squadron standing east, the enemy not yet in sight.", {"paused": True}),
        Checkpoint(200, "Signal No. 2 answered: Swift closing her station astern.", {"scale": "macro", "macro_zoom": 7}, [expect("signals are going out", _signalled(1)), expect("Swift forms line", _mission_is(run, "swift", "station"))]),
        Checkpoint(430, "Swift in her station; Hazard's captain already looking to the enemy.", {"scale": "macro", "macro_zoom": 7}, [expect("Swift holds her station", _in_station(run, 260.0))]),
        Checkpoint(700, "No. 1 made: the squadron engaging.", {"scale": "macro", "macro_zoom": 7}, [expect("Swift engages", _mission_is(run, "swift", "engage", "station", "withdraw"))]),
        Checkpoint(880, "The end of the business.", {"scale": "macro", "macro_zoom": 8}, [expect("five signals made", _signalled(4))]),
    ]
    return run
