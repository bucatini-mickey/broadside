# What a person is made of: identity, character, state of mind, loyalties,
# cravings, skills, body, and life story.
#
# Every sailor, officer and marine on every ship (friend, enemy or
# neutral) carries these components. They're plain data like all ECS
# components; the behaviour lives in sim/people/health.py and psyche.py.
# See docs/design/11_people.md for the model and the reasoning behind each
# number.
#
# Conventions: traits and states are floats. Personality traits are 0..1
# with 0.5 as the population average; they change only slowly, if at all.
# Psyche values are 0..1 states that move day to day (morale is -1..1).
# Skills are 0..1 proficiency (0.2 green, 0.5 competent, 0.8 expert).

from __future__ import annotations

from dataclasses import dataclass, field

# Every role aboard has a skill. A sailor's proficiency in each decides how
# fast and how well he does that job - and so what job he's given.
SKILLS = [
    "seamanship",   # general ship-handling: hauling, belaying, knots
    "topwork",      # aloft: loosing, reefing, furling
    "helm",         # steering by compass and by the feel of the sails
    "gunnery",      # working a gun: loading drill, speed
    "gunlaying",    # aiming: judging range and the roll
    "musketry",     # small arms: marines, sharpshooters in the tops
    "melee",        # cutlass, pike, boarding axe
    "carpentry",    # hull, spars, shot-plugs under fire
    "sailmaking",   # canvas repair
    "rigging",      # splicing, knotting, the bosun's trade
    "cooking",
    "medicine",     # surgeon and loblolly boys
    "navigation",   # master, mates, midshipmen
    "leadership",   # getting men to do things
    "lookout",      # eyesight and attention: sighting sails first
]


@dataclass
class Identity:
    given: str
    family: str
    culture: str  # key into sim/people/cultures.CULTURES
    nation: str  # the nation he's a subject of (may differ from the ship's)
    birth_year: int
    birthplace: str
    background: str  # key into generate.BACKGROUNDS
    nickname: str = ""
    rank: str = "able seaman"

    @property
    def full(self) -> str:
        nick = f" '{self.nickname}'" if self.nickname else ""
        return f"{self.given}{nick} {self.family}"


@dataclass
class Personality:
    """Stable character. 0.5 = average."""

    bravery: float = 0.5
    temper: float = 0.5  # quickness to anger / violence
    sociability: float = 0.5
    discipline: float = 0.5  # acceptance of orders and hierarchy
    ambition: float = 0.5
    honesty: float = 0.5
    optimism: float = 0.5
    resilience: float = 0.5  # how well stress is absorbed


# What a man can feel, and how fast each fades. Feelings are the fast
# layer: something happens, he feels it, and the feeling colours his mood
# while it lasts. Morale is the slow layer underneath, moved by the
# feelings rather than by events directly - see docs/design/18_life_aboard.md.
EMOTIONS = {
    "fear": 45.0,        # seconds to fade appreciably
    "anger": 240.0,
    "grief": 2400.0,
    "pride": 900.0,
    "shame": 1200.0,
    "hope": 1800.0,
    "contentment": 1200.0,
}


@dataclass
class Psyche:
    """Changing state of mind."""

    morale: float = 0.3  # -1 mutinous despair .. +1 eager
    stress: float = 0.1
    anxiety: float = 0.1
    depression: float = 0.05
    confidence: float = 0.5
    fear: float = 0.0  # acute, in action - kept as its own field, it is read everywhere
    grievance: float = 0.0  # accumulated resentment toward officers/ship
    # The other feelings, 0..1 each, decaying at their own rates.
    feelings: dict = field(default_factory=dict)

    def feel(self, what: str, amount: float) -> None:
        """Feel something, with diminishing returns: the twentieth broadside
        does not make a man twenty times prouder, and nothing saturates at
        one just because it happened often."""
        cur = self.feelings.get(what, 0.0)
        if amount >= 0.0:
            cur = cur + amount * (1.0 - cur)
        else:
            cur = cur + amount * cur
        self.feelings[what] = max(0.0, min(1.0, cur))
        if what == "fear":
            self.fear = self.feelings["fear"]

    def feeling(self, what: str) -> float:
        return self.fear if what == "fear" else self.feelings.get(what, 0.0)

    @property
    def spirits(self) -> float:
        """The balance of what he is feeling now, -1..1."""
        good = self.feeling("pride") + self.feeling("hope") + self.feeling("contentment")
        bad = self.feeling("fear") + self.feeling("anger") + self.feeling("grief") + self.feeling("shame")
        return max(-1.0, min(1.0, (good - bad) / 3.0))


@dataclass
class Allegiance:
    """Devotion, 0..1, to the things a man might fight for."""

    nation: float = 0.5
    cause: float = 0.5  # the war itself
    captain: float = 0.5
    ship: float = 0.4  # the ship and her company


@dataclass
class Cravings:
    """Drink as a coping need. `dependence` is the trait (how much he needs
    it), `need` the current state. The grog ration relieves it."""

    dependence: float = 0.3
    need: float = 0.2
    tobacco: float = 0.3


@dataclass
class Skills:
    level: dict = field(default_factory=dict)  # skill -> 0..1
    xp: dict = field(default_factory=dict)  # skill -> practice accumulated

    def get(self, skill: str) -> float:
        return self.level.get(skill, 0.0)


# --- Body ------------------------------------------------------------------

# name -> (vital, share of body blood supply a wound here drains fastest,
# can be lost). Vital parts kill outright when destroyed.
BODY_PLAN = {
    "head": (True, 1.2, False),
    "neck": (True, 2.0, False),
    "chest": (True, 1.5, False),
    "abdomen": (False, 1.3, False),
    "left arm": (False, 0.8, True),
    "right arm": (False, 0.8, True),
    "left hand": (False, 0.4, True),
    "right hand": (False, 0.4, True),
    "left leg": (False, 1.0, True),
    "right leg": (False, 1.0, True),
    "left foot": (False, 0.3, True),
    "right foot": (False, 0.3, True),
}


@dataclass
class BodyPart:
    """A part of a body, and the several things in it that can be hurt
    separately. A ball through the thigh that breaks the bone, cuts the
    artery and severs the tendon is three different disasters, and the
    surgeon treats them differently - see docs/design/18_life_aboard.md."""

    health: float = 1.0  # 0 = destroyed / severed
    bleed_ml_s: float = 0.0  # current bleeding rate from wounds here
    fractured: bool = False  # the bone is broken: no load, great pain
    artery_cut: bool = False  # it will not clot on its own
    tendon_cut: bool = False  # it still holds, but will not obey
    missing: bool = False
    infection: float = 0.0  # 0..1
    tourniquet: bool = False  # stops the bleeding, costs the limb in time
    splinted: bool = False  # the bone held straight so it can knit
    wounds: list = field(default_factory=list)  # short descriptions

    @property
    def usable(self) -> float:
        """How much of this part's work it can still do, 0..1."""
        if self.missing:
            return 0.0
        v = self.health
        if self.fractured and not self.splinted:
            v *= 0.15
        elif self.fractured:
            v *= 0.45
        if self.tendon_cut:
            v *= 0.25
        if self.tourniquet:
            v *= 0.3
        return max(0.0, min(1.0, v - 0.4 * self.infection))


@dataclass
class Body:
    """Blood and heartbeat are what death is measured by: an adult holds
    about 5 litres; losing more than ~30% brings collapse, ~40% is fatal
    without help. Destroying a vital part kills outright."""

    parts: dict = field(default_factory=lambda: {k: BodyPart() for k in BODY_PLAN})
    blood_ml: float = 5000.0
    blood_max_ml: float = 5000.0
    heart_rate: float = 72.0
    pain: float = 0.0
    conscious: bool = True
    alive: bool = True
    cause_of_death: str = ""

    @property
    def blood_fraction(self) -> float:
        return self.blood_ml / self.blood_max_ml

    @property
    def bleeding_ml_s(self) -> float:
        return sum(p.bleed_ml_s for p in self.parts.values())

    def capability(self, what: str) -> float:
        """What this body can still do, 0..1 - what every task should ask
        instead of reading limbs itself.

        grip    hauling on a rope, ramming home a charge, holding a cutlass
        reach   lifting a ball into a muzzle, passing a cartridge
        stand   staying on your feet on a wet, moving deck
        walk    getting anywhere, aloft included
        see     keeping a lookout
        speak   passing an order along the deck
        """
        if not self.alive:
            return 0.0
        p = self.parts
        hands = (p["left hand"].usable + p["right hand"].usable) / 2.0
        arms = (p["left arm"].usable + p["right arm"].usable) / 2.0
        legs = (p["left leg"].usable + p["right leg"].usable) / 2.0
        feet = (p["left foot"].usable + p["right foot"].usable) / 2.0
        core = (p["chest"].usable + p["abdomen"].usable) / 2.0
        head = p["head"].usable
        pain_tax = 1.0 - 0.55 * min(1.0, self.pain)
        blood_tax = max(0.25, min(1.0, (self.blood_fraction - 0.55) / 0.35))
        base = {
            "grip": 0.65 * hands + 0.35 * arms,
            "reach": 0.5 * arms + 0.3 * hands + 0.2 * core,
            "stand": 0.6 * legs + 0.25 * feet + 0.15 * core,
            "walk": 0.5 * legs + 0.3 * feet + 0.2 * core,
            "see": head,
            "speak": 0.5 + 0.5 * head,
        }.get(what, 1.0)
        if not self.conscious:
            return 0.0
        return max(0.0, min(1.0, base * pain_tax * blood_tax))


@dataclass
class Biography:
    """A person's story: dated events, from birth to now. Written by world
    history at generation, and by the simulation as things happen."""

    events: list = field(default_factory=list)  # [(year or sim-time label, text)]

    def add(self, when, text: str) -> None:
        self.events.append((when, text))


@dataclass
class Dead:
    """Marker: this person has died. The body stays where it fell."""

    cause: str = ""
    time_s: float = 0.0
