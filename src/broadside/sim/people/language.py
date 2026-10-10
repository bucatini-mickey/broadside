# Generated languages, Dwarf Fortress style.
#
# No real peoples, no real languages: every culture in the world speaks a
# language generated from a seed. To make those languages *feel* like
# languages - with a consistent sound, familiar-ish but unplaceable - each
# is built by blending the sound systems of one or two "flavours" and then
# mutating the result: dropping some sounds, adding a signature sound or
# spelling habit of its own. The flavours are inspired by real phonologies
# (Latin, Welsh, Esperanto, Slavic, Germanic, Greek, Nahuatl, Finnish,
# Swahili, Quechua, Japanese, Turkish...) but they're only raw material:
# they are never named in the game, and a blended, mutated language
# doesn't read as any of them.
#
# Each language has a lexicon: English concepts ("salt", "bay", "iron",
# "wolf") map to words, generated deterministically on first use. Names
# are built from meaningful words, so every name has a translation -
# Varnakkel, "Saltbay"; Captain Oris Tlekhaan, "Iron-Tide" - as in DF.

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field

# --- Flavours (internal raw material; never shown to the player) ------------
#
# onsets / nuclei / codas: (sound, weight). shapes: syllable templates.
# given_end / family_end: endings that give personal names their feel.


@dataclass
class Flavour:
    onsets: list
    nuclei: list
    codas: list
    shapes: list  # [("CV", w), ("CVC", w), ("V", w), ("CCV", w)...]
    clusters: list = field(default_factory=list)  # onset clusters for "CC"
    syllables: tuple = (1, 2, 2, 2, 3)
    given_end: list = field(default_factory=list)
    linker: str = ""  # vowel inserted between compound parts
    modifier_first: bool = True


def _w(s: str, default: int = 3) -> list:
    """'p t k:5 s' -> [("p",3),("t",3),("k",5),("s",3)]"""
    out = []
    for tok in s.split():
        if ":" in tok:
            a, b = tok.split(":")
            out.append((a, int(b)))
        else:
            out.append((tok, default))
    return out


FLAVOURS = {
    # Latin-like
    "lat": Flavour(_w("p t k:2 c b d g m n l r:4 s:4 v f qu:1 st:1"), _w("a:5 e:4 i:4 o:3 u:3 ae:1"), _w("s:4 m:2 n:3 r:2 x:1 t:1"),
                   [("CV", 5), ("CVC", 3), ("V", 1)], _w("pr tr cr fl st gr"), (2, 2, 3, 3), _w("us:3 a:3 o:2 ius:1 ex:1"), "i", False),
    # Welsh-like
    "wel": Flavour(_w("ll:2 dd:2 rh:1 ff:1 th:1 g c b d m n:4 w:3 gw:2 t p s"), _w("a:4 e:3 y:4 w:2 ai:2 ae:1 o:3 i:2"), _w("n:4 dd:2 th:1 r:3 l:2 ch:2 s:1"),
                   [("CV", 4), ("CVC", 5), ("V", 1)], _w("br dr gl gr tr cl"), (1, 2, 2, 3), _w("wyn:2 ydd:2 an:2 og:1 edd:1"), "o", False),
    # Esperanto-like
    "esp": Flavour(_w("b c d f g h j k l:4 m n:4 p r:4 s:4 t v z ŝ:1 ĝ:1"), _w("a:5 e:5 i:4 o:5 u:3 aj:1 oj:1"), _w("n:3 s:2 l:2 r:2 j:1"),
                   [("CV", 6), ("CVC", 3), ("V", 1)], _w("kr pl tr sp st"), (2, 2, 3), _w("o:4 an:2 io:1 eto:1"), "o", True),
    # Slavic-like
    "sla": Flavour(_w("b v d z zh:2 k l:3 m n p r:4 s t ch:2 sh:2 kh:1 g"), _w("a:4 o:4 e:3 i:3 u:2 y:2"), _w("v:2 k:2 n:2 r:2 sk:1 ts:1 d:1 l:1"),
                   [("CV", 4), ("CVC", 4), ("CCV", 2)], _w("str zv pr tr gr sv vl br dr"), (2, 2, 3), _w("an:2 or:2 imir:1 ek:2 ota:1"), "o", True),
    # Germanic-like
    "ger": Flavour(_w("b d f g h:2 k l m n r s t th:2 w:2 sk:1 sw:1"), _w("a:4 e:4 i:3 o:3 u:3 ei:1 au:1"), _w("d:2 t:2 n:3 r:3 ld:2 nd:2 rk:1 st:1 lf:1 ng:1"),
                   [("CV", 3), ("CVC", 6)], _w("br fr gr hr kn st thr"), (1, 2, 2), _w("ric:2 wald:2 mund:1 bert:1 helm:1 olf:1"), "e", True),
    # Greek-like
    "gre": Flavour(_w("p t k:3 th:2 ph:2 ch:2 m n l r:3 s:3 d g x:1 z:1"), _w("a:4 e:3 i:3 o:4 y:1 ai:1 eu:1 ou:1"), _w("s:4 n:3 r:1 x:1"),
                   [("CV", 5), ("CVC", 3), ("V", 1)], _w("kr pr tr pl kl ps:1"), (2, 3, 3), _w("os:4 as:2 ides:1 eus:1 on:2"), "o", True),
    # Nahuatl-like
    "nah": Flavour(_w("tl:4 tz:2 ch:2 x:2 k:3 qu:2 hu:2 m:3 n:3 p t:3 y:2 z:1"), _w("a:5 e:3 i:4 o:4"), _w("tl:3 n:2 k:1 x:1 z:1 h:1"),
                   [("CV", 6), ("CVC", 3)], [], (2, 3, 3), _w("tl:3 in:2 atl:1 otl:1 qui:1"), "a", True),
    # Finnish-like
    "fin": Flavour(_w("k:4 t:4 p s:3 h:2 v:3 j:2 l:3 m n:3 r:2"), _w("a:4 ä:3 e:3 i:4 o:3 u:3 ö:1 y:2 aa:1 ii:1 uu:1"), _w("n:3 s:2 t:2 l:2 kk:1 tt:1"),
                   [("CV", 5), ("CVC", 4), ("V", 1)], [], (2, 3, 3), _w("o:2 i:2 nen:2 la:1 kki:1"), "i", True),
    # Swahili-like
    "swa": Flavour(_w("mb:2 nd:2 ng:2 ny:1 k:3 t:3 m:3 w:3 j:2 s:2 z:1 b:2 l:2 h:1 ch:1"), _w("a:5 e:3 i:4 o:3 u:4"), [],
                   [("CV", 9), ("V", 1)], [], (2, 3, 3), _w("i:2 e:2 a:2 o:1 ani:1"), "a", False),
    # Quechua-like
    "que": Flavour(_w("q:3 k:3 ch:2 p t:3 w:3 y:3 ll:2 m n r s:2 h:1"), _w("a:6 i:4 u:4"), _w("q:1 k:1 n:2 y:2 s:1 r:1"),
                   [("CV", 6), ("CVC", 3)], [], (2, 2, 3), _w("ku:2 q:1 lla:1 y:2 ri:1"), "i", True),
    # Japanese-like
    "jap": Flavour(_w("k:4 s:3 t:3 n:3 h:2 m:3 y:2 r:4 w:1 g:2 z:1 d:1 b:1 sh:2 ch:1 ts:1"), _w("a:4 i:4 u:3 e:3 o:4"), _w("n:2"),
                   [("CV", 8), ("CVC", 1), ("V", 1)], [], (2, 3, 3), _w("o:2 i:2 ro:1 ki:1 a:1"), "", True),
    # Turkish-like
    "tur": Flavour(_w("b c:1 ç:1 d g h k:3 l m n r:3 s:3 ş:1 t y:2 z:2"), _w("a:4 e:4 ı:2 i:3 o:2 ö:1 u:2 ü:1"), _w("n:3 r:3 l:2 k:2 z:1 t:1 ş:1"),
                   [("CV", 4), ("CVC", 5)], [], (2, 2, 3), _w("an:2 er:2 ek:1 ay:1 ün:1"), "a", True),
}

# Spelling habits a language can adopt as its own signature.
SIGNATURES = ["kh", "vr", "ss", "aa", "é", "ô", "'", "zh", "dh", "rr", "yr", "ae", "ö", "q", "x", "ll"]

# The words a language needs for names. Kept English; each language maps
# them to its own words.
CONCEPTS_PLACE_HEAD = ["bay", "cape", "isle", "haven", "rock", "hill", "cove", "point", "shore", "harbour", "fort", "town", "reach", "sound", "head", "strand"]
CONCEPTS_PLACE_MOD = ["salt", "stone", "red", "white", "black", "old", "new", "high", "gull", "wind", "sun", "moon", "iron", "grey", "green", "deep", "far", "bright", "olive", "fig", "cedar", "gold", "storm", "dawn", "wolf", "shell", "coral", "king", "saint", "twin"]
CONCEPTS_NAME = ["iron", "stone", "tide", "wave", "storm", "wind", "oak", "ash", "wolf", "bear", "hawk", "raven", "fire", "salt", "blood", "bone", "hand", "heart", "eye", "shield", "sword", "spear", "hammer", "anchor", "sail", "rope", "star", "moon", "sun", "thunder", "frost", "stern", "bold", "swift", "grey", "red", "black", "gold", "deep", "true"]
CONCEPTS_SHIP = ["thunder", "resolve", "valour", "fury", "vengeance", "glory", "triumph", "tempest", "lion", "eagle", "dragon", "serpent", "defiance", "fortune", "victory", "hope", "dawn", "star", "crown", "sword", "shield", "spear", "wave", "wind", "storm", "faith", "honour", "wrath", "courage", "sea"]


def _pick(rng: random.Random, weighted: list) -> str:
    total = sum(w for _, w in weighted)
    r = rng.uniform(0, total)
    for s, w in weighted:
        r -= w
        if r <= 0:
            return s
    return weighted[-1][0]


def _blend(a: list, b: list, wb: float, rng: random.Random, drop: float) -> list:
    merged: dict = {}
    for s, w in a:
        merged[s] = merged.get(s, 0) + w * (1 - wb)
    for s, w in b:
        merged[s] = merged.get(s, 0) + w * wb
    out = [(s, w) for s, w in merged.items() if rng.random() > drop or w > 3]
    return out or list(merged.items())


@dataclass
class Language:
    seed: int
    onsets: list
    nuclei: list
    codas: list
    shapes: list
    clusters: list
    syllables: tuple
    given_end: list
    linker: str
    modifier_first: bool
    signature: str
    lexicon: dict = field(default_factory=dict)

    # --- words ----------------------------------------------------------

    def _syllable(self, rng: random.Random, first: bool, last: bool) -> str:
        shape = _pick(rng, self.shapes)
        s = ""
        if shape.startswith("CC") and self.clusters:
            s += _pick(rng, self.clusters)
        elif shape.startswith("C"):
            s += _pick(rng, self.onsets)
        s += _pick(rng, self.nuclei)
        if shape.endswith("VC") and self.codas:
            s += _pick(rng, self.codas)
        return s

    def make_word(self, rng: random.Random, syllables: int | None = None) -> str:
        n = syllables or rng.choice(self.syllables)
        parts = [self._syllable(rng, i == 0, i == n - 1) for i in range(n)]
        w = "".join(parts)
        # The language's signature habit shows up now and then.
        if self.signature and rng.random() < 0.25 and len(w) > 3:
            i = rng.randrange(1, len(w) - 1)
            w = w[:i] + self.signature + w[i + 1 :]
        # Tidy impossible runs: no three identical letters, no 4 consonants.
        out = []
        for ch in w:
            if len(out) >= 2 and out[-1] == ch and out[-2] == ch:
                continue
            out.append(ch)
        w = "".join(out)
        return w

    def word(self, concept: str) -> str:
        """This language's word for an English concept (stable)."""
        if concept not in self.lexicon:
            rng = random.Random(zlib.crc32(f"{self.seed}:{concept}".encode()))
            n = 1 if len(concept) <= 4 and rng.random() < 0.6 else rng.choice([1, 2, 2])
            self.lexicon[concept] = self.make_word(rng, n)
        return self.lexicon[concept]

    def compound(self, modifier: str, head: str) -> tuple[str, str]:
        """(native, translation) for modifier+head, in the language's order."""
        a, b = self.word(modifier), self.word(head)
        first, second = (a, b) if self.modifier_first else (b, a)
        if first[-1:] in "aeiouyäöü" and second[:1] in "aeiouyäöü":
            second = second[1:] or second
        elif self.linker and first[-1:] not in "aeiouyäöü" and second[:1] not in "aeiouyäöü" and len(first) + len(second) > 7:
            first = first + self.linker
        native = (first + second)
        return native[:1].upper() + native[1:], f"{modifier.title()}{head}"


def make_language(seed: int, flavours: list | None = None) -> Language:
    rng = random.Random(seed * 2654435761 % (2 ** 32))
    keys = flavours or rng.sample(sorted(FLAVOURS), 2 if rng.random() < 0.75 else 1)
    a = FLAVOURS[keys[0]]
    b = FLAVOURS[keys[1]] if len(keys) > 1 else a
    wb = rng.uniform(0.2, 0.45) if len(keys) > 1 else 0.0
    drop = rng.uniform(0.1, 0.25)
    return Language(
        seed=seed,
        onsets=_blend(a.onsets, b.onsets, wb, rng, drop),
        nuclei=_blend(a.nuclei, b.nuclei, wb, rng, drop * 0.5),
        codas=_blend(a.codas, b.codas, wb, rng, drop) if (a.codas or b.codas) else [],
        shapes=_blend(a.shapes, b.shapes, wb, rng, 0.0),
        clusters=_blend(a.clusters, b.clusters, wb, rng, drop) if (a.clusters or b.clusters) else [],
        syllables=a.syllables if rng.random() > wb else b.syllables,
        given_end=_blend(a.given_end, b.given_end, wb, rng, drop),
        linker=a.linker if rng.random() > wb else b.linker,
        modifier_first=a.modifier_first if rng.random() > wb else b.modifier_first,
        signature=rng.choice(SIGNATURES) if rng.random() < 0.7 else "",
    )
