# Wounds, bleeding, heartbeat and death.
#
# Death is measured by blood. A wound bleeds at a rate set by where it is
# and how bad it is; minor bleeding clots within minutes, a severed limb or
# an opened neck does not. As blood is lost the heart races (the body's
# attempt to keep pressure up), consciousness goes at about 30-35% loss,
# and past about 45% the heart stops. Destroying a vital part - head,
# neck, chest - kills outright. A surgeon (Phase 1) can tourniquet, bind
# and amputate, which is simply acting on these same numbers.
#
# Only people carrying an `Injured` marker are ticked, so a healthy crew of
# hundreds costs nothing here.

from __future__ import annotations

import math
from dataclasses import dataclass

from broadside.sim import components as c
from broadside.sim.people import components as pc

# ml/s of bleeding from a fully destroyed part, scaled by the part's
# bleed factor (components.BODY_PLAN). A severed thigh artery can empty a
# man in two or three minutes; a cut hand bleeds slowly and clots.
BASE_BLEED_ML_S = 12.0
CLOT_TIME_S = 90.0  # time constant for minor bleeding to stop
UNCONSCIOUS_AT = 0.67  # blood fraction
DEATH_AT = 0.55


@dataclass
class Injured:
    """Marker: this person has something the health system must tick."""


def wound(state, ent: int, part: str, severity: float, kind: str = "splinter") -> str:
    """Apply a wound. Returns a one-line description for the log."""
    world = state.world
    body = world.component_for_entity(ent, pc.Body)
    if not body.alive:
        return ""
    vital, bleed_factor, can_lose = pc.BODY_PLAN[part]
    p = body.parts[part]
    severity = max(0.0, min(1.0, severity))
    p.health = max(0.0, p.health - severity)
    p.bleed_ml_s += BASE_BLEED_ML_S * bleed_factor * severity ** 1.5
    body.pain = min(1.0, body.pain + 0.4 * severity)
    what = {"splinter": "splinter wound", "shot": "shot wound", "cut": "cut", "crush": "crushing injury", "burn": "burn"}.get(kind, kind)
    desc = f"{what} to the {part}"
    if p.health <= 0.0:
        if vital:
            _die(state, ent, f"{what} to the {part}")
            desc = f"killed by a {what} to the {part}"
        elif can_lose:
            p.missing = True
            p.bleed_ml_s = max(p.bleed_ml_s, BASE_BLEED_ML_S * bleed_factor * 1.2)
            desc = f"{part} carried away"
    elif severity > 0.5 and part.endswith(("arm", "leg", "hand", "foot")):
        p.fractured = True
        desc += ", bone broken"
    # A deep wound in a limb opens the artery or cuts the tendons; those
    # are what decide whether he bleeds out, and whether he works again.
    if severity > 0.6 and bleed_factor >= 0.8:
        p.artery_cut = True
        desc += ", an artery opened"
    if severity > 0.45 and part.endswith(("arm", "leg", "hand", "foot")) and state.rng.stream("wounds").random() < severity:
        p.tendon_cut = True
        desc += ", the tendons cut"
    p.wounds.append(desc)
    if not world.has_component(ent, Injured):
        world.add_component(ent, Injured())
    bio = world.try_component(ent, pc.Biography)
    if bio is not None:
        bio.add(state.clock_text(), desc[:1].upper() + desc[1:] + ".")
    return desc


def _die(state, ent: int, cause: str) -> None:
    world = state.world
    body = world.component_for_entity(ent, pc.Body)
    if not body.alive:
        return
    body.alive = False
    body.conscious = False
    body.heart_rate = 0.0
    body.cause_of_death = cause
    world.add_component(ent, pc.Dead(cause=cause, time_s=state.now_s))
    task = world.try_component(ent, c.CrewTask)
    if task is not None:
        task.kind, task.station, task.station_kind, task.path = "dead", None, "", []
    name = world.try_component(ent, c.Name)
    bio = world.try_component(ent, pc.Biography)
    if bio is not None:
        bio.add(state.clock_text(), f"Died: {cause}.")
    if name is not None:
        state.say(f"{name.full} is dead ({cause}).", "alert")


def health_system(state, dt: float) -> None:
    world = state.world
    for ent, (body, _inj) in list(world.get_components(pc.Body, Injured)):
        if not body.alive:
            world.remove_component(ent, Injured)
            continue
        lost = 0.0
        for p in body.parts.values():
            if p.bleed_ml_s <= 0:
                continue
            lost += p.bleed_ml_s * dt
            # Clotting: slow bleeds stop; heavy arterial ones barely slow,
            # and an opened artery will not stop at all without a hand on it.
            if p.tourniquet:
                p.bleed_ml_s *= math.exp(-dt / 6.0)
            elif p.artery_cut:
                p.bleed_ml_s *= math.exp(-dt / (CLOT_TIME_S * 40.0))
            else:
                tau = CLOT_TIME_S * (1.0 + p.bleed_ml_s / 3.0) ** 2
                p.bleed_ml_s *= math.exp(-dt / tau)
            if p.bleed_ml_s < 0.05:  # a trickle this small has effectively stopped
                p.bleed_ml_s = 0.0
        body.blood_ml = max(0.0, body.blood_ml - lost)
        frac = body.blood_fraction
        psyche = world.try_component(ent, pc.Psyche)
        fear = psyche.fear if psyche is not None else 0.0
        target_hr = 72.0 + 230.0 * max(0.0, 1.0 - frac) + 40.0 * fear + 30.0 * body.pain
        body.heart_rate += (min(190.0, target_hr) - body.heart_rate) * min(1.0, dt / 10.0)
        body.pain = max(0.0, body.pain - dt / 1800.0)
        was = body.conscious
        body.conscious = frac > UNCONSCIOUS_AT and body.pain < 0.95
        if was and not body.conscious:
            name = world.try_component(ent, c.Name)
            if name is not None:
                state.say(f"{name.full} has collapsed.", "alert")
        if frac < DEATH_AT:
            _die(state, ent, "loss of blood")
        elif body.bleeding_ml_s == 0.0 and body.pain < 0.05 and frac > 0.95:
            world.remove_component(ent, Injured)


def apply_tourniquet(state, ent: int, part: str) -> str:
    """A ligature above the wound: it stops the bleeding and begins to kill
    the limb. The surgeon's first act, and the reason so many men came home
    with one arm."""
    world = state.world
    body = world.component_for_entity(ent, pc.Body)
    p = body.parts.get(part)
    if p is None or p.tourniquet:
        return ""
    p.tourniquet = True
    name = world.try_component(ent, c.Name)
    bio = world.try_component(ent, pc.Biography)
    if bio is not None:
        bio.add(state.clock_text(), f"A tourniquet put on the {part}.")
    return f"{name.full if name else 'He'}: tourniquet on the {part}."


def condition_words(body: pc.Body) -> str:
    if not body.alive:
        return f"dead ({body.cause_of_death})"
    frac = body.blood_fraction
    parts = []
    if not body.conscious:
        parts.append("unconscious")
    if body.bleeding_ml_s > 3:
        parts.append("bleeding heavily")
    elif body.bleeding_ml_s > 0.3:
        parts.append("bleeding")
    if frac < 0.8:
        parts.append("pale and weak")
    hurt = [k for k, p in body.parts.items() if p.missing or p.health < 0.7]
    if hurt:
        parts.append("hurt: " + ", ".join(hurt[:3]))
    return ", ".join(parts) if parts else "sound"
