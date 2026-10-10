# The scenario library: test environments for the vision engine, the two
# view scales, and the crew/order systems. Each one isolates a mechanism -
# an island hiding a ship, fog rolling in, smoke from a broadside, a hull
# dropping below the horizon - so it can be watched, and checked.
#
# Coordinates are metres, +x east, +y north, the player's ship usually at
# the origin. Wind is given as the direction it blows FROM.
#
# Adding one: write a function decorated with @scenario that builds a scene
# with SceneBuilder and returns builder.build(...) with checkpoints.

from __future__ import annotations

from broadside.scenarios.base import Checkpoint, SceneBuilder, contact, expect, eyes, log_contains, scenario, ship_named
from broadside.sim import components as c
from broadside.sim.items import Contents, Item, Stowed
from broadside.sim.systems.crew_tasks import manned_counts
from broadside.view.compose import ViewState


def _orders(state, ship=None) -> c.ShipOrders:
    return state.world.component_for_entity(ship if ship is not None else state.player_ship, c.ShipOrders)


def _sail(state, ship, trim) -> None:
    state.world.component_for_entity(ship, c.SailPlan).trim = trim


# ---------------------------------------------------------------------------


@scenario(
    "open_water",
    "Open water, clear day",
    "Baseline: your sloop with a consort frigate to starboard and a neutral brig ahead, "
    "in clear weather. Shows the 1 m deck view, the macro view, and planning mode.",
    look_for=[
        "Local view: every cell is 1 m. Bulwarks #, guns ─│╱╲ pointing outboard, masts O, wheel Ø, hatches ≡.",
        "Your crew are @ (coloured by role); you are the highlighted @ on the quarterdeck.",
        "Grey ▒ bars are the sails, braced round to the wind - they swing as the ship changes course.",
        "Thin dark wedges fanning out from the masts: that is your own rigging blocking your sight.",
        "Macro view: ships become clusters of ▓ with a heading arrow, labelled A, B...",
    ],
    duration_s=60,
)
def open_water(seed: int = 1805):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=12.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.6, crew=40)
    b.set_speed(me, 5.0)
    consort = b.ship("frigate_38", name="HMS Arethusa", faction="british", x_m=40.0, y_m=-220.0, heading_degrees=90.0, trim=0.55)
    b.set_speed(consort, 5.0)
    brig = b.ship("brig_14", name="Santa Rosa", faction="neutral", x_m=650.0, y_m=180.0, heading_degrees=260.0, trim=0.5)
    b.set_speed(brig, 4.0)
    return b.build(
        duration_s=60,
        checkpoints=[
            Checkpoint(3, "Deck view, captain's eye: the whole sloop at 1 m per cell.", {"scale": "local"}),
            Checkpoint(3, "Same moment in PLANNING mode (time stopped): the whole ship revealed, including what the masts hid.", {"scale": "local", "paused": True}),
            Checkpoint(20, "Macro view (12 m per column): consort A to starboard, merchant B ahead.", {"scale": "macro", "macro_zoom": 4}, [contact("HMS Arethusa", "hull"), contact("Santa Rosa", "hull")]),
            Checkpoint(45, "Ship-up rotation: the view turns with the ship, bow always up.", {"scale": "local", "rotation": "ship", "local_zoom": 1}),
        ],
    )


@scenario(
    "island_occlusion",
    "Island occlusion",
    "A French frigate sails south behind a wooded island. You watch it disappear behind the land, "
    "its last known position left as a ghost '?', then reappear on the far side.",
    look_for=[
        "The island casts a black 'shadow' away from you - everything in it is out of sight.",
        "When the frigate goes behind the island its marker becomes '?' (last known position).",
        "Terrain you have seen stays drawn in dim memory colours when it goes out of sight.",
    ],
    duration_s=220,
)
def island_occlusion(seed: int = 1806):
    b = SceneBuilder(seed, wind_from=90.0, wind_knots=14.0)
    me = b.player("sloop_18", heading_degrees=0.0, trim=0.2, crew=30)
    b.island(400.0, 0.0, 120.0, peak_m=80.0)
    foe = b.ship("frigate_38", name="Hebe", faction="french", x_m=650.0, y_m=400.0, heading_degrees=180.0, trim=1.0)
    b.set_speed(foe, 7.0)
    return b.build(
        duration_s=220,
        chart=ViewState(scale="macro", macro_zoom=4, pan=(320.0, 0.0)),
        checkpoints=[
            Checkpoint(15, "Hebe (A) in sight to the north-east, beyond the island's shoulder.", {}, [contact("Hebe", "hull")]),
            Checkpoint(100, "Hebe is behind the island: LOST, drawn as '?' where she was last seen. The island's black shadow is everything you can't see.", {}, [contact("Hebe", "lost"), eyes("captain", "Hebe", "none")]),
            Checkpoint(100, "Same moment through the masthead lookout's eyes (higher, but the wooded island tops 80 m).", {"observer": "lookout"}),
            Checkpoint(215, "Hebe reappears south of the island.", {}, [contact("Hebe", "hull")]),
        ],
    )


@scenario(
    "topsails_over_reef",
    "Topsails over a low islet",
    "A low, bare islet (9 m) lies between you and a French frigate. From the quarterdeck her hull is "
    "hidden but her masts and topsails show above the land; the masthead lookout sees all of her.",
    look_for=[
        "Captain's eye: only the frigate's sails (▒) and mastheads (O) appear above the islet - hull hidden.",
        "Macro view: a contact seen only by her topsails is drawn '†'.",
        "Switch to the masthead (o): from 29 m up the whole hull is visible over the islet.",
    ],
    duration_s=60,
)
def topsails_over_reef(seed: int = 1807):
    b = SceneBuilder(seed, wind_from=270.0, wind_knots=8.0)
    me = b.player("sloop_18", heading_degrees=0.0, trim=0.2, crew=30)
    b.island(300.0, 0.0, 60.0, peak_m=9.0, wooded=False, shoal_m=25.0)
    b.ship("frigate_38", name="Topaze", faction="french", x_m=650.0, y_m=0.0, heading_degrees=0.0, trim=0.2)
    return b.build(
        duration_s=60,
        chart=ViewState(scale="macro", macro_zoom=4),
        checkpoints=[
            Checkpoint(12, "Captain's eye at 1 m scale, camera panned 640 m east onto the frigate. The islet (out of frame, west) shadows this whole patch of sea - all black - yet her canvas and mastheads show above it; the '!' is the masthead's report of her hull.", {"scale": "local", "pan": (640.0, 0.0), "square_local": True}, [eyes("captain", "Topaze", "topsails")]),
            Checkpoint(12, "Same, from the masthead: the whole frigate is visible over the islet.", {"scale": "local", "pan": (640.0, 0.0), "square_local": True, "observer": "lookout"}, [eyes("lookout", "Topaze", "hull")]),
            Checkpoint(20, "Macro view: the lookout's report puts her hull 'IN SIGHT (masthead)'.", {"scale": "macro", "macro_zoom": 4}, [contact("Topaze", "hull"), log_contains("Masthead")]),
        ],
    )


@scenario(
    "fog_bank",
    "Fog bank rolls through",
    "A bank of sea fog (60 m visibility inside) drifts down on the wind, swallows you, your consort "
    "and a French frigate, and moves on.",
    look_for=[
        "Fog shows as a grey ░ wall: hidden by murk, not by anything solid.",
        "Inside the bank the visible circle shrinks to a few tens of metres; the HUD shows IN FOG.",
        "From the masthead (o) the lookout can glimpse mastheads standing above the fog's 30 m top.",
        "After it passes, contacts are re-sighted as it clears.",
    ],
    duration_s=210,
)
def fog_bank(seed: int = 1808):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=14.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.25, crew=30)
    b.fog(0.0, 800.0, 1100.0, 380.0, visibility_m=60.0, top_m=30.0, drift_factor=1.0)
    foe = b.ship("frigate_38", name="Vestale", faction="french", x_m=-320.0, y_m=230.0, heading_degrees=90.0, trim=0.2)
    b.ship("brig_14", name="HMS Cygnet", faction="british", x_m=250.0, y_m=-200.0, heading_degrees=90.0, trim=0.2)
    del foe
    return b.build(
        duration_s=210,
        chart=ViewState(scale="macro", macro_zoom=3),
        checkpoints=[
            Checkpoint(8, "The fog bank to the north, a grey wall (20 m per column). Vestale (A) is still clear of it.", {"scale": "macro", "macro_zoom": 5}, [contact("Vestale", "hull"), contact("HMS Cygnet", "hull")]),
            Checkpoint(80, "Inside the fog: visibility collapses to tens of metres. Both contacts lost.", {"scale": "macro", "macro_zoom": 3}, [eyes("captain", "Vestale", "none"), eyes("captain", "HMS Cygnet", "none")]),
            Checkpoint(80, "Same moment at 1 m scale: you can barely see your own bowsprit.", {"scale": "local"}),
            Checkpoint(205, "The fog has passed to the south; Vestale is back in sight.", {"scale": "macro", "macro_zoom": 3}, [contact("Vestale", "hull")]),
        ],
    )


@scenario(
    "broadside_smoke",
    "Broadside smoke",
    "Both ships at quarters, 140 m apart in a light northerly. Broadsides are exchanged and the powder "
    "smoke drifts downwind over the enemy - hiding her hull from your quarterdeck while her topsails "
    "still show above it.",
    look_for=[
        "Muzzle flashes * along the side, then grey ░▒▓ smoke billowing out and drifting south.",
        "The smoke hides the enemy's hull but her sails show above it (smoke only rises ~10-15 m).",
        "Watch it thin and clear over a minute or two; the lookout sees over it.",
    ],
    duration_s=240,
)
def broadside_smoke(seed: int = 1809):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=6.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.4, crew=56)
    foe = b.ship("frigate_38", name="Semillante", faction="french", x_m=0.0, y_m=-140.0, heading_degrees=90.0, trim=0.35)
    b.world.component_for_entity(me, c.ShipOrders).quarters = True
    b.world.component_for_entity(foe, c.ShipOrders).quarters = True
    run = b.build(
        duration_s=240,
        checkpoints=[
            Checkpoint(30, "Cleared for action, 140 m apart. Guns manned and loaded; enemy fully in sight.", {}, [eyes("captain", "Semillante", "hull")]),
            Checkpoint(40.5, "Semillante's broadside, then ours: muzzle flashes * and the first smoke.", {}),
            Checkpoint(60, "Smoke drifts south over the enemy: her hull is hidden, her topsails still show above.", {}, [eyes("captain", "Semillante", "topsails", "none")]),
            Checkpoint(60, "Planning view of the same moment (paused, 1 m): gun crews at their guns, reloading.", {"paused": True, "local_zoom": 0, "square_local": False, "pan": (0.0, 0.0)}),
            Checkpoint(235, "The smoke has cleared.", {}, [eyes("captain", "Semillante", "hull")]),
        ],
    )
    run.sim.at(38.0, lambda st: setattr(_orders(st, ship_named(st, "Semillante")), "fire_side", -1), "Semillante opens fire!")
    run.sim.at(40.0, lambda st: setattr(_orders(st), "fire_side", 1), "Captain: 'Fire as she bears!'")
    return run


@scenario(
    "beat_to_quarters",
    "Beat to quarters (planning mode)",
    "Dwarf-Fortress style orders: the game starts paused, you order the ship to quarters, and when time "
    "runs the crew run to their stations along real paths across the 1 m deck, then fire a broadside.",
    look_for=[
        "Paused (planning) view shows every sailor and fitting, even ones your masts hide.",
        "After the order, hands path around masts, hatches and guns to their stations.",
        "Guns count as manned with 2+ crew; the HUD tracks loaded/manned per side.",
    ],
    duration_s=90,
)
def beat_to_quarters(seed: int = 1810):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=10.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.45, crew=60)
    b.ship("brig_14", name="Target hulk", faction="neutral", x_m=0.0, y_m=-180.0, heading_degrees=90.0, trim=0.0)
    run = b.build(
        duration_s=90,
        checkpoints=[
            Checkpoint(0.5, "Live view: the captain's eye. Masts cast narrow blind wedges over the deck.", {"scale": "local"}),
            Checkpoint(0.5, "Planning mode (paused): the whole ship and every hand is shown regardless of sight lines.", {"scale": "local", "paused": True}),
            Checkpoint(12, "Hands running to stations.", {"scale": "local", "paused": True}),
            Checkpoint(
                45,
                "At quarters: gun crews closed up on both sides, helm manned, sail-trimmers at the masts.",
                {"scale": "local", "paused": True},
                [expect("12+ deck guns manned", lambda st: (sum(1 for v in manned_counts(st, st.player_ship).values() if v >= 2) >= 12, f"{sum(1 for v in manned_counts(st, st.player_ship).values() if v >= 2)} manned"))],
            ),
            Checkpoint(52, "Starboard broadside fired at the hulk.", {"scale": "local"}, [log_contains("Starboard broadside")]),
        ],
    )
    run.sim.at(1.0, lambda st: setattr(_orders(st), "quarters", True), "Order: beat to quarters.")
    run.sim.at(50.0, lambda st: setattr(_orders(st), "fire_side", 1), "Order: fire the starboard battery.")
    return run


@scenario(
    "hull_down",
    "Hull down on the horizon",
    "A French frigate 17 km away. The earth's curvature hides her hull below the horizon: from the "
    "quarterdeck only her topsails show, while the lookout 29 m up sees her whole. As you close, "
    "her hull rises into view.",
    look_for=[
        "Chart scale (320 m per column): the contact is '†' - topsails only - until her hull clears the horizon.",
        "The masthead lookout's report arrives first ('Deck there!').",
    ],
    duration_s=330,
    slow=True,
)
def hull_down(seed: int = 1811):
    # The frigate is on the starboard beam - not ahead, where your own
    # courses would hide her from the quarterdeck anyway.
    b = SceneBuilder(seed, wind_from=90.0, wind_knots=16.0, haze_m=80000.0)
    me = b.player("sloop_18", heading_degrees=0.0, trim=0.4, crew=20)
    b.set_speed(me, 4.0)
    foe = b.ship("frigate_38", name="Pomone", faction="french", x_m=16900.0, y_m=0.0, heading_degrees=270.0, trim=1.0)
    b.set_speed(foe, 7.0)
    return b.build(
        duration_s=330,
        chart=ViewState(scale="macro", macro_zoom=9, pan=(8000.0, 0.0)),
        checkpoints=[
            Checkpoint(10, "~17 km on the starboard beam: from the quarterdeck only her topsails are above the horizon (†).", {}, [eyes("captain", "Pomone", "topsails"), eyes("lookout", "Pomone", "hull")]),
            Checkpoint(325, "She has run down toward you: her hull has risen over the horizon.", {}, [eyes("captain", "Pomone", "hull")]),
        ],
    )


@scenario(
    "night_passage",
    "Nightfall",
    "Dusk deepens into night over two minutes (compressed). A French frigate 1.4 km off fades out of "
    "sight as the light goes; a British brig close aboard stays visible longer.",
    look_for=[
        "The whole view dims toward the grey-blue murk as effective visibility falls.",
        "The frigate is lost first; the nearby brig lingers.",
    ],
    duration_s=150,
)
def night_passage(seed: int = 1812):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=10.0, haze_m=12000.0, light=0.6, start_hour=19.5)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.4, crew=30)
    b.ship("frigate_38", name="Diane", faction="french", x_m=300.0, y_m=-1400.0, heading_degrees=90.0, trim=0.4)
    b.ship("brig_14", name="HMS Swift", faction="british", x_m=-60.0, y_m=-160.0, heading_degrees=90.0, trim=0.4)
    run = b.build(
        duration_s=150,
        chart=ViewState(scale="macro", macro_zoom=5),
        checkpoints=[
            Checkpoint(5, "Dusk: both ships in sight.", {"scale": "macro", "macro_zoom": 5}, [contact("Diane", "hull"), contact("HMS Swift", "hull")]),
            Checkpoint(140, "Night: Diane is lost in the dark; Swift, close aboard, is still visible.", {"scale": "macro", "macro_zoom": 5}, [eyes("captain", "Diane", "none"), eyes("captain", "HMS Swift", "hull")]),
        ],
    )
    for i in range(1, 13):
        light = 0.6 * (0.8 ** i)
        run.sim.at(i * 10.0, lambda st, L=light: setattr(st.atmosphere, "light", L))
    return run


@scenario(
    "narrow_strait",
    "Narrow strait",
    "Threading a 600 m strait between two coasts, past rocks, on an autopilot course. A French brig "
    "waits behind a headland and only comes into view as you round it.",
    look_for=[
        "Coasts rise inland: beach ░, scrub/woods ♣, hills ^ - woods add ~12 m of canopy to block sight.",
        "The ship steers itself along waypoints (HUD: wp N) without running aground.",
        "The brig is hidden by the headland at first, then sighted.",
    ],
    duration_s=260,
    slow=True,
)
def narrow_strait(seed: int = 1813):
    b = SceneBuilder(seed, wind_from=200.0, wind_knots=13.0)
    me = b.player("sloop_18", heading_degrees=0.0, trim=1.0, crew=30)
    b.set_speed(me, 5.0)
    b.coast(270.0, 300.0, max_height_m=90.0)
    b.coast(90.0, 330.0, max_height_m=110.0)
    b.island(260.0, 650.0, 120.0, peak_m=40.0)
    b.rock(90.0, 280.0, radius=5.0, height_m=5.0)
    b.rock(-150.0, 520.0, radius=4.0, height_m=3.0)
    b.rock(-60.0, 820.0, radius=6.0, height_m=7.0)
    b.waypoints(me, [(0.0, 250.0), (-60.0, 480.0), (20.0, 760.0), (0.0, 1100.0)])
    b.ship("brig_14", name="Mutine", faction="french", x_m=150.0, y_m=900.0, heading_degrees=180.0, trim=0.0)
    return b.build(
        duration_s=260,
        chart=ViewState(scale="macro", macro_zoom=3),
        checkpoints=[
            Checkpoint(10, "Entering the strait. The brig is hidden behind the headland to the north-east.", {"scale": "macro", "macro_zoom": 3}, [eyes("captain", "Mutine", "none")]),
            Checkpoint(10, "Deck view at the entrance.", {"scale": "local", "local_zoom": 1}),
            Checkpoint(255, "Rounding the headland: Mutine sighted, and still afloat.", {"scale": "macro", "macro_zoom": 3}, [contact("Mutine", "hull", "topsails"), expect("not aground", lambda st: (not st.world.component_for_entity(st.player_ship, c.Helm).aground, "afloat"))]),
        ],
    )


@scenario(
    "fleet_action",
    "Fleets in line of battle",
    "Macro scale: a British line of six 74s, your frigate to windward as repeating ship, and a French "
    "line on the opposite tack, part of it screened by an island. Each ship is a small cluster of glyphs.",
    look_for=[
        "Every ship is a cluster ▓ with a heading arrow; allied cyan, enemy red, labelled A..M.",
        "French ships behind the island are '?' (last seen) or not shown at all if never seen.",
        "Contacts panel lists what you actually know, including masthead reports.",
    ],
    duration_s=150,
)
def fleet_action(seed: int = 1814):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=11.0, haze_m=20000.0)
    me = b.player("frigate_38", name="HMS Euryalus", heading_degrees=90.0, trim=0.5, crew=40, x_m=-300.0, y_m=250.0)
    b.set_speed(me, 4.0)
    names_gb = ["HMS Victory", "HMS Temeraire", "HMS Neptune", "HMS Leviathan", "HMS Conqueror", "HMS Britannia"]
    names_fr = ["Bucentaure", "Redoutable", "Neptune (Fr)", "Heros", "Intrepide", "Scipion"]
    for i, n in enumerate(names_gb):
        s = b.ship("ship_of_the_line_74", name=n, faction="british", x_m=-i * 260.0, y_m=0.0, heading_degrees=90.0, trim=0.45)
        b.set_speed(s, 4.0)
    for i, n in enumerate(names_fr):
        s = b.ship("ship_of_the_line_74", name=n, faction="french", x_m=-200.0 + i * 260.0, y_m=-1500.0, heading_degrees=270.0, trim=0.45)
        b.set_speed(s, 4.0)
    b.island(300.0, -900.0, 170.0, peak_m=60.0)
    return b.build(
        duration_s=150,
        chart=ViewState(scale="macro", macro_zoom=6, pan=(250.0, -620.0)),
        checkpoints=[
            Checkpoint(10, "Both lines at 40 m per column. The wooded island's shadow screens part of the French line: J (Heros) has never been seen at all, and ships at its edge show only their topsails (†).", {}, [expect("some French ships in sight", _n_french_seen(2))]),
            Checkpoint(10, "Zoomed to 8 m per column on the British line: each 74 is a cluster of glyphs with its sails.", {"macro_zoom": 3, "pan": (-450.0, -250.0)}),
            Checkpoint(10, "Chart scale, 160 m per column: whole fleets as single symbols.", {"macro_zoom": 8, "pan": (0.0, 0.0)}),
            Checkpoint(140, "Two minutes on: the lines have moved on; contacts updated as ships clear the island.", {}, [expect("some French ships in sight", _n_french_seen(2))]),
        ],
    )


def _n_french_seen(n: int):
    def fn(state):
        recs = state.world.component_for_entity(state.player_ship, c.Contacts).records
        k = 0
        for ent, rec in recs.items():
            fac = state.world.try_component(ent, c.Faction)
            if fac is not None and fac.name == "french" and rec.status in ("hull", "topsails"):
                k += 1
        return k >= n, f"{k} French ships in sight"

    return fn


@scenario(
    "own_sails_blind_spot",
    "Blinded by your own canvas",
    "A French brig dead ahead. With the courses set, your own sails blot out the view forward from the "
    "quarterdeck - only the masthead sees her. Reduce to fighting sail (courses clewed up) and she "
    "appears under the topsails.",
    look_for=[
        "Big black wedge ahead of the ship: that's your own courses and jib in the way.",
        "At t=20 the courses are clewed up (sail 40%): the wedge shrinks and the brig appears.",
    ],
    duration_s=60,
)
def own_sails_blind_spot(seed: int = 1815):
    b = SceneBuilder(seed, wind_from=300.0, wind_knots=10.0)
    me = b.player("sloop_18", heading_degrees=0.0, trim=0.8, crew=30)
    b.set_speed(me, 3.0)
    b.ship("brig_14", name="Etourdie", faction="french", x_m=45.0, y_m=160.0, heading_degrees=180.0, trim=0.1)
    run = b.build(
        duration_s=60,
        checkpoints=[
            Checkpoint(10, "Courses set: the captain can't see past his own canvas. The brig (reported by the masthead) is '!'.", {}, [eyes("captain", "Etourdie", "none"), eyes("lookout", "Etourdie", "hull")]),
            Checkpoint(35, "Fighting sail: courses clewed up, and the brig is in plain sight under the topsails.", {}, [eyes("captain", "Etourdie", "hull")]),
        ],
    )
    run.sim.at(20.0, lambda st: _sail(st, st.player_ship, 0.4), "Order: clew up the courses - fighting sail.")
    return run


@scenario(
    "first_rate_quarters",
    "A first rate clears for action",
    "HMS Victory's size at 1 m per cell: a 57 m, 16 m-beam first rate with 160 hands on the weather "
    "deck, beating to quarters. Shows the scale the ship pane is built for.",
    look_for=[
        "The ship pane: a first rate is ~17 cells wide and ~57 long (73 with the bowsprit) - it needs a tall terminal.",
        "Planning mode (paused) shows every hand; watch the quarterdeck and forecastle gun crews close up.",
        "The masthead of a first rate is ~60 m up: switch eyes with o.",
    ],
    duration_s=60,
)
def first_rate_quarters(seed: int = 1816):
    b = SceneBuilder(seed, wind_from=315.0, wind_knots=9.0)
    me = b.player("first_rate_100", name="HMS Victory", heading_degrees=0.0, trim=0.4, crew=160)
    b.set_speed(me, 2.5)
    b.ship("ship_of_the_line_74", name="HMS Temeraire", faction="british", x_m=-20.0, y_m=-260.0, heading_degrees=0.0, trim=0.4)
    b.ship("ship_of_the_line_74", name="Redoutable", faction="french", x_m=600.0, y_m=250.0, heading_degrees=0.0, trim=0.3)
    run = b.build(
        duration_s=60,
        chart=ViewState(scale="macro", macro_zoom=4),
        checkpoints=[
            Checkpoint(1, "Before the order: hands about their work. Planning view.", {"paused": True}),
            Checkpoint(12, "Drums beating: 160 men streaming to their stations.", {"paused": True}),
            Checkpoint(40, "Cleared for action: quarterdeck and forecastle guns manned.", {"paused": True}, [expect("12+ weather-deck guns manned", lambda st: (sum(1 for v in manned_counts(st, st.player_ship).values() if v >= 2) >= 12, f"{sum(1 for v in manned_counts(st, st.player_ship).values() if v >= 2)} manned"))]),
            Checkpoint(40, "Same moment, live: what the captain actually sees past his own masts and canvas.", {}),
        ],
    )
    run.sim.at(2.0, lambda st: setattr(_orders(st), "quarters", True), "Order: beat to quarters.")
    return run


def _fouled(state) -> tuple:
    f = state.world.try_component(state.player_ship, c.Fouled)
    return f is not None, f"fouled, {len(f.gangways)} crossings" if f else "not fouled"


def _boarders_across(n: int):
    def fn(state):
        foe = ship_named(state, "Mouche")
        k = sum(1 for _e, cm in state.world.get_component(c.CrewMember) if cm.home_ship == state.player_ship and cm.ship == foe)
        return k >= n, f"{k} of our men on her deck"

    return fn


def _blood_spilled(state):
    from broadside.sim.people.components import Body, Dead

    foe = ship_named(state, "Mouche")
    hurt = {state.player_ship: 0, foe: 0}
    dead = 0
    for e, (cm, body) in state.world.get_components(c.CrewMember, Body):
        if cm.home_ship in hurt and body.blood_ml < body.blood_max_ml - 1:
            hurt[cm.home_ship] += 1
        if state.world.has_component(e, Dead):
            dead += 1
    return all(v > 0 for v in hurt.values()), f"wounded: ours {hurt[state.player_ship]}, theirs {hurt[foe]}; dead {dead}"


@scenario(
    "boarding_action",
    "Fall aboard and board",
    "Your sloop runs aboard a French brig. The hulls foul where their planks meet (damaging them), "
    "boarders cross over the rails onto her deck, and the two crews fight man to man - every one of "
    "them a generated person with a body that bleeds.",
    look_for=[
        "Both ships at 2x2 cells per metre: every man on BOTH decks is drawn and simulated the same way.",
        "Where the hulls met the planks darken (damaged) - each tile has a material and a condition.",
        "Our boarders (role colours) cross onto the brig; French crew are red. Bleeding men get a dark red cell; the dead are %.",
        "Use the look cursor (l) on anyone to see who they are, their wounds and pulse.",
    ],
    duration_s=120,
)
def boarding_action(seed: int = 1817):
    b = SceneBuilder(seed, wind_from=0.0, wind_knots=9.0)
    me = b.player("sloop_18", heading_degrees=90.0, trim=0.35, crew=56)
    b.set_speed(me, 4.0)
    foe = b.ship("brig_14", name="Mouche", faction="french", x_m=48.0, y_m=-7.8, heading_degrees=90.0, trim=0.0, crew=44)
    b.world.component_for_entity(me, c.ShipOrders).quarters = True
    run = b.build(
        duration_s=120,
        chart=ViewState(scale="macro", macro_zoom=2),
        checkpoints=[
            Checkpoint(3, "Closing the brig under fighting sail. Both crews in full detail.", {"paused": True}),
            Checkpoint(18, "Fallen aboard: the hulls have fouled. Damaged planks where they struck.", {"paused": True}, [expect("ships fouled", _fouled)]),
            Checkpoint(40, "Boarders away: our men crossing onto her deck.", {"paused": True}, [expect("5+ boarders across", _boarders_across(5))]),
            Checkpoint(90, "Hand to hand: men wounded, bleeding and dying on both sides.", {"paused": True}, [expect("blood spilled on both sides", _blood_spilled)]),
            Checkpoint(90, "Same moment, live view: what the captain can see of the melee.", {}),
        ],
    )
    run.sim.at(22.0, lambda st: setattr(_orders(st), "boarders_away", True), "Captain: 'Boarders away!'")
    return run


def _approach_point(world, port, rng_seed: int = 0):
    """World metres of a spot just offshore of `port`, and the bearing from
    there to the port - found by walking out from the town toward open sea
    until the water is ~40 m deep."""
    import math as _m

    import numpy as _np

    geo = world.geo
    cell = geo.cell_km * 1000.0
    px, py = (port.col + 0.5) * cell, (port.row + 0.5) * cell
    best = None
    for ang in range(0, 360, 10):
        dx, dy = _m.sin(_m.radians(ang)), _m.cos(_m.radians(ang))
        for d in _np.arange(500.0, 25000.0, 250.0):
            h = float(geo.sample_m(_np.array([px + dx * d]), _np.array([py + dy * d]))[0])
            if h < -40.0:
                if best is None or d < best[0]:
                    best = (d, px + dx * d, py + dy * d, (ang + 180.0) % 360.0)
                break
    if best is None:
        return px, py - 5000.0, 0.0
    return best[1], best[2], best[3]


def _world_crew_check(world_ref):
    def fn(state):
        from broadside.sim.people.components import Biography, Identity

        places = set(world_ref["world"].places_of(world_ref["world"].player_nation.id))
        battles = {n for _y, n in world_ref["world"].battles_for(world_ref["world"].player_nation.id)}
        born_here = vets = 0
        for e, (cm, ident, bio) in state.world.get_components(c.CrewMember, Identity, Biography):
            if cm.home_ship != state.player_ship:
                continue
            born_here += ident.birthplace in places
            vets += any(any(b in text for b in battles) for _y, text in bio.events)
        return born_here > 20 and vets > 0, f"{born_here} born in the nation's ports, {vets} veterans of its battles"

    return fn


@scenario(
    "generated_home_port",
    "Home port on a generated coast",
    "World generation groundwork: a fictional Mediterranean is generated from a seed (coasts, islands, "
    "ports, nations, 155 years of history), and your ship is placed off your nation's home port. The "
    "coast in the chart and at 1 m is the generated one; your crew were born in its towns and some "
    "fought in its recorded battles.",
    look_for=[
        "The chart shows the generated coastline around the port; zoom out (TAB, -) for more.",
        "Look (l) at a sailor: his birthplace is a town of your generated nation; veterans cite its battles.",
        "python -m broadside.worldgen --seed 1805 --out world  writes the map and the chronicle.",
    ],
    duration_s=40,
)
def generated_home_port(seed: int = 1805):
    from broadside.sim.world.terrain import WorldHeightmap
    from broadside.worldgen import CampaignSetup, generate_world

    world = generate_world(seed, CampaignSetup(captain="Thomas Hardy", ship="Dauntless", nation="Albion"))
    port = world.home_port()
    wx, wy, bearing = _approach_point(world, port)
    b = SceneBuilder(seed, wind_from=(bearing + 110.0) % 360.0, wind_knots=11.0)
    b.terrain.add(WorldHeightmap(world.geo, wx, wy, seed=seed))
    places = world.places_of(world.player_nation.id)
    battles = world.battles_for(world.player_nation.id)
    me = b.player("frigate_38", name=f"HMS {world.player_ship_name}", heading_degrees=bearing, trim=0.4, crew=60,
                  captain_name=world.player_captain, places=places, battles=battles)
    b.set_speed(me, 3.0)
    ref = {"world": world}
    return b.build(
        duration_s=40,
        chart=ViewState(scale="macro", macro_zoom=7),
        checkpoints=[
            Checkpoint(5, f"Off {port.name}, seat of {world.player_nation.name}. The generated coast at 80 m per column.", {}, [expect("crew from this world", _world_crew_check(ref))]),
            Checkpoint(5, "The same coast at chart scale (320 m per column).", {"macro_zoom": 9}),
        ],
    )


# --- Physics sandbox: one gun, one wall ------------------------------------


def _gun_vs_wall_scene(seed: int, crew: int = 3, verbose: bool = True):
    from broadside.sim.items import place_item

    b = SceneBuilder(seed, wind_from=200.0, wind_knots=6.0)
    me = b.player("gunboat_24", name="Gunboat No. 7", heading_degrees=0.0, trim=0.0, crew=crew, victual_days=10)
    b.island(165.0, 0.0, 48.0, peak_m=16.0, wooded=False, shoal_m=20.0)
    b.wall(124.0, 0.0, 0.0, length_m=20.0, thickness_m=2.0, height_m=5.0, name="curtain wall")
    w = b.world
    layout = w.component_for_entity(me, c.ShipBody).layout
    gun = layout.guns[0]
    battery = w.component_for_entity(me, c.Battery)
    battery.verbose_drill = verbose
    gs = battery.guns[0]
    _unready(gs)
    # Cartridges and shot to hand: the box beside the gun, the garland at her breech.
    for dx in (1, -1, 2):
        if layout.tile(gun.x + dx, gun.y - gun.side) in (2, 7):
            place_item(w, me, "cartridge box", {"powder cartridge": 24}, "cartridges", 24, gun.x + dx, gun.y - gun.side)
            break
    for _e, (item, stw, cont) in w.get_components(Item, Stowed, Contents):
        if stw.ship == me and item.kind == "shot garland":
            cont.goods = {k: 24 for k in cont.goods}
            cont.capacity = 24
    captain = next(e for e, o in w.get_component(c.Observer) if o.ship == me and o.post == "captain")
    run = b.build(duration_s=240, chart=ViewState(scale="elevation"), checkpoints=[])
    run.captain = captain
    run.gun_tile = gun.crew_tiles[0]
    return run


def _unready(gs) -> None:
    """A gun as she lies in the sandbox: empty, run in, nothing done."""
    from broadside.sim.gundrill import reset_after_firing

    reset_after_firing(gs)
    gs.needs_sponge = False  # she has not been fired: no embers to quench


@scenario(
    "gun_vs_wall",
    "Sandbox: you, a gun and a wall",
    "A gunboat with one 24-pounder lies 120 m off a stone curtain wall on an islet. You are the captain: "
    "walk to the gun and work her yourself, one order of the drill at a time - sponge, cartridge, ram, wad, "
    "shot, ram, run out, prime, lay - and knock the wall down block by block. Single-handed, running a "
    "two-and-a-half-tonne gun out takes half a minute; that is what a crew is for.",
    look_for=[
        "m: walk mode - move yourself (the highlighted @) with the arrow keys; stand beside the gun (=, starboard side).",
        "e: the next order in the drill, with how long it will take you; number keys to do it.",
        "Laying her by handspike and quoin (train/elevate) counts as laying her - or leave it and the drill will.",
        "The right-hand pane shows the wall face-on: cracks, craters, holes, falling masonry and dust. TAB to the chart.",
    ],
    duration_s=60,
)
def gun_vs_wall(seed: int = 1818):
    run = _gun_vs_wall_scene(seed, crew=3)
    run.checkpoints = [Checkpoint(1, "Your gunboat, the shot garland and cartridge box by the gun; the wall face-on at right.", {"paused": True})]
    return run


def _wall_stat(key: str, n: int, label: str):
    def fn(state):
        from broadside.sim.voxels import VoxelStructure

        vs = next(v for _e, v in state.world.get_component(VoxelStructure))
        val = getattr(vs, key)
        return val >= n, f"{val} {label}"

    return fn


def _dust_present(state):
    d = sum(1 for p in state.atmosphere.smoke if p.kind == "dust")
    return d > 0, f"{d} dust clouds"


def _breach(state):
    """A breach: somewhere the wall's full thickness is gone at the base."""
    from broadside.sim.voxels import VoxelStructure

    vs = next(v for _e, v in state.world.get_component(VoxelStructure))
    solid = vs.solid
    nz, ny, nx = vs.shape
    open_cols = 0
    for ix in range(nx):
        if not solid[0:2, :, ix].any() and solid[:, :, ix].size:
            # Only count columns inside the wall's own footprint.
            if solid[:, :, ix].any() or vs.material[:, :, ix].size:
                open_cols += 1
    return open_cols >= 2, f"{open_cols} blocks' worth of open breach through the wall"


def _rounds_fired(n: int):
    def fn(state):
        fired = sum(1 for e in state.log if any(w in e.text.lower() for w in ("gun fires", "broadside", "fire! (")))
        return fired >= n, f"{fired} rounds fired"

    return fn


@scenario(
    "gun_vs_wall_demo",
    "Sandbox demo: a gun crew breaches a wall",
    "The same sandbox with a gun's crew aboard. Beat to quarters and they go to their stations - gun captain, "
    "rammer, loader, tackle men - and work the piece through the whole drill on their own, the gun captain "
    "laying her on the wall by eye and misjudging the range by however green he is. Round shot smashes 0.5 m "
    "stone blocks, cracks their neighbours, and unsupported masonry falls as rubble in a cloud of dust.",
    look_for=[
        "Log: every step of the drill, with the name of the man doing it. Rate of fire is the sum of those steps.",
        "Deck: four men at the gun, each busy in turn; watch them idle while they wait for the man ahead.",
        "Right: the wall face-on. Craters, then holes through, then the courses above sagging and falling as rubble.",
    ],
    duration_s=620,
)
def gun_vs_wall_demo(seed: int = 1818):
    run = _gun_vs_wall_scene(seed, crew=9)

    def beat(st):
        o = _orders(st)
        o.quarters = True
        o.fire_at_will = True

    run.sim.at(2.0, beat, "Beat to quarters, and fire as she bears.")
    wall_view = {"pan": (124.0, 0.0), "subcell": 2, "fit": False}
    run.checkpoints = [
        Checkpoint(3, "Quarters: the gun's crew leave their work and walk to their stations.", {"paused": True}),
        Checkpoint(30, "The drill under way - sponge, cartridge, ram, wad, shot, ram, run out, prime, lay.", {"paused": True}),
        Checkpoint(60, "First round away: powder smoke on the water, stone dust at the wall.", {}, [expect("the crew has fired", _rounds_fired(1)), expect("dust thrown up", _dust_present)]),
        Checkpoint(300, "Five minutes, five rounds: the foot of the wall cratered and holed.", {}, [expect("rounds fired", _rounds_fired(4)), expect("blocks smashed", _wall_stat("destroyed", 10, "blocks smashed"))]),
        Checkpoint(615, "Ten minutes, ten rounds: a breach, and the courses above it down as rubble.", {}, [expect("steady fire", _rounds_fired(8)), expect("masonry fell", _wall_stat("fallen", 6, "blocks fell")), expect("a breach", _breach)]),
        Checkpoint(615, "From above, zoomed on the wall: the rubble spill in front of the breach.", wall_view),
    ]
    return run
