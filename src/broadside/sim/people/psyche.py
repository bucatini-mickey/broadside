# State of mind: stress, anxiety, depression, fear, morale, drink - and
# the ship-level picture they add up to, including the risk of mutiny.
#
# Each quantity relaxes toward a target set by a person's circumstances
# and character, at its own speed: fear in seconds, stress over minutes,
# anxiety over the hour, depression over days, grievance over weeks. So a
# single bad afternoon frightens a man, a bad month breaks him, and a ship
# where many men are broken and resentful is a ship in danger.
#
# The grog ration (issued at dinner and supper, period practice) relieves
# the drink need; men with a high dependence suffer without it, which is
# why stopping a ship's grog was a punishment - and a gamble.

from __future__ import annotations

import math
from dataclasses import dataclass

from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.people.health import Injured

GROG_HOURS = (12.0, 17.0)  # dinner and supper
DRINK_NEED_PER_HOUR = 0.12  # at full dependence


@dataclass
class ShipMorale:
    """Aggregate state of a ship's company, recomputed by the psyche
    system. `mutiny_risk` is 0..1: not a scripted trigger, a pressure that
    Phase 1's discipline system (and the crew's own ringleaders) act on."""

    morale: float = 0.0
    stress: float = 0.0
    grievance: float = 0.0
    devotion_captain: float = 0.5
    drink_need: float = 0.0
    mutiny_risk: float = 0.0
    alive: int = 0
    dead: int = 0
    wounded: int = 0


# How strongly each event is felt, before character is taken into account.
APPRAISALS = {
    "gunfire_near": {"fear": 0.10},
    "struck": {"fear": 0.22, "anger": 0.12},
    "mate_killed": {"grief": 0.3, "fear": 0.12},
    "mate_hurt": {"grief": 0.1, "fear": 0.05},
    # Repeated events are deliberately small: a crew firing briskly should
    # end an action in high spirits, not in ecstasy after two minutes.
    "our_broadside": {"pride": 0.02, "hope": 0.012},
    "enemy_struck": {"pride": 0.05, "hope": 0.03},
    "grog": {"contentment": 0.35},
    "fed": {"contentment": 0.2},
    "short_commons": {"anger": 0.12},
    "soaked": {"anger": 0.04},
    "rested": {"contentment": 0.12},
    "flogging_witnessed": {"fear": 0.2, "anger": 0.18, "shame": 0.08},
    "prize_taken": {"pride": 0.4, "hope": 0.35},
}


def appraise(state, ent: int, event: str, weight: float = 1.0) -> None:
    """One thing happened to one man, and he feels about it. Character
    decides how much: a brave man fears less, a hot-tempered one angers
    faster, a resilient one shrugs."""
    world = state.world
    psy = world.try_component(ent, pc.Psyche)
    if psy is None:
        return
    pers = world.try_component(ent, pc.Personality)
    for what, base in APPRAISALS.get(event, {}).items():
        amount = base * weight
        if pers is not None:
            if what == "fear":
                amount *= 1.4 - pers.bravery
            elif what == "anger":
                amount *= 0.6 + pers.temper
            elif what in ("grief", "shame"):
                amount *= 1.3 - pers.resilience
            elif what in ("hope", "contentment", "pride"):
                amount *= 0.6 + pers.optimism
        psy.feel(what, amount)


def appraise_ship(state, ship: int, event: str, weight: float = 1.0, on_deck_only: bool = False) -> None:
    """The whole company takes something the same way - a broadside fired,
    a shipmate killed in sight of them, the grog served out."""
    world = state.world
    for ent, crew in world.get_component(c.CrewMember):
        if crew.ship != ship:
            continue
        if on_deck_only and not world.has_component(ent, c.DeckPosition):
            continue
        appraise(state, ent, event, weight)


def _hour(state) -> float:
    return (state.start_hour + state.now_s / 3600.0) % 24.0


def psyche_system(state, dt: float) -> None:
    world = state.world
    hour = _hour(state)
    prev = getattr(state, "_psyche_last_hour", None)
    grog = prev is not None and any((prev < h <= hour) or (prev > hour and (h > prev or h <= hour)) for h in GROG_HOURS)
    state._psyche_last_hour = hour
    if grog:
        state.say("Up spirits! The grog ration is served.", "info")

    # Fear from gunfire nearby.
    shots = [e for e in state.recent if e[1] == "gunfire" and state.now_s - e[0] <= dt + 0.01]
    positions = {}
    if shots:
        for ship, pos in world.get_component(c.WorldPosition):
            positions[ship] = (pos.x_m, pos.y_m)

    agg: dict = {}
    for ent, (psy, pers, crav, alleg, crew) in world.get_components(pc.Psyche, pc.Personality, pc.Cravings, pc.Allegiance, c.CrewMember):
        body = world.try_component(ent, pc.Body)
        a = agg.setdefault(crew.home_ship if crew.home_ship >= 0 else crew.ship, [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0])
        if body is not None and not body.alive:
            a[6] += 1
            continue
        needs = world.try_component(ent, c.Needs)
        fatigue = needs.fatigue if needs else 0.2
        hunger = needs.hunger if needs else 0.2

        crav.need = min(1.0, crav.need + crav.dependence * DRINK_NEED_PER_HOUR * dt / 3600.0)
        if grog:
            crav.need = max(0.0, crav.need - 0.7)
            appraise(state, ent, "grog")

        for t, _kind, x, y, loud in shots:
            sp = positions.get(crew.ship)
            if sp is None:
                continue
            d2 = (sp[0] - x) ** 2 + (sp[1] - y) ** 2
            if d2 < 400.0 ** 2:
                psy.fear = min(1.0, psy.fear + loud * 0.03 * (1.2 - pers.bravery) * (1.0 - psy.confidence * 0.5))
        psy.fear = max(0.0, psy.fear - dt / 40.0 * (0.5 + pers.bravery))
        psy.feelings["fear"] = psy.fear
        # Every other feeling fades at its own rate.
        for what, tau in pc.EMOTIONS.items():
            if what == "fear":
                continue
            have = psy.feelings.get(what)
            if have:
                psy.feelings[what] = have * math.exp(-dt / tau)
                if psy.feelings[what] < 0.002:
                    del psy.feelings[what]

        pain = body.pain if body is not None else 0.0
        stress_target = 0.08 + 0.25 * fatigue + 0.15 * hunger + 0.35 * crav.need * crav.dependence + 0.6 * psy.fear + 0.2 * psy.grievance + 0.4 * pain
        psy.stress += (min(1.0, stress_target) - psy.stress) * min(1.0, dt / 600.0 * (1.5 - pers.resilience))
        psy.anxiety += (min(1.0, psy.stress * (1.3 - pers.resilience)) - psy.anxiety) * min(1.0, dt / 1800.0)
        dep_target = 0.5 * psy.stress + 0.3 * psy.grievance + 0.2 * (0.5 - pers.optimism)
        psy.depression += (max(0.0, min(1.0, dep_target)) - psy.depression) * min(1.0, dt / (3 * 86400.0))
        devotion = (alleg.nation + alleg.cause + alleg.captain + alleg.ship) / 4.0
        morale_target = (
            0.15
            + 0.6 * (devotion - 0.5)
            + 0.4 * (pers.optimism - 0.5)
            + 0.25 * (psy.confidence - 0.5)
            + 0.5 * psy.spirits  # what he is feeling right now
            - 0.7 * psy.stress
            - 0.6 * psy.depression
            - 0.5 * psy.grievance
        )
        psy.morale += (max(-1.0, min(1.0, morale_target)) - psy.morale) * min(1.0, dt / 1200.0)

        mood = world.try_component(ent, c.Mood)
        if mood is not None:
            mood.value = psy.morale

        a[0] += 1
        a[1] += psy.morale
        a[2] += psy.stress
        a[3] += psy.grievance
        a[4] += alleg.captain
        a[5] += crav.need
        if world.has_component(ent, Injured):
            a[7] += 1

    for ship, a in agg.items():
        sm = world.try_component(ship, ShipMorale)
        if sm is None:
            continue
        n = max(1, a[0])
        sm.alive, sm.dead, sm.wounded = a[0], a[6], a[7]
        sm.morale, sm.stress, sm.grievance, sm.devotion_captain, sm.drink_need = a[1] / n, a[2] / n, a[3] / n, a[4] / n, a[5] / n
        sm.mutiny_risk = max(0.0, min(1.0, 1.4 * (sm.grievance - 0.25) + 0.8 * (0.1 - sm.morale) + 0.8 * (0.45 - sm.devotion_captain) + 0.3 * sm.drink_need))
