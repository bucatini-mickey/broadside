# Talking to other ships: flag signals.
#
# A captain has no radio. To say anything to a consort he sends a
# midshipman to the signal locker, who bends the numbered flags of the
# signal book to the halyards and hoists them where they can be read. The
# other ship's lookouts must see them - through haze, smoke, or a press of
# sail in the way - and her signal midshipman must find the number in his
# book before anyone acts. All of that takes time, and a green ship takes
# longer.
#
# The numbers here are the ship's own telegraphic code book: the signals
# that mattered in action, kept short so they could be read at three miles.
# Semaphore proper belonged to the shore telegraph; at sea this was how it
# was done.

from __future__ import annotations

from dataclasses import dataclass, field

from broadside.sim import components as c
from broadside.sim.people import components as pc

# number -> what it says
SIGNAL_BOOK = {
    1: "Engage the enemy more closely",
    2: "Form line of battle",
    3: "Make all sail",
    4: "Enemy in sight",
    5: "Tack in succession",
    6: "Wear together",
    7: "Come within hail",
    8: "Report your damage",
    9: "Discontinue the action",
    10: "Anchor",
    11: "Prepare to board",
    12: "Well done",
}

HOIST_BASE_S = 14.0  # bending the flags on and running them up
READ_BASE_S = 8.0  # the other ship's midshipman finding it in his book
MAX_READ_RANGE_M = 6000.0


@dataclass
class Signals:
    """What this ship is flying, and who has answered it."""

    hoisted: int = 0  # signal number at the masthead, 0 = nothing flying
    since_s: float = -1.0
    acknowledged: list = field(default_factory=list)  # ships that have answered
    reading: dict = field(default_factory=dict)  # ship -> sim time it will have read it
    # Who it is addressed to: an entity, or -1 for the whole squadron.
    to_ship: int = -1

    @property
    def text(self) -> str:
        return SIGNAL_BOOK.get(self.hoisted, "")


def hoist_time(skill: float) -> float:
    return HOIST_BASE_S * (0.6 + 1.0 * (1.0 - max(0.0, min(1.0, skill))))


def hoist(state, ship: int, number: int, to_ship: int = -1) -> bool:
    """Put a signal up. The flags are already flying by the time this is
    called - the time was spent in the Activity that led here. `to_ship`
    addresses it to one ship; by default the whole squadron reads it."""
    if number not in SIGNAL_BOOK:
        return False
    world = state.world
    sig = world.try_component(ship, Signals)
    if sig is None:
        sig = Signals()
        world.add_component(ship, sig)
    sig.hoisted = number
    sig.since_s = state.now_s
    sig.acknowledged = []
    sig.reading = {}
    sig.to_ship = to_ship
    if ship == state.player_ship:
        whom = ""
        if to_ship >= 0:
            nm = world.try_component(to_ship, c.Name)
            whom = f" to {nm.full}" if nm is not None else ""
        state.say(f"Signal No. {number}{whom}: '{SIGNAL_BOOK[number]}'.", "order")
    return True


def haul_down(state, ship: int) -> None:
    sig = state.world.try_component(ship, Signals)
    if sig is None or not sig.hoisted:
        return
    if ship == state.player_ship:
        state.say(f"Signal No. {sig.hoisted} hauled down.", "order")
    sig.hoisted = 0
    sig.acknowledged = []
    sig.reading = {}


def _best_lookout(world, ship: int) -> float:
    best = 0.3
    for ent, obs in world.get_component(c.Observer):
        if obs.ship != ship:
            continue
        sk = world.try_component(ent, pc.Skills)
        if sk is not None:
            best = max(best, sk.get("lookout"))
    return best


def signals_system(state, dt: float) -> None:
    """Other ships read what is flying, if they can see it, and answer."""
    world = state.world
    flying = [(ship, sig) for ship, sig in world.get_component(Signals) if sig.hoisted]
    if not flying:
        return
    others = [(e, p) for e, (p, _b) in world.get_components(c.WorldPosition, c.ShipBody)]
    for ship, sig in flying:
        mine = world.component_for_entity(ship, c.WorldPosition)
        for other, pos in others:
            if other == ship or other in sig.acknowledged:
                continue
            d = ((pos.x_m - mine.x_m) ** 2 + (pos.y_m - mine.y_m) ** 2) ** 0.5
            if d > MAX_READ_RANGE_M:
                sig.reading.pop(other, None)
                continue
            # The flags have to be legible: haze and smoke count against them.
            clarity = _clarity(state, ship, other)
            if clarity < 0.25:
                sig.reading.pop(other, None)
                continue
            due = sig.reading.get(other)
            if due is None:
                skill = _best_lookout(world, other)
                sig.reading[other] = state.now_s + READ_BASE_S * (0.7 + 1.3 * (1.0 - skill)) + d / 3000.0 * 6.0
                continue
            if state.now_s >= due:
                ours = world.try_component(ship, c.Faction)
                theirs = world.try_component(other, c.Faction)
                friend = ours is not None and theirs is not None and ours.name == theirs.name
                if friend:
                    sig.acknowledged.append(other)
                    if ship == state.player_ship:
                        nm = world.try_component(other, c.Name)
                        state.say(f"{nm.full if nm else 'She'} answers the signal.", "sight")
                else:
                    # The enemy can read your flags too; he simply does not
                    # answer them. (What he makes of them is his affair.)
                    sig.reading[other] = state.now_s + 1e9
                _hand_to_captain(state, ship, other, sig)


def _clarity(state, ship: int, other: int) -> float:
    """How plainly one ship can make out the other's masthead - taken from
    her own contact record where she has one, so fog and smoke tell."""
    contacts = state.world.try_component(other, c.Contacts)
    if contacts is None:
        return 1.0  # a ship with no eyes of her own is assumed to see
    rec = contacts.records.get(ship)
    if rec is None:
        return 1.0 if not contacts.records else 0.4
    return rec.clarity if rec.status in ("hull", "topsails") else 0.1


MISREAD_CHANCE = 0.22  # at no skill at all; a good signal midshipman rarely does


def _hand_to_captain(state, from_ship: int, to_ship: int, sig: Signals) -> None:
    """The signal has been read aboard her. Her signal midshipman may have
    read it wrong - the flags are small and the day may be thick - and then
    her captain acts on the wrong order, which happened often enough to lose
    battles. Friendly ships only: an enemy reads your flags but has no
    reason to obey them."""
    from broadside.sim.systems.captain_ai import ShipCaptainAI

    world = state.world
    if sig.to_ship >= 0 and to_ship != sig.to_ship:
        return
    a = world.try_component(from_ship, c.Faction)
    b = world.try_component(to_ship, c.Faction)
    if a is None or b is None or a.name != b.name:
        return
    ai = world.try_component(to_ship, ShipCaptainAI)
    if ai is None:
        return
    number = sig.hoisted
    skill = _best_lookout(world, to_ship)
    clarity = _clarity(state, from_ship, to_ship)
    rng = state.rng.stream("signals")
    if rng.random() < MISREAD_CHANCE * (1.0 - skill) * (1.5 - clarity):
        wrong = max(1, min(max(SIGNAL_BOOK), number + rng.choice((-1, 1))))
        if wrong != number:
            number = wrong
            nm = world.try_component(to_ship, c.Name)
            if from_ship == state.player_ship:
                state.say(f"{nm.full if nm else 'She'} seems to read it as No. {number}.", "alert")
    ai.signal_pending = number
    ai.signal_from = from_ship
    ai.signal_at_s = state.now_s


def make_signal(state, ship: int, number: int, to_ship: int = -1) -> str:
    """Order a signal made. The captain says "make signal number one"; a
    hand goes to the locker, bends the flags on and hoists them, and that
    takes as long as it takes him. Returns what to tell the player."""
    from broadside.sim.actions import Activity
    from broadside.sim.people import components as pc

    world = state.world
    if number not in SIGNAL_BOOK:
        return "No such signal in the book."
    best = None
    for ent, (crew, _pos) in world.get_components(c.CrewMember, c.DeckPosition):
        if crew.ship != ship or world.has_component(ent, Activity) or world.has_component(ent, pc.Dead):
            continue
        body = world.try_component(ent, pc.Body)
        if body is not None and (not body.alive or not body.conscious):
            continue
        sk = world.try_component(ent, pc.Skills)
        skill = sk.get("seamanship") if sk is not None else 0.4
        role = world.try_component(ent, c.Role)
        # A midshipman for choice, then any hand who is not at a gun.
        bonus = 0.4 if role is not None and role.title in ("Midshipman", "Ship's Boy") else 0.0
        task = world.try_component(ent, c.CrewTask)
        if task is not None and task.station_kind == "gun":
            bonus -= 0.3
        if best is None or skill + bonus > best[0]:
            best = (skill + bonus, ent, skill)
    if best is None:
        return "There is no one at hand to make the signal."
    _score, hand, skill = best
    seconds = hoist_time(skill)
    nm = world.try_component(hand, c.Name)
    world.add_component(
        hand,
        Activity(f"Make signal No. {number}", seconds, seconds, lambda st, n=number, t=to_ship, sh=ship: hoist(st, sh, n, t)),
    )
    who = nm.full if nm is not None else "A hand"
    return f"{who} away to the signal locker - No. {number} in {seconds:.0f} s."
