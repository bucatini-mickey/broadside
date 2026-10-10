# Guns: reloading by their crews, rippling broadsides, muzzle flash - and,
# most importantly for the vision engine, the powder smoke every discharge
# puts into the air.
#
# A gun reloads only while manned (two or more of its crew at their
# stations; faster with a full crew of four). A broadside order fires every
# loaded, manned gun on that side in a ripple from bow to stern. Each shot
# emits a smoke puff just outboard of the gunport with the muzzle blast's
# momentum; the atmosphere system then drifts it downwind. Whether your own
# smoke blinds you depends on which side of the enemy the wind is - the
# weather-gage trade-off period captains argued over.
#
# No shot ballistics or damage yet - that's roadmap Phase 2, which will
# hang off the same fire event.

from __future__ import annotations

from broadside.sim import components as c
from broadside.sim import gundrill as gd
from broadside.sim.gundrill import reset_after_firing
from broadside.sim.people import components as pc
from broadside.sim.systems.crew_tasks import manned_counts
from broadside.sim.units import heading_axes

MIN_CREW_TO_WORK_GUN = 2
# How often the gun captains lay again as the range runs off.
RELAY_INTERVAL_S = 30.0
FULL_CREW = 4
FLASH_S = 0.5
BELOW_DECK_CLEAR_S = 25.0  # time for the gundeck to clear away after quarters
MUZZLE_OUTBOARD_M = 2.5
MUZZLE_VELOCITY_MS = 12.0


def gunnery_system(state, dt: float) -> None:
    world = state.world
    for ship, (battery, orders, body, pos, heading) in world.get_components(
        c.Battery, c.ShipOrders, c.ShipBody, c.WorldPosition, c.Heading
    ):
        layout = body.layout
        specs = layout.guns
        manned = manned_counts(state, ship) if not battery.abstract_crew else {}
        below_ready = orders.quarters and orders.quarters_since_s >= 0 and state.now_s - orders.quarters_since_s >= BELOW_DECK_CLEAR_S

        def crew_at(gs) -> int:
            spec = specs[gs.index]
            if battery.abstract_crew or not spec.on_deck:
                return FULL_CREW if (below_ready or (battery.abstract_crew and orders.quarters)) else 0
            return manned.get(gs.index, 0)

        for gs in battery.guns:
            if gs.flash_s > 0:
                gs.flash_s = max(0.0, gs.flash_s - dt)
            if not gs.loaded:
                # A gun on the weather deck with real men at her is worked
                # step by step by those men (sim/gundrill.py). Guns below
                # decks, and ships simulated without crew entities, still
                # reload on a timer scaled by how many hands they have.
                if not battery.abstract_crew and specs[gs.index].on_deck:
                    continue
                n = crew_at(gs)
                if n >= MIN_CREW_TO_WORK_GUN:
                    gs.reload_left_s -= dt * (n / FULL_CREW)
                    if gs.reload_left_s <= 0:
                        gs.loaded = True
                        gs.charged = gs.charge_rammed = gs.wadded = True
                        gs.shotted = gs.rammed = gs.run_out = gs.primed = gs.laid = True
                        gs.needs_sponge = False

        # The word reaches the deck and the gun captains lay their pieces
        # for the range: quoin under the breech, handspikes to train. They
        # do it again whenever the word changes, and every half minute as
        # the range runs off - a gun laid for five cables is no use when
        # she has closed to two.
        stale = state.now_s - battery.laid_at_s > RELAY_INTERVAL_S
        if orders.quarters and (battery.laid_for != orders.gun_target or stale):
            crews = {} if battery.abstract_crew else gd.crew_at_guns(state, ship)
            for gs in battery.guns:
                if not gs.loaded:
                    continue  # being worked; the drill lays it in its turn
                spec = specs[gs.index]
                men = crews.get(gs.index) or []
                if battery.abstract_crew or not spec.on_deck:
                    if crew_at(gs) < MIN_CREW_TO_WORK_GUN:
                        continue
                    skill = 0.45
                elif not men:
                    continue
                else:
                    sk = world.try_component(men[0][0], pc.Skills)
                    skill = sk.get("gunlaying") if sk is not None else 0.4
                gd.lay_gun(state, ship, spec, gs, skill)
            battery.laid_for = orders.gun_target
            battery.laid_at_s = state.now_s

        sides = []
        if orders.fire_side:
            sides.append(orders.fire_side)
            orders.fire_side = 0
        elif orders.fire_at_will and orders.quarters and not battery.pending_fire:
            for side in (-1, 1):
                ready = [g for g in battery.guns if specs[g.index].side == side and g.loaded and crew_at(g) >= MIN_CREW_TO_WORK_GUN]
                total = [g for g in battery.guns if specs[g.index].side == side]
                if total and len(ready) >= max(1, len(total) // 2):
                    sides.append(side)
                    break

        for side in sides:
            ready = [g for g in battery.guns if specs[g.index].side == side and g.loaded and crew_at(g) >= MIN_CREW_TO_WORK_GUN]
            ready.sort(key=lambda g: -specs[g.index].x)  # bow to stern
            name = world.try_component(ship, c.Name)
            side_name = "Starboard" if side > 0 else "Larboard"
            if not ready:
                if ship == state.player_ship:
                    state.say(f"{side_name} battery not ready - no guns loaded and manned.", "gun")
                continue
            for i, g in enumerate(ready):
                battery.pending_fire.append((i * orders.ripple_s, g.index))
            from broadside.sim.people.psyche import appraise_ship

            appraise_ship(state, ship, "our_broadside", min(1.5, 0.4 + 0.1 * len(ready)), on_deck_only=True)
            who = "our" if ship == state.player_ship else (name.full + "'s" if name else "a")
            if len(ready) == 1:
                state.say(f"{who.capitalize() if who == 'our' else who} {side_name.lower()} gun fires!", "gun")
            else:
                state.say(f"{side_name} broadside - {who} {len(ready)} guns fire!", "gun")

        if battery.pending_fire:
            keep = []
            for delay, gi in battery.pending_fire:
                delay -= dt
                if delay > 0:
                    keep.append((delay, gi))
                    continue
                gs = battery.guns[gi]
                spec = specs[gi]
                discharge(state, ship, gi, gs, battery.reload_s)
            battery.pending_fire = keep


def discharge(state, ship: int, gi: int, gs, reload_s: float = 75.0) -> int:
    """Fire one gun: the ball (a real projectile), the flash, the smoke.
    Shared by broadsides and by a man working the gun by hand."""
    from broadside.sim.systems.ballistics import fire_gun

    world = state.world
    layout = world.component_for_entity(ship, c.ShipBody).layout
    pos = world.component_for_entity(ship, c.WorldPosition)
    heading = world.component_for_entity(ship, c.Heading)
    spec = layout.guns[gi]
    proj = fire_gun(state, ship, gi, elevation_deg=gs.elevation_deg, train_deg=gs.train_deg)
    reset_after_firing(gs)  # she has recoiled inboard: the drill starts again
    gs.reload_left_s = reload_s
    gs.flash_s = FLASH_S
    fx, fy, sx, sy = heading_axes(heading.degrees)
    u, v = layout.local_m(spec.x, spec.y)
    v_out = v + spec.side * MUZZLE_OUTBOARD_M
    wx = pos.x_m + u * fx + v_out * sx
    wy = pos.y_m + u * fy + v_out * sy
    state.atmosphere.emit_smoke(wx, wy, sx * spec.side * MUZZLE_VELOCITY_MS, sy * spec.side * MUZZLE_VELOCITY_MS)
    state.recent.append((state.now_s, "gunfire", wx, wy, 1.0))
    return proj
