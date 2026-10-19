//! The glass: what it finds, the words for it, and the picture.

use broadside::game::{Game, Scenario};
use broadside::glass::{self, Glass};
use broadside::screen::{self, Mode, Ui};
use std::f32::consts::PI;
use tachyon::prelude::*;

#[test]
fn tab_holds_the_brig_and_the_glass_reports_her() {
    let g = Game::new(Scenario::Action, 1805);
    let mut gl = Glass::new(true);
    assert_eq!(gl.next(&g), Some(1));
    // Held, the middle of the field is on her.
    let e = glass::eye(&g);
    let her = &g.ships[1].craft;
    let b = (her.x - e.0).atan2(-(her.y - e.1));
    assert!(broadside::ship::wrap(gl.bearing(&g) - b).abs() < 0.01);
    let r = glass::report(&g, &gl);
    assert_eq!(r.len(), 1, "{r:?}");
    assert!(r[0].starts_with("a brig, hull up, bearing "), "{}", r[0]);
    assert!(r[0].contains("cables") && r[0].contains(" on the starboard bow"), "{}", r[0]);
    // Looking right astern there is nothing to see.
    gl.ahead();
    gl.sweep(4.0 * PI / gl.field);
    assert!(glass::relative_words(gl.rel).contains("astern"), "{}", gl.rel);
    assert_eq!(glass::report(&g, &gl), vec!["Nothing to be made out that way.".to_string()]);
}

#[test]
fn the_glass_shows_more_than_the_eye_far_off() {
    let mut g = Game::new(Scenario::Action, 1805);
    // Send the stranger 15 km off: from the deck she is hull down, a sail by eye; the glass names her rig.
    let you = (g.ships[0].craft.x, g.ships[0].craft.y);
    g.ships[1].craft.x = you.0 + 12000.0;
    g.ships[1].craft.y = you.1 + 10000.0;
    let eye = glass::look(&g, 1, 1.0);
    let glass_ = glass::look(&g, 1, glass::POWER);
    assert!(eye.hull_down && glass_.hull_down);
    assert!(glass_.clarity > eye.clarity);
    let by_eye = glass::what(&g.ships[1], &eye);
    let by_glass = glass::what(&g.ships[1], &glass_);
    assert!(by_eye == "a sail" || by_eye == "a two-master", "{by_eye}");
    assert_eq!(by_glass, "a two-master");
    assert!(glass::report_one(&g, 1, glass::POWER).unwrap().contains("hull down"));
}

#[test]
fn the_glass_view_draws_her_in_ascii_and_holds_relative_to_her_head() {
    let mut g = Game::new(Scenario::Action, 1805);
    for _ in 0..20 {
        g.tick();
    }
    let mut ui = Ui::new(&g);
    ui.mode = Mode::Glass;
    ui.glass.next(&g);
    let mut f = Frame::new(180, 56);
    screen::draw(&mut f, &g, &mut ui);
    tachyon::display::Display::default().apply(&mut f);
    let text = f.to_text();
    assert!(text.is_ascii());
    assert!(text.contains("THE GLASS x10 - "), "no title");
    // Her hull and canvas, the reticle, the compass along the foot.
    assert!(text.contains("#####") && text.contains("%%%%") && text.contains("+"), "{text}");
    assert!(text.contains(&format!("the {}", g.ships[1].name)));
    // Let her go and turn our ship: the glass turns with her head.
    ui.glass.hold = None;
    let rel = ui.glass.rel;
    g.ships[0].craft.heading += 0.5;
    assert!((ui.glass.rel - rel).abs() < 1e-6);
    assert!(broadside::ship::wrap(ui.glass.bearing(&g) - (g.ships[0].craft.heading + rel)).abs() < 1e-5);
}
