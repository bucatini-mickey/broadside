# World history: a century and a half of wars, battles, sieges, treaties,
# famous admirals and famous ships, simulated year by year before play
# begins - the Dwarf Fortress "legends" idea, at a naval scale.
#
# It isn't decoration. The result is the world's present: who owns which
# port, who is at war with whom (the campaign starts in a great war), how
# strong each navy is - and a store of named battles, admirals and ships
# that generated people can have been part of: an old seaman who "fought
# at the Battle of Varnakkel in 1782", a captain whose father died at the
# siege of Tlekhaan. See docs/design/12_world_generation.md.

from __future__ import annotations

import random
from dataclasses import dataclass, field

from broadside.sim.people.cultures import CULTURES
from broadside.worldgen.polity import Nation, Settlement

@dataclass
class HistEvent:
    year: int
    kind: str  # "war" | "peace" | "battle" | "siege" | "founding" | "person" | "ship" | "wreck" | "plague" | "alliance"
    text: str
    nations: tuple = ()
    settlement: int = -1
    col: int = -1
    row: int = -1
    name: str = ""  # e.g. the battle's name


@dataclass
class Figure:
    """A notable person of history (admirals, captains)."""

    name: str
    nation: int
    born: int
    died: int | None = None
    deeds: list = field(default_factory=list)


@dataclass
class History:
    start: int
    end: int
    events: list = field(default_factory=list)
    wars: list = field(default_factory=list)  # [(a, b, start, end or None)]
    figures: list = field(default_factory=list)
    ships: list = field(default_factory=list)  # [(name, nation, launched, fate)]

    def battles_of(self, nation_id: int) -> list:
        return [e for e in self.events if e.kind in ("battle", "siege") and nation_id in e.nations]

    def at_war(self, a: int, b: int) -> bool:
        return any({x, y} == {a, b} and end is None for x, y, s, end in self.wars)


def _nearest_settlement(settlements, col, row):
    return min(settlements, key=lambda s: (s.col - col) ** 2 + (s.row - row) ** 2)


def simulate_history(nations: list, settlements: list, rng: random.Random, start: int = 1650, end: int = 1805) -> History:
    hist = History(start, end)
    by_id = {s.id: s for s in settlements}

    def say(year, kind, text, nats=(), s: Settlement | None = None, name=""):
        hist.events.append(HistEvent(year, kind, text, tuple(nats), s.id if s else -1, s.col if s else -1, s.row if s else -1, name))
        if s is not None:
            s.history.append((year, text))

    for n in nations:
        n.strength = 1.0 + 0.1 * sum(1 for s in settlements if s.owner == n.id)
        say(start, "founding", f"The {n.government} of {n.name} holds {sum(1 for s in settlements if s.owner == n.id)} ports; its seat is {by_id[n.capital].name}.", (n.id,), by_id[n.capital])

    active: dict = {}  # (a, b) -> start year
    for year in range(start + 1, end + 1):
        # Relations drift; old grudges linger. Neighbours quarrel more.
        for a in nations:
            for b in nations:
                if a.id >= b.id:
                    continue
                drift = rng.gauss(0, 0.08) - 0.01 * (a.culture != b.culture)
                if (a.id, b.id) in active:
                    drift -= 0.02
                a.relations[b.id] = b.relations[a.id] = max(-1.0, min(1.0, a.relations[b.id] + drift))

        # Shipbuilding pulls each navy back toward what its ports can
        # support, so a lost war hurts for a generation but isn't forever.
        for n in nations:
            ports = sum(1 for s_ in settlements if s_.owner == n.id)
            base = (35 if n.outside_power else 6) + 2.2 * ports
            n.navy = max(3, int(round(n.navy + (base - n.navy) * 0.08 + rng.gauss(0, 1))))

        # Declarations of war.
        for a in nations:
            for b in nations:
                if a.id >= b.id or (a.id, b.id) in active:
                    continue
                if a.relations[b.id] < -0.55 and rng.random() < 0.25:
                    active[(a.id, b.id)] = year
                    hist.wars.append([a.id, b.id, year, None])
                    say(year, "war", f"War between {a.name} and {b.name}.", (a.id, b.id))

        # Fighting.
        for (ai, bi), since in list(active.items()):
            a, b = nations[ai], nations[bi]
            for _ in range(rng.choice([0, 1, 1, 2])):
                _battle(hist, rng, year, a, b, settlements, say)
            if rng.random() < 0.35:
                _siege(hist, rng, year, a, b, settlements, say)
            exhaustion = (year - since) * 0.08 + rng.random() * 0.3
            if exhaustion > 0.75 and rng.random() < 0.4:
                del active[(ai, bi)]
                for w in hist.wars:
                    if w[0] == ai and w[1] == bi and w[3] is None:
                        w[3] = year
                a.relations[bi] = b.relations[ai] = rng.uniform(-0.2, 0.3)
                say(year, "peace", f"Peace of {rng.choice([s for s in settlements if s.owner in (ai, bi)] or settlements).name} ends the war between {a.name} and {b.name}.", (ai, bi))

        # Notable people and ships.
        if rng.random() < 0.18:
            n = rng.choice(nations)
            cult = CULTURES[n.culture]
            g, f = cult.person_name(rng)
            fig = Figure(f"{g} {f}", n.id, year - rng.randint(28, 45))
            hist.figures.append(fig)
            say(year, "person", f"{fig.name} is made admiral of {n.name}.", (n.id,))
        if rng.random() < 0.3:
            n = rng.choice(nations)
            ship, meaning = CULTURES[n.culture].ship_name(rng)
            guns = rng.choice([64, 74, 74, 74, 80, 90, 98, 100, 110])
            hist.ships.append([ship, n.id, year, None])
            say(year, "ship", f"{n.name} launches the {ship} ('{meaning}'), {guns} guns.", (n.id,))
        if rng.random() < 0.06:
            s = rng.choice(settlements)
            s.population = int(s.population * rng.uniform(0.55, 0.8))
            say(year, "plague", f"Plague in {s.name}.", (s.owner,), s)
        if rng.random() < 0.08:
            live = [sh for sh in hist.ships if sh[3] is None]
            if live:
                sh = rng.choice(live)
                sh[3] = f"wrecked {year}"
                say(year, "wreck", f"The {sh[0]} of {nations[sh[1]].name} is lost in a storm.", (sh[1],))

    # The present: a great war involving the player's nation.
    player = next(n for n in nations if n.player)
    foes = sorted((n for n in nations if n.id != player.id), key=lambda n: player.relations[n.id])
    for foe in foes[:2]:
        key = (min(player.id, foe.id), max(player.id, foe.id))
        if key not in active:
            active[key] = end
            hist.wars.append([key[0], key[1], end, None])
            player.relations[foe.id] = foe.relations[player.id] = -0.8
            say(end, "war", f"{player.name} and {foe.name} go to war: the present war begins.", (player.id, foe.id))
    return hist


def _battle(hist, rng, year, a, b, settlements, say) -> None:
    near = [s for s in settlements if s.owner in (a.id, b.id)] or settlements
    place = rng.choice(near)
    cult = CULTURES[a.culture if rng.random() < 0.5 else b.culture]
    where = rng.choice([place.name, cult.place_name(rng), cult.place_name(rng)])
    ships = rng.randint(3, 25)
    win = a if rng.random() < a.navy / (a.navy + b.navy) else b
    lose = b if win is a else a
    lost = max(0, int(ships * rng.uniform(0.0, 0.3)))
    lose.navy = max(3, lose.navy - lost)
    win.navy += rng.randint(0, 2)
    adm = [f for f in hist.figures if f.nation == win.id and f.died is None]
    by = f" under {rng.choice(adm).name}" if adm else ""
    if adm and rng.random() < 0.3:
        dead = rng.choice([f for f in hist.figures if f.nation == lose.id and f.died is None] or adm)
        dead.died = year
        dead.deeds.append(f"killed at the Battle of {where}")
    name = f"Battle of {where}"
    say(year, "battle", f"{name}: {win.name}{by} defeats {lose.name}; {lost} of {ships} ships lost.", (a.id, b.id), place, name)


def _siege(hist, rng, year, a, b, settlements, say) -> None:
    attacker, defender = (a, b) if rng.random() < a.strength / (a.strength + b.strength) else (b, a)
    targets = [s for s in settlements if s.owner == defender.id and s.id != defender.capital]
    if not targets:
        return
    s = rng.choice(targets)
    if rng.random() < (0.35 if s.fortified else 0.7):
        s.owner = attacker.id
        attacker.strength += 0.1
        defender.strength = max(0.3, defender.strength - 0.1)
        say(year, "siege", f"{attacker.name} takes {s.name} from {defender.name}.", (a.id, b.id), s, f"Siege of {s.name}")
    else:
        say(year, "siege", f"{attacker.name} besieges {s.name} but is beaten off.", (a.id, b.id), s, f"Siege of {s.name}")
