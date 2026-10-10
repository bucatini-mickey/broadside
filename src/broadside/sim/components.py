# ECS component definitions.
#
# Components are plain data - dataclasses with no behaviour. Anything that
# looks like a method that mutates other components belongs in a system
# (sim/systems/*.py), not here. See docs/design/01_architecture.md.
#
# This file intentionally covers only what Phase 0 (the skeleton) actually
# uses. docs/design/02_simulation_systems.md describes a much larger set of
# state (sectioned hull integrity, per-sail damage, per-limb injury, full
# skill/task scheduling, etc.) that later phases will add here without
# needing to change this file's overall shape.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

Color = tuple[int, int, int]

M_PER_NM = 1852.0


# --- Identity & rendering -----------------------------------------------


@dataclass
class Name:
    full: str


@dataclass
class Renderable:
    """How to draw this entity's single terminal cell.

    `fg` is a fallback colour, used as-is for entities with no more
    specific colour rule (e.g. static deck fittings). For entities that
    also carry a `Role` component (i.e. crew), the render layer looks up
    colour by role via render.palette instead of using `fg` - colour
    policy belongs in render/, not here; see docs/design/01_architecture.md
    on keeping sim/ free of any dependency on render/.
    """

    glyph: str
    fg: Color = (220, 220, 220)
    bg: Color | None = None  # None = let the background show through


# --- Coordinate spaces -----------------------------------------------
#
# WorldPosition (continuous, nautical miles) is for ships and other things
# that exist on the campaign chart. DeckPosition (integer tiles) is for
# sailors and fittings, relative to their ship's own local grid. These are
# deliberately never conflated - see docs/design/01_architecture.md,
# "Two coordinate spaces".


@dataclass
class WorldPosition:
    x_nm: float = 0.0
    y_nm: float = 0.0

    # Metre accessors: vision, terrain and the 1 m deck view all work in
    # metres; the chart-scale sim keeps nautical miles.
    @property
    def x_m(self) -> float:
        return self.x_nm * M_PER_NM

    @x_m.setter
    def x_m(self, value: float) -> None:
        self.x_nm = value / M_PER_NM

    @property
    def y_m(self) -> float:
        return self.y_nm * M_PER_NM

    @y_m.setter
    def y_m(self, value: float) -> None:
        self.y_nm = value / M_PER_NM


@dataclass
class Heading:
    """Compass heading in degrees, 0 = north, 90 = east, increasing clockwise."""

    degrees: float = 0.0


@dataclass
class DeckPosition:
    """Integer tile coordinates on the owning ship's local deck grid."""

    x: int
    y: int


# --- Ship ---------------------------------------------------------------


@dataclass
class ShipTag:
    """Marker component: this entity is a ship."""

    ship_class: str  # e.g. "sloop_18" - matches a key in sim/data/ships/


@dataclass
class Hull:
    length_m: float
    beam_m: float
    max_crew: int
    integrity: float = 1.0  # 0..1, simplified single value for the skeleton
    #  Later phases replace `integrity` with per-section state (bow/waist/
    #  stern x port/starboard) per docs/design/02_simulation_systems.md.


@dataclass
class SailPlan:
    """Simplified single trim value for the skeleton (0 = bare poles, 1 =
    full sail). Later phases replace this with a dict of named sails, each
    independently set/reefed/furled and independently damageable, per
    docs/design/02_simulation_systems.md.

    `ordered` is what the captain has called for; `trim` is what is
    actually set, and it follows the order at the speed men can go aloft
    and handle canvas (navigation.sailing_inertia_system). -1 means no
    change is pending. Writing `trim` directly is still what scenarios and
    the crew-less ships do."""

    trim: float = 0.5
    ordered: float = -1.0


@dataclass
class Speed:
    """Ship's current speed over water, in knots. Written by the sailing
    system each tick from wind + heading + trim; read by movement and
    render."""

    knots: float = 0.0


@dataclass
class DeckGrid:
    """The tile dimensions of this ship's local deck grid, so the deck
    renderer and crew-wander AI know the walkable bounds."""

    width: int
    height: int


# --- Crew -----------------------------------------------------------


@dataclass
class CrewMember:
    """Marker + back-reference: this entity is a sailor, serving aboard
    `ship`."""

    ship: int  # esper entity id of the ship this sailor is aboard now
    home_ship: int = -1  # the ship he belongs to (differs when he's boarded another)


@dataclass
class Role:
    title: str  # e.g. "Topman", "Gun Captain", "Ship's Boy" - see
    #  docs/design/02_simulation_systems.md sec. 3 for the fuller role list
    #  later phases draw from.


@dataclass
class Needs:
    """0.0 = fully satisfied, 1.0 = critical. Decays over time (crew_ai
    system) and is relieved by scheduled activity in later phases; the
    skeleton only implements decay, as the seed for that later work."""

    fatigue: float = 0.0
    hunger: float = 0.0
    thirst: float = 0.0


@dataclass
class Mood:
    """-1.0 (miserable) to 1.0 (thriving). Derived each tick from Needs by
    the crew_ai system; later phases add event-based modifiers (battle,
    flogging, prize money, shore leave) per
    docs/design/02_simulation_systems.md sec. 3."""

    value: float = 0.0

    @property
    def label(self) -> str:
        if self.value > 0.5:
            return "content"
        if self.value > 0.1:
            return "steady"
        if self.value > -0.3:
            return "weary"
        if self.value > -0.7:
            return "sullen"
        return "despondent"


@dataclass
class Wanderer:
    """Marks a sailor as currently free to wander their deck station
    (Phase 0's placeholder for the full task-scheduling system in
    docs/design/02_simulation_systems.md sec. 3). Holds a pending
    destination tile so movement is gradual rather than teleporting.

    `cooldown_ticks` throttles movement to roughly a human walking pace
    rather than one tile per 100ms sim tick - decremented each tick by the
    crew_wander system, which only steps the sailor when it reaches zero.
    """

    target: tuple[int, int] | None = None
    cooldown_ticks: int = 0


# --- Engine v1: bodies, sight, orders -------------------------------------
#
# Added with the vision/scene engine (docs/design/07_vision_and_views.md).
# These are still plain data; the behaviour lives in sim/systems/.


@dataclass
class ShipBody:
    """The ship's physical 1 m deck plan (sim/shiplayout.py) - what its
    hull, fittings, masts and guns occupy, and how tall each is. Shared,
    read-only data per class; per-ship mutable state lives elsewhere."""

    layout: Any  # sim.shiplayout.DeckLayout (Any to keep this module import-light)


@dataclass
class Faction:
    """Which side a ship belongs to - "british", "french", "neutral"...
    Drives colouring in the view and (later) AI hostility."""

    name: str


@dataclass
class Helm:
    """Who is steering and toward what. The helm turns the ship toward
    `desired_heading` at a finite rate (a ship cannot spin on the spot), or,
    with waypoints set, steers for each in turn - tacking when the next
    waypoint lies too close to the wind."""

    desired_heading: float = 0.0
    turn_rate_dps: float = 3.0
    waypoints: list = field(default_factory=list)  # [(x_m, y_m), ...]
    loop: bool = False
    arrive_radius_m: float = 80.0
    tack_side: int = 0  # -1/+1 while beating to windward, 0 otherwise
    aground: bool = False


@dataclass
class GunState:
    """Per-gun mutable state; the gun's position/side come from the ship's
    DeckLayout.guns[index]."""

    index: int
    loaded: bool = True  # charged and shotted (abstract crews just set this)
    reload_left_s: float = 0.0
    flash_s: float = 0.0  # >0 while the muzzle flash is showing
    # The drill, step by step (sim/gundrill.py). Every one of these flags is
    # set by a named man doing a real job that takes real time - whether
    # that man is the crew's rammer or the player himself.
    needs_sponge: bool = False  # after firing: sponge out embers before loading
    charged: bool = True  # powder cartridge in the muzzle
    charge_rammed: bool = True  # cartridge rammed down onto the breech
    wadded: bool = True  # wad on the charge
    shotted: bool = True  # ball in the muzzle
    rammed: bool = True  # shot rammed home
    run_out: bool = True  # hauled out on the side tackles, muzzle through the port
    primed: bool = True  # priming quill in the vent, cartridge pricked
    laid: bool = True  # aimed: trained and elevated on something
    elevation_deg: float = 0.0
    train_deg: float = 0.0  # + trained forward, - aft
    # Who is working this gun this instant, and at which step, so two men
    # never do the same job and an interrupted step can be picked up again.
    working: int = -1
    working_key: str = ""
    starved: bool = False  # the drill is stopped for want of powder or shot
    target: int = -1  # what the gun captain last laid on (entity), -1 none


@dataclass
class Battery:
    guns: list = field(default_factory=list)  # [GunState, ...]
    reload_s: float = 75.0  # full-crew reload time, seconds
    abstract_crew: bool = False  # no crew entities; guns count as manned at quarters
    verbose_drill: bool = False  # log every step of the drill (sandbox/tutorial)
    served_s: float = -1e9  # when cartridges were last brought up from the magazine
    pending_fire: list = field(default_factory=list)  # [(delay_s, gun_index), ...]
    # The target her gun captains have laid their pieces for. When the word
    # changes they lay again: without this a loaded gun kept whatever
    # elevation it had, so the first broadside of an action went out at
    # point blank whatever the range.
    laid_for: int = -2
    laid_at_s: float = -1e9


@dataclass
class ShipOrders:
    """Standing orders the captain has given. Set instantly by the player
    (even while paused - the Dwarf-Fortress planning pattern); the crew and
    systems act on them once time runs."""

    quarters: bool = False  # beat to quarters: crew to gun stations
    fire_side: int = 0  # -1 port / +1 starboard broadside requested, 0 none
    fire_at_will: bool = False  # keep firing each side as guns reload (AI use)
    ripple_s: float = 0.35  # delay between successive guns in a broadside
    gun_target: int = -1  # "fire at that one": an entity the captain has named
    gun_target_since_s: float = -1.0  # when he said so - the crews take time to take it in
    boarders_away: bool = False  # send boarders onto a ship we're fouled with
    boarders_assigned: bool = False
    applied_quarters: bool = False
    # Ground tackle. `anchor` is the order; `anchored` is her condition,
    # and `anchor_work_s` is the work left at the capstan or the cathead.
    anchor: bool = False
    anchored: bool = False
    anchor_work_s: float = 0.0
    # Two-thirds rations: the stores last half again as long, and the men
    # like it exactly as much as you would expect.
    short_allowance: bool = False
    # When the mainbrace was last spliced - an extra issue of grog.
    spliced_at_s: float = -1e9  # what the crew system last acted on
    quarters_since_s: float = -1.0  # sim time quarters was last ordered


@dataclass
class Observer:
    """A pair of eyes aboard a ship: the captain on the quarterdeck, or a
    lookout aloft. `eye_height_m` is above the waterline and is what lets a
    masthead lookout see over rocks, smoke and his own sails."""

    ship: int
    post: str = "captain"  # "captain" | "lookout"
    eye_height_m: float = 4.0
    report_delay_s: float = 0.0  # time for a sighting to reach the captain


@dataclass
class Aloft:
    """Marker: this crew member is up the rigging (not drawn on deck)."""

    mast: str = "main"


@dataclass
class ContactRecord:
    """What a ship knows about another vessel. Knowledge, not truth: the
    position is where it was last seen, which may be long out of date."""

    entity: int
    status: str = "none"  # "hull" | "topsails" | "reported" | "lost"
    x_m: float = 0.0
    y_m: float = 0.0
    heading: float = 0.0
    last_seen_s: float = -1.0
    first_seen_s: float = -1.0
    seen_by: str = ""  # which observer post
    clarity: float = 0.0  # transmittance of the best sight line, 0..1
    pending_report_s: float = -1.0  # lookout sighting still being passed down


@dataclass
class Contacts:
    records: dict = field(default_factory=dict)  # entity -> ContactRecord
    # Lookout sightings still being called down to the deck:
    # entity -> (due_s, x_m, y_m, heading, status, clarity)
    pending: dict = field(default_factory=dict)


@dataclass
class CrewTask:
    """What a sailor is doing: idle wander, or heading to/holding a station.
    `path` is the remaining list of deck tiles to walk (BFS on the plan)."""

    kind: str = "idle"  # "idle" | "station"
    station: Optional[tuple] = None  # target tile
    station_kind: str = ""  # "gun" | "helm" | "sail" | "post"
    gun_index: int = -1
    station_no: int = 0  # at a gun: his number in the crew (1 = gun captain)
    path: list = field(default_factory=list)
    cooldown_ticks: int = 0


@dataclass
class Fouled:
    """Two hulls in contact - collided or lashed together. Neither can sail
    away until cut free. `gangways` are pairs of touching deck tiles
    ((our x, y), (their x, y)) that men can cross."""

    other: int
    since_s: float = 0.0
    gangways: list = field(default_factory=list)


@dataclass
class Below:
    """Marker: this person is aboard but below decks (gundecks, hold,
    berth) - fully simulated, just not on the weather-deck grid, which is
    the only deck level drawn so far."""

    deck: str = "gundeck"
