# Generating people with a story.
#
# A sailor is generated from a background (how he came to be at sea), a
# culture and nation, and an age. Those drive everything else coherently:
# a Newcastle collier's hand is an expert seaman with no love of the navy;
# a pressed landsman is green, resentful and anxious; a career topman is
# nimble aloft and proud of his ship. Traits are drawn around background
# means, skills grow with years at sea in the areas his life used, and the
# biography records the milestones that made him.
#
# All draws come from the caller's RNG stream, so a crew is reproducible
# from the campaign seed.

from __future__ import annotations

import random
from dataclasses import dataclass, field

from broadside.sim.people import components as pc
from broadside.sim.people.cultures import CULTURES, DEFAULT_KEYS


@dataclass
class Background:
    key: str
    label: str
    age: tuple  # (min, max) at time of service
    skills: dict  # skill -> base proficiency at ~5 years' experience
    traits: dict = field(default_factory=dict)  # personality mean shifts
    allegiance: dict = field(default_factory=dict)
    drink: float = 0.3
    grievance: float = 0.0
    how: str = ""  # how he came aboard, for the biography


BACKGROUNDS: dict[str, Background] = {b.key: b for b in [
    Background("career_seaman", "career man-of-war's man", (20, 45),
               {"seamanship": 0.6, "topwork": 0.55, "gunnery": 0.55, "rigging": 0.45, "helm": 0.35, "melee": 0.35},
               {"discipline": 0.1, "bravery": 0.05}, {"ship": 0.2, "captain": 0.1}, 0.45, 0.0, "volunteered for the navy"),
    Background("merchant_seaman", "merchant seaman", (20, 50),
               {"seamanship": 0.65, "topwork": 0.5, "helm": 0.45, "rigging": 0.45},
               {"discipline": -0.1, "ambition": 0.05}, {"cause": -0.15, "nation": -0.05}, 0.4, 0.25, "was pressed out of a merchantman"),
    Background("pressed_landsman", "pressed landsman", (18, 40),
               {"seamanship": 0.1},
               {"discipline": -0.1, "optimism": -0.1}, {"cause": -0.2, "captain": -0.1, "ship": -0.1}, 0.35, 0.45, "was taken by the press gang"),
    Background("volunteer_landsman", "volunteer landsman", (17, 30),
               {"seamanship": 0.15, "musketry": 0.1},
               {"ambition": 0.1, "optimism": 0.1}, {"cause": 0.15, "nation": 0.1}, 0.25, 0.0, "volunteered for the bounty"),
    Background("fisherman", "fisherman", (18, 45),
               {"seamanship": 0.45, "helm": 0.3, "lookout": 0.45, "rigging": 0.3},
               {"resilience": 0.1}, {"nation": 0.05}, 0.35, 0.15, "was pressed from the fishing fleet"),
    Background("quota_man", "quota man", (18, 45),
               {"seamanship": 0.05},
               {"honesty": -0.15, "temper": 0.1, "discipline": -0.15}, {"cause": -0.25, "captain": -0.15}, 0.5, 0.5, "was sent to sea by the magistrates in lieu of gaol"),
    Background("ships_boy", "ship's boy", (11, 16),
               {"seamanship": 0.1, "topwork": 0.15},
               {"optimism": 0.1}, {"ship": 0.1}, 0.05, 0.0, "came to sea as a boy"),
    Background("foreign_seaman", "foreign seaman", (20, 45),
               {"seamanship": 0.55, "topwork": 0.45, "rigging": 0.4},
               {}, {"nation": -0.3, "cause": -0.2}, 0.4, 0.2, "signed on in a foreign port"),
    Background("marine", "marine", (18, 35),
               {"musketry": 0.6, "melee": 0.5, "seamanship": 0.1},
               {"discipline": 0.2, "bravery": 0.05}, {"nation": 0.1, "cause": 0.1}, 0.4, 0.0, "enlisted in the marines"),
    Background("tradesman", "skilled tradesman", (22, 50),
               {"seamanship": 0.2, "carpentry": 0.3, "sailmaking": 0.3},
               {"discipline": 0.05}, {}, 0.3, 0.1, "was rated for his trade"),
    Background("gentleman_officer", "officer", (14, 50),
               {"seamanship": 0.5, "navigation": 0.55, "leadership": 0.5, "gunnery": 0.3, "melee": 0.35},
               {"ambition": 0.2, "discipline": 0.15, "bravery": 0.05}, {"nation": 0.25, "cause": 0.2, "captain": 0.1}, 0.25, 0.0, "entered the service as a midshipman"),
]}

# Crew make-up of a typical warship, by background (weights).
CREW_MIX = {
    "career_seaman": 22, "merchant_seaman": 20, "pressed_landsman": 16, "volunteer_landsman": 8,
    "fisherman": 6, "quota_man": 5, "ships_boy": 5, "foreign_seaman": 8, "marine": 7, "tradesman": 3,
}

# Where a ship's company comes from: mostly her own nation's people, with a
# real admixture of others (a period warship's company was often a quarter
# or more men from other nations and peoples).
FOREIGN_SHARE = 0.3

NICKNAMES = {
    "bravery": ("Lionheart", "Mouse"),
    "temper": ("Hothead", "Placid"),
    "sociability": ("Chatty", "Silent"),
    "honesty": ("Honest", "Fingers"),
    "optimism": ("Sunny", "Gloomy"),
}

RANK_BY_SKILL = [
    ("marine", lambda b, s: b.key == "marine"),
    ("ship's boy", lambda b, s: b.key == "ships_boy"),
    ("landsman", lambda b, s: s.get("seamanship", 0) < 0.3),
    ("ordinary seaman", lambda b, s: s.get("seamanship", 0) < 0.5),
    ("able seaman", lambda b, s: True),
]

# Role -> the skill that decides fitness for it.
ROLE_SKILL = {
    "Topman": "topwork",
    "Gun Captain": "gunlaying",
    "Quartermaster's Mate": "helm",
    "Carpenter's Mate": "carpentry",
    "Bosun's Mate": "rigging",
    "Sailmaker's Mate": "sailmaking",
    "Marine": "musketry",
    "Waister": "seamanship",
    "Loblolly Boy": "medicine",
    "Cook's Mate": "cooking",
}


def _clip(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _pick_weighted(rng: random.Random, weights: dict) -> str:
    total = sum(weights.values())
    r = rng.uniform(0, total)
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return next(iter(weights))


@dataclass
class Person:
    identity: pc.Identity
    personality: pc.Personality
    psyche: pc.Psyche
    allegiance: pc.Allegiance
    cravings: pc.Cravings
    skills: pc.Skills
    body: pc.Body
    biography: pc.Biography
    role: str

    def components(self) -> list:
        return [self.identity, self.personality, self.psyche, self.allegiance, self.cravings, self.skills, self.body, self.biography]


def generate_person(
    rng: random.Random,
    *,
    nation: str = "british",
    main_culture: str = "k0",
    year: int = 1805,
    background: str | None = None,
    culture: str | None = None,
    birthplace: str | None = None,
    places: list | None = None,
    battles: list | None = None,
    others: list | None = None,
) -> Person:
    """One person, coherent from background to biography. `places` is an
    optional list of town names (e.g. from a generated world) to draw
    birthplaces from; otherwise the culture invents one."""
    bg = BACKGROUNDS[background or _pick_weighted(rng, CREW_MIX)]
    if culture is not None:
        ck = culture
    elif rng.random() < FOREIGN_SHARE:
        pool = [k for k in (others or DEFAULT_KEYS) if k != main_culture] or [main_culture]
        ck = rng.choice(pool)
    else:
        ck = main_culture
    cult = CULTURES[ck]
    foreign = ck != main_culture
    given, family = cult.person_name(rng)
    age = rng.randint(*bg.age)
    birth = year - age
    home = birthplace or (rng.choice(places) if places and not foreign else cult.place_name(rng))

    def trait(name: str) -> float:
        return _clip(rng.gauss(0.5 + bg.traits.get(name, 0.0), 0.15))

    pers = pc.Personality(**{k: trait(k) for k in ("bravery", "temper", "sociability", "discipline", "ambition", "honesty", "optimism", "resilience")})

    years_at_sea = max(0.0, age - max(bg.age[0] - 2, 12) + rng.uniform(-1, 2))
    experience = min(1.0, years_at_sea / 8.0)
    skills = pc.Skills()
    for sk in pc.SKILLS:
        base = bg.skills.get(sk, 0.03)
        lvl = base * (0.5 + 0.9 * experience) + rng.gauss(0, 0.07)
        if sk == "lookout":
            lvl = max(lvl, rng.uniform(0.15, 0.7))  # eyesight is innate
        skills.level[sk] = round(_clip(lvl), 3)
    # A specialism: most men are notably better at one thing.
    spec = rng.choice([s for s in pc.SKILLS if s not in ("navigation", "leadership")])
    skills.level[spec] = round(_clip(skills.level[spec] + rng.uniform(0.1, 0.3)), 3)
    skills.level["gunlaying"] = round(max(skills.level["gunlaying"], skills.level["gunnery"] * rng.uniform(0.5, 1.1)), 3)

    def devotion(name: str, base: float) -> float:
        v = base + bg.allegiance.get(name, 0.0) + (pers.discipline - 0.5) * 0.3
        if foreign and name in ("nation", "cause"):
            v -= 0.25
        return _clip(v + rng.gauss(0, 0.1))

    allegiance = pc.Allegiance(nation=devotion("nation", 0.55), cause=devotion("cause", 0.5), captain=devotion("captain", 0.45), ship=devotion("ship", 0.4))
    drink = _clip(rng.gauss(bg.drink, 0.18))
    cravings = pc.Cravings(dependence=drink, need=_clip(drink * rng.uniform(0.1, 0.6)), tobacco=_clip(rng.gauss(0.4, 0.2)))
    anxiety = _clip(rng.gauss(0.2 + (0.5 - pers.resilience) * 0.3 + (0.1 if bg.key == "pressed_landsman" else 0), 0.1))
    psyche = pc.Psyche(
        morale=max(-1.0, min(1.0, rng.gauss(0.25 + (pers.optimism - 0.5) * 0.6 - bg.grievance * 0.4, 0.15))),
        stress=_clip(rng.gauss(0.15, 0.07)),
        anxiety=anxiety,
        depression=_clip(rng.gauss(0.08 + (0.5 - pers.optimism) * 0.2, 0.06)),
        confidence=_clip(0.3 + 0.5 * experience + (pers.bravery - 0.5) * 0.4 + rng.gauss(0, 0.08)),
        grievance=_clip(bg.grievance + rng.gauss(0, 0.08)),
    )
    blood = 5000.0 * (0.75 if age < 16 else 1.0) * rng.uniform(0.92, 1.08)
    body = pc.Body(blood_ml=blood, blood_max_ml=blood, heart_rate=rng.uniform(60, 80))
    # Old injuries tell a story too.
    bio = pc.Biography()
    bio.add(birth, f"Born in {home}.")
    first_sea = birth + max(bg.age[0] - 2, 11) + rng.randint(0, 3)
    if bg.key == "gentleman_officer":
        bio.add(first_sea, "Entered the service as a midshipman.")
    elif first_sea < year:
        bio.add(first_sea, {"fisherman": "First went out with the fishing boats.", "merchant_seaman": "Went to sea in a merchant brig.", "ships_boy": "Came aboard as a boy.", "tradesman": "Apprenticed to his trade ashore."}.get(bg.key, "First went to sea."))
    bio.add(year - rng.randint(0, 2), f"{bg.how[:1].upper()}{bg.how[1:]}.")
    # Veterans of this world's history: battles fought while he was at sea.
    if battles and bg.key not in ("pressed_landsman", "volunteer_landsman", "quota_man", "ships_boy"):
        fought = [(y, n) for y, n in battles if first_sea <= y < year]
        for y, n in sorted(rng.sample(fought, min(len(fought), rng.choice([0, 0, 0, 1, 1, 2]))) if fought else []):
            bio.add(y, f"Fought at the {n}.")
            skills.level["gunnery"] = round(_clip(skills.level["gunnery"] + 0.05), 3)
            psyche.confidence = _clip(psyche.confidence + 0.03)
    if years_at_sea > 6 and rng.random() < 0.25:
        part = rng.choice(["left hand", "right hand", "left leg", "right arm"])
        body.parts[part].health = rng.uniform(0.6, 0.9)
        body.parts[part].wounds.append("old wound, healed badly")
        bio.add(year - rng.randint(1, int(years_at_sea)), f"Wounded in the {part} in an old action.")
    if drink > 0.75:
        bio.add(year - rng.randint(0, 5), "Flogged for drunkenness.")

    nickname = ""
    if rng.random() < 0.3:
        tname = rng.choice(list(NICKNAMES))
        val = getattr(pers, tname)
        if val > 0.75:
            nickname = NICKNAMES[tname][0]
        elif val < 0.25:
            nickname = NICKNAMES[tname][1]
    if not nickname and drink > 0.8 and rng.random() < 0.5:
        nickname = "Grog"

    rank = next(r for r, test in RANK_BY_SKILL if test(bg, skills.level))
    if bg.key == "gentleman_officer":
        rank = "midshipman" if age < 20 else "lieutenant"
    ident = pc.Identity(given, family, ck, nation, birth, home, bg.key, nickname, rank)
    return Person(ident, pers, psyche, allegiance, cravings, skills, body, bio, role="")


def assign_roles(people: list, rng: random.Random) -> None:
    """Fit men to roles by skill: the best gun-layers become gun captains,
    the best helmsmen quartermaster's mates, and so on; the rest are topmen
    (if good aloft) or waisters. Proportions follow a period quarter bill."""
    quotas = [("Gun Captain", 0.10), ("Topman", 0.22), ("Quartermaster's Mate", 0.03), ("Carpenter's Mate", 0.03),
              ("Bosun's Mate", 0.03), ("Sailmaker's Mate", 0.02), ("Loblolly Boy", 0.01), ("Cook's Mate", 0.02)]
    pool = [p for p in people if p.identity.background not in ("marine", "ships_boy", "gentleman_officer")]
    n = len(pool)
    for p in people:
        if p.identity.background == "marine":
            p.role = "Marine"
        elif p.identity.background == "ships_boy":
            p.role = "Ship's Boy"
        elif p.identity.background == "gentleman_officer":
            p.role = "Midshipman" if p.identity.rank == "midshipman" else "Lieutenant"
    for role, share in quotas:
        k = max(1, int(round(share * n))) if n >= 8 else (1 if role in ("Gun Captain", "Topman") and n >= 2 else 0)
        skill = ROLE_SKILL[role]
        free = sorted((p for p in pool if not p.role), key=lambda p: -p.skills.get(skill))
        for p in free[:k]:
            p.role = role
    for p in pool:
        if not p.role:
            p.role = "Waister" if p.skills.get("seamanship") < 0.35 else "Topman" if p.skills.get("topwork") > 0.4 else "Afterguard"
