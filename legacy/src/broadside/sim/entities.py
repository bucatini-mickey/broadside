# Entity factory functions. Keeping entity assembly here (rather than
# scattered at call sites) means "what components make up a ship" or "what
# makes up a sailor" has one obvious place to look and to extend as later
# phases add components.

from __future__ import annotations

import random

import esper

from broadside.sim import components as c
from broadside.sim.shipdata.loader import ShipClassData, load_ship_class

FIRST_NAMES = [
    "James", "Thomas", "William", "John", "Henry", "George", "Edward",
    "Samuel", "Joseph", "Robert", "Charles", "Richard", "Isaac", "Owen",
]
LAST_NAMES = [
    "Hollis", "Fenwick", "Pryce", "Coombes", "Marsh", "Kettering", "Dray",
    "Fairweather", "Winlock", "Astley", "Corbin", "Whitlow", "Sedgwick",
]

ROLES = [
    "Topman", "Waister", "Gun Captain", "Landsman", "Ship's Boy",
    "Bosun's Mate", "Quartermaster's Mate", "Carpenter's Mate",
]


def random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def create_ship(
    world: esper.World,
    ship_class: str,
    *,
    x_nm: float = 0.0,
    y_nm: float = 0.0,
    heading_degrees: float = 0.0,
) -> tuple[int, ShipClassData]:
    """Create a ship entity from a ship-class data file. Returns the entity
    id and the loaded class data (callers commonly need both - e.g. to know
    the deck grid size when placing crew)."""
    data = load_ship_class(ship_class)
    ship = world.create_entity(
        c.Name(data.name),
        c.ShipTag(ship_class=ship_class),
        c.Hull(length_m=data.length_m, beam_m=data.beam_m, max_crew=data.max_crew),
        c.SailPlan(trim=0.5),
        c.Speed(knots=0.0),
        c.WorldPosition(x_nm=x_nm, y_nm=y_nm),
        c.Heading(degrees=heading_degrees),
        c.DeckGrid(width=data.deck_width, height=data.deck_height),
    )
    return ship, data


def create_sailor(
    world: esper.World,
    ship: int,
    deck_width: int,
    deck_height: int,
    rng: random.Random,
    *,
    role: str | None = None,
) -> int:
    """Create a sailor entity crewing `ship`, placed at a random deck tile."""
    x = rng.randint(1, max(1, deck_width - 2))
    y = rng.randint(1, max(1, deck_height - 2))
    chosen_role = role or rng.choice(ROLES)
    return world.create_entity(
        c.Name(random_name(rng)),
        c.CrewMember(ship=ship),
        c.Role(title=chosen_role),
        c.DeckPosition(x=x, y=y),
        # No fg colour set here deliberately: crew glyphs are coloured by
        # role at render time (render/palette.role_color), keeping sim/
        # free of any render-layer concept of colour. See the Renderable
        # docstring in sim/components.py.
        c.Renderable(glyph="@"),
        c.Needs(
            fatigue=rng.uniform(0.0, 0.3),
            hunger=rng.uniform(0.0, 0.3),
            thirst=rng.uniform(0.0, 0.3),
        ),
        c.Mood(value=rng.uniform(-0.1, 0.4)),
        c.Wanderer(),
    )


# --- Engine v1 spawning ----------------------------------------------------
#
# spawn_ship builds a fully-bodied ship for the vision/scene engine: 1 m
# deck plan, helm, battery, orders, contacts, faction - plus, optionally, a
# named crew placed on real walkable deck tiles, a captain at his post on
# the quarterdeck and a lookout at the main masthead (the two observers the
# sighting system uses). create_ship above stays as the minimal Phase 0
# constructor.

from broadside.sim import shiplayout as _sl  # noqa: E402

CAPTAIN_NAMES = ["Hornby", "Aubrey", "Pellew", "Saumarez", "Cochrane", "Hardy", "Troubridge", "Foley"]


def spawn_ship(
    world: esper.World,
    ship_class: str,
    rng: random.Random,
    *,
    x_m: float = 0.0,
    y_m: float = 0.0,
    heading_degrees: float = 0.0,
    name: str | None = None,
    faction: str = "british",
    trim: float = 0.6,
    crew: int = 0,
    complement: int | None = None,
    observers: bool = True,
    abstract_crew: bool | None = None,
    victual_days: int = 60,
    captain_name: str | None = None,
    culture: str | None = None,
    year: int = 1805,
    places: list | None = None,
    battles: list | None = None,
) -> int:
    """A fully-bodied ship. Every one of her company is a generated person
    (sim/people): `crew` of them stand on the weather deck (drawn, pathing,
    working guns), the rest of the `complement` are aboard below decks -
    fully simulated, not yet drawn. Complement defaults to the class's
    full establishment. Every deck tile gets a material and a condition,
    and her hold is victualled for `victual_days`."""
    from broadside.sim import items as _items
    from broadside.sim import structure as _structure
    from broadside.sim.people import FACTION_CULTURE
    from broadside.sim.people.generate import assign_roles, generate_person
    from broadside.sim.people.psyche import ShipMorale

    data = load_ship_class(ship_class)
    layout = _sl.build_deck_layout(data)
    main_culture = culture or FACTION_CULTURE.get(faction, "k0")
    complement = data.max_crew if complement is None else max(complement, crew)
    ship = world.create_entity(
        c.Name(name or data.name),
        c.ShipTag(ship_class=ship_class),
        c.Hull(length_m=data.length_m, beam_m=data.beam_m, max_crew=data.max_crew),
        c.SailPlan(trim=trim),
        c.Speed(knots=0.0),
        c.WorldPosition(x_nm=x_m / c.M_PER_NM, y_nm=y_m / c.M_PER_NM),
        c.Heading(degrees=heading_degrees),
        c.DeckGrid(width=layout.width, height=layout.height),
        c.ShipBody(layout=layout),
        c.Faction(faction),
        c.Helm(desired_heading=heading_degrees, turn_rate_dps=max(1.1, 70.0 / data.length_m)),
        c.Battery(
            guns=[c.GunState(index=g.index) for g in layout.guns],
            reload_s=75.0,
            abstract_crew=(crew == 0) if abstract_crew is None else abstract_crew,
        ),
        c.ShipOrders(),
        c.Contacts(),
        _structure.new_structure_state(layout),
        ShipMorale(),
    )

    people = [generate_person(rng, nation=faction, main_culture=main_culture, year=year, places=places, battles=battles) for _ in range(complement)]
    assign_roles(people, rng)
    # The men on deck: prefer those whose work is up here.
    deck_first = sorted(range(len(people)), key=lambda i: (people[i].role in ("Marine", "Loblolly Boy", "Cook's Mate"), rng.random()))
    on_deck = set(deck_first[:crew])
    free_tiles = layout.walkable_tiles()
    rng.shuffle(free_tiles)
    for k, p in enumerate(people):
        comps = [
            c.Name(p.identity.full),
            c.CrewMember(ship=ship, home_ship=ship),
            c.Role(title=p.role),
            c.Renderable(glyph="@"),
            c.Needs(fatigue=rng.uniform(0.0, 0.3), hunger=rng.uniform(0.0, 0.3), thirst=rng.uniform(0.0, 0.3)),
            c.Mood(value=p.psyche.morale),
        ] + p.components()
        if k in on_deck and free_tiles:
            x, y = free_tiles.pop()
            comps += [c.DeckPosition(x=x, y=y), c.CrewTask(cooldown_ticks=rng.randint(0, 40))]
        else:
            comps.append(c.Below())
        world.create_entity(*comps)

    if observers:
        cx, cy = layout.captain_post
        cap = generate_person(rng, nation=faction, main_culture=main_culture, culture=main_culture, year=year, background="gentleman_officer", places=places, battles=battles)
        cap.identity.rank = "captain"
        cap.identity.nickname = ""
        if captain_name:
            parts = captain_name.split()
            cap.identity.given, cap.identity.family = (" ".join(parts[:-1]) or parts[0]), parts[-1]
        cap.skills.level["leadership"] = max(cap.skills.level["leadership"], rng.uniform(0.55, 0.85))
        cap.skills.level["navigation"] = max(cap.skills.level["navigation"], rng.uniform(0.5, 0.8))
        cap.biography.add(year, f"Took command of {name or data.name}.")
        world.create_entity(
            c.Name(f"Capt. {cap.identity.given} {cap.identity.family}"),
            c.CrewMember(ship=ship, home_ship=ship),
            c.Role(title="Captain"),
            c.DeckPosition(x=cx, y=cy),
            c.Renderable(glyph="@"),
            c.CrewTask(kind="station", station=(cx, cy), station_kind="post"),
            c.Observer(ship=ship, post="captain", eye_height_m=layout.freeboard_m + _sl.EYE_ABOVE_DECK_M),
            *cap.components(),
        )
        # His mind, as a component on the ship: what he is trying to do and
        # what he is like (sim/systems/captain_ai.py). It is read only for
        # ships that are not the player's.
        from broadside.sim.systems.captain_ai import from_person as _captain_mind

        world.add_component(ship, _captain_mind(cap))
        mast = layout.main_mast()
        if mast is not None:
            look = generate_person(rng, nation=faction, main_culture=main_culture, year=year, background="career_seaman", places=places)
            look.skills.level["lookout"] = max(look.skills.level["lookout"], rng.uniform(0.6, 0.9))
            world.create_entity(
                c.Name(look.identity.full),
                c.CrewMember(ship=ship, home_ship=ship),
                c.Role(title="Lookout"),
                c.DeckPosition(x=mast.x, y=mast.y),
                c.Renderable(glyph="@"),
                c.CrewTask(kind="station", station=(mast.x, mast.y), station_kind="post"),
                c.Aloft(mast=mast.name),
                c.Observer(ship=ship, post="lookout", eye_height_m=layout.freeboard_m + 0.92 * mast.height_above_deck, report_delay_s=6.0),
                *look.components(),
            )
    if victual_days > 0:
        _items.victual_ship(world, ship, layout, complement + (2 if observers else 0), victual_days, rng)
    return ship


def create_crew_member(world: esper.World, ship: int, x: int, y: int, rng: random.Random, role: str | None = None) -> int:
    """Phase 0-style minimal sailor (no person model). Kept for the classic
    demo; spawn_ship now generates full people."""
    return world.create_entity(
        c.Name(random_name(rng)),
        c.CrewMember(ship=ship, home_ship=ship),
        c.Role(title=role or rng.choice(ROLES)),
        c.DeckPosition(x=x, y=y),
        c.Renderable(glyph="@"),
        c.Needs(
            fatigue=rng.uniform(0.0, 0.3),
            hunger=rng.uniform(0.0, 0.3),
            thirst=rng.uniform(0.0, 0.3),
        ),
        c.Mood(value=rng.uniform(-0.1, 0.4)),
        c.CrewTask(cooldown_ticks=rng.randint(0, 40)),
    )


def find_captain(world: esper.World, ship: int) -> int | None:
    for ent, obs in world.get_component(c.Observer):
        if obs.ship == ship and obs.post == "captain":
            return ent
    return None


def find_observer(world: esper.World, ship: int, post: str) -> int | None:
    for ent, obs in world.get_component(c.Observer):
        if obs.ship == ship and obs.post == post:
            return ent
    return None
