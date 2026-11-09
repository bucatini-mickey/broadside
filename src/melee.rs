//! Hand-to-hand fighting (BRD-06): men of different factions on the same
//! deck close and strike, with cutlass, pike, bayonet, fists or a single
//! pistol shot, and every blow that lands is a real wound through the body
//! model (`game::wound` -> `Body::strike`), exactly as splinters and shot
//! are. The dead and the senseless stay where they fall.
//!
//! How tachyon creatures attack (`Species::Attack`, `Life::attack`): a held
//! blow of a kind and a force, a flat chance to hit, a part picked at random
//! by size. Here the same pieces are used, but who hits whom is decided by
//! skill: the chance to land a blow rises with the striker's `melee` skill
//! (the pistol uses `musketry`) over the defender's, each worn down by
//! fatigue, hurt hands and legs, and fear. The force of the blow comes from
//! the weapon, the striker's strength and a little from his skill.
//!
//! Will to fight (a stand-in: no morale model exists yet, see
//! `docs/MECHANICS.md` PSY rows): one number per man, from his bravery and
//! discipline, lowered by pain, blood lost and fatigue. Below [`BREAK`] he
//! loses heart and runs from the enemy; he rallies once it is back above
//! [`RALLY`] and some seconds have passed. Nothing else (comrades falling,
//! the captain, grievance, drink) feeds it yet.
//!
//! Who goes to meet the enemy: marines, topmen, waisters, bosun's and
//! carpenter's mates and the officers, within sight; gun crews, the
//! quartermaster and boys hold their posts and fight only what comes to
//! them (or what has struck them). Defenders turning out in order is BRD-07.

use crate::crew::{self, Role};
use crate::game::wound;
use crate::ship::{Note, Ship};
use std::collections::HashMap;
use tachyon::life::body::DamageKind;
use tachyon::life::mind::{Control, Goal, Routine, Task};
use tachyon::life::Creature;
use tachyon::prelude::*;

/// Will to fight below which a man breaks and runs.
pub const BREAK: f32 = 0.30;
/// ... and above which he can rally (after [`MIN_BROKEN`] seconds).
pub const RALLY: f32 = 0.40;
pub const MIN_BROKEN: f32 = 8.0;
/// How far a man goes to meet the enemy.
pub const SEEK: i32 = 12;
/// Fatigue (0..1) a swing costs the one who makes it, and the one who parries.
pub const TIRE_SWING: f32 = 0.006;
pub const TIRE_PARRY: f32 = 0.003;
/// A man beset by this many seconds of blows cannot be got at by more men.
pub const SWARM: f32 = 1.4;
pub const SWARM_PER_BLOW: f32 = 0.7;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Weapon {
    Cutlass,
    Pike,
    Bayonet,
    Cuff,
}

impl Weapon {
    pub fn name(self) -> &'static str {
        match self {
            Weapon::Cutlass => "cutlass",
            Weapon::Pike => "boarding pike",
            Weapon::Bayonet => "bayonet",
            Weapon::Cuff => "fists",
        }
    }
    pub fn verb(self) -> &'static str {
        match self {
            Weapon::Cutlass => "cuts",
            Weapon::Pike => "thrusts a pike at",
            Weapon::Bayonet => "stabs",
            Weapon::Cuff => "cuffs",
        }
    }
    pub fn kind(self) -> DamageKind {
        match self {
            Weapon::Cutlass => DamageKind::Edge,
            Weapon::Pike | Weapon::Bayonet => DamageKind::Point,
            Weapon::Cuff => DamageKind::Blunt,
        }
    }
    /// Force of a good blow, before strength and skill.
    pub fn force(self) -> f32 {
        match self {
            Weapon::Cutlass => 55.0,
            Weapon::Pike => 75.0,
            Weapon::Bayonet => 65.0,
            Weapon::Cuff => 25.0,
        }
    }
    /// Seconds between blows for a fresh, able man.
    pub fn interval(self) -> f32 {
        match self {
            Weapon::Cutlass => 1.6,
            Weapon::Pike => 2.2,
            Weapon::Bayonet => 2.0,
            Weapon::Cuff => 1.4,
        }
    }
    /// How many cells away he can strike (a pike keeps a cutlass off).
    pub fn reach(self) -> i32 {
        if self == Weapon::Pike { 2 } else { 1 }
    }
}

/// Pistol ball: fired once, at close quarters; the pistol is then dropped.
pub const PISTOL_FORCE: f32 = 150.0;
pub const PISTOL_RANGE: i32 = 3;

/// What a man carries.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Arms {
    pub weapon: Weapon,
    /// A loaded pistol in the belt (one shot).
    pub pistol: bool,
}

impl Default for Arms {
    fn default() -> Arms {
        Arms { weapon: Weapon::Cutlass, pistol: false }
    }
}

/// A man's fighting, from tick to tick.
#[derive(Clone, Debug, Default)]
pub struct Fray {
    /// Seconds until he can strike again.
    pub cool: f32,
    /// Seconds he goes on seeking the enemy after being struck.
    pub provoked: f32,
    /// Seconds until he thinks again about where to go.
    pub think: f32,
    pub engaged: bool,
    pub broken: bool,
    /// Seconds in his present state (broken or not).
    pub since: f32,
    /// Who last hurt him, and whether his falling has been told.
    pub by: Option<String>,
    pub told: bool,
    pub blows: u32,
    pub hits: u32,
    /// Seconds of attention the men round him have taken (each blow on him adds; only so many can get at one man).
    pub swarm: f32,
    /// Called home by his captain: he walks to the rail and does not seek the enemy.
    pub recalled: bool,
    /// Turned out by the boarding bill: leaves his station to meet the boarders, anywhere on the weather deck.
    pub turned_out: bool,
}

/// His will to fight, 0..1: bravery and discipline, less pain, blood lost
/// and fatigue. (See the module notes: this is the stand-in for morale.)
pub fn will(bravery: f32, discipline: f32, c: &Creature) -> f32 {
    let base = 0.2 + 0.55 * bravery + 0.25 * discipline;
    let wounds = 0.09 * c.caps.pain.clamp(0.0, 8.0) + 0.9 * (1.0 - c.caps.blood).max(0.0);
    (base - wounds - 0.2 * c.needs.fatigue).clamp(0.0, 1.0)
}

/// How well his body and nerve let him use his skill, 0..1: fatigue, hurt
/// hands and legs, and fear (a man with little will fights worse).
pub fn condition(c: &Creature, will: f32) -> f32 {
    let body = (0.3 + 0.7 * c.caps.grasp.clamp(0.0, 1.0)) * (0.5 + 0.5 * c.caps.moving.clamp(0.0, 1.0)) * c.caps.conscious.clamp(0.0, 1.0).max(0.2);
    body * (1.0 - 0.5 * c.needs.fatigue) * (0.7 + 0.3 * (will / 0.6).min(1.0))
}

/// Chance the striker lands a blow, from the skills of both as worn by
/// condition. `bonus` is added for a defender who is not defending.
pub fn hit_chance(strike_skill: f32, strike_cond: f32, guard_skill: f32, guard_cond: f32, bonus: f32) -> f32 {
    (0.40 + 0.8 * (strike_skill * strike_cond - guard_skill * guard_cond) + bonus).clamp(0.06, 0.94)
}

struct Man {
    p: usize,
    id: ThingId,
    pos: Pos,
    faction: u16,
    player: bool,
}

/// Seconds between the quarter bill's looks at the boarders on deck.
pub const TURNOUT_EVERY: f32 = 3.0;

/// The boarding station bill (LIF-10, partial): with the enemy on her weather
/// deck, the bill turns out the tops, waisters and mates first, then men from
/// the guns (never the gun captains), to match the boarders two for every
/// one, less those already turned out. Returns how many were newly turned out.
pub fn turn_out(ship: &mut Ship, lines: &mut Vec<String>) -> usize {
    let (_, foes) = deck_strength(ship);
    if foes == 0 {
        return 0;
    }
    let out = ship.people.iter().filter(|p| p.fray.turned_out && ship.able(p) && !p.fray.broken).count();
    let want = (foes * 2).saturating_sub(out);
    if want == 0 {
        return 0;
    }
    let mut cand: Vec<(u32, usize)> = Vec::new();
    for (i, p) in ship.people.iter().enumerate() {
        if p.home.is_some() || p.crossed.is_some() || p.boarding || p.fray.turned_out || p.fray.broken || !ship.able(p) {
            continue;
        }
        let Some(c) = p.thing.and_then(|id| ship.craft.scene.life.get(id)) else { continue };
        if c.mind.control == Control::Player || c.mind.faction != ship.faction {
            continue;
        }
        let rank = match p.role {
            Role::Topman | Role::Waister | Role::BosunsMate | Role::Carpenter => 0,
            Role::Gunner => 1,
            _ => continue,
        };
        cand.push((rank, i));
    }
    cand.sort();
    let mut n = 0;
    for &(_, i) in cand.iter().take(want) {
        ship.people[i].fray.turned_out = true;
        ship.people[i].fray.think = 0.0;
        n += 1;
    }
    if n > 0 && out == 0 {
        lines.push(format!("The {}: boarders on deck! The bill turns out {n} hands from the guns and tops.", ship.name));
    }
    n
}

/// Men on her weather deck: (her own on their feet, the enemy's). The
/// measure of whether the deck is held.
pub fn deck_strength(ship: &Ship) -> (usize, usize) {
    let z = ship.layout.deck_z;
    let (mut own, mut foe) = (0, 0);
    for c in ship.craft.scene.life.creatures.iter().filter(|c| c.alive && !c.out) {
        if ship.craft.scene.things.get(c.thing).is_some_and(|t| t.pos().z == z) {
            if c.mind.faction == ship.faction {
                own += 1;
            } else {
                foe += 1;
            }
        }
    }
    (own, foe)
}

/// Are there men of another faction alive and on their feet aboard?
pub fn mixed(ship: &Ship) -> bool {
    ship.craft.scene.life.creatures.iter().any(|c| c.alive && !c.out && c.mind.faction != ship.faction)
}

fn occupied(ship: &Ship, p: Pos) -> bool {
    let s = &ship.craft.scene;
    s.things.at(p).any(|(id, _)| s.life.get(id).is_some_and(|c| c.alive))
}

fn free_tile(ship: &Ship, p: Pos) -> bool {
    let s = &ship.craft.scene;
    ship.craft.in_footprint(p.x, p.y) && s.world.standable(p) && !s.things.blocks_move(p) && !occupied(ship, p)
}

fn go(ship: &mut Ship, id: ThingId, at: Pos) {
    if let Some(c) = ship.craft.scene.life.get_mut(id) {
        if c.mind.control == Control::Player {
            return;
        }
        c.mind.routine = Routine::new().with(0.0, 24.0, Task::Stay { at });
        c.mind.next_plan = 0;
        c.mind.next_think = 0;
        c.mind.path.clear();
        c.mind.goal = Goal::Idle(0);
        c.mind.asleep = false;
    }
}

/// Back to what he was doing: a defender to his station, a boarder stands.
fn stand_down(ship: &mut Ship, p: usize) {
    let per = ship.people[p].clone();
    ship.people[p].fray.engaged = false;
    if per.fray.recalled {
        return;
    }
    let Some(id) = per.thing else { return };
    let Some(here) = ship.pos_of(&per) else { return };
    let at = if per.home.is_some() {
        here
    } else {
        match ship.station_of(&per, ship.orders.quarters) {
            Some(a) => a,
            None => here,
        }
    };
    go(ship, id, at);
}

/// No enemy on his feet aboard any more: everyone who was fighting stands down.
fn calm(ship: &mut Ship) {
    let busy: Vec<usize> = (0..ship.people.len()).filter(|&i| ship.people[i].fray.engaged || ship.people[i].fray.broken || ship.people[i].fray.turned_out).collect();
    for p in busy {
        ship.people[p].fray.broken = false;
        ship.people[p].fray.provoked = 0.0;
        ship.people[p].fray.turned_out = false;
        stand_down(ship, p);
    }
}

/// Say who has fallen: once for each man, when the life step has made him
/// dead or senseless after a blow.
fn tell_fallen(ship: &mut Ship, fleet: &[String], lines: &mut Vec<String>) {
    for p in 0..ship.people.len() {
        if ship.people[p].fray.by.is_none() || ship.people[p].crossed.is_some() {
            continue;
        }
        let Some(id) = ship.people[p].thing else { continue };
        let Some((alive, out)) = ship.craft.scene.life.get(id).map(|c| (c.alive, c.out)) else { continue };
        let per = &ship.people[p];
        if alive && !out {
            ship.people[p].fray.told = false;
            continue;
        }
        if per.fray.told {
            continue;
        }
        let home = per.home.and_then(|h| fleet.get(h).cloned()).unwrap_or_else(|| ship.name.clone());
        let by = per.fray.by.clone().unwrap_or_default();
        let who = format!("{} of the {}", per.name(), home);
        lines.push(if alive { format!("{who} goes down, hurt by {by}.") } else { format!("{who} is killed by {by}.") });
        ship.people[p].fray.told = true;
    }
}

/// One tick of fighting aboard `ship`. Says what happened in `lines`.
/// `fleet` is every ship's name by id, to say whose man is whose.
pub fn step(ship: &mut Ship, rng: &mut Rng, dt: f32, fleet: &[String], lines: &mut Vec<String>) {
    tell_fallen(ship, fleet, lines);
    // A ship that has struck is not fought for: arms are laid down.
    if ship.struck || !mixed(ship) {
        calm(ship);
        return;
    }
    ship.turnout_cool -= dt;
    if ship.turnout_cool <= 0.0 {
        ship.turnout_cool = TURNOUT_EVERY;
        turn_out(ship, lines);
    }
    let mut men: Vec<Man> = Vec::new();
    let mut at: HashMap<ThingId, usize> = HashMap::new();
    for (p, per) in ship.people.iter().enumerate() {
        if per.crossed.is_some() {
            continue;
        }
        let Some(id) = per.thing else { continue };
        let Some(c) = ship.craft.scene.life.get(id) else { continue };
        if !c.alive || c.out {
            continue;
        }
        let Some(t) = ship.craft.scene.things.get(id) else { continue };
        at.insert(id, men.len());
        men.push(Man { p, id, pos: t.pos(), faction: c.mind.faction, player: c.mind.control == Control::Player });
    }
    let n = men.len();
    if n == 0 {
        return;
    }
    let start = ship.craft.scene.clock.tick as usize % n;
    for off in 0..n {
        let k = (start + off) % n;
        let (p, id, pos, faction, player) = (men[k].p, men[k].id, men[k].pos, men[k].faction, men[k].player);
        // The man's own state.
        let (w, cond) = {
            let per = &ship.people[p];
            let Some(c) = ship.craft.scene.life.get(id) else { continue };
            let w = will(per.bravery, per.discipline, c);
            (w, condition(c, w))
        };
        {
            let f = &mut ship.people[p].fray;
            f.cool -= dt;
            f.provoked = (f.provoked - dt).max(0.0);
            f.think -= dt;
            f.swarm = (f.swarm - dt).max(0.0);
            f.since += dt;
        }
        // Nerve.
        let was_broken = ship.people[p].fray.broken;
        if !player {
            let f = &mut ship.people[p].fray;
            if !f.broken && w < BREAK {
                f.broken = true;
                f.since = 0.0;
            } else if f.broken && f.since >= MIN_BROKEN && w >= RALLY {
                f.broken = false;
                f.since = 0.0;
            }
        }
        let broken = ship.people[p].fray.broken;
        if broken && !was_broken {
            let per = &ship.people[p];
            let home = per.home.and_then(|h| fleet.get(h).cloned()).unwrap_or_else(|| ship.name.clone());
            lines.push(format!("{} of the {} loses heart and runs.", per.name(), home));
        }
        // The enemy about him.
        let mut near: Option<(i32, f32, usize)> = None; // (distance, condition of the foe, man)
        for (j, o) in men.iter().enumerate() {
            if o.faction == faction || o.pos.z != pos.z {
                continue;
            }
            let d = pos.dist2d(o.pos);
            if d > SEEK + 4 {
                continue;
            }
            let oc = ship.craft.scene.life.get(o.id).map_or(1.0, |c| c.caps.blood);
            if near.map_or(true, |(bd, bc, _)| d < bd || (d == bd && oc < bc)) {
                near = Some((d, oc, j));
            }
        }
        let Some((dist, _, foe)) = near else {
            // Turned out from below: go up and across the deck to the nearest boarder.
            if ship.people[p].fray.turned_out && !broken && !player {
                if ship.people[p].fray.think <= 0.0 {
                    ship.people[p].fray.think = 2.5;
                    let z = ship.layout.deck_z;
                    let reach = ship.people[p].arms.weapon.reach();
                    let goal = men.iter().filter(|o| o.faction != faction && o.pos.z == z).min_by_key(|o| o.pos.dist2d(pos)).map(|o| o.pos);
                    if let Some(to) = goal.and_then(|g| approach_tile(ship, pos, g, reach)) {
                        go(ship, id, to);
                        ship.people[p].fray.engaged = true;
                    }
                }
                continue;
            }
            if ship.people[p].fray.engaged {
                stand_down(ship, p);
            }
            continue;
        };
        let weapon = ship.people[p].arms.weapon;
        let reach = weapon.reach();
        // Running (a man called home keeps walking to the rail instead).
        if broken && !player && !ship.people[p].fray.recalled {
            if ship.people[p].fray.think <= 0.0 {
                ship.people[p].fray.think = 1.5;
                if let Some(to) = flee_tile(ship, &men, k) {
                    go(ship, id, to);
                    ship.people[p].fray.engaged = false;
                    continue;
                }
                // Cornered: he fights on, as a man will.
            } else {
                // Still running to the place he chose.
                continue;
            }
        }
        if broken && ship.people[p].fray.recalled {
            continue;
        }
        // Who he can get at: the nearest foe in reach who is not already
        // beset by others (only so many blades can reach one man).
        let pistol_ready = ship.people[p].arms.pistol;
        let mut target: Option<(i32, usize)> = None;
        for (j, o) in men.iter().enumerate() {
            if o.faction == faction || o.pos.z != pos.z || ship.people[o.p].fray.swarm > SWARM {
                continue;
            }
            let d = pos.dist2d(o.pos);
            if (d <= reach || (pistol_ready && d <= PISTOL_RANGE)) && target.map_or(true, |(bd, _)| d < bd) {
                target = Some((d, j));
            }
        }
        if let Some((tdist, tfoe)) = target {
            if !ship.people[p].fray.engaged {
                // Closing with the enemy: a moment to find his man before the first blow.
                ship.people[p].fray.engaged = true;
                ship.people[p].fray.cool = ship.people[p].fray.cool.max(0.0) + 0.9 * rng.f32() * weapon.interval();
            }
            if ship.people[p].fray.cool <= 0.0 {
                let foe_p = men[tfoe].p;
                ship.people[foe_p].fray.swarm += SWARM_PER_BLOW;
                if pistol_ready && tdist <= PISTOL_RANGE {
                    shoot(ship, rng, p, foe_p, tdist, cond, lines, fleet);
                    ship.people[p].fray.cool = 1.2;
                } else {
                    swing(ship, rng, p, foe_p, tdist, cond, lines, fleet);
                    let slow = 1.0 + 0.9 * ship.craft.scene.life.get(id).map_or(0.0, |c| c.needs.fatigue);
                    let grasp = ship.craft.scene.life.get(id).map_or(1.0, |c| c.caps.grasp.clamp(0.0, 1.0));
                    ship.people[p].fray.cool = weapon.interval() * slow / (0.4 + 0.6 * grasp) * (0.85 + 0.3 * rng.f32());
                }
            }
            continue;
        }
        if dist <= reach {
            ship.people[p].fray.engaged = true;
            continue;
        }
        // Going to meet him?
        let role = ship.people[p].role;
        let seeker = ship.people[p].fray.turned_out || matches!(role, Role::Marine | Role::Topman | Role::Waister | Role::BosunsMate | Role::Carpenter | Role::Lieutenant | Role::Midshipman | Role::Captain);
        if (seeker || ship.people[p].fray.provoked > 0.0) && dist <= SEEK && !player && !ship.people[p].fray.recalled && ship.people[p].fray.think <= 0.0 {
            ship.people[p].fray.think = 2.0;
            ship.people[p].fray.engaged = true;
            let foe_pos = men[foe].pos;
            if let Some(to) = approach_tile(ship, pos, foe_pos, reach) {
                go(ship, id, to);
            }
        }
    }
}

/// A free place from which `from` can strike at `foe`, the nearest to him.
fn approach_tile(ship: &Ship, from: Pos, foe: Pos, reach: i32) -> Option<Pos> {
    let mut best: Option<(i32, Pos)> = None;
    for dy in -reach..=reach {
        for dx in -reach..=reach {
            if dx == 0 && dy == 0 {
                continue;
            }
            let q = Pos::new(foe.x + dx, foe.y + dy, foe.z);
            if !free_tile(ship, q) {
                continue;
            }
            let d = q.dist2d(from);
            if best.map_or(true, |(bd, _)| d < bd) {
                best = Some((d, q));
            }
        }
    }
    best.map(|b| b.1)
}

/// Somewhere farther from the enemy than he stands, on his own deck.
fn flee_tile(ship: &Ship, men: &[Man], k: usize) -> Option<Pos> {
    let me = &men[k];
    let foes: Vec<Pos> = men.iter().filter(|o| o.faction != me.faction && o.pos.z == me.pos.z && o.pos.dist2d(me.pos) <= 16).map(|o| o.pos).collect();
    if foes.is_empty() {
        return None;
    }
    let gap = |q: Pos| foes.iter().map(|f| q.dist2d(*f)).min().unwrap_or(99);
    let here = gap(me.pos);
    let mut best: Option<(f32, Pos)> = None;
    for dy in -8..=8 {
        for dx in -8..=8 {
            let q = Pos::new(me.pos.x + dx, me.pos.y + dy, me.pos.z);
            if !free_tile(ship, q) {
                continue;
            }
            let score = gap(q) as f32 - 0.25 * q.dist2d(me.pos) as f32;
            if gap(q) > here + 1 && best.map_or(true, |(b, _)| score > b) {
                best = Some((score, q));
            }
        }
    }
    best.map(|b| b.1)
}

fn tire(ship: &mut Ship, p: usize, by: f32) {
    if let Some(c) = ship.people[p].thing.and_then(|id| ship.craft.scene.life.get_mut(id)) {
        c.needs.fatigue = (c.needs.fatigue + by).min(1.0);
    }
}

fn state_of(ship: &Ship, p: usize) -> (f32, bool) {
    let per = &ship.people[p];
    match per.thing.and_then(|id| ship.craft.scene.life.get(id)) {
        Some(c) => {
            let w = will(per.bravery, per.discipline, c);
            (condition(c, w), per.fray.broken)
        }
        None => (1.0, false),
    }
}

fn describe(ship: &Ship, p: usize, fleet: &[String]) -> String {
    let per = &ship.people[p];
    format!("{} of the {}", per.name(), per.home.and_then(|h| fleet.get(h).cloned()).unwrap_or_else(|| ship.name.clone()))
}

/// The hurt a blow did, told in the log if it is a bad one and to the
/// ship's people otherwise.
fn tell_hit(ship: &mut Ship, lines: &mut Vec<String>, a: &str, verb: &str, d: usize, what: &str) {
    let victim = ship.people[d].name();
    let text = format!("{a} {verb} {victim}: {what}.");
    if what.contains("carried away") || what.starts_with("through") || what.contains("badly") {
        lines.push(text);
    } else {
        ship.notes.push(Note { text, urgent: false });
    }
}

fn hurt(ship: &mut Ship, rng: &mut Rng, a: usize, d: usize, kind: DamageKind, force: f32, verb: &str, fleet: &[String], lines: &mut Vec<String>) -> bool {
    let Some(did) = ship.people[d].thing else { return false };
    let Some(what) = wound(ship, did, kind, force, rng) else { return false };
    let by = describe(ship, a, fleet);
    ship.people[d].fray.by = Some(ship.people[a].name());
    ship.people[d].fray.told = false;
    ship.people[d].fray.provoked = 8.0;
    ship.people[a].fray.hits += 1;
    tell_hit(ship, lines, &by, verb, d, &what);
    true
}

/// A cutlass cut, a pike thrust, a bayonet, a cuff.
#[allow(clippy::too_many_arguments)]
fn swing(ship: &mut Ship, rng: &mut Rng, a: usize, d: usize, dist: i32, a_cond: f32, lines: &mut Vec<String>, fleet: &[String]) {
    let weapon = ship.people[a].arms.weapon;
    let (d_cond, d_broken) = state_of(ship, d);
    let sa = ship.people[a].skill("melee");
    let sd = ship.people[d].skill("melee");
    // A pike is clumsy at arm's length; a man running or down is not guarding.
    let mut bonus = if d_broken { 0.15 } else { 0.0 };
    if weapon == Weapon::Pike && dist <= 1 {
        bonus -= 0.12;
    }
    let guard = if d_broken { 0.5 * sd } else { sd };
    let chance = hit_chance(sa, a_cond, guard, d_cond, bonus);
    ship.people[a].fray.blows += 1;
    crew::practise(&mut ship.people[a], "melee", 1.0);
    tire(ship, a, TIRE_SWING);
    tire(ship, d, TIRE_PARRY);
    ship.people[d].fray.provoked = ship.people[d].fray.provoked.max(8.0);
    if !rng.chance(chance) {
        return;
    }
    let strength = ship.people[a].thing.and_then(|id| ship.craft.scene.life.get(id)).map_or(1.0, |c| c.caps.grasp.clamp(0.3, 1.0));
    let force = weapon.force() * (0.7 + 0.3 * strength) * (0.85 + 0.3 * rng.f32()) * (0.8 + 0.4 * sa);
    hurt(ship, rng, a, d, weapon.kind(), force, weapon.verb(), fleet, lines);
}

/// A pistol ball at close quarters. The pistol is spent either way.
#[allow(clippy::too_many_arguments)]
fn shoot(ship: &mut Ship, rng: &mut Rng, a: usize, d: usize, dist: i32, a_cond: f32, lines: &mut Vec<String>, fleet: &[String]) {
    ship.people[a].arms.pistol = false;
    ship.people[a].fray.blows += 1;
    crew::practise(&mut ship.people[a], "musketry", 1.0);
    let sk = ship.people[a].skill("musketry") * a_cond;
    let chance = (0.40 + 0.5 * sk - 0.08 * (dist - 1) as f32).clamp(0.08, 0.9);
    ship.people[d].fray.provoked = ship.people[d].fray.provoked.max(8.0);
    if !rng.chance(chance) {
        return;
    }
    let force = PISTOL_FORCE * (0.8 + 0.4 * rng.f32());
    hurt(ship, rng, a, d, DamageKind::Point, force, "shoots", fleet, lines);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn creature(blood: f32, pain: f32, fatigue: f32) -> Creature {
        let mut s = Ship::new(0, &crate::data::load_all()[0], &tachyon::lang::Culture::new(5), 0, 1000.0, 1000.0, 0.0, 9, 10, false);
        let id = s.people.iter().find_map(|p| p.thing).unwrap();
        let mut c = s.craft.scene.life.get_mut(id).unwrap().clone();
        c.caps.blood = blood;
        c.caps.pain = pain;
        c.needs.fatigue = fatigue;
        c
    }

    #[test]
    fn will_falls_with_wounds_and_rises_with_bravery() {
        let whole = creature(1.0, 0.0, 0.1);
        let hurt = creature(0.8, 2.0, 0.1);
        assert!(will(0.5, 0.5, &whole) > will(0.5, 0.5, &hurt));
        assert!(will(0.9, 0.5, &whole) > will(0.2, 0.5, &whole));
        assert!(will(0.5, 0.5, &hurt) < BREAK, "an ordinary man with two bad wounds loses heart");
        assert!(will(0.9, 0.7, &hurt) > BREAK, "a brave steady one does not");
    }

    #[test]
    fn chance_follows_skill_and_condition() {
        assert!(hit_chance(0.8, 1.0, 0.1, 1.0, 0.0) > hit_chance(0.4, 1.0, 0.4, 1.0, 0.0));
        assert!(hit_chance(0.5, 1.0, 0.5, 1.0, 0.0) > hit_chance(0.5, 0.5, 0.5, 1.0, 0.0), "tired or afraid, he strikes worse");
        let c = creature(1.0, 0.0, 0.0);
        assert!(condition(&c, 0.9) > condition(&c, 0.1), "fear costs skill");
        let tired = creature(1.0, 0.0, 0.9);
        assert!(condition(&c, 0.6) > condition(&tired, 0.6));
    }
}
