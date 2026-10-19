//! Broadside, played headless.

use broadside::ai::Captain;
use broadside::crew::Role;
use broadside::data;
use broadside::game::{Game, Scenario, SECS};
use broadside::ship::{wrap, Fire, Ship};
use tachyon::lang::Culture;

fn run(g: &mut Game, secs: f64) {
    for _ in 0..(secs / SECS) as usize {
        g.tick();
    }
}

#[test]
fn every_class_loads_builds_and_floats_at_her_draught() {
    let classes = data::load_all();
    assert_eq!(classes.len(), 7, "the seven classes of the first Broadside");
    let culture = Culture::new(5);
    for c in &classes {
        let s = Ship::new(0, c, &culture, 0, 1000.0, 1000.0, 0.0, 9, 60, false);
        let draft = s.craft.draft();
        assert!((draft - c.draught_m).abs() < 1.2, "{}: draws {draft:.2} m, the books say {:.1}", c.key, c.draught_m);
        let weather_guns = c.guns.iter().map(|b| b.count as usize).sum::<usize>();
        assert!(s.guns.len() + 2 >= weather_guns, "{}: {} of {} guns found a place", c.key, s.guns.len(), weather_guns);
        assert!(s.people.len() == c.max_crew as usize, "{}: her whole company", c.key);
        assert!(!s.name.is_empty() && !s.meaning.is_empty());
        assert!(s.craft.scene.life.creatures.len() >= 20.min(c.max_crew as usize), "{}: men aboard", c.key);
    }
}

#[test]
fn at_quarters_the_crews_go_to_their_guns() {
    let mut g = Game::new(Scenario::FreeSailing(2), 3);
    g.ships[0].orders.quarters = true;
    run(&mut g, 60.0);
    let s = &g.ships[0];
    let (mut at, mut n) = (0, 0);
    for p in s.people.iter().filter(|p| p.role == Role::GunCaptain) {
        if let (Some(pos), Some(post)) = (s.pos_of(p), s.station_of(p, true)) {
            n += 1;
            if pos.z == post.z && pos.dist2d(post) <= 1 {
                at += 1;
            }
        }
    }
    assert!(n > 0 && at * 10 >= n * 7, "{at} of {n} gun captains at their guns after a minute");
}

#[test]
fn the_quartermaster_steers_the_course_you_order() {
    let mut g = Game::new(Scenario::FreeSailing(2), 4);
    run(&mut g, 20.0);
    let want = (g.ships[0].craft.heading + 0.6).rem_euclid(std::f32::consts::TAU);
    g.ships[0].orders.course = Some(want);
    run(&mut g, 90.0);
    let err = wrap(g.ships[0].craft.heading - want).abs();
    assert!(err < 0.12, "steering {:.1} deg off the ordered course", err.to_degrees());
}

#[test]
fn with_nobody_at_the_wheel_she_cannot_be_steered() {
    let mut g = Game::new(Scenario::FreeSailing(2), 4);
    run(&mut g, 20.0);
    // The quartermasters are killed.
    let ids: Vec<_> = g.ships[0].people.iter().filter(|p| p.role == Role::Helmsman).filter_map(|p| p.thing).collect();
    for id in ids {
        if let Some(c) = g.ships[0].craft.scene.life.get_mut(id) {
            c.alive = false;
        }
    }
    let h0 = g.ships[0].craft.heading;
    g.ships[0].orders.course = Some((h0 + 1.2).rem_euclid(std::f32::consts::TAU));
    run(&mut g, 60.0);
    assert!(wrap(g.ships[0].craft.heading - h0).abs() < 0.4, "she does not answer an order nobody carries out");
}

#[test]
fn the_drill_sets_her_rate_of_fire() {
    let mut g = Game::new(Scenario::FreeSailing(2), 6);
    g.ships[0].orders.quarters = true;
    // Time for the crews to reach their guns and run them out.
    run(&mut g, 90.0);
    let (ready, total) = g.ships[0].battery_state(1);
    assert!(total > 0 && ready * 10 >= total * 7, "{ready} of {total} starboard guns ready after the people reached them");
    g.ships[0].orders.fire = Fire::Broadside(1);
    run(&mut g, 5.0);
    let fired: u32 = g.ships[0].guns.iter().map(|s| s.fired).sum();
    assert!(fired as usize >= ready.saturating_sub(1), "{fired} guns fired of {ready} ready");
    // Reloading from the recoil: sponge, load, ram, wad, shot, ram, run out, prime, lay.
    let mut first_ready = None;
    for k in 0..400 {
        g.tick();
        let (r, _) = g.ships[0].battery_state(1);
        if r > 0 && first_ready.is_none() {
            first_ready = Some(k as f64 * SECS);
        }
    }
    let t = first_ready.expect("a gun reloaded");
    assert!((25.0..150.0).contains(&t), "first gun ready again after {t:.0} s (period crews: about a minute)");
}

#[test]
fn an_action_is_fought_to_a_decision_or_to_blood() {
    let mut g = Game::new(Scenario::Action, 11);
    g.captains[0] = Some(Captain::from(&g.ships[0].people[0]));
    run(&mut g, 900.0);
    let struck: Vec<bool> = g.ships.iter().map(|s| s.craft.holes.len() + s.guns.iter().filter(|x| x.disabled).count() > 0 || s.muster().2 + s.muster().1 > 0).collect();
    let fired: Vec<u32> = g.ships.iter().map(|s| s.guns.iter().map(|x| x.fired).sum()).collect();
    for l in g.log.lines.iter().rev().take(15) {
        println!("{}", l.0);
    }
    assert!(fired.iter().all(|&f| f >= 6), "both ships fought their guns: {fired:?}");
    let hits = g.log.lines.iter().filter(|(l, _)| l.contains(" is struck ")).count();
    assert!(hits > 0 || struck.iter().any(|&s| s), "shot told on someone");
}
