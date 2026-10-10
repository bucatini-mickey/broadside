# Words about people: the short readout the look cursor shows, and the full
# "who is this man" sheet (biography, character, skills, body) - the
# groundwork for a crew roster screen.

from __future__ import annotations

from broadside.sim import components as c
from broadside.sim.people import components as pc
from broadside.sim.people.cultures import CULTURES
from broadside.sim.people.generate import BACKGROUNDS
from broadside.sim.people.health import condition_words


def _level(v: float, words) -> str:
    return words[min(len(words) - 1, int(v * len(words)))]


def psyche_words(psy: pc.Psyche, crav: pc.Cravings | None = None) -> str:
    bits = [_level((psy.morale + 1) / 2, ["mutinous", "bitter", "sullen", "steady", "cheerful", "eager"])]
    if psy.fear > 0.4:
        bits.append("terrified" if psy.fear > 0.7 else "frightened")
    if psy.anxiety > 0.45:
        bits.append("anxious")
    if psy.depression > 0.35:
        bits.append("low in spirits")
    if psy.grievance > 0.45:
        bits.append("resentful")
    if crav is not None and crav.need * crav.dependence > 0.35:
        bits.append("craving drink")
    return ", ".join(bits)


def person_brief(world, ent: int, year: int = 1805) -> list:
    """Two or three lines for the look readout."""
    ident = world.try_component(ent, pc.Identity)
    name = world.component_for_entity(ent, c.Name).full
    role = world.try_component(ent, c.Role)
    if ident is None:
        return [f"  {name}, {role.title if role else ''}"]
    cult = CULTURES.get(ident.culture)
    lines = [f"  {name} - {role.title if role else ident.rank}"]
    lines.append(f"    {cult.adjective if cult else ''}, {year - ident.birth_year}, of {ident.birthplace}; {BACKGROUNDS[ident.background].label}")
    body = world.try_component(ent, pc.Body)
    psy = world.try_component(ent, pc.Psyche)
    crav = world.try_component(ent, pc.Cravings)
    state_bits = []
    if body is not None:
        state_bits.append(condition_words(body))
        if body.alive:
            state_bits.append(f"pulse {body.heart_rate:.0f}")
    if psy is not None and (body is None or body.alive):
        state_bits.append(psyche_words(psy, crav))
    lines.append("    " + "; ".join(b for b in state_bits if b))
    return lines


def person_sheet(world, ent: int, year: int = 1805) -> list:
    """Everything we know about a person, as text lines."""
    out = person_brief(world, ent, year)
    pers = world.try_component(ent, pc.Personality)
    if pers is not None:
        traits = []
        for name, lo, hi in (("bravery", "timid", "brave"), ("temper", "placid", "hot-tempered"), ("sociability", "solitary", "sociable"),
                             ("discipline", "insubordinate", "obedient"), ("honesty", "light-fingered", "honest"), ("optimism", "gloomy", "cheerful"),
                             ("resilience", "brittle", "hardy")):
            v = getattr(pers, name)
            if v > 0.68:
                traits.append(hi)
            elif v < 0.32:
                traits.append(lo)
        out.append("  Character: " + (", ".join(traits) if traits else "unremarkable"))
    al = world.try_component(ent, pc.Allegiance)
    if al is not None:
        out.append(f"  Devotion: nation {al.nation:.2f}, cause {al.cause:.2f}, captain {al.captain:.2f}, ship {al.ship:.2f}")
    crav = world.try_component(ent, pc.Cravings)
    if crav is not None:
        out.append(f"  Drink: dependence {crav.dependence:.2f}, need {crav.need:.2f}")
    sk = world.try_component(ent, pc.Skills)
    if sk is not None:
        best = sorted(sk.level.items(), key=lambda kv: -kv[1])[:5]
        out.append("  Best at: " + ", ".join(f"{k} {v:.2f}" for k, v in best))
    body = world.try_component(ent, pc.Body)
    if body is not None:
        out.append(f"  Blood {body.blood_ml:.0f}/{body.blood_max_ml:.0f} ml, bleeding {body.bleeding_ml_s:.1f} ml/s, pain {body.pain:.2f}")
        for part, p in body.parts.items():
            if p.wounds or p.missing:
                out.append(f"    {part}: {'; '.join(p.wounds)}")
    bio = world.try_component(ent, pc.Biography)
    if bio is not None:
        out.append("  Story:")
        for when, text in bio.events:
            out.append(f"    {when}: {text}")
    return out
