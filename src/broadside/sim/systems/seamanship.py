# The three things a captain does that are neither sailing nor fighting:
# bringing her up to an anchor, stretching the stores, and giving the men
# something to be cheerful about.
#
# All three are orders, and all three take real work by real men: the
# anchor is let go from the cathead and weighed at the capstan, the ration
# is cut by the purser and resented by the mess, and the grog is served
# out. Nothing here is instant and nothing is free.

from __future__ import annotations

from broadside.sim import components as c
from broadside.sim.items import Contents, Stowed
from broadside.sim.people import components as pc

# Letting go is quick; weighing is the heaviest routine work in the ship.
LET_GO_S = 14.0
WEIGH_S = 75.0
# She will not lie quietly to her anchor with her canvas full, and you
# cannot let go while she is still running down on it.
MAX_TRIM_TO_ANCHOR = 0.22
MAX_SPEED_TO_ANCHOR_KN = 2.6
# Riding to an anchor she still fetches about a little, but makes no way.
ANCHOR_DRAG_PER_S = 0.9

SPLICE_INTERVAL_S = 3600.0
SHORT_ALLOWANCE_FACTOR = 1.5  # how much longer the stores last
SHORT_ALLOWANCE_GRIEVANCE_PER_HOUR = 0.10


def _crew_hands(state, ship: int) -> int:
    n = 0
    for _ent, crew in state.world.get_component(c.CrewMember):
        if crew.ship == ship:
            n += 1
    return n


def anchor_system(state, dt: float) -> None:
    """Let go and weigh. The order is `ShipOrders.anchor`; her condition is
    `anchored`, and the work between the two takes men and time."""
    world = state.world
    for ship, (orders, speed, sails) in world.get_components(c.ShipOrders, c.Speed, c.SailPlan):
        name = world.try_component(ship, c.Name)
        who = name.full if name is not None else "She"
        if orders.anchor == orders.anchored:
            orders.anchor_work_s = 0.0
            if orders.anchored:
                # Riding to it: she makes no way, whatever her canvas.
                speed.knots = max(0.0, speed.knots - ANCHOR_DRAG_PER_S * dt)
            continue
        if orders.anchor_work_s <= 0.0:
            # Starting the work - if she is in a state to do it at all.
            if orders.anchor:
                if sails.trim > MAX_TRIM_TO_ANCHOR:
                    if ship == state.player_ship:
                        state.say("She will not lie to her anchor under sail - shorten right in first (s).", "warn")
                    orders.anchor = False
                    continue
                if speed.knots > MAX_SPEED_TO_ANCHOR_KN:
                    if ship == state.player_ship:
                        state.say(f"Too much way on her to let go - {speed.knots:.1f} knots. Take the way off her.", "warn")
                    orders.anchor = False
                    continue
                orders.anchor_work_s = LET_GO_S
                state.say(f"Stand by to let go - {who}'s people are at the cathead.", "order")
            else:
                hands = max(1, _crew_hands(state, ship))
                orders.anchor_work_s = WEIGH_S * min(2.0, max(0.6, 24.0 / hands))
                state.say(f"Hands to the capstan - weighing {who}'s anchor.", "order")
            continue
        orders.anchor_work_s -= dt
        if orders.anchor_work_s > 0.0:
            continue
        orders.anchor_work_s = 0.0
        orders.anchored = orders.anchor
        if orders.anchored:
            speed.knots = 0.0
            state.say(f"The anchor is let go. {who} brings up and rides to it.", "order")
        else:
            state.say(f"Anchor's aweigh - {who} is under way.", "order")


def moored_to(state, ship: int, max_m: float = 140.0):
    """The nearest building to a ship that is lying to her anchor - which
    is what being docked amounts to in a Mediterranean port: anchored in
    the roads, within a boat's pull of the quay."""
    world = state.world
    orders = world.try_component(ship, c.ShipOrders)
    pos = world.try_component(ship, c.WorldPosition)
    if orders is None or pos is None or not orders.anchored:
        return None
    from broadside.sim.voxels import VoxelStructure

    best, bd = None, max_m * max_m
    for ent, (_vs, bpos) in world.get_components(VoxelStructure, c.WorldPosition):
        if ent == ship:
            continue
        d = (bpos.x_m - pos.x_m) ** 2 + (bpos.y_m - pos.y_m) ** 2
        if d < bd:
            best, bd = ent, d
    return best


def rations_system(state, dt: float) -> None:
    """Short allowance: the stores go further and the men mind it. Their
    grievance is what turns into sullenness and, in the end, trouble."""
    world = state.world
    for ship, orders in world.get_component(c.ShipOrders):
        if not orders.short_allowance:
            continue
        from broadside.sim.people.psyche import appraise

        per_s = SHORT_ALLOWANCE_GRIEVANCE_PER_HOUR / 3600.0 * dt
        for ent, (psy, crew) in world.get_components(pc.Psyche, c.CrewMember):
            if crew.ship != ship:
                continue
            psy.grievance = min(1.0, psy.grievance + per_s)
            # And they feel it now, not only in the ledger: short commons
            # is an appraisal the psyche model already knows.
            appraise(state, ent, "short_commons", 0.02 * dt / 30.0)


def days_of_victuals(state, ship: int) -> float:
    """How long her provisions will last at the present allowance."""
    from broadside.sim.items import RATION, stores_summary

    hands = max(1, _crew_hands(state, ship))
    tot = stores_summary(world=state.world, ship=ship)
    days = None
    for commodity, (_unit, per_day) in RATION.items():
        have = tot.get(commodity, 0.0)
        d = have / max(1e-6, per_day * hands)
        days = d if days is None else min(days, d)
    days = 0.0 if days is None else days
    orders = state.world.try_component(ship, c.ShipOrders)
    if orders is not None and orders.short_allowance:
        days *= SHORT_ALLOWANCE_FACTOR
    return days


def splice_the_mainbrace(state, ship: int) -> str:
    """An extra issue of grog, out of the captain's own goodwill. It costs
    rum out of the hold and it works: a ship's company that has just been
    given a drink is a different ship's company."""
    world = state.world
    orders = world.component_for_entity(ship, c.ShipOrders)
    if state.now_s - orders.spliced_at_s < SPLICE_INTERVAL_S:
        return "The men have been served once already - any more and you will have a drunken ship."
    hands = max(1, _crew_hands(state, ship))
    want = 0.5 * hands  # half a pint a man
    got = 0.0
    for _ent, (stowed, cont) in world.get_components(Stowed, Contents):
        if stowed.ship != ship or "rum" not in cont.goods:
            continue
        take = min(cont.goods["rum"], want - got)
        cont.goods["rum"] -= take
        got += take
        if got >= want - 1e-6:
            break
    if got < want * 0.25:
        return "There is no rum left in the hold to serve out."
    share = got / want
    from broadside.sim.people.psyche import appraise

    for ent, (_psy, crav, crew) in world.get_components(pc.Psyche, pc.Cravings, c.CrewMember):
        if crew.ship != ship:
            continue
        # The same appraisal the daily issue makes, at a double allowance:
        # contentment now, which is what morale is made of (people/psyche.py).
        appraise(state, ent, "grog", 2.0 * share)
        crav.need = max(0.0, crav.need - 0.6 * share)
    orders.spliced_at_s = state.now_s
    state.say("'Splice the mainbrace!' - and a cheer runs forward along the deck.", "order")
    return "Splice the mainbrace: an extra issue of grog, and the men know whose doing it was."
