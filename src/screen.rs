//! The command screen (after `docs/legacy/08_interface.md`):
//!
//! ```text
//! +- THE SHIP --------------+- CHART ---------------------------+
//! | her own grid, bow up,   |  the sea round her, north up      |
//! | at the level you look   +-----------------------------------+
//! | at, with her people at  | status: time, heading in points,  |
//! | their work              | log, wind, sail, quarters         |
//! |                         | 1 LOG 2 CREW 3 ORDERS 4 SHIP 5 KEYS|
//! |                         |   one panel, the full width       |
//! +-------------------------+-----------------------------------+
//! | the keys worth keeping in front of you                       |
//! ```

use crate::crew::{Role, SKILLS};
use crate::drill;
use crate::game::Game;
use crate::ship::{wrap, Fire, Ship};
use std::f32::consts::{PI, TAU};
use tachyon::ballistics::{Placement, V3};
use tachyon::craft;
use tachyon::prelude::*;
use tachyon::sea::screen_axes;
use tachyon::ui::{self, keybar, panel, tabs, Log, Table, Theme};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Panel {
    Log,
    Crew,
    Orders,
    Ship,
    Keys,
}

pub const PANELS: [&str; 5] = ["LOG", "CREW", "ORDERS", "SHIP", "KEYS"];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Commanding from the quarterdeck: the whole ship in view.
    Command,
    /// Being the captain: walk her decks, see what he sees.
    Walk,
    /// A cursor to look at anything aboard.
    Look,
}

pub struct Ui {
    pub panel: Panel,
    pub mode: Mode,
    pub view: MapView,
    pub level: i32,
    pub cursor: Pos,
    pub mpc: f32,
    pub crew: Table,
    pub theme: Theme,
    pub message: String,
    pub confirm_strike: bool,
}

impl Ui {
    pub fn new(g: &Game) -> Ui {
        let you = g.you();
        let mut view = MapView::new();
        view.wide = true;
        view.lighting = true;
        view.depth = 3;
        view.up_depth = 0;
        let l = &you.layout;
        Ui {
            panel: Panel::Log,
            mode: Mode::Command,
            view,
            level: l.deck_z,
            cursor: Pos::new(l.cx, (l.bow_y + l.stern_y) / 2, l.deck_z),
            mpc: 24.0,
            crew: Table::default(),
            theme: Theme::default(),
            message: String::new(),
            confirm_strike: false,
        }
    }
}

const POINTS: [&str; 32] = [
    "N", "N by E", "NNE", "NE by N", "NE", "NE by E", "ENE", "E by N", "E", "E by S", "ESE", "SE by E", "SE", "SE by S", "SSE", "S by E", "S", "S by W", "SSW", "SW by S", "SW", "SW by W", "WSW", "W by S", "W", "W by N", "WNW", "NW by W", "NW", "NW by N", "NNW", "N by W",
];

/// A compass heading in points: "NE by E".
pub fn points(h: f32) -> &'static str {
    POINTS[((h.rem_euclid(TAU) / (TAU / 32.0)).round() as usize) % 32]
}

/// Beaufort's words for a wind of `ms` metres a second.
pub fn beaufort(ms: f32) -> &'static str {
    const B: [(f32, &str); 12] = [
        (0.5, "calm"), (1.6, "light air"), (3.4, "light breeze"), (5.5, "gentle breeze"), (8.0, "moderate breeze"), (10.8, "fresh breeze"), (13.9, "strong breeze"), (17.2, "near gale"), (20.8, "gale"), (24.5, "strong gale"), (28.5, "storm"), (99.0, "hurricane"),
    ];
    B.iter().find(|(v, _)| ms < *v).map(|(_, s)| *s).unwrap_or("hurricane")
}

/// Where the wind is coming from relative to her: "on the larboard quarter".
pub fn wind_on(heading: f32, wind: (f32, f32)) -> String {
    let from = wind.0.atan2(-wind.1) + PI;
    let rel = wrap(from - heading);
    let side = if rel >= 0.0 { "starboard" } else { "larboard" };
    let a = rel.abs().to_degrees();
    match a {
        a if a < 25.0 => "dead ahead".into(),
        a if a < 70.0 => format!("on the {side} bow"),
        a if a < 110.0 => format!("on the {side} beam"),
        a if a < 160.0 => format!("on the {side} quarter"),
        _ => "dead astern".into(),
    }
}

fn sail_words(s: f32) -> &'static str {
    match s {
        s if s < 0.05 => "furled",
        s if s < 0.4 => "topsails",
        s if s < 0.7 => "fighting sail",
        s if s < 0.9 => "plain sail",
        _ => "all plain sail",
    }
}

pub fn draw(f: &mut Frame, g: &Game, ui: &mut Ui) {
    let t = ui.theme;
    f.clear(t.bg);
    let (w, h) = (f.width(), f.height());
    let foot = 2;
    let left_w = (w / 2).max(40).min(w - 40);
    let ship_r = Rect::new(0, 0, left_w, h - foot);
    let right_x = left_w;
    let right_w = w - left_w;
    let chart_h = ((h - foot) * 2 / 5).max(8);
    draw_ship_pane(f, g, ui, ship_r);
    let chart_in = panel(f, Rect::new(right_x, 0, right_w, chart_h), &format!("CHART  {:.0} m a cell", ui.mpc), &t);
    draw_chart(f, g, ui, chart_in);
    let strip = Rect::new(right_x, chart_h, right_w, 2);
    draw_strip(f, g, strip, &t);
    let tabs_y = chart_h + 2;
    let active = PANELS.iter().position(|p| *p == panel_name(ui.panel)).unwrap_or(0);
    tabs(f, right_x + 1, tabs_y, right_w - 2, &PANELS, active, &t);
    let body = panel(f, Rect::new(right_x, tabs_y + 1, right_w, h - foot - tabs_y - 1), "", &t);
    match ui.panel {
        Panel::Log => draw_log(f, g, ui, body),
        Panel::Crew => draw_crew(f, g, ui, body),
        Panel::Orders => draw_orders(f, g, body, &t),
        Panel::Ship => draw_ship_info(f, g, body, &t),
        Panel::Keys => draw_keys(f, body, &t),
    }
    draw_footer(f, g, ui, Rect::new(0, h - foot, w, foot));
}

fn panel_name(p: Panel) -> &'static str {
    match p {
        Panel::Log => "LOG",
        Panel::Crew => "CREW",
        Panel::Orders => "ORDERS",
        Panel::Ship => "SHIP",
        Panel::Keys => "KEYS",
    }
}

fn draw_ship_pane(f: &mut Frame, g: &Game, ui: &mut Ui, r: Rect) {
    let you = g.you();
    let t = ui.theme;
    let walk_pos = you.you().and_then(|id| you.craft.scene.things.get(id)).map(|th| th.pos());
    let (center, title) = match ui.mode {
        Mode::Walk => {
            let p = walk_pos.unwrap_or(ui.cursor);
            ui.level = p.z;
            (p, format!("THE {} - you, on the {}", you.name.to_uppercase(), you.layout.level_name(p.z)))
        }
        Mode::Look => (Pos::new(you.layout.cx, (you.layout.bow_y + you.layout.stern_y) / 2, ui.cursor.z), format!("THE {} - looking: {}", you.name.to_uppercase(), you.layout.level_name(ui.cursor.z))),
        Mode::Command => (Pos::new(you.layout.cx, (you.layout.bow_y + you.layout.stern_y) / 2, ui.level), format!("THE {} - {}", you.name.to_uppercase(), you.layout.level_name(ui.level))),
    };
    let inner = panel(f, r, &title, &t);
    ui.view.center = center;
    ui.view.observer = if ui.mode == Mode::Walk { walk_pos } else { None };
    ui.view.sight_radius = 30;
    ui.view.cursor = if ui.mode == Mode::Look { Some(ui.cursor) } else { None };
    let others: Vec<&tachyon::craft::Craft> = g.ships[1..].iter().map(|s| &s.craft).collect();
    craft::draw(f, inner, &mut ui.view, &you.craft, &g.sea, &others);
    effects_on_ship(f, g, inner, &ui.view, &you.craft.placement());
}

fn effects_on_ship(f: &mut Frame, g: &Game, area: Rect, view: &MapView, place: &Placement) {
    let (cols, rows) = view.cells_for(area);
    let (x0, y0) = (view.center.x - cols / 2, view.center.y - rows / 2);
    let mut put = |p: V3, ch: char, fg: Rgb, smoke: bool| {
        let l = place.to_local(p);
        let (sx, sy) = (l[0].floor() as i32 - x0, l[1].floor() as i32 - y0);
        if sx < 0 || sy < 0 || sx >= cols || sy >= rows {
            return;
        }
        let px = area.x + if view.wide { sx * 2 } else { sx };
        let old = f.get(px, area.y + sy);
        if smoke {
            let bg = old.bg.lerp(Rgb(170, 170, 162), 0.55);
            f.set(px, area.y + sy, Cell::new(old.ch, old.fg.lerp(bg, 0.5), bg));
            if view.wide {
                let o2 = f.get(px + 1, area.y + sy);
                f.set(px + 1, area.y + sy, Cell::new(o2.ch, o2.fg.lerp(bg, 0.5), bg));
            }
        } else {
            f.set(px, area.y + sy, Cell::new(ch, fg, old.bg));
        }
    };
    for (m, ttl) in &g.smoke {
        let r = m.radius.min(14.0) as i32;
        for dy in -r..=r {
            for dx in -r..=r {
                if dx * dx + dy * dy <= r * r && (dx * 7 + dy * 13 + (*ttl as i32)).rem_euclid(3) != 0 {
                    put([m.x + dx as f32, m.y + dy as f32, 3.0], ' ', Rgb::WHITE, true);
                }
            }
        }
    }
    for m in &g.marks {
        put(m.at, m.ch, m.fg, false);
    }
    for s in &g.shots.shots {
        put(s.pos, if s.in_water { 'o' } else { '*' }, Rgb(255, 240, 200), false);
    }
}

fn draw_chart(f: &mut Frame, g: &Game, ui: &Ui, area: Rect) {
    let you = g.you();
    let refs: Vec<&tachyon::craft::Craft> = g.ships.iter().map(|s| &s.craft).collect();
    // Centred on her, or between her and her mark (or the nearest stranger) when both fit.
    let other = you.orders.target.and_then(|i| g.ships.get(i)).or_else(|| g.ships.iter().skip(1).min_by(|a, b| (a.craft.x - you.craft.x).hypot(a.craft.y - you.craft.y).total_cmp(&(b.craft.x - you.craft.x).hypot(b.craft.y - you.craft.y))));
    let (cx, cy) = match other {
        Some(o) if (o.craft.x - you.craft.x).abs() < ui.mpc * area.w as f32 * 0.4 && (o.craft.y - you.craft.y).abs() < ui.mpc * area.h as f32 * 0.8 => ((you.craft.x + o.craft.x) / 2.0, (you.craft.y + o.craft.y) / 2.0),
        _ => (you.craft.x, you.craft.y),
    };
    craft::draw_chart(f, area, &g.sea, &refs, cx, cy, ui.mpc, 0.0, true);
    let cols = area.w / 2;
    let (right, down) = screen_axes(0.0);
    let to_screen = |x: f32, y: f32| {
        let (rx, ry) = (x - cx, y - cy);
        (cols / 2 + ((rx * right.0 + ry * right.1) / ui.mpc).round() as i32, area.h / 2 + ((rx * down.0 + ry * down.1) / ui.mpc).round() as i32)
    };
    let mut put = |x: f32, y: f32, ch: char, fg: Rgb| {
        let (sx, sy) = to_screen(x, y);
        if sx >= 0 && sy >= 0 && sx < cols && sy < area.h {
            let px = area.x + sx * 2;
            let bg = f.get(px, area.y + sy).bg;
            f.set(px, area.y + sy, Cell::new(ch, fg, bg));
        }
    };
    for (m, _) in &g.smoke {
        put(m.x, m.y, ':', Rgb(200, 200, 190));
    }
    for m in &g.marks {
        put(m.at[0], m.at[1], m.ch, m.fg);
    }
    for s in &g.shots.shots {
        put(s.pos[0], s.pos[1], '.', Rgb(255, 240, 200));
    }
    // Names beside the ships.
    for s in &g.ships {
        let (sx, sy) = to_screen(s.craft.x, s.craft.y);
        let label = if s.struck { format!("{} (struck)", s.name) } else { s.name.clone() };
        let px = area.x + sx * 2 + 3 + (s.craft.length / ui.mpc) as i32;
        if sy >= 0 && sy < area.h && px < area.right() {
            let c = if s.faction == 0 { Rgb(240, 230, 190) } else { Rgb(240, 150, 120) };
            let bg = f.get(px, area.y + sy).bg;
            f.text_clip(px, area.y + sy, area.right() - px, &label, c, bg);
        }
    }
}

fn draw_strip(f: &mut Frame, g: &Game, r: Rect, t: &Theme) {
    let you = g.you();
    f.fill(r, Cell::new(' ', t.text, Rgb(20, 24, 32)));
    let bg = Rgb(20, 24, 32);
    let h = (g.time / 3600.0) % 24.0;
    let ws = g.wind.0.hypot(g.wind.1);
    let line1 = format!(
        " {:02}:{:02}  {} {:03.0}  {:.1} kn  {} {}",
        h as u32,
        (h.fract() * 60.0) as u32,
        points(you.craft.heading),
        you.craft.heading.rem_euclid(TAU).to_degrees(),
        you.craft.speed() * 1.944,
        beaufort(ws),
        wind_on(you.craft.heading, g.wind)
    );
    f.text_clip(r.x, r.y, r.w, &line1, t.title, bg);
    let course = you.orders.course.map(|c| format!("course {} {:03.0}", points(c), c.rem_euclid(TAU).to_degrees())).unwrap_or("helm lashed".into());
    let q = if you.orders.quarters { "AT QUARTERS" } else { "stood down" };
    let fire = match you.orders.fire {
        Fire::Hold => "hold fire",
        Fire::AtWill => "fire as they bear",
        Fire::Broadside(_) => "broadside!",
    };
    let line2 = format!(" {course}  {} ({:.0}%)  {q}, {fire}  heel {:+.0}", sail_words(you.orders.sail), you.set * 100.0, you.craft.roll.to_degrees());
    f.text_clip(r.x, r.y + 1, r.w, &line2, if you.orders.quarters { t.warn } else { t.text }, bg);
}

fn draw_log(f: &mut Frame, g: &Game, ui: &Ui, r: Rect) {
    let t = ui.theme;
    if ui.mode == Mode::Look {
        let lines = look_at(g, ui.cursor);
        let top = (lines.len() as i32).min(r.h / 2);
        for (k, (s, c)) in lines.iter().take(top as usize).enumerate() {
            f.text_clip(r.x, r.y + k as i32, r.w, s, *c, t.bg);
        }
        g.log.draw(f, Rect::new(r.x, r.y + top + 1, r.w, r.h - top - 1), t.bg);
    } else {
        g.log.draw(f, r, t.bg);
    }
}

/// What is at a cell of her grid: the place, and anyone in it.
pub fn look_at(g: &Game, p: Pos) -> Vec<(String, Rgb)> {
    let you = g.you();
    let scene = &you.craft.scene;
    let mut out: Vec<(String, Rgb)> = Vec::new();
    for line in tachyon::view::inspect::describe(scene, p) {
        out.push((line, Rgb(206, 206, 212)));
    }
    for (id, _) in scene.things.at(p) {
        if scene.life.get(id).is_some() {
            if let Some(person) = you.people.iter().find(|q| q.thing == Some(id)) {
                out.push((format!("{} - {}", person.name(), person.role.name()), Rgb(236, 222, 180)));
                out.push((format!("  {}", person.story()), Rgb(150, 150, 160)));
            }
            out.extend(scene.life.describe(&scene.things, id));
        }
    }
    if let Some(gi) = you.layout.guns.iter().position(|s| s.pos == p) {
        let gs = &you.guns[gi];
        out.push((format!("gun {} ({}): {}", gi + 1, you.layout.guns[gi].deck, gs.status()), Rgb(236, 222, 180)));
    }
    out
}

fn health(ship: &Ship, id: Option<ThingId>) -> (String, Rgb) {
    let Some(c) = id.and_then(|i| ship.craft.scene.life.get(i)) else { return ("below".into(), Rgb(126, 132, 146)) };
    if !c.alive {
        ("dead".into(), Rgb(200, 60, 50))
    } else if c.out {
        ("senseless".into(), Rgb(230, 110, 90))
    } else if c.body.bleeding() > 0.05 {
        ("bleeding".into(), Rgb(230, 110, 90))
    } else if c.caps.moving < 0.6 || c.caps.grasp < 0.6 {
        ("wounded".into(), Rgb(232, 196, 96))
    } else {
        ("fit".into(), Rgb(140, 200, 120))
    }
}

fn draw_crew(f: &mut Frame, g: &Game, ui: &mut Ui, r: Rect) {
    let t = ui.theme;
    let you = g.you();
    let (fit, hurt, dead) = you.muster();
    f.text_clip(r.x, r.y, r.w, &format!("{} souls: {fit} fit, {hurt} hurt, {dead} dead. Skills 0-9: {}", you.people.len(), "se to he gn gl mu me ri ca sa lo na le md co"), t.dim, t.bg);
    let header: [(&str, i32); 4] = [("name", 23), ("role", 18), ("state", 10), ("skills", 31)];
    let rows: Vec<Vec<(String, Rgb)>> = you
        .people
        .iter()
        .map(|p| {
            let digits: String = p.skills.iter().map(|s| char::from_digit((s * 9.99) as u32, 10).unwrap_or('9')).collect::<Vec<_>>().chunks(1).map(|c| format!("{} ", c[0])).collect();
            let (state, sc) = health(you, p.thing);
            vec![(p.name(), t.text), (p.role.name().to_string(), p.role.colour()), (state, sc), (digits, t.dim)]
        })
        .collect();
    let sheet_h = (r.h / 3).clamp(4, 9);
    ui.crew.draw(f, Rect::new(r.x, r.y + 1, r.w, r.h - 1 - sheet_h), &header, &rows, &t);
    // The selected man's sheet.
    let sel = ui.crew.list.selected.min(you.people.len().saturating_sub(1));
    if let Some(p) = you.people.get(sel) {
        let y = r.bottom() - sheet_h;
        let mut lines: Vec<(String, Rgb)> = vec![
            (format!("{} \"{}\", {}", p.name(), p.meaning, p.role.name()), t.title),
            (format!("{}. Brave {:.0}%, steady {:.0}%.", p.story(), p.bravery * 100.0, p.discipline * 100.0), t.dim),
        ];
        let best: Vec<String> = {
            let mut s: Vec<(usize, f32)> = p.skills.iter().copied().enumerate().collect();
            s.sort_by(|a, b| b.1.total_cmp(&a.1));
            s.iter().take(3).map(|(i, v)| format!("{} {:.0}%", SKILLS[*i], v * 100.0)).collect()
        };
        lines.push((format!("Best at: {}", best.join(", ")), t.text));
        if let Some(id) = p.thing {
            let mut d = you.craft.scene.life.describe(&you.craft.scene.things, id);
            d.retain(|(s, _)| !s.is_empty());
            lines.extend(d.into_iter().skip(1));
        }
        for (k, (s, c)) in lines.iter().take(sheet_h as usize).enumerate() {
            f.text_clip(r.x, y + k as i32, r.w, s, *c, t.bg);
        }
    }
}

fn draw_orders(f: &mut Frame, g: &Game, r: Rect, t: &Theme) {
    let you = g.you();
    let mut lines: Vec<(String, Rgb)> = Vec::new();
    let course = you.orders.course.map(|c| format!("{} ({:03.0})", points(c), c.rem_euclid(TAU).to_degrees())).unwrap_or("none - the helm is lashed".into());
    lines.push((format!("Course: {course}; steering {}", points(you.craft.heading)), t.text));
    lines.push((format!("Sail: {} ordered, {:.0}% set", sail_words(you.orders.sail), you.set * 100.0), t.text));
    lines.push((format!("Quarters: {}", if you.orders.quarters { "the people are at their stations" } else { "stood down; the watch below is below" }), t.text));
    let fire = match you.orders.fire {
        Fire::Hold => "hold your fire",
        Fire::AtWill => "fire as they bear, on the roll",
        Fire::Broadside(_) => "a broadside, now",
    };
    lines.push((format!("Fire: {fire}"), t.text));
    match you.orders.target.and_then(|i| g.ships.get(i)) {
        Some(s) => {
            let (dx, dy) = (s.craft.x - you.craft.x, s.craft.y - you.craft.y);
            let b = dx.atan2(-dy);
            let rel = wrap(b - you.craft.heading).to_degrees();
            let side = if rel > 0.0 { "starboard" } else { "larboard" };
            lines.push((format!("Mark: the {}, {} {:.0} m, {:.0} deg on the {side}", s.name, points(b), dx.hypot(dy), rel.abs()), t.warn));
        }
        None => lines.push(("Mark: none named (n names one)".into(), t.dim)),
    }
    let (lr, lt) = you.battery_state(-1);
    let (sr, st) = you.battery_state(1);
    lines.push((format!("Larboard battery {lr}/{lt} ready; starboard {sr}/{st}. Powder {} rounds, shot {}.", you.powder, you.shot), t.text));
    lines.push((String::new(), t.text));
    for (i, (slot, gs)) in you.layout.guns.iter().zip(&you.guns).enumerate() {
        let side = if slot.side > 0 { "stbd" } else { "lbd " };
        let c = if gs.ready() { t.good } else if gs.disabled { t.bad } else { t.dim };
        let laid = if gs.ready() { format!(" train {:+.0} elev {:+.1}", gs.train.to_degrees(), gs.elevation.to_degrees()) } else { String::new() };
        lines.push((format!("{:>3} {side} {:<16} {}{laid}", i + 1, slot.deck, gs.status()), c));
    }
    for (k, (s, c)) in lines.iter().take(r.h as usize).enumerate() {
        f.text_clip(r.x, r.y + k as i32, r.w, s, *c, t.bg);
    }
    let _ = drill::READY;
}

fn draw_ship_info(f: &mut Frame, g: &Game, r: Rect, t: &Theme) {
    let mut lines: Vec<(String, Rgb)> = Vec::new();
    for (i, s) in g.ships.iter().enumerate() {
        let c = &s.class;
        let who = if i == 0 { "Yours".to_string() } else { format!("{}", g.cultures[s.faction as usize].adjective) };
        lines.push((format!("{who}: the {} \"{}\", {} ({})", s.name, s.meaning, c.name, c.rate), if i == 0 { t.title } else { Rgb(240, 160, 130) }));
        let (fit, hurt, dead) = s.muster();
        let state = match s.craft.state {
            tachyon::craft::Floating::Afloat => if s.struck { "struck" } else { "afloat" },
            tachyon::craft::Floating::Aground => "AGROUND",
            tachyon::craft::Floating::Foundered => "FOUNDERING",
        };
        lines.push((format!("  {:.1} m x {:.1} m, draught {:.2} m, {} guns; {fit} fit, {hurt} hurt, {dead} dead; {state}", c.length_m, c.beam_m, s.craft.draft(), s.guns.len()), t.text));
        lines.push((format!("  {:.0} t of water in her, {} shot holes, {} guns dismounted; heel {:+.0}", s.craft.water_inside / 1000.0, s.craft.holes.len(), s.guns.iter().filter(|g| g.disabled).count(), s.craft.roll.to_degrees()), t.dim));
        if let Some(Some(cap)) = g.captains.get(i) {
            lines.push((format!("  Captain {}: {}", s.captain().name(), cap.describe()), t.dim));
        }
        lines.push((String::new(), t.text));
    }
    let st = g.sea.state();
    let (rising, springs) = g.sea.tide_phase();
    lines.push((format!("Sea {:.1} m, {:.0} s; swell {:.1} m. Tide {:+.1} m and {} ({:.0}% springs).", st.hs, st.tp, st.swell_hs, g.sea.tide(), if rising { "rising" } else { "falling" }, springs * 100.0), t.text));
    for (k, (s, c)) in lines.iter().take(r.h as usize).enumerate() {
        f.text_clip(r.x, r.y + k as i32, r.w, s, *c, t.bg);
    }
}

pub const KEYS: [(&str, &str); 22] = [
    ("a d", "alter course 5 deg"),
    ("A D", "alter course 30 deg"),
    ("x", "steady as she goes"),
    ("w s", "more / less sail"),
    ("b", "beat to quarters / stand down"),
    ("n", "name your mark (next enemy)"),
    ("f", "fire as they bear / hold fire"),
    ("[ ]", "larboard / starboard broadside"),
    ("1-5 Tab", "panels"),
    ("m", "walk mode: be the captain"),
    ("arrows", "walk (or move the cursor)"),
    ("< >", "climb down / up a ladder"),
    ("l", "look at anything aboard"),
    ("PgUp PgDn", "look at another level"),
    ("+ -", "zoom the chart"),
    ("space", "pause"),
    (", .", "slower / faster time"),
    ("up down", "choose a man (crew panel)"),
    ("Enter", "find him aboard (crew panel)"),
    ("S S", "strike your colours"),
    ("Esc", "back / leave walk or look"),
    ("q", "back to the menu"),
];

fn draw_keys(f: &mut Frame, r: Rect, t: &Theme) {
    for (k, (key, what)) in KEYS.iter().enumerate().take(r.h as usize) {
        f.text_clip(r.x, r.y + k as i32, 12, key, t.title, t.bg);
        f.text_clip(r.x + 12, r.y + k as i32, r.w - 12, what, t.text, t.bg);
    }
}

fn draw_footer(f: &mut Frame, g: &Game, ui: &Ui, r: Rect) {
    let t = ui.theme;
    f.fill(r, Cell::new(' ', t.text, t.bg));
    let msg = if let Some(o) = &g.over {
        format!("{o}  (q for the menu)")
    } else if ui.confirm_strike {
        "Strike your colours? Press S again to strike, anything else not to.".into()
    } else if !ui.message.is_empty() {
        ui.message.clone()
    } else {
        match ui.mode {
            Mode::Walk => "Walking the deck as the captain: arrows to walk, < > ladders, Esc to command from the quarterdeck.".into(),
            Mode::Look => "Look: arrows move the cursor, PgUp/PgDn change level, Esc to finish.".into(),
            Mode::Command => String::new(),
        }
    };
    if !msg.is_empty() {
        f.text_clip(r.x + 1, r.y, r.w - 2, &msg, t.warn, t.bg);
        keybar(f, Rect::new(r.x + 1, r.y + 1, r.w - 2, 1), &[("1-5", "panels"), ("b", "quarters"), ("n", "mark"), ("f", "at will"), ("[ ]", "broadside"), ("m", "walk"), ("l", "look"), ("q", "menu")], &t);
    } else {
        keybar(f, Rect::new(r.x + 1, r.y, r.w - 2, 2), &[("a/d", "course"), ("w/s", "sail"), ("b", "quarters"), ("n", "mark"), ("f", "fire at will"), ("[ ]", "broadside"), ("1-5", "panels"), ("m", "walk"), ("l", "look"), ("PgUp/Dn", "level"), ("space", "pause"), ("q", "menu")], &t);
    }
}

/// Wrap the log's API for the game (so the log can be scrolled from keys).
pub fn scroll_log(log: &mut Log, by: i32) {
    log.scroll(by);
}

#[allow(dead_code)]
fn role_glyphs() -> Vec<(char, &'static str)> {
    [Role::Captain, Role::Lieutenant, Role::GunCaptain, Role::Topman, Role::Marine, Role::BosunsMate, Role::Boy, Role::Waister].iter().map(|r| (r.glyph(), r.name())).collect()
}

#[allow(dead_code)]
fn unused(_: &ui::Menu) {}
