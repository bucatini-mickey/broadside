# Cultures: peoples with their own generated language (sim/people/
# language.py), and the naming traditions built from it.
#
# Nothing here names a real people. A culture's name for itself is a word
# in its own language; its given names come from its sound system; its
# family names and place names are compounds of meaningful words, each
# with a translation ("Tlekhaan" - "Iron-Tide"; "Varnakkel" - "Saltbay"),
# the way Dwarf Fortress does it.
#
# Hand-built scenarios use a fixed set of default cultures (keys k0..k8,
# mapped to scenario factions in sim/people/__init__.py). A generated world
# makes its own cultures from its seed and registers them here.

from __future__ import annotations

import random
from dataclasses import dataclass, field

from broadside.sim.people.language import (
    CONCEPTS_NAME,
    CONCEPTS_PLACE_HEAD,
    CONCEPTS_PLACE_MOD,
    CONCEPTS_SHIP,
    Language,
    make_language,
)

# Generated words that happen to be real English words - some rude, some
# just jarring - are rejected as names.
_BLOCK = ("shit", "cunt", "fuck", "cock", "dick", "piss", "fag", "nig", "tit", "ass", "cum", "poo", "wank", "twat", "slut", "rape", "kill")
_REAL = {"box", "das", "the", "and", "man", "men", "boy", "cat", "dog", "hat", "mad", "sad", "bad", "god", "sin", "war", "was", "his", "her", "him", "yes", "sex", "gay", "fat", "pig", "cow", "rat", "bum"}


def acceptable(word: str) -> bool:
    w = word.lower()
    return not any(b in w for b in _BLOCK) and w not in _REAL


GOVERNMENTS = ["kingdom", "republic", "merchant republic", "empire", "duchy", "league of free cities", "principality", "confederacy", "commonwealth", "grand despotate"]


@dataclass
class Culture:
    key: str
    language: Language
    name: str  # the people's own name for themselves
    adjective: str  # used in English text: "an Orveshi seaman"
    given: list = field(default_factory=list)
    family: list = field(default_factory=list)
    meanings: dict = field(default_factory=dict)  # native name -> translation

    def meaning(self, native: str) -> str:
        return self.meanings.get(native, "")

    def person_name(self, rng: random.Random) -> tuple[str, str]:
        return rng.choice(self.given), rng.choice(self.family)

    def word(self, rng: random.Random, syllables: int | None = None) -> str:
        w = self.language.make_word(rng, syllables)
        return w[:1].upper() + w[1:]

    def place_name(self, rng: random.Random) -> str:
        mod, head = rng.choice(CONCEPTS_PLACE_MOD), rng.choice(CONCEPTS_PLACE_HEAD)
        if rng.random() < 0.75:
            native, meaning = self.language.compound(mod, head)
            if len(native) < 4:
                native = native + self.language.word("town")
        else:
            h = self.language.word(head)
            m = self.language.word(mod)
            a, b = (m, h) if self.language.modifier_first else (h, m)
            native = f"{a[:1].upper()}{a[1:]} {b[:1].upper()}{b[1:]}"
            meaning = f"{mod.title()} {head.title()}"
        self.meanings[native] = meaning
        return native

    def land_name(self, rng: random.Random) -> str:
        mod = rng.choice(CONCEPTS_PLACE_MOD + CONCEPTS_NAME)
        native, meaning = self.language.compound(mod, "land")
        self.meanings[native] = meaning
        return native

    def nation_name(self, rng: random.Random) -> str:
        return self.land_name(rng)

    def ship_name(self, rng: random.Random) -> tuple[str, str]:
        concept = rng.choice(CONCEPTS_SHIP)
        w = self.language.word(concept)
        meaning = concept.title()
        if len(w) < 5 or not acceptable(w):
            mod = rng.choice(["great", "swift", "bold", "iron", "red", "high", "true", "storm"])
            w, _ = self.language.compound(mod, concept)
            meaning = f"{mod.title()} {concept.title()}"
        native = w[:1].upper() + w[1:]
        self.meanings[native] = meaning
        return native, meaning


def make_culture(key: str, seed: int, flavours: list | None = None) -> Culture:
    lang = make_language(seed, flavours)
    rng = random.Random(seed + 99991)
    stem = lang.word("people")
    while len(stem) < 4 or not acceptable(stem):
        stem = lang.make_word(rng, 2)
    lang.lexicon["people"] = stem
    stem = stem[:1].upper() + stem[1:]
    if stem[-1:].lower() in "aeiouyäöü":
        adjective = stem + rng.choice(["n", "ri", "si"])
    else:
        adjective = stem + rng.choice(["i", "ian", "ese", "ar", "ic"])
    c = Culture(key, lang, stem, adjective)
    # Given names: sound-system words, some with a name ending.
    seen = set()
    while len(c.given) < 48:
        w = lang.make_word(rng, rng.choice([1, 2, 2]))
        if rng.random() < 0.5 and lang.given_end:
            end = rng.choice(lang.given_end)[0]
            w = w.rstrip("aeiouyäöü") + end if w[-1:] in "aeiouyäöü" and end[:1] in "aeiouyäöü" else w + end
        w = w[:1].upper() + w[1:]
        if 4 <= len(w) <= 11 and w not in seen and acceptable(w):
            seen.add(w)
            c.given.append(w)
    # Family names: meaningful compounds ("Iron-Tide"), or "child of" forms.
    child = lang.word("son")
    while len(c.family) < 64:
        if rng.random() < 0.65:
            a, b = rng.sample(CONCEPTS_NAME, 2)
            native, _ = lang.compound(a, b)
            meaning = f"{a.title()}-{b.title()}"
        else:
            g = rng.choice(c.given)
            native = (g + child) if lang.modifier_first is False else (child[:1].upper() + child[1:] + g.lower())
            meaning = f"child of {g}"
        if 4 <= len(native) <= 14 and native not in c.meanings and acceptable(native):
            c.meanings[native] = meaning
            c.family.append(native)
    return c


CULTURES: dict[str, Culture] = {}


def register(c: Culture) -> Culture:
    CULTURES[c.key] = c
    return c


# The default peoples of hand-built scenarios. Each blends two sound
# systems (see language.FLAVOURS) - fixed here so scenario crews are stable.
_DEFAULT_BLENDS = [("ger", "wel"), ("lat", "esp"), ("lat", "sla"), ("sla", "fin"), ("gre", "tur"), ("nah", "que"), ("swa", "jap"), ("tur", "lat"), ("fin", "ger")]
for _i, _fl in enumerate(_DEFAULT_BLENDS):
    register(make_culture(f"k{_i}", 1001 + _i * 37, list(_fl)))
DEFAULT_KEYS = [f"k{i}" for i in range(len(_DEFAULT_BLENDS))]


def culture(key: str) -> Culture:
    return CULTURES[key]
