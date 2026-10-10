# Sighting: which other ships each ship's observers can actually see, and
# what the ship therefore *knows* about them.
#
# This is gameplay knowledge, not rendering. A ship's Contacts are its
# picture of the world: where each vessel was last seen, how clearly, and
# by whom. The captain's own eyes update it immediately; a masthead
# lookout sees further (over rocks, smoke and the ship's own sails) but his
# first sighting takes a few seconds to be called down to the quarterdeck.
# When nobody can see a vessel any more the record goes stale - "lost" -
# but keeps its last known position, which is what the chart view draws.
# Later, semaphore reports will write into the same records.
#
# Each observer traces rays (sim/vision.py) to three points along every
# other hull (bow, midships, stern) at bulwark height, and up to the head
# of the mainmast. Hull visible = "hull"; only the masts = "topsails"
# (hull down, or behind a low islet, or above a smoke bank).

from __future__ import annotations

import math

import numpy as np

from broadside.sim import components as c
from broadside.sim.units import bearing_degrees
from broadside.sim.vision import VIS_FAINT, Eye, direct_sampler, trace

FRESH_S = 3.0  # a record seen this recently is "being tracked"
STATUS_RANK = {"hull": 2, "topsails": 1}


def observer_eye(state, obs_ent: int) -> Eye | None:
    world = state.world
    obs = world.try_component(obs_ent, c.Observer)
    dpos = world.try_component(obs_ent, c.DeckPosition)
    if obs is None or dpos is None:
        return None
    g = state.scene().geom_for(obs.ship)
    if g is None:
        return None
    x, y = g.tile_world(dpos.x, dpos.y)
    return Eye(x=x, y=y, h=obs.eye_height_m)


def sighting_system(state, dt: float) -> None:
    world = state.world
    scene = state.scene()
    haze = state.atmosphere.haze_sigma
    now = state.now_s

    # Per observing ship: target -> best (rank, clarity, post, delay)
    best: dict[int, dict[int, tuple[int, float, str, float]]] = {}
    for obs_ent, obs in world.get_component(c.Observer):
        eye = observer_eye(state, obs_ent)
        if eye is None:
            continue
        targets = [g for g in scene.geoms if g.entity != obs.ship]
        if not targets:
            continue
        tx, ty, tl, th, skip, owner = [], [], [], [], [], []
        for g in targets:
            half = g.layout.hull_length * 0.33
            for u in (-half, 0.0, half):
                x, y = g.to_world(u, 0.0)
                tx.append(x)
                ty.append(y)
                tl.append(g.hull_top_m() - 0.3)
                th.append(g.mast_top_m() - 1.0)
                # Ignore obstruction within the target ship's own footprint
                # (its own sails and bulwarks) - we're asking whether *it*
                # can be seen, not whether its deck can.
                skip.append(g.layout.beam * 0.5 + 1.0)
                owner.append(g.entity)
        tx = np.array(tx)
        ty = np.array(ty)
        far = float(np.max(np.hypot(tx - eye.x, ty - eye.y)))
        step = min(25.0, max(1.5, far / 400.0))
        sampler = direct_sampler(scene, ignore_hull_of=obs.ship, include_people=False)
        sight = trace(eye, tx, ty, np.array(tl), np.array(th), sampler, step_m=step, haze_sigma=haze, end_skip_m=np.array(skip), max_samples=900, poles=scene.poles(), sails=scene.sail_walls())
        ship_best = best.setdefault(obs.ship, {})
        for i, ent in enumerate(owner):
            low, high = sight.low[i], sight.high[i]
            if low >= VIS_FAINT:
                cand = (2, float(low), obs.post, obs.report_delay_s)
            elif high >= VIS_FAINT:
                cand = (1, float(high), obs.post, obs.report_delay_s)
            else:
                continue
            cur = ship_best.get(ent)
            # Prefer the immediate (captain) sighting at equal rank.
            if cur is None or (cand[0], -cand[3], cand[1]) > (cur[0], -cur[3], cur[1]):
                ship_best[ent] = cand

    for ship, (contacts,) in _ships_with_contacts(world):
        seen = best.get(ship, {})
        me = world.try_component(ship, c.WorldPosition)
        for g in scene.geoms:
            if g.entity == ship:
                continue
            rec = contacts.records.get(g.entity)
            if rec is None:
                rec = c.ContactRecord(entity=g.entity)
                contacts.records[g.entity] = rec
            hit = seen.get(g.entity)
            status = {2: "hull", 1: "topsails"}.get(hit[0]) if hit else None
            fresh = rec.last_seen_s >= 0 and now - rec.last_seen_s <= FRESH_S and rec.status in STATUS_RANK
            if hit is not None:
                rank, clarity, post, delay = hit
                if delay <= 0 or fresh:
                    _update(rec, g, status, clarity, post, now)
                    contacts.pending.pop(g.entity, None)
                    if rec.first_seen_s == now and ship == state.player_ship:
                        state.say(_sighting_text(state, "Sighted", g, me), "sight")
                elif g.entity not in contacts.pending:
                    contacts.pending[g.entity] = (now + delay, g.x, g.y, g.heading, status, clarity)
            elif rec.status in STATUS_RANK and not fresh:
                rec.status = "lost"
                if ship == state.player_ship:
                    state.say(f"Lost sight of {g.name or 'a vessel'}.", "sight")

        # Deliver lookout reports whose time has come.
        for ent, (due, x, y, hdg, status, clarity) in list(contacts.pending.items()):
            if now < due:
                continue
            del contacts.pending[ent]
            rec = contacts.records.get(ent)
            g = scene.geom_for(ent)
            if rec is None or g is None:
                continue
            first = rec.first_seen_s < 0
            rec.status = status
            rec.x_m, rec.y_m, rec.heading = x, y, hdg
            rec.last_seen_s = due
            rec.seen_by = "lookout"
            rec.clarity = clarity
            if first:
                rec.first_seen_s = due
            if ship == state.player_ship:
                what = "Sail ho!" if status == "topsails" else "Deck there! Ship in sight"
                state.say(f"Masthead: {what} {_bearing_text(me, x, y)} - {g.name or 'unknown'}", "sight")


def _ships_with_contacts(world):
    for ent, contacts in world.get_component(c.Contacts):
        yield ent, (contacts,)


def _update(rec, g, status, clarity, post, now) -> None:
    rec.status = status
    rec.x_m, rec.y_m, rec.heading = g.x, g.y, g.heading
    rec.last_seen_s = now
    rec.seen_by = post
    rec.clarity = clarity
    if rec.first_seen_s < 0:
        rec.first_seen_s = now


def _bearing_text(me, x, y) -> str:
    if me is None:
        return ""
    dx, dy = x - me.x_m, y - me.y_m
    rng = math.hypot(dx, dy)
    return f"bearing {bearing_degrees(dx, dy):03.0f}, {rng:,.0f} m"


def _sighting_text(state, verb, g, me) -> str:
    return f"{verb} {g.name or 'a vessel'} {_bearing_text(me, g.x, g.y)}"


def sight_ship(state, obs_ent: int, target_ent: int) -> str:
    """What one observer can see of one ship right now: "hull",
    "topsails" or "none". Same geometry as the sighting system, for a
    single pair - used by scenario checks and the look readout."""
    world = state.world
    obs = world.try_component(obs_ent, c.Observer)
    eye = observer_eye(state, obs_ent)
    scene = state.scene()
    g = scene.geom_for(target_ent)
    if obs is None or eye is None or g is None:
        return "none"
    half = g.layout.hull_length * 0.33
    us = np.array([-half, 0.0, half])
    tx, ty = g.to_world(us, np.zeros(3))
    far = float(np.max(np.hypot(tx - eye.x, ty - eye.y)))
    sight = trace(
        eye,
        tx,
        ty,
        g.hull_top_m() - 0.3,
        g.mast_top_m() - 1.0,
        direct_sampler(scene, ignore_hull_of=obs.ship, include_people=False),
        step_m=min(25.0, max(1.5, far / 400.0)),
        haze_sigma=state.atmosphere.haze_sigma,
        end_skip_m=g.layout.beam * 0.5 + 1.0,
        max_samples=900,
        poles=scene.poles(),
        sails=scene.sail_walls(),
    )
    if sight.low.max() >= VIS_FAINT:
        return "hull"
    if sight.high.max() >= VIS_FAINT:
        return "topsails"
    return "none"
