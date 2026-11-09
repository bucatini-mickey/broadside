//! "Boarders away": with two ships fouled, the quarter bill tells off the
//! best fighters and the marines. They walk to the rail as creatures; the
//! marines fire musketry across the gap; then the men cross one after
//! another and appear on the other ship's deck. Each carries a record of his
//! home ship (`Person::home`), so he can be called back or be known as
//! foreign; on his own roll his place is kept (`Person::crossed`).
//!
//! The fighting itself is `melee`. Not yet: the defenders turning out
//! (BRD-07): they meet the boarders as they come, man by man.
//!
//! Engine-general (for Tachyon, not built): moving a creature, with its body,
//! needs and wounds, from one scene to another (here done by hand in
//! [`cross`]).

use crate::crew::{self, Person};
use crate::foul::Foul;
use crate::game::wound;
use crate::ship::{Note, Ship};
use tachyon::life::mind::{Goal, Routine, Task};
use tachyon::prelude::*;

/// Seconds the marines fire from the rails before the crossing begins.
pub const MUSKET_SECS: f64 = 14.0;
/// Seconds between one man stepping across and the next.
pub const CROSS_GAP: f32 = 0.8;
/// Seconds after the order before the party goes with whoever has reached the rail.
pub const PATIENCE: f64 = 40.0;
/// Seconds fouled before an AI captain with the numbers sends his boarders.
pub const AI_RESOLVE: f64 = 8.0;

/// How many the bill tells off from a ship's able hands.
pub fn party_size(able: usize) -> usize {
    (able / 4).clamp(4, 24)
}

/// One ship's boarding party at a foul.
#[derive(Clone, Debug)]
pub struct Party {
    /// Places in her `people`, best first.
    pub men: Vec<usize>,
    pub since: f64,
    /// When the crossing may begin (set once enough are at the rail).
    pub go_at: Option<f64>,
    pub clock: f32,
    /// Seconds until each man (as `men`) has his musket loaded.
    pub reload: Vec<f32>,
    pub crossed: usize,
    pub volleys: u32,
    pub hits: u32,
    pub recalling: bool,
}

fn two(ships: &mut [Ship], i: usize, j: usize) -> (&mut Ship, &mut Ship) {
    if i < j {
        let (l, r) = ships.split_at_mut(j);
        (&mut l[i], &mut r[0])
    } else {
        let (l, r) = ships.split_at_mut(i);
        (&mut r[0], &mut l[j])
    }
}

fn at_rail(s: &Ship, p: &Person, rail: Pos) -> bool {
    s.pos_of(p).is_some_and(|q| q.z == rail.z && q.dist2d(rail) <= 2)
}

/// A free standing place on the weather deck near `rail`.
pub fn landing(s: &Ship, rail: Pos) -> Option<Pos> {
    let mut best: Option<(i32, Pos)> = None;
    for dy in -3..=3 {
        for dx in -3..=3 {
            let p = Pos::new(rail.x + dx, rail.y + dy, rail.z);
            if !s.craft.in_footprint(p.x, p.y) || !s.craft.scene.world.standable(p) || s.craft.scene.things.blocks_move(p) {
                continue;
            }
            if s.craft.scene.things.at(p).any(|(id, _)| s.craft.scene.life.get(id).is_some()) {
                continue;
            }
            let d = dx * dx + dy * dy;
            if best.map_or(true, |(bd, _)| d < bd) {
                best = Some((d, p));
            }
        }
    }
    best.map(|b| b.1)
}

/// Carry man `i` of `src` across to `dst`, setting him down at `at`. He
/// keeps his body, wounds and fatigue. If he is one of `dst`'s own come home
/// he takes his old place on her roll; otherwise he is added to it, with
/// `home` the ship he belongs to. His place on `src`'s roll stays, marked
/// `crossed`. Returns his place on `dst`'s roll.
pub fn cross(src: &mut Ship, i: usize, dst: &mut Ship, at: Pos) -> Option<usize> {
    let id = src.people[i].thing?;
    let (body, needs, caps) = {
        let c = src.craft.scene.life.get(id)?;
        if !c.alive {
            return None;
        }
        (c.body.clone(), c.needs.clone(), c.caps)
    };
    let mut p = src.people[i].clone();
    p.boarding = false;
    p.fray.recalled = false;
    p.fray.engaged = false;
    p.crossed = None;
    p.gun = None;
    let returning = p.home == Some(dst.id);
    if returning {
        p.home = None;
    } else if p.home.is_none() {
        p.home = Some(src.id);
    }
    let slot = if returning {
        dst.people.iter().position(|q| q.crossed == Some(src.id) && q.given == p.given && q.family == p.family && q.age == p.age)
    } else {
        None
    };
    let faction = src.faction;
    crew::embark(&mut dst.craft.scene, &dst.crew_kinds, &mut p, at, Control::Ai, faction);
    if let Some(c) = p.thing.and_then(|t| dst.craft.scene.life.get_mut(t)) {
        c.body = body;
        c.needs = needs;
        c.caps = caps;
        c.mind.routine = Routine::new().with(0.0, 24.0, Task::Stay { at });
        c.mind.next_plan = 0;
        c.mind.next_think = 0;
        c.mind.path.clear();
        c.mind.goal = Goal::Idle(0);
        c.mind.asleep = false;
    }
    src.craft.scene.things.despawn(id);
    src.people[i].thing = None;
    src.people[i].crossed = Some(dst.id);
    src.people[i].boarding = false;
    Some(match slot {
        Some(j) => {
            dst.people[j] = p;
            j
        }
        None => {
            dst.people.push(p);
            dst.people.len() - 1
        }
    })
}

/// Men of `host` who belong to ship `home` (id) and can still walk.
pub fn foreigners(host: &Ship, home: usize) -> Vec<usize> {
    (0..host.people.len()).filter(|&i| host.people[i].home == Some(home) && host.able(&host.people[i])).collect()
}

/// One tick of both ships' boarding at a foul. Says what happened in `lines`.
pub fn step(ships: &mut [Ship], f: &mut Foul, time: f64, dt: f32, lines: &mut Vec<String>) {
    for side in 0..2 {
        let (mi, oi) = if side == 0 { (f.a, f.b) } else { (f.b, f.a) };
        let (my_rail, their_rail) = (f.rails[side], f.rails[1 - side]);
        let (me, other) = two(ships, mi, oi);
        if me.struck && f.party[side].is_none() {
            me.orders.boarders_away = false;
        }
        // The order, given.
        if me.orders.boarders_away && f.party[side].is_none() {
            let able = me.people.iter().filter(|p| me.able(p)).count();
            let men = crew::boarding_party(&me.people, &|i| me.able(&me.people[i]) && me.people[i].thing.is_some(), party_size(able));
            if men.is_empty() {
                me.orders.boarders_away = false;
            } else {
                for &i in &men {
                    me.people[i].boarding = true;
                }
                me.send_to(&men, my_rail);
                lines.push(format!("The {}: boarders away! {} hands go to the rail, marines with muskets.", me.name, men.len()));
                f.party[side] = Some(Party { reload: vec![-1.0; men.len()], men, since: time, go_at: None, clock: 0.0, crossed: 0, volleys: 0, hits: 0, recalling: false });
            }
        }
        let Some(mut party) = f.party[side].take() else { continue };
        // The order, belayed.
        if !me.orders.boarders_away && !party.recalling {
            if party.crossed == 0 {
                for &i in &party.men {
                    me.people[i].boarding = false;
                }
                me.assign(me.orders.quarters);
                lines.push(format!("The {}: belay boarding.", me.name));
                continue;
            }
            party.recalling = true;
            let back = foreigners(other, me.id);
            other.send_to(&back, their_rail);
            lines.push(format!("The {}: boarders, back aboard!", me.name));
        }
        if party.recalling {
            // Our men on her deck walk to her rail and come back over it.
            party.clock -= dt;
            let back = foreigners(other, me.id);
            for &j in &back {
                other.people[j].fray.recalled = true;
            }
            if back.is_empty() {
                for &i in &party.men {
                    me.people[i].boarding = false;
                }
                lines.push(format!("The {}'s boarders are home.", me.name));
                continue;
            }
            if party.clock <= 0.0 {
                let ready = back.iter().copied().find(|&j| at_rail(other, &other.people[j], their_rail));
                if let (Some(j), Some(at)) = (ready, landing(me, my_rail)) {
                    cross(other, j, me, at);
                    party.clock = CROSS_GAP;
                }
            }
            f.party[side] = Some(party);
            continue;
        }
        // Marines at the rail fire across the gap.
        let mut here = 0usize;
        let live = party.men.iter().filter(|&&i| me.people[i].crossed.is_none() && me.able(&me.people[i])).count();
        let mut marines_there = false;
        let mut marines_there_n = 0usize;
        let marines_live = party.men.iter().filter(|&&i| me.people[i].crossed.is_none() && me.able(&me.people[i]) && me.people[i].role == crew::Role::Marine).count();
        for (k, &i) in party.men.iter().enumerate() {
            let p = me.people[i].clone();
            if p.crossed.is_some() || !me.able(&p) || !at_rail(me, &p, my_rail) {
                continue;
            }
            here += 1;
            if p.role != crew::Role::Marine {
                continue;
            }
            marines_there = true;
            marines_there_n += 1;
            if party.reload[k] < 0.0 {
                // Just arrived: prime and load.
                party.reload[k] = 3.0 + 4.0 * me.rng.f32();
                continue;
            }
            party.reload[k] -= dt;
            if party.reload[k] > 0.0 {
                continue;
            }
            // Fire at the nearest of her men on her weather deck.
            let mut near: Vec<(i32, usize)> = (0..other.people.len())
                .filter(|&j| other.able(&other.people[j]))
                .filter_map(|j| other.pos_of(&other.people[j]).filter(|q| q.z == their_rail.z).map(|q| (q.dist2d(their_rail), j)))
                .collect();
            near.sort();
            let pool = near.len().min(3);
            party.reload[k] = 20.0 - 8.0 * p.skill("musketry") + 4.0 * me.rng.f32();
            if pool == 0 {
                continue;
            }
            let j = near[(me.rng.f32() * pool as f32) as usize % pool].1;
            party.volleys += 1;
            if me.rng.chance((0.15 + 0.55 * p.skill("musketry")).clamp(0.1, 0.8)) {
                if let Some(id) = other.people[j].thing {
                    let force = 90.0 + 90.0 * me.rng.f32();
                    if let Some(what) = wound(other, id, DamageKind::Point, force, &mut me.rng) {
                        party.hits += 1;
                        let who = other.craft.scene.life.name(&other.craft.scene.things, id);
                        other.notes.push(Note { text: format!("{who} is shot by a musket from the {}: {what}.", me.name), urgent: false });
                        lines.push(format!("{} of the {} shoots {who} of the {}: {what}.", p.name(), me.name, other.name));
                    }
                }
            }
            crew::practise(&mut me.people[i], "musketry", 1.0);
        }
        // When enough are at the rail, the marines have their say, then the crossing.
        if party.go_at.is_none() && live > 0 {
            if (here * 2 >= live && marines_there_n >= marines_live) || (time - party.since >= PATIENCE && here > 0) {
                party.go_at = Some(time + if marines_there { MUSKET_SECS } else { 0.0 });
                if marines_there {
                    lines.push(format!("Marines of the {} open musketry from the rail.", me.name));
                }
            }
        }
        if party.go_at.is_some_and(|g| time >= g) {
            party.clock -= dt;
            if party.clock <= 0.0 {
                let ready = party.men.iter().copied().find(|&i| me.people[i].crossed.is_none() && me.able(&me.people[i]) && at_rail(me, &me.people[i], my_rail));
                if let (Some(i), Some(at)) = (ready, landing(other, their_rail)) {
                    if cross(me, i, other, at).is_some() {
                        if party.crossed == 0 {
                            lines.push(format!("Boarders of the {} cross to the {}!", me.name, other.name));
                        }
                        party.crossed += 1;
                        party.clock = CROSS_GAP;
                    }
                }
            }
        }
        // All across (or fallen): the party is done; the order stands until belayed.
        let waiting = party.men.iter().any(|&i| me.people[i].crossed.is_none() && me.able(&me.people[i]));
        if !waiting {
            for &i in &party.men {
                me.people[i].boarding = false;
            }
            if party.crossed > 0 && party.go_at.is_some() {
                // Keep the record so a recall knows there is someone to call.
                party.men.clear();
                party.reload.clear();
            }
        }
        f.party[side] = Some(party);
    }
}
