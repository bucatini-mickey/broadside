# The sandbox: a ship to potter about on.
#
# Not a battle and not a demonstration - a place to stand on a deck, walk
# where you like, and try things on the objects around you. A brig with her
# company aboard, provisions struck up on deck where you can look into
# them, a signal locker on the quarterdeck, a gun's crew who will work
# their piece through the whole drill when you beat to quarters, a derelict
# hulk moored to starboard to fire into, and a stone wall on an islet to
# knock down.
#
# Everything here is the ordinary engine: nothing is scripted, nothing is
# special-cased. See docs/design/16_observation_and_targeting.md.

from __future__ import annotations

from broadside.scenarios.base import Checkpoint, SceneBuilder, expect, scenario
from broadside.sim import components as c
from broadside.sim.items import Contents, Item, Stowed, place_item

DECK_STORES = (
    ("cask", {"salt beef": 180.0}, "lb", 336.0),
    ("cask", {"salt pork": 140.0}, "lb", 320.0),
    ("bag", {"ship's biscuit": 90.0}, "lb", 112.0),
    ("barrel", {"dried peas": 120.0}, "pint", 288.0),
    ("firkin", {"butter": 40.0}, "lb", 56.0),
    ("puncheon", {"rum": 300.0}, "pint", 576.0),
    ("fire bucket", {"salt water": 8.0}, "litre", 9.0),
)


def _stow_on_deck(world, ship: int, layout) -> int:
    """Strike a few casks up on deck, in the waist where they would be
    lashed down, so you can walk up to them and look inside."""
    taken = {(st.x, st.y) for _e, (i, st) in world.get_components(Item, Stowed) if st.x is not None}
    spots = []
    cy = layout.centre_row
    for x in range(int(0.40 * layout.hull_length), int(0.72 * layout.hull_length)):
        for dy in (-2, 2, -3, 3):
            if layout.tile(x, cy + dy) == 2 and (x, cy + dy) not in taken:
                spots.append((x, cy + dy))
    n = 0
    for (kind, goods, unit, cap), (x, y) in zip(DECK_STORES, spots):
        place_item(world, ship, kind, goods, unit, cap, x, y)
        n += 1
    return n


def _sandbox_scene(seed: int):
    b = SceneBuilder(seed, wind_from=270.0, wind_knots=7.0, start_hour=9.5)
    me = b.player("brig_14", name="Kestrel", heading_degrees=0.0, trim=0.35, crew=44, victual_days=30)
    b.set_speed(me, 3.5)  # under way, the wind abeam: her handiest point
    # A shoal to starboard with a stone curtain wall on it, and a derelict
    # hulk moored short of it: something to knock down, and something to
    # shoot into.
    b.island(430.0, 60.0, 90.0, peak_m=14.0, wooded=False, shoal_m=30.0)
    b.wall(350.0, 40.0, 0.0, length_m=24.0, thickness_m=2.0, height_m=6.0, name="sea wall")
    hulk = b.ship("brig_14", name="Derelict hulk", faction="french", x_m=120.0, y_m=30.0, heading_degrees=15.0, trim=0.0, crew=0)
    w = b.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    battery = w.component_for_entity(me, c.Battery)
    battery.verbose_drill = True  # narrate the drill in the log
    casks = _stow_on_deck(w, me, layout)
    run = b.build(duration_s=180, checkpoints=[])
    run.hulk = hulk
    run.casks = casks
    run.captain = next(e for e, o in w.get_component(c.Observer) if o.ship == me and o.post == "captain")
    return run


def _deck_items(kind: str, at_least: int):
    def fn(state):
        n = 0
        for _e, (item, st) in state.world.get_components(Item, Stowed):
            if st.ship == state.player_ship and st.x is not None and (kind in item.kind or kind == "any"):
                n += 1
        return n >= at_least, f"{n} {kind} items on deck"

    return fn


def _crew_about(state):
    n = sum(1 for _e, (crew, _p) in state.world.get_components(c.CrewMember, c.DeckPosition) if crew.ship == state.player_ship)
    return n > 20, f"{n} hands on deck"


@scenario(
    "sandbox",
    "Sandbox: a deck to walk, things to try",
    "A brig at sea with her company aboard and nothing required of you. Walk the deck, look into the casks "
    "struck up in the waist, drink from the scuttlebutt, read the signal book and hoist a signal, beat to "
    "quarters and watch the gun crews work their pieces through the drill, and fire into the derelict hulk "
    "to starboard or at the stone wall on the islet beyond her.",
    look_for=[
        "m: walk mode. Arrow keys walk you about the deck; e shows what you can do where you stand.",
        "Casks, bags and a rum puncheon in the waist: stand beside one and inspect it to see what is in it.",
        "Signal locker by the wheel: read the book, hoist a signal, and watch for it to be answered.",
        "b beats to quarters: men walk to their stations, and every gun's crew starts the drill. The log names them.",
        "[ and ] fire the batteries. The hulk is 120 m to starboard; the wall on the islet is 350 m off.",
    ],
    duration_s=180,
)
def sandbox(seed: int = 1806):
    run = _sandbox_scene(seed)
    run.checkpoints = [
        Checkpoint(2, "Your brig, her company about their work, stores struck up on deck.", {"paused": True}, [expect("stores on deck", _deck_items("any", 6)), expect("a crew aboard", _crew_about)]),
        Checkpoint(25, "The captain's eye: what you can actually see from the quarterdeck.", {}),
        Checkpoint(40, "The macro view: the hulk to starboard, the islet and its wall beyond.", {"scale": "macro", "macro_zoom": 3}),
        Checkpoint(55, "Walk mode (m): three cells to the metre, the captain in the middle, the view his own.", {"follow": run.captain, "subcell": 5, "fit": False, "square_local": True}),
        Checkpoint(56, "The same, with time stopped: planning mode shows the whole ship around him.", {"follow": run.captain, "subcell": 5, "fit": False, "square_local": True, "paused": True}),
    ]
    return run


def _asleep_count(state) -> int:
    from broadside.sim.people.life import Asleep

    return sum(
        1
        for e, cm in state.world.get_component(c.CrewMember)
        if cm.ship == state.player_ship and state.world.has_component(e, Asleep)
    )


def _some_asleep(state):
    n = _asleep_count(state)
    return n > 5, f"{n} men asleep below"


def _raining(state):
    r = state.atmosphere.rain
    return r > 0.3, f"rain {r:.2f}, visibility {state.atmosphere.effective_visibility_m() / 1000:.1f} km"


def _everyone_turned_out(state):
    from broadside.sim.people.life import Asleep

    below = sum(
        1
        for e, cm in state.world.get_component(c.CrewMember)
        if cm.ship == state.player_ship and state.world.has_component(e, c.Below)
    )
    asleep = _asleep_count(state)
    return below == 0 and asleep == 0, f"{below} below, {asleep} asleep"


@scenario(
    "night_watch",
    "A night at sea: watches, sleep, and a squall",
    "Two bells in the middle watch. Half the company is asleep below in their hammocks and the other half "
    "has the deck; a squall comes up and soaks them; then you beat to quarters at four in the morning and "
    "every man turns out, which is how a night action ruined a crew for days. Shows the day aboard: the "
    "watch bill, sleep paying off fatigue, meals out of the casks, and weather on your back.",
    look_for=[
        "Panel 2 (crew): who is below, who is asleep, and the fatigue of each watch.",
        "The log: the squall coming up, the rain, and the hands turning out when the drums go.",
        "The deck is thin at night - half the company is in their hammocks until you call them.",
        "Levels (z): at this zoom you can look down through her to the hold, or up to the mastheads.",
    ],
    duration_s=420,
)
def night_watch(seed: int = 1804):
    b = SceneBuilder(seed, wind_from=250.0, wind_knots=11.0, start_hour=1.0, light=0.12)
    me = b.player("brig_14", name="Kestrel", heading_degrees=20.0, trim=0.35, crew=44, victual_days=30)
    b.set_speed(me, 4.0)
    b.island(900.0, 400.0, 150.0, peak_m=30.0, wooded=True, shoal_m=40.0)
    w = b.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    _stow_on_deck(w, me, layout)
    run = b.build(duration_s=420, checkpoints=[])
    run.captain = next(e for e, o in w.get_component(c.Observer) if o.ship == me and o.post == "captain")

    def squall(st):
        st.atmosphere.clear_visibility_m = st.atmosphere.haze_visibility_m
        st.atmosphere.squall_until_s = st.now_s + 240.0
        st.atmosphere.squall_gust_knots = 16.0
        st.say("A squall coming up on the weather bow - rain and a hard puff with it.", "alert")

    def quarters(st):
        w.component_for_entity(me, c.ShipOrders).quarters = True

    run.sim.at(90.0, squall)
    run.sim.at(300.0, quarters, "All hands! Beat to quarters!")
    run.checkpoints = [
        Checkpoint(60, "Two bells in the middle watch: the watch below is asleep, the deck thinly manned.", {"paused": True}, [expect("the watch below is asleep", _some_asleep)]),
        Checkpoint(180, "The squall: rain, a harder wind, and a shorter horizon.", {}, [expect("it is raining", _raining)]),
        Checkpoint(200, "Looking out into the weather by eye; the chart marks the field of view.", {
            "look_out": __import__("broadside.view.firstperson", fromlist=["Look"]).Look(bearing_deg=20.0, fov_deg=70.0),
            "look_sector": (20.0, 70.0),
        }),
        Checkpoint(205, "The same bearing through the glass: a narrow field, and the chart says so.", {
            "look_out": __import__("broadside.view.firstperson", fromlist=["Look"]).Look(bearing_deg=20.0, fov_deg=7.0, glass=True),
            "look_sector": (20.0, 7.0),
        }),
        Checkpoint(240, "Her levels: the hold under your feet.", {"z_m": -1.0, "subcell": 2, "fit": False, "local_zoom": 0}),
        Checkpoint(242, "And the same moment at the mastheads.", {"z_m": 18.0, "subcell": 2, "fit": False, "local_zoom": 0}),
        Checkpoint(380, "Four in the morning, all hands: every man turned out, wet and tired.", {}, [expect("every man turned out", _everyone_turned_out)]),
    ]
    return run
