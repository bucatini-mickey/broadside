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

#[test]
fn a_round_fired_teaches_the_gun_captain_and_pulses_read() {
    let mut g = Game::new(Scenario::FreeSailing(2), 6);
    let s = &mut g.ships[0];
    let gc = s.people.iter().position(|p| p.gun.is_some_and(|(_, k)| k == 0)).expect("a gun captain");
    let gun = s.people[gc].gun.unwrap().0;
    let before = s.people[gc].skill("gunlaying");
    let _ = s.people[gc].skill("gunnery");
    // Fire that gun by hand through the ripple.
    s.guns[gun].step = broadside::drill::READY;
    s.orders.fire = Fire::Hold;
    s.ripple.push((gun, 0.0));
    let s = &mut g.ships[0];
    s.step(0.1, &g.sea, g.wind, None);
    assert!(s.people[gc].skill("gunlaying") > before, "practice raised his gunlaying");
    let pulse = s.pulse(&s.people[1]).expect("a living man has a pulse");
    assert!((40..=200).contains(&pulse), "pulse {pulse}");
}

#[test]
fn only_rated_ships_stand_in_the_line() {
    use broadside::data::Rate;
    let classes = data::load_all();
    let line: Vec<&str> = classes.iter().filter(|c| c.stands_in_line()).map(|c| c.key.as_str()).collect();
    assert_eq!(line.len(), 2, "74 and first rate only: {line:?}");
    for c in &classes {
        if c.key.contains("frigate") {
            assert_eq!(c.rating(), Rate::Fifth);
            assert!(!c.stands_in_line());
        }
    }
    assert!(Rate::First < Rate::Third && Rate::Third.of_the_line() && !Rate::Unrated.of_the_line());
}

/// Two brigs side by side, b to starboard of a, closing at `closing` m/s.
fn alongside(closing: f32, gap: f32) -> Game {
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
    g.ships[1].craft.x = x + gap;
    g.ships[1].craft.y = y;
    g.ships[1].craft.vx = -closing;
    g.ships[0].craft.vx = 0.0;
    g
}

fn first_foul(g: &mut Game, secs: f64) -> bool {
    for _ in 0..(secs / SECS) as usize {
        g.tick();
        if !g.fouls.is_empty() {
            return true;
        }
    }
    false
}

#[test]
fn a_slow_meeting_at_the_rails_leaves_the_ships_fouled_and_moving_as_a_pair() {
    let mut g = alongside(0.5, 11.0);
    assert!(first_foul(&mut g, 40.0), "fouled");
    let f = g.fouls[0].clone();
    let (a, b) = (f.a, f.b);
    run(&mut g, 30.0);
    assert_eq!(g.fouls.len(), 1, "still fouled with nobody cutting");
    let (ca, cb) = (&g.ships[a].craft, &g.ships[b].craft);
    let (fwd, stb) = ca.axes();
    let (dx, dy) = (cb.x - ca.x, cb.y - ca.y);
    assert!((dx * fwd.0 + dy * fwd.1 - f.off.0).abs() < 0.05 && (dx * stb.0 + dy * stb.1 - f.off.1).abs() < 0.05, "held at the contact");
    assert!((ca.vx - cb.vx).abs() < 1e-4 && (ca.vy - cb.vy).abs() < 1e-4, "one velocity");
    assert!(wrap(cb.heading - ca.heading - f.dh).abs() < 1e-3, "one heading");
}

#[test]
fn a_hard_collision_still_separates_and_does_not_foul() {
    let mut g = alongside(6.0, 14.0);
    let mut worst: f32 = 0.0;
    for _ in 0..40 {
        g.tick();
        worst = worst.max(g.ships[0].craft.speed());
    }
    assert!(g.fouls.is_empty(), "a hard blow does not foul");
    assert!(worst > 1.0, "it knocked her at rest into motion: {worst}");
    // The pair were shoved to a seam's width apart, not locked at the contact.
    let gap = (g.ships[1].craft.x - g.ships[0].craft.x).abs();
    assert!(gap > 8.0, "and they are apart again: {gap}");
}

#[test]
fn the_order_to_cut_free_takes_hands_at_the_rails_and_time() {
    let mut g = alongside(0.5, 11.0);
    assert!(first_foul(&mut g, 40.0));
    g.ships[0].orders.cut_free = true;
    let t0 = g.time;
    run(&mut g, 2.0);
    assert!(!g.fouls.is_empty(), "not cut in a moment");
    assert!(!g.fouls[0].cutters[0].is_empty(), "hands sent");
    assert!(g.fouls[0].cutters[1].is_empty(), "the other ship was not ordered");
    let mut cut_at = None;
    for _ in 0..(300.0 / SECS) as usize {
        g.tick();
        if g.fouls.is_empty() {
            cut_at = Some(g.time - t0);
            break;
        }
    }
    let t = cut_at.expect("cut apart in the end");
    assert!(t > 8.0, "it took real work: {t:.0} s");
    assert!(!g.ships[0].orders.cut_free);
    run(&mut g, 20.0);
    assert!(g.fouls.is_empty(), "and they do not foul at once again");
}

#[test]
fn with_no_hands_able_the_lines_are_not_cut() {
    let mut g = alongside(0.5, 11.0);
    assert!(first_foul(&mut g, 40.0));
    let ids: Vec<_> = g.ships[0].people.iter().filter_map(|p| p.thing).collect();
    for id in ids {
        if let Some(c) = g.ships[0].craft.scene.life.get_mut(id) {
            c.alive = false;
        }
    }
    g.ships[0].orders.cut_free = true;
    run(&mut g, 120.0);
    for l in g.log.lines.iter().rev().take(6) { println!("{}", l.0); } assert!(!g.fouls.is_empty(), "still fouled"); assert!(g.fouls[0].work < 1.0, "nobody to do it: {} man-seconds, {} cutters", g.fouls[0].work, g.fouls[0].cutters[0].len());
}

#[test]
fn an_ai_captain_cuts_free_in_time() {
    let mut g = alongside(0.5, 11.0);
    g.captains[0] = None;
    assert!(first_foul(&mut g, 40.0));
    g.captains[1] = Some(Captain::from(&g.ships[1].people[0]));
    run(&mut g, 200.0);
    assert!(g.fouls.is_empty(), "the other captain had them cut apart");
}
