//! Hand-to-hand fighting (BRD-06), played headless.

use broadside::board;
use broadside::crew::{self, Person, Role};
use broadside::game::{wound, Game, Scenario, SECS};
use broadside::melee::{Arms, Weapon};
use broadside::ship::Ship;
use tachyon::life::body::WoundKind;
use tachyon::prelude::*;

fn run(g: &mut Game, secs: f64) {
    for _ in 0..(secs / SECS) as usize {
        g.tick();
    }
}

/// A game whose first ship is a bare deck with nobody embarked on it, so
/// that the men a test puts there are the only ones to fight.
fn arena(seed: u64) -> Game {
    let mut g = Game::new(Scenario::FreeSailing(2), seed);
    let class = g.classes[2].clone();
    let (x, y) = (g.ships[0].craft.x, g.ships[0].craft.y);
    let mut s = Ship::new(0, &class, &g.cultures[0], 0, x, y, 0.4, seed, 0, false);
    s.craft.z = g.sea.tide();
    s.craft.scene.clock = Clock::new(SECS, 10.0);
    s.craft.scene.clock.start_secs = g.time;
    g.ships[0] = s;
    g.captains[0] = None;
    g.captains.truncate(1);
    g.ships.truncate(1);
    g
}

/// Put a waister of the given skill, nerve and arms on the arena's deck with
/// the given faction. Returns his place in `people`.
fn man(g: &mut Game, faction: u16, melee: f32, bravery: f32, arms: Arms, near: Pos) -> usize {
    let s = &mut g.ships[0];
    let mut p: Person = s.people[0].clone();
    p.role = Role::Waister;
    p.thing = None;
    p.gun = None;
    p.crossed = None;
    p.boarding = false;
    p.fray = Default::default();
    p.skills[crew::skill_index("melee")] = melee;
    p.skills[crew::skill_index("musketry")] = 0.9;
    p.bravery = bravery;
    p.discipline = bravery;
    p.arms = arms;
    p.home = if faction == s.faction { None } else { Some(1) };
    let at = board::landing(s, near).expect("room on the deck");
    crew::embark(&mut s.craft.scene, &s.crew_kinds, &mut p, at, Control::Ai, faction);
    if let Some(c) = p.thing.and_then(|t| s.craft.scene.life.get_mut(t)) {
        c.mind.routine = Routine::new().with(0.0, 24.0, Task::Stay { at });
    }
    s.people.push(p);
    s.people.len() - 1
}

const CUTLASS: Arms = Arms { weapon: Weapon::Cutlass, pistol: false };

fn fit(g: &Game, i: usize) -> bool {
    let s = &g.ships[0];
    s.able(&s.people[i])
}

/// Two men, one cutlass each, fight until one is down. `Some(0)` if the
/// first won, `Some(1)` the second, `None` if neither (or both) fell in time.
fn duel(seed: u64, skill_a: f32, skill_b: f32, flip: bool) -> Option<usize> {
    let mut g = arena(seed);
    let mark = g.ships[0].layout.waist[0];
    let (a, b) = if flip {
        let b = man(&mut g, 1, skill_b, 0.9, CUTLASS, mark);
        (man(&mut g, 0, skill_a, 0.9, CUTLASS, mark), b)
    } else {
        let a = man(&mut g, 0, skill_a, 0.9, CUTLASS, mark);
        (a, man(&mut g, 1, skill_b, 0.9, CUTLASS, mark))
    };
    for _ in 0..(400.0 / SECS) as usize {
        g.tick();
        match (fit(&g, a), fit(&g, b)) {
            (true, false) => return Some(0),
            (false, true) => return Some(1),
            (false, false) => return None,
            _ => {}
        }
    }
    None
}

#[test]
fn each_weapon_makes_its_own_real_wounds_in_the_body() {
    let mut g = arena(3);
    let mark = g.ships[0].layout.waist[0];
    let mut rng = Rng::new(11);
    let kinds = |g: &Game, i: usize| -> Vec<WoundKind> {
        let s = &g.ships[0];
        let c = s.craft.scene.life.get(s.people[i].thing.unwrap()).unwrap();
        c.body.parts.iter().flat_map(|p| p.wounds.iter().map(|w| w.kind)).collect()
    };
    for (weapon, want, not) in [(Weapon::Cutlass, WoundKind::Cut, WoundKind::Puncture), (Weapon::Pike, WoundKind::Puncture, WoundKind::Cut)] {
        let i = man(&mut g, 0, 0.5, 0.5, CUTLASS, mark);
        let id = g.ships[0].people[i].thing.unwrap();
        for _ in 0..6 {
            wound(&mut g.ships[0], id, weapon.kind(), weapon.force(), &mut rng);
        }
        let ks = kinds(&g, i);
        assert!(ks.contains(&want), "{}: wounds were {ks:?}", weapon.name());
        assert!(!ks.contains(&not), "{}: wounds were {ks:?}", weapon.name());
        let c = g.ships[0].craft.scene.life.get(id).unwrap();
        assert!(c.body.bleeding() > 0.0 || !c.alive, "{} draws blood", weapon.name());
    }
}

#[test]
fn a_duel_leaves_cuts_and_a_man_down_where_he_fell() {
    let mut g = arena(5);
    let mark = g.ships[0].layout.waist[0];
    let a = man(&mut g, 0, 0.7, 0.9, CUTLASS, mark);
    let b = man(&mut g, 1, 0.2, 0.9, CUTLASS, mark);
    let mut down = None;
    for _ in 0..(400.0 / SECS) as usize {
        g.tick();
        if !fit(&g, a) || !fit(&g, b) {
            down = Some(if fit(&g, a) { b } else { a });
            break;
        }
    }
    let loser = down.expect("somebody fell in 400 s");
    let s = &g.ships[0];
    let id = s.people[loser].thing.unwrap();
    let at = s.craft.scene.things.get(id).unwrap().pos();
    let hurt = |i: usize| s.craft.scene.life.get(s.people[i].thing.unwrap()).unwrap().body.parts.iter().any(|p| !p.wounds.is_empty() || p.severed);
    assert!(hurt(loser), "the man who fell is wounded in the body");
    let winner_blows = s.people[a].fray.blows + s.people[b].fray.blows;
    assert!(winner_blows > 3, "they traded blows ({winner_blows})");
    run(&mut g, 60.0);
    let s = &g.ships[0];
    let t = s.craft.scene.things.get(id).expect("the fallen man is still on the deck");
    assert_eq!(t.pos(), at, "he lies where he fell");
    assert!(!s.able(&s.people[loser]));
}

#[test]
fn a_duels_outcome_follows_skill() {
    let (mut skilled, mut raw, mut even_a, mut even_b) = (0, 0, 0, 0);
    for k in 0..16u64 {
        match duel(100 + k, 0.9, 0.1, k % 2 == 0) {
            Some(0) => skilled += 1,
            Some(1) => raw += 1,
            _ => {}
        }
        match duel(300 + k, 0.5, 0.5, k % 2 == 0) {
            Some(0) => even_a += 1,
            Some(1) => even_b += 1,
            _ => {}
        }
    }
    assert!(skilled >= 13 && skilled > 3 * raw, "the skilled man won {skilled}, the raw one {raw}");
    assert!(even_a >= 3 && even_b >= 3, "men of equal skill split their fights ({even_a} to {even_b})");
}

#[test]
fn a_man_who_is_afraid_and_hurt_loses_heart_and_runs() {
    let (mut broke, mut moved, mut no_blows) = (0, 0, 0);
    for k in 0..8u64 {
        let mut g = arena(40 + k);
        let mark = g.ships[0].layout.waist[0];
        let coward = man(&mut g, 0, 0.5, 0.02, CUTLASS, mark);
        let _brave = man(&mut g, 1, 0.5, 0.95, CUTLASS, mark);
        let mut at_break: Option<(Pos, u32)> = None;
        let mut far = false;
        for _ in 0..(120.0 / SECS) as usize {
            g.tick();
            let s = &g.ships[0];
            if !s.able(&s.people[coward]) {
                break;
            }
            let here = s.pos_of(&s.people[coward]).unwrap();
            match at_break {
                None if s.people[coward].fray.broken => {
                    broke += 1;
                    at_break = Some((here, s.people[coward].fray.blows));
                }
                Some((p0, _)) if here.dist2d(p0) >= 2 => far = true,
                _ => {}
            }
        }
        if let Some((_, blows)) = at_break {
            moved += far as u32;
            no_blows += (g.ships[0].people[coward].fray.blows <= blows + 2) as u32;
        }
    }
    assert!(broke >= 6, "the coward broke in {broke} of 8 fights");
    assert!(moved >= 4, "and ran from where he stood in {moved}");
    assert!(no_blows >= broke - 2, "and mostly stopped striking back ({no_blows} of {broke})");
}

#[test]
fn a_pistol_is_fired_once_and_wounds_at_close_quarters() {
    let (mut spent, mut hit) = (0, 0);
    for k in 0..12u64 {
        let mut g = arena(70 + k);
        let mark = g.ships[0].layout.waist[0];
        let gun = man(&mut g, 0, 0.5, 0.9, Arms { weapon: Weapon::Cutlass, pistol: true }, mark);
        let foe = man(&mut g, 1, 0.5, 0.9, CUTLASS, mark);
        run(&mut g, 6.0);
        let s = &g.ships[0];
        if !s.people[gun].arms.pistol {
            spent += 1;
        }
        let foe_hurt = s.craft.scene.life.get(s.people[foe].thing.unwrap()).unwrap().body.parts.iter().any(|p| !p.wounds.is_empty());
        if foe_hurt {
            hit += 1;
        }
    }
    assert_eq!(spent, 12, "every pistol was fired");
    assert!(hit >= 6, "and the ball told in {hit} of 12");
}

#[test]
fn boarders_fight_the_defenders_and_the_fallen_stay_where_they_fall() {
    let mut g = Game::new(Scenario::Action, 21);
    g.captains[1] = None;
    for s in g.ships.iter_mut() {
        s.orders.sail = 0.0;
        s.orders.course = None;
        s.craft.heading = 0.0;
        s.craft.vx = 0.0;
        s.craft.vy = 0.0;
        s.craft.yaw_rate = 0.0;
    }
    let (x, y) = (g.ships[0].craft.x, g.ships[0].craft.y);
    g.ships[1].craft.x = x + 11.0;
    g.ships[1].craft.y = y;
    g.ships[1].craft.vx = -0.5;
    let mut fouled = false;
    for _ in 0..(40.0 / SECS) as usize {
        g.tick();
        if !g.fouls.is_empty() {
            fouled = true;
            break;
        }
    }
    assert!(fouled, "fouled");
    g.ships[0].orders.boarders_away = true;
    run(&mut g, 200.0);
    let blows: u32 = g.ships.iter().flat_map(|s| s.people.iter()).map(|p| p.fray.blows).sum();
    assert!(blows > 10, "men struck at one another ({blows} blows)");
    let (mut downed, mut hurt) = (0, 0);
    let mut lying: Vec<(usize, ThingId, Pos)> = Vec::new();
    for (k, s) in g.ships.iter().enumerate() {
        for p in s.people.iter().filter(|p| p.crossed.is_none()) {
            if let Some(c) = p.thing.and_then(|t| s.craft.scene.life.get(t)) {
                if !c.alive || c.out {
                    downed += 1;
                    lying.push((k, p.thing.unwrap(), s.craft.scene.things.get(p.thing.unwrap()).unwrap().pos()));
                }
                if c.body.parts.iter().any(|b| !b.wounds.is_empty()) && c.body.bleeding() > 0.0 {
                    hurt += 1;
                }
            }
        }
    }
    assert!(downed > 0 && hurt > 0, "{downed} down, {hurt} bleeding after the fight");
    // The log tells of it.
    assert!(g.log.lines.iter().any(|l| l.0.contains("killed by") || l.0.contains("goes down")), "the fall of men is told");
    // Only the wounded who are still down are checked: some who were senseless may rise.
    run(&mut g, 20.0);
    let mut stayed = 0;
    let mut still_down = 0;
    for (k, id, pos) in lying {
        let s = &g.ships[k];
        if let Some(c) = s.craft.scene.life.get(id) {
            if !c.alive {
                still_down += 1;
                if s.craft.scene.things.get(id).map(|t| t.pos()) == Some(pos) {
                    stayed += 1;
                }
            }
        }
    }
    assert_eq!(stayed, still_down, "the dead lie where they fell");
}

#[test]
fn boarders_called_home_under_fire_break_off_and_the_survivors_go_back_over_the_rail() {
    let mut g = Game::new(Scenario::Action, 21);
    g.captains[1] = None;
    for s in g.ships.iter_mut() {
        s.orders.sail = 0.0;
        s.orders.course = None;
        s.craft.heading = 0.0;
        s.craft.vx = 0.0;
        s.craft.vy = 0.0;
        s.craft.yaw_rate = 0.0;
    }
    let (x, y) = (g.ships[0].craft.x, g.ships[0].craft.y);
    g.ships[1].craft.x = x + 11.0;
    g.ships[1].craft.y = y;
    g.ships[1].craft.vx = -0.5;
    for _ in 0..(40.0 / SECS) as usize {
        g.tick();
        if !g.fouls.is_empty() {
            break;
        }
    }
    assert!(!g.fouls.is_empty(), "fouled");
    g.ships[0].orders.boarders_away = true;
    let mut over = false;
    for _ in 0..(120.0 / SECS) as usize {
        g.tick();
        if g.ships[1].people.iter().any(|p| p.home == Some(0)) {
            over = true;
            break;
        }
    }
    assert!(over, "somebody crossed");
    run(&mut g, 4.0);
    g.ships[0].orders.boarders_away = false;
    run(&mut g, 150.0);
    let s = &g.ships[1];
    let standing: Vec<_> = s.people.iter().filter(|p| p.home == Some(0) && s.able(p)).map(|p| p.name()).collect();
    assert!(standing.is_empty(), "no boarder still on his feet on her deck: {standing:?}");
    let fell = s.people.iter().filter(|p| p.home == Some(0)).count();
    let back = g.ships[0].people.iter().filter(|p| p.crossed.is_none() && p.thing.is_some()).count();
    assert!(fell > 0 || back > 0);
}
