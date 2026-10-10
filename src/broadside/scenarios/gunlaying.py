# Laying the guns: bearings, aspect, and the fall of shot before you fire.
#
# The complaint this answers was that you could not tell how you lay to
# the enemy, so you could not aim. The chart now draws her own beams and
# fore-and-aft line, the line of fire runs out to whatever the guns are
# laid on with her aspect written at the end of it, and `p` shows the gun
# captain's estimate of where the shot would go - his arc, his splash, and
# how far out he may be.
#
# See docs/design/21_bearings_and_the_fall_of_shot.md.

from __future__ import annotations

import math

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.sim import components as c
from broadside.sim.systems.ballistics import gun_to_bear, predict_shot
from broadside.view.orientation import aspect_short, relative_short


def _scene(seed: int):
    b = SceneBuilder(seed, wind_from=30.0, wind_knots=12.0, start_hour=9.0)
    me = b.player("frigate_38", name="Kestrel", heading_degrees=0.0, trim=0.55, crew=120)
    b.set_speed(me, 5.0)
    # One on the starboard beam, broadside on: the shot that tells.
    beam = b.ship("brig_14", name="Vigilante", faction="french", x_m=620.0, y_m=60.0,
                  heading_degrees=0.0, trim=0.5, crew=40, observers=True)
    b.set_speed(beam, 4.0)
    # One fine on the bow, bows on: a harder mark, and nothing will bear.
    bow = b.ship("sloop_18", name="Guepe", faction="french", x_m=240.0, y_m=1500.0,
                 heading_degrees=185.0, trim=0.5, crew=30, observers=True)
    b.set_speed(bow, 4.5)
    run = b.build(duration_s=320.0, checkpoints=[])
    run.me, run.beam, run.bow = me, beam, bow
    # Beat to quarters and name her, so her guns are actually laid: the
    # preview is a dry run of *this* gun at *its present lay*, and a gun
    # nobody has laid is still at point blank.
    orders = run.state.world.component_for_entity(me, c.ShipOrders)
    orders.quarters = True
    orders.quarters_since_s = 0.0
    orders.gun_target = beam
    orders.gun_target_since_s = 0.0
    # Laid, not fired: this scenario is about knowing where the shot
    # would go before the word is given.
    orders.fire_at_will = False
    return run


def _aim_at(run, which: str):
    """A checkpoint value worked out at the moment of the snapshot."""

    def fn(state):
        return getattr(run, which)

    return fn


def _shot_at(run, which: str):
    def fn(state):
        target = getattr(run, which)
        hers = state.world.try_component(target, c.WorldPosition)
        if hers is None:
            return None
        gi, train = gun_to_bear(state, run.me, hers.x_m, hers.y_m)
        if gi < 0:
            return None
        return predict_shot(state, run.me, gi, train_deg=train, target=target, skill=0.65)

    return fn


def _bears(run, which: str, want: bool):
    def fn(state):
        hers = state.world.component_for_entity(getattr(run, which), c.WorldPosition)
        gi, train = gun_to_bear(state, run.me, hers.x_m, hers.y_m)
        if want:
            return gi >= 0, f"gun {gi} trained {train:+.1f} deg"
        return gi < 0, "nothing bears" if gi < 0 else f"gun {gi} bears"

    return fn


def _aspect_is(run, which: str, word: str):
    def fn(state):
        w = state.world
        mine = w.component_for_entity(run.me, c.WorldPosition)
        hers = w.component_for_entity(getattr(run, which), c.WorldPosition)
        her_head = w.component_for_entity(getattr(run, which), c.Heading).degrees
        heading = w.component_for_entity(run.me, c.Heading).degrees
        bearing = math.degrees(math.atan2(hers.x_m - mine.x_m, hers.y_m - mine.y_m)) % 360.0
        asp = aspect_short(her_head, bearing)
        rel = relative_short((bearing - heading + 180.0) % 360.0 - 180.0)
        return word in asp, f"{rel}, {asp}"

    return fn


def _tells(run, which: str):
    def fn(state):
        shot = _shot_at(run, which)(state)
        if shot is None:
            return False, "no gun bears"
        return "short" not in shot.verdict, f"{shot.graze_m:.0f} m +-{shot.spread_m:.0f}: {shot.verdict}"

    return fn


@scenario(
    "laying_the_guns",
    "Laying the guns",
    "Bearings, aspect and the fall of shot: how she lies to us, and what the shot would do about it, "
    "before the word is given. The chart's own axes, the line of fire to the ship the guns are laid on, "
    "and the gun captain's estimate of where his shot would land.",
    look_for=[
        "The chart draws her beams and her fore-and-aft line, so a north-up view still has a bow.",
        "The line of fire runs to what the guns are laid on, with the enemy's aspect at her end.",
        "`p` shows the gun captain's estimate: his arc, his splash, his range and his doubt.",
    ],
)
def laying_the_guns(seed: int = 1821):
    run = _scene(seed)
    run.checkpoints = [
        Checkpoint(
            8, "Her own axes on the chart: ahead, astern, and both beams, with the four-point diagonals between.",
            {"scale": "macro", "macro_zoom": 4},
            [expect("Vigilante lies broadside on", _aspect_is(run, "beam", "broadside"))],
        ),
        Checkpoint(
            20, "Guns laid on Vigilante: the line of fire, her bearing, her range, her aspect.",
            {"scale": "macro", "macro_zoom": 4, "contact": _aim_at(run, "beam")},
            [expect("a gun bears on her", _bears(run, "beam", True))],
        ),
        Checkpoint(
            40, "The gun captain's estimate: the track over the water, the splash, and how far out he may be.",
            {"scale": "macro", "macro_zoom": 4, "contact": _aim_at(run, "beam"), "shot": _shot_at(run, "beam")},
            [expect("the shot would tell on her", _tells(run, "beam"))],
        ),
        Checkpoint(
            120, "Guepe fine on the bow, bows on: a poor mark, and no broadside gun will bear.",
            {"scale": "macro", "macro_zoom": 5, "contact": _aim_at(run, "bow")},
            [expect("nothing bears on the bow", _bears(run, "bow", False))],
        ),
        Checkpoint(
            260, "As she comes round, Guepe draws aft and opens her side: now the guns will bear.",
            {"scale": "macro", "macro_zoom": 5, "contact": _aim_at(run, "bow"), "shot": _shot_at(run, "bow")},
            [expect("her bearing and aspect are reported", _aspect_is(run, "bow", ""))],
        ),
    ]
    return run
