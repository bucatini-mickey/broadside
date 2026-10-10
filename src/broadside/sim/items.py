# Items and containers: every cask, barrel, shot garland and bread bag is
# an entity with its contents recorded.
#
# A ship's stores are generated from her complement and the length of the
# cruise she's victualled for, using period ration scales (per man per
# day: a gallon of beer or water, a pound of biscuit, salt beef or pork
# on alternate days, half a pint of rum as grog...). Casks sit in the hold
# (not yet drawn - one deck level for now) or on the weather deck where
# they'd really be: shot garlands beside each gun, the scuttlebutt of
# drinking water by the mainmast, fire buckets. Consumption and resupply
# (Phase 5) act on these same numbers.

from __future__ import annotations

import random
from dataclasses import dataclass, field

import esper

from broadside.sim import components as c
from broadside.sim import shiplayout as sl

# Period cask sizes, litres (imperial gallons x 4.546).
BUTT_L = 491.0  # 108 gal
PUNCHEON_L = 327.0  # 72 gal
HOGSHEAD_L = 245.0  # 54 gal
BARREL_L = 164.0  # 36 gal

# Per man per day.
RATION = {
    "fresh water": ("litre", 4.5),
    "ship's biscuit": ("lb", 1.0),
    "salt beef": ("lb", 0.57),  # 4 lb per man per week, on beef days
    "salt pork": ("lb", 0.29),
    "dried peas": ("pint", 0.29),
    "oatmeal": ("pint", 0.43),
    "cheese": ("lb", 0.14),
    "butter": ("lb", 0.14),
    "rum": ("pint", 0.5),  # issued as grog, cut with water
}

CONTAINER_FOR = {
    "fresh water": ("butt", BUTT_L, "litre"),
    "ship's biscuit": ("bag", 112.0, "lb"),
    "salt beef": ("cask", 336.0, "lb"),
    "salt pork": ("cask", 320.0, "lb"),
    "dried peas": ("barrel", 288.0, "pint"),
    "oatmeal": ("barrel", 288.0, "pint"),
    "cheese": ("crate", 112.0, "lb"),
    "butter": ("firkin", 56.0, "lb"),
    "rum": ("puncheon", 576.0, "pint"),
    "gunpowder": ("barrel", 90.0, "lb"),
}


@dataclass
class Item:
    kind: str  # what it is: "cask", "shot garland", "fire bucket"...
    material: str = "oak"
    condition: float = 1.0


@dataclass
class Contents:
    """What a container holds: commodity -> quantity (in `unit`)."""

    goods: dict = field(default_factory=dict)
    unit: str = ""
    capacity: float = 0.0


@dataclass
class Stowed:
    """Where an item is aboard. `x, y` is a weather-deck tile, or None when
    stowed below (the hold isn't drawn yet)."""

    ship: int
    x: int | None = None
    y: int | None = None
    place: str = "hold"  # "hold" | "weather deck" | "magazine"


def _container(world, ship, commodity, qty, place="hold", x=None, y=None) -> int:
    kind, cap, unit = CONTAINER_FOR[commodity]
    return world.create_entity(
        Item(kind=kind, material="oak"),
        Contents(goods={commodity: round(qty, 1)}, unit=unit, capacity=cap),
        Stowed(ship=ship, x=x, y=y, place=place),
    )


def victual_ship(world: esper.World, ship: int, layout: sl.DeckLayout, complement: int, days: int, rng: random.Random) -> dict:
    """Load a ship's stores for `complement` men and `days` at sea.
    Returns a summary {commodity: (containers, total)}."""
    summary = {}
    for commodity, (unit, per_day) in RATION.items():
        total = per_day * complement * days
        _kind, cap, _u = CONTAINER_FOR[commodity]
        n = 0
        left = total
        while left > 0.01:
            q = min(cap, left)
            _container(world, ship, commodity, q)
            left -= q
            n += 1
        summary[commodity] = (n, total)
    # Powder: roughly 60 charges per gun at ~1/3 shot weight - approximated
    # per gun here; the gunner's magazine.
    guns = len(layout.guns)
    powder_lb = guns * 60 * 6.0
    n = 0
    left = powder_lb
    while left > 0.01:
        q = min(90.0, left)
        world.create_entity(Item(kind="powder barrel"), Contents(goods={"gunpowder": q}, unit="lb", capacity=90.0), Stowed(ship=ship, place="magazine"))
        left -= q
        n += 1
    summary["gunpowder"] = (n, powder_lb)

    # Round shot: about sixty rounds a gun was the establishment, stowed
    # below in the shot lockers and brought up as the garlands empty.
    per_kind: dict = {}
    for g in layout.guns:
        per_kind[_shot_for(g.kind)] = per_kind.get(_shot_for(g.kind), 0) + ROUNDS_PER_GUN
    for kind, rounds in per_kind.items():
        world.create_entity(
            Item(kind="shot locker", material="oak"),
            Contents(goods={kind: float(rounds)}, unit="rounds", capacity=float(rounds)),
            Stowed(ship=ship, place="hold"),
        )
        summary[kind] = (1, float(rounds))

    # On the weather deck: a shot garland by each gun, the scuttlebutt by
    # the mainmast, fire buckets along the waist.
    for g in layout.guns:
        if not g.on_deck:
            continue
        gx, gy = g.x, g.y - g.side  # one tile inboard of the gun
        if layout.tile(gx, gy) in sl.WALKABLE:
            shot = _shot_for(g.kind)
            world.create_entity(Item(kind="shot garland", material="oak"), Contents(goods={shot: 12}, unit="rounds", capacity=12), Stowed(ship=ship, x=gx, y=gy, place="weather deck"))
    # The signal locker on the quarterdeck, beside the wheel: the flags of
    # the ship's code book (sim/systems/signals.py).
    wx, wy = layout.helm
    for dx, dy in ((0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        if layout.tile(wx + dx, wy + dy) in sl.WALKABLE:
            world.create_entity(
                Item(kind="signal locker", material="oak"),
                Contents(goods={"signal flags": 1.0}, unit="set", capacity=1.0),
                Stowed(ship=ship, x=wx + dx, y=wy + dy, place="weather deck"),
            )
            break

    main = layout.main_mast()
    if main is not None:
        for dx, dy in ((1, 1), (1, -1), (-1, 1)):
            if layout.tile(main.x + dx, main.y + dy) in sl.WALKABLE:
                world.create_entity(Item(kind="scuttlebutt", material="oak"), Contents(goods={"fresh water": round(HOGSHEAD_L * rng.uniform(0.4, 0.95), 1)}, unit="litre", capacity=HOGSHEAD_L), Stowed(ship=ship, x=main.x + dx, y=main.y + dy, place="weather deck"))
                break
    return summary


def _shot_for(gun_kind: str) -> str:
    k = gun_kind.lower()
    for w in ("68", "32", "24", "18", "12", "9", "6"):
        if w in k:
            return f"{w}-pdr round shot"
    return "round shot"


CARTRIDGES_PER_GUN = 10
GARLAND_ROUNDS = 12  # what stands at a gun, ready to hand
ROUNDS_PER_GUN = 60  # the establishment, stowed below


def cartridge_lb(gun_kind: str) -> float:
    """Powder in one cartridge: a third of the shot's weight was the
    standard service charge for a long gun, a quarter for a carronade."""
    lb = 12.0
    digits = ""
    for ch in gun_kind:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if digits:
        lb = float(digits)
    return lb * (0.25 if "carronade" in gun_kind.lower() else 0.333)


def serve_out_ammunition(world: esper.World, ship: int, layout: sl.DeckLayout, per_gun: int = CARTRIDGES_PER_GUN) -> int:
    """Clearing for action, and every few minutes after: the boys bring
    cartridges up from the magazine and shot up from the lockers, filling
    the box and the garland beside each gun on deck. Both come out of real
    stores, so a ship can be fought dry. Returns how many rounds of powder
    and shot were served out between them."""
    boxes = {}
    for ent, (item, st, cont) in world.get_components(Item, Stowed, Contents):
        if st.ship == ship and item.kind == "cartridge box" and st.x is not None:
            boxes[(st.x, st.y)] = cont
    powder = [cont for _e, (item, st, cont) in world.get_components(Item, Stowed, Contents) if st.ship == ship and st.place == "magazine" and cont.goods.get("gunpowder", 0) > 0]
    lockers = [cont for _e, (item, st, cont) in world.get_components(Item, Stowed, Contents) if st.ship == ship and item.kind == "shot locker"]
    garlands = {}
    for ent, (item, st, cont) in world.get_components(Item, Stowed, Contents):
        if st.ship == ship and item.kind == "shot garland" and st.x is not None:
            garlands[(st.x, st.y)] = cont
    served = 0
    for g in layout.guns:
        if not g.on_deck:
            continue
        spot = None
        for dx, dy in ((0, -g.side), (1, -g.side), (-1, -g.side), (0, -2 * g.side)):
            x, y = g.x + dx, g.y + dy
            if (x, y) in boxes:
                spot = (x, y)
                break
            if layout.tile(x, y) in sl.WALKABLE and spot is None:
                spot = (x, y)
        if spot is None:
            continue
        cont = boxes.get(spot)
        if cont is None:
            cont = Contents(goods={"powder cartridge": 0.0}, unit="cartridges", capacity=float(per_gun))
            world.create_entity(Item(kind="cartridge box", material="oak"), cont, Stowed(ship=ship, x=spot[0], y=spot[1], place="weather deck"))
            boxes[spot] = cont
        want = per_gun - cont.goods.get("powder cartridge", 0.0)
        lb = cartridge_lb(g.kind)
        while want > 0 and powder:
            if powder[0].goods["gunpowder"] < lb:
                powder.pop(0)
                continue
            powder[0].goods["gunpowder"] = round(powder[0].goods["gunpowder"] - lb, 2)
            cont.goods["powder cartridge"] = cont.goods.get("powder cartridge", 0.0) + 1
            want -= 1
            served += 1
        # And shot from the locker into this gun's garland.
        shot_kind = _shot_for(g.kind)
        garland = None
        for dx, dy in ((0, -g.side), (1, -g.side), (-1, -g.side), (0, -2 * g.side), (0, 0)):
            garland = garlands.get((g.x + dx, g.y + dy))
            if garland is not None:
                break
        if garland is None:
            continue
        need = GARLAND_ROUNDS - sum(garland.goods.values())
        while need > 0 and lockers:
            have = lockers[0].goods.get(shot_kind, 0)
            if have <= 0:
                lockers.pop(0)
                continue
            lockers[0].goods[shot_kind] = have - 1
            garland.goods[shot_kind] = garland.goods.get(shot_kind, 0) + 1
            need -= 1
            served += 1
    return served


def items_at(world: esper.World, ship: int, x: int, y: int) -> list:
    out = []
    for ent, (item, st) in world.get_components(Item, Stowed):
        if st.ship == ship and st.x == x and st.y == y:
            out.append((ent, item, world.try_component(ent, Contents)))
    return out


def stores_summary(world: esper.World, ship: int) -> dict:
    tot: dict = {}
    for ent, (st, cont) in world.get_components(Stowed, Contents):
        if st.ship != ship:
            continue
        for k, q in cont.goods.items():
            tot[k] = tot.get(k, 0.0) + q
    return tot


def place_item(world: esper.World, ship: int, kind: str, goods: dict, unit: str, capacity: float, x: int, y: int, material: str = "oak") -> int:
    """Put a container on a weather-deck tile."""
    return world.create_entity(Item(kind=kind, material=material), Contents(goods=dict(goods), unit=unit, capacity=capacity), Stowed(ship=ship, x=x, y=y, place="weather deck"))
