//! Defenders turning out (BRD-07) and the captain's answer to boarders, headless.

use broadside::ai::{Captain, Mission};
use broadside::board;
use broadside::crew::{self, Person, Role};
use broadside::game::{Game, Scenario, SECS};
use broadside::melee::{self, Arms, Weapon};
use broadside::ship::Ship;
use tachyon::prelude::*;

const CUTLASS: Arms = Arms { weapon: Weapon::Cutlass, pistol: false };

fn arena(seed: u64) -> Game {
    arena_of(seed, 2)
}

fn arena_of(seed: u64, class: usize) -> Game {
    let mut g = Game::new(Scenario::FreeSailing(2), seed);
    let class = g.classes[class].clone();
    let (x, y) = (g.ships[0].craft.x, g.ships[0].craft.y);
    let mut s = Ship::new(0, &class, &g.cultures[0], 0, x, y, 0.4, seed, 0, false);
    s.craft.z = g.sea.tide();
    s.craft.scene.clock = Clock::new(SECS, 10.0);
    s.craft.scene.clock.start_secs = g.time;
    g.ships[0] = s;
    g.captains.truncate(1);
    g.captains[0] = None;
    g.ships.truncate(1);
    g
}

fn put(g: &mut Game, faction: u16, role: Role, melee_skill: f32, at: Pos) -> usize {
    let s = &mut g.ships[0];
    let mut p: Person = s.people[0].clone();
    p.role = role;
    p.thing = None;
    p.gun = None;
    p.crossed = None;
    p.boarding = false;
    p.fray = Default::default();
    p.skills[crew::skill_index("melee")] = melee_skill;
    p.bravery = 0.9;
    p.discipline = 0.9;
    p.arms = CUTLASS;
    p.home = if faction == s.faction { None } else { Some(1) };
    crew::embark(&mut s.craft.scene, &s.crew_kinds, &mut p, at, Control::Ai, faction);
    if let Some(c) = p.thing.and_then(|t| s.craft.scene.life.get_mut(t)) {
        c.mind.routine = Routine::new().with(0.0, 24.0, Task::Stay { at });
    }
    s.people.push(p);
    s.people.len() - 1
}

#[test]
fn the_bill_turns_out_tops_and_guns_to_meet_boarders() {
    let mut g = arena_of(7, g_classes_last());
    let deck = g.ships[0].layout.waist[0];
    let gun_at = g.ships[0].layout.guns.iter().map(|s| s.crew[0]).find(|p| p.z != deck.z).expect("a gun below the weather deck");
    assert_ne!(gun_at.z, deck.z, "the guns are on another deck");
    let top_at = g.ships[0].layout.topmen[0];
    let top = put(&mut g, 0, Role::Topman, 0.5, top_at);
    let gunner = put(&mut g, 0, Role::Gunner, 0.5, gun_at);
    let gcap = put(&mut g, 0, Role::GunCaptain, 0.5, gun_at);
    let at = board::landing(&g.ships[0], deck).unwrap();
    put(&mut g, 1, Role::Marine, 0.5, at);
    let at = board::landing(&g.ships[0], deck).unwrap();
    put(&mut g, 1, Role::Marine, 0.5, at);
    let mut lines = Vec::new();
    let n = melee::turn_out(&mut g.ships[0], &mut lines);
    assert_eq!(n, 2, "topman and gunner turned out, not the gun captain");
    assert!(g.ships[0].people[top].fray.turned_out && g.ships[0].people[gunner].fray.turned_out);
    assert!(!g.ships[0].people[gcap].fray.turned_out);
    // The gunner goes up to the weather deck.
    let mut up = false;
    for _ in 0..(60.0 / SECS) as usize {
        g.tick();
        let s = &g.ships[0];
        if s.pos_of(&s.people[gunner]).is_some_and(|p| p.z == s.layout.deck_z) {
            up = true;
            break;
        }
    }
    assert!(up, "the gunner left the gundeck for the weather deck");
}

#[test]
fn a_captain_whose_deck_is_lost_strikes() {
    let mut g = arena(9);
    let deck = g.ships[0].layout.waist[0];
    let cap_at = g.ships[0].layout.captain;
    let cap = put(&mut g, 0, Role::Captain, 0.3, cap_at);
    g.captains[0] = Some(Captain::from(&g.ships[0].people[cap]));
    for _ in 0..8 {
        let at = board::landing(&g.ships[0], deck).unwrap();
        put(&mut g, 1, Role::Marine, 0.9, at);
    }
    let mut mission = Vec::new();
    for _ in 0..(200.0 / SECS) as usize {
        g.tick();
        mission.push(g.captains[0].as_ref().unwrap().mission);
        if g.ships[0].struck {
            break;
        }
    }
    assert!(mission.contains(&Mission::Repel), "he first set about repelling them");
    assert!(g.ships[0].struck, "with the deck theirs, he struck");
}

fn g_classes_last() -> usize {
    Game::new(Scenario::FreeSailing(2), 1).classes.len() - 1
}

/// A brig with her guns out and water in her is laid aboard by a bold captain.
#[test]
fn a_bold_captain_lays_a_crippled_ship_aboard() {
    let mut fouled = 0;
    for seed in [1u64, 2, 3] {
        let mut g = Game::new(Scenario::Action, seed);
        let ids: Vec<ThingId> = g.ships[1].people.iter().filter_map(|p| p.thing).collect();
        let mut rng = Rng::new(5);
        for &id in ids.iter().take(ids.len() * 6 / 10) {
            for _ in 0..4 {
                broadside::game::wound(&mut g.ships[1], id, tachyon::life::body::DamageKind::Point, 400.0, &mut rng);
            }
        }
        for gun in g.ships[1].guns.iter_mut() {
            gun.disabled = true;
        }
        g.ships[1].orders.sail = 0.0;
        g.captains[1] = None;
        for k in 0..1 {
            let mut c = Captain::from(&g.ships[k].people[0]);
            c.aggression = 0.9;
            g.captains[k] = Some(c);
        }
        let mut boarded = false;
        for _ in 0..(900.0 / SECS) as usize {
            g.tick();
            boarded |= matches!(g.captains[0].as_ref().unwrap().mission, Mission::Board(_));
            if !g.fouls.is_empty() {
                fouled += 1;
                break;
            }
        }
        println!("seed {seed}: mission Board seen {boarded}, fouled {}", !g.fouls.is_empty());
    }
    assert!(fouled > 0, "at least once she is laid aboard");
}
