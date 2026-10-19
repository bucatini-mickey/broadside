//! The glass: a first-person look along a bearing (`docs/legacy/16`, `21`).
//!
//! `t` takes up the glass (a 7 degree field, ten times the eye), `T` looks
//! by eye (70 degrees). The look is held relative to her head, as a man on
//! her deck holds it: three points off the starboard bow stays three points
//! off the bow when she comes round. It tilts, carries a reticle, and `TAB`
//! holds a ship in the field and follows her.
//!
//! What can be seen is `tachyon::sight`: the horizon, the island, smoke and
//! other hulls in the way, the haze. This module adds the naval words for
//! it ("three points on the starboard bow", "her larboard quarter to us",
//! "a brig, hull up, bearing NNE, about 150 m") and the picture.
//!
//! Not simulated yet: raising the glass takes no time; the report is the
//! captain's own and always honest (a lookout's would depend on the man).

use crate::game::Game;
use crate::screen::points;
use crate::ship::{wrap, Ship};
use std::f32::consts::{PI, TAU};
use tachyon::prelude::*;
use tachyon::sight::{self, Air, Band, Field, Obstacle, Seen, Target};

pub const GLASS_FIELD: f32 = 7.0 * PI / 180.0;
pub const EYE_FIELD: f32 = 70.0 * PI / 180.0;
/// How much the glass magnifies (the eye's field over the glass's).
pub const POWER: f32 = 10.0;
/// A point of the compass, 11.25 degrees.
pub const POINT: f32 = TAU / 32.0;
pub const CABLE: f32 = 185.2;
const EYE_ABOVE_DECK: f32 = 1.2;
const MIN_PITCH: f32 = -20.0 * PI / 180.0;
const MAX_PITCH: f32 = 40.0 * PI / 180.0;

#[derive(Clone, Debug)]
pub struct Glass {
    /// The glass (true) or the naked eye.
    pub glass: bool,
    /// Where she looks relative to her head (radians, + to starboard).
    pub rel: f32,
    /// Tilt above the horizontal (radians).
    pub pitch: f32,
    /// Width of the field (radians): `+`/`-` narrow and widen it.
    pub field: f32,
    /// The ship held in the field, if any.
    pub hold: Option<usize>,
}

impl Glass {
    pub fn new(glass: bool) -> Glass {
        Glass { glass, rel: 0.0, pitch: 0.0, field: if glass { GLASS_FIELD } else { EYE_FIELD }, hold: None }
    }

    pub fn power(&self) -> f32 {
        if self.glass { POWER * GLASS_FIELD / self.field } else { 1.0 }
    }

    /// Sweep by `quarters` quarter-fields; lets go of a held ship.
    pub fn sweep(&mut self, quarters: f32) {
        self.hold = None;
        self.rel = wrap(self.rel + quarters * self.field / 4.0);
    }

    pub fn tilt(&mut self, by: f32) {
        self.pitch = (self.pitch + by).clamp(MIN_PITCH, MAX_PITCH);
    }

    /// `+` narrows the field (a glass only), `-` widens it.
    pub fn zoom(&mut self, narrower: bool) {
        let (lo, hi) = if self.glass { (GLASS_FIELD / 2.0, GLASS_FIELD * 2.0) } else { (EYE_FIELD / 2.0, EYE_FIELD * 1.5) };
        self.field = if narrower { self.field / 1.4 } else { self.field * 1.4 }.clamp(lo, hi);
    }

    /// Dead ahead and level.
    pub fn ahead(&mut self) {
        self.hold = None;
        self.rel = 0.0;
        self.pitch = 0.0;
    }

    /// Keep a held ship in the middle of the field (she moves; we turn).
    pub fn follow(&mut self, g: &Game) {
        let Some(i) = self.hold else { return };
        match g.ships.get(i).filter(|s| s.craft.state != tachyon::craft::Floating::Foundered) {
            Some(s) => {
                let you = g.you();
                let b = (s.craft.x - you.craft.x).atan2(-(s.craft.y - you.craft.y));
                self.rel = wrap(b - you.craft.heading);
            }
            None => self.hold = None,
        }
    }

    /// `TAB`: take the next ship in sight into the glass, nearest first.
    pub fn next(&mut self, g: &Game) -> Option<usize> {
        let you = g.you();
        let mut seen: Vec<(f32, usize)> = (1..g.ships.len()).filter(|&i| look(g, i, self.power()).clarity >= 1.0).map(|i| ((g.ships[i].craft.x - you.craft.x).hypot(g.ships[i].craft.y - you.craft.y), i)).collect();
        seen.sort_by(|a, b| a.0.total_cmp(&b.0));
        let at = self.hold.and_then(|h| seen.iter().position(|s| s.1 == h)).map(|k| k + 1).unwrap_or(0);
        self.hold = seen.get(at % seen.len().max(1)).map(|s| s.1);
        self.follow(g);
        self.hold
    }

    /// The compass bearing down the middle of the field.
    pub fn bearing(&self, g: &Game) -> f32 {
        (g.you().craft.heading + self.rel).rem_euclid(TAU)
    }
}

// ------------------------------------------------------------------ words

/// A relative bearing (radians, + to starboard) as a lookout called it:
/// "dead ahead", "three points on the starboard bow", "on the larboard
/// beam", "two points on the larboard quarter", "right astern". The forward
/// quadrants count from ahead, the after ones from astern.
pub fn relative_words(rel: f32) -> String {
    const N: [&str; 8] = ["", "one point", "two points", "three points", "four points", "five points", "six points", "seven points"];
    let rel = wrap(rel);
    let off = rel.abs();
    let side = if rel > 0.0 { "starboard" } else { "larboard" };
    if off < POINT / 2.0 {
        "dead ahead".into()
    } else if off > PI - POINT / 2.0 {
        "right astern".into()
    } else if (off - PI / 2.0).abs() < POINT / 2.0 {
        format!("on the {side} beam")
    } else if off < PI / 2.0 {
        format!("{} on the {side} bow", N[((off / POINT).round() as usize).clamp(1, 7)])
    } else {
        format!("{} on the {side} quarter", N[(((PI - off) / POINT).round() as usize).clamp(1, 7)])
    }
}

/// The same, short: "3pt stbd bow".
pub fn relative_short(rel: f32) -> String {
    let rel = wrap(rel);
    let off = rel.abs();
    let side = if rel > 0.0 { "stbd" } else { "lbd" };
    if off < POINT / 2.0 {
        "ahead".into()
    } else if off > PI - POINT / 2.0 {
        "astern".into()
    } else if (off - PI / 2.0).abs() < POINT / 2.0 {
        format!("{side} beam")
    } else if off < PI / 2.0 {
        format!("{}pt {side} bow", ((off / POINT).round() as i32).clamp(1, 7))
    } else {
        format!("{}pt {side} quarter", (((PI - off) / POINT).round() as i32).clamp(1, 7))
    }
}

/// How she lies to us: where we bear from her (0 bows on, PI stern on,
/// + her starboard side to us). `bearing` is ours to her.
pub fn aspect(her_heading: f32, bearing: f32) -> f32 {
    wrap(bearing + PI - her_heading)
}

/// What of her we see: "bows on", "her starboard bow to us", "broadside
/// on, her larboard side to us", "her larboard quarter to us", "stern on".
pub fn aspect_words(her_heading: f32, bearing: f32) -> String {
    let a = aspect(her_heading, bearing);
    let side = if a > 0.0 { "starboard" } else { "larboard" };
    match a.abs().to_degrees() {
        d if d < 22.5 => "bows on".into(),
        d if d > 157.5 => "stern on".into(),
        d if (67.5..=112.5).contains(&d) => format!("broadside on, her {side} side to us"),
        d if d < 90.0 => format!("her {side} bow to us"),
        _ => format!("her {side} quarter to us"),
    }
}

pub fn aspect_short(her_heading: f32, bearing: f32) -> String {
    let a = aspect(her_heading, bearing);
    let side = if a > 0.0 { "stbd" } else { "lbd" };
    match a.abs().to_degrees() {
        d if d < 22.5 => "bows on".into(),
        d if d > 157.5 => "stern on".into(),
        d if (67.5..=112.5).contains(&d) => format!("broadside ({side})"),
        d if d < 90.0 => format!("{side} bow"),
        _ => format!("{side} quarter"),
    }
}

/// A range as it was called: metres close to, cables further off.
pub fn range_words(m: f32) -> String {
    match m {
        m if m < 300.0 => format!("about {:.0} m", (m / 10.0).round() * 10.0),
        m if m < 1000.0 => format!("about {:.0} m", (m / 50.0).round() * 50.0),
        m => {
            let c = (m / CABLE * 2.0).round() / 2.0;
            if c.fract() == 0.0 { format!("about {c:.0} cables") } else { format!("about {c:.1} cables") }
        }
    }
}

// ------------------------------------------------------------- what is seen

/// Heights of a ship above the water (m): her deck and her trucks.
pub fn heights(s: &Ship) -> (f32, f32) {
    let deck = s.layout.deck_z as f32 + 1.0 - s.craft.waterline;
    (deck.max(0.5), deck + s.class.length_m * 0.45)
}

/// Where the captain's eye is: x, y and height above mean sea level.
pub fn eye(g: &Game) -> (f32, f32, f32) {
    let you = g.you();
    let at = you.you().and_then(|id| you.craft.scene.things.get(id)).map(|t| t.pos()).filter(|p| p.z >= you.layout.deck_z).unwrap_or(you.layout.wheel);
    let w = you.craft.placement().cell_to_world(at);
    (w[0], w[1], w[2] - 0.5 + EYE_ABOVE_DECK)
}

/// The day's light from the hour: full by day, dusk and dawn either side.
pub fn daylight(time: f64) -> f32 {
    let h = ((time / 3600.0) % 24.0) as f32;
    ((h - 5.0).min(19.0 - h) / 1.5).clamp(0.05, 1.0)
}

/// The air between her and everything: haze, smoke, other hulls.
pub fn air(g: &Game, except: usize) -> Air {
    let obstacles = g.ships.iter().enumerate().skip(1).filter(|(i, _)| *i != except).map(|(_, s)| Obstacle { x: s.craft.x, y: s.craft.y, radius: s.class.beam_m / 2.0, top: g.sea.tide() + heights(s).0 }).collect();
    Air { visibility: 25_000.0, light: daylight(g.time), sea_level: g.sea.tide(), waves: g.sea.state().hs, murk: g.smoke.iter().map(|(m, _)| *m).collect(), obstacles }
}

/// Her breadth as seen from `bearing`: her length end-on to her beam.
pub fn breadth(s: &Ship, bearing: f32) -> f32 {
    let a = aspect(s.craft.heading, bearing);
    (s.class.length_m * a.sin().abs()).max(s.class.beam_m * a.cos().abs()).max(s.class.beam_m)
}

/// Look at ship `i` from her quarterdeck with a glass of `power`.
pub fn look(g: &Game, i: usize, power: f32) -> Seen {
    let s = &g.ships[i];
    let e = eye(g);
    let b = (s.craft.x - e.0).atan2(-(s.craft.y - e.1));
    let (deck, top) = heights(s);
    let set = s.set.clamp(0.0, 1.0);
    let t = Target { x: s.craft.x, y: s.craft.y, bottom: g.sea.tide(), top: g.sea.tide() + top, hull: deck, breadth: breadth(s, b), contrast: 0.45 + 0.3 * set };
    sight::look(e, &t, &air(g, i), power, |x, y| g.sea.ground(x, y))
}

/// What she is, as plainly as `seen` lets you say it.
pub fn what(s: &Ship, seen: &Seen) -> String {
    let detail = seen.size / sight::EYE_ANGLE;
    let noun = |k: &str| -> &'static str {
        match k {
            k if k.contains("brig") => "a brig",
            k if k.contains("cutter") => "a cutter",
            k if k.contains("gunboat") => "a gunboat",
            k if k.contains("sloop") => "a sloop of war",
            k if k.contains("frigate") => "a frigate",
            _ => "a ship of the line",
        }
    };
    if seen.clarity >= 3.0 && detail >= 30.0 && !seen.hull_down {
        noun(&s.class.key).into()
    } else if seen.clarity >= 2.0 && detail >= 10.0 {
        match s.layout.masts.len() {
            1 => "a one-master".into(),
            2 => "a two-master".into(),
            _ => "a three-master".into(),
        }
    } else if s.set > 0.05 {
        "a sail".into()
    } else {
        "a hull".into()
    }
}

/// "a brig, hull up, bearing NNE, about 150 m" - and, if she is close
/// enough to tell, how she lies.
pub fn report_one(g: &Game, i: usize, power: f32) -> Option<String> {
    let seen = look(g, i, power);
    if seen.clarity < 1.0 {
        return None;
    }
    let s = &g.ships[i];
    let state = if seen.hull_down { "hull down" } else { "hull up" };
    let mut line = format!("{}, {state}, bearing {}, {}", what(s, &seen), points(seen.bearing), range_words(seen.range));
    if seen.clarity >= 3.0 && seen.size / sight::EYE_ANGLE >= 30.0 {
        line += &format!("; {}", aspect_words(s.craft.heading, seen.bearing));
        if s.struck {
            line += "; her colours are struck";
        }
    }
    let rel = wrap(seen.bearing - g.you().craft.heading);
    line += &format!(" ({})", relative_words(rel));
    Some(line)
}

/// What a look along the glass finds: every ship in the field that can be
/// made out, nearest first.
pub fn report(g: &Game, gl: &Glass) -> Vec<String> {
    let e = eye(g);
    let b = gl.bearing(g);
    let mut inside: Vec<(f32, usize)> = (1..g.ships.len())
        .filter_map(|i| {
            let s = &g.ships[i];
            let (dx, dy) = (s.craft.x - e.0, s.craft.y - e.1);
            (wrap(dx.atan2(-dy) - b).abs() <= gl.field / 2.0).then(|| (dx.hypot(dy), i))
        })
        .collect();
    inside.sort_by(|a, b| a.0.total_cmp(&b.0));
    let out: Vec<String> = inside.iter().filter_map(|&(_, i)| report_one(g, i, gl.power())).collect();
    if out.is_empty() { vec!["Nothing to be made out that way.".into()] } else { out }
}

// ---------------------------------------------------------------- picture

const SKY: Rgb = Rgb(150, 178, 206);
const SEA: Rgb = Rgb(90, 140, 190);
const HULL: Rgb = Rgb(156, 112, 66);
const CANVAS: Rgb = Rgb(236, 232, 218);
const MAST: Rgb = Rgb(200, 162, 104);
const MARK: Rgb = Rgb(250, 232, 170);

/// Fade a colour into the haze over `d` metres.
fn hazed(c: Rgb, d: f32, vis: f32, light: f32) -> Rgb {
    let k = 1.0 - (-3.912 * d / vis).exp();
    c.lerp(SKY, k * 0.85).lerp(Rgb(10, 12, 20), (1.0 - light) * 0.8)
}

/// The pane's title: "THE GLASS x10 - three points on the starboard bow (NE by E 056)".
pub fn title(g: &Game, gl: &Glass) -> String {
    let b = gl.bearing(g);
    let what = if gl.glass { format!("THE GLASS x{:.0}", gl.power()) } else { "BY EYE".into() };
    let tilt = if gl.pitch.abs() > 0.01 { format!(", {:+.0} deg", gl.pitch.to_degrees()) } else { String::new() };
    format!("{what} - {} ({} {:03.0}){tilt}", relative_words(gl.rel), points(b), b.to_degrees())
}

/// Draw the look into `r`.
pub fn draw(f: &mut Frame, g: &Game, gl: &Glass, r: Rect, bg: Rgb) {
    let e = eye(g);
    let air = air(g, usize::MAX);
    let eye_h = e.2 - air.sea_level;
    let fld = Field::new(gl.bearing(g), gl.field, gl.pitch, r.w, r.h - 1, 2.0, 9f32.to_radians());
    let light = air.light;
    // Depth of what is drawn in each cell, so nearer things hide farther.
    let mut depth = vec![f32::INFINITY; (r.w * r.h) as usize];
    let put = |f: &mut Frame, depth: &mut Vec<f32>, c: i32, row: i32, d: f32, ch: char, fg: Rgb| {
        if c < 0 || row < 0 || c >= r.w || row >= r.h - 1 {
            return;
        }
        let k = (row * r.w + c) as usize;
        if d <= depth[k] {
            depth[k] = d;
            f.set(r.x + c, r.y + row, Cell::new(ch, fg, bg));
        }
    };
    f.fill(Rect::new(r.x, r.y, r.w, r.h), Cell::new(' ', SKY, bg));
    // The sea, out to its horizon.
    let hz = fld.horizon_row(eye_h).round().max(0.0) as i32;
    for row in hz..r.h - 1 {
        let el = fld.elevation_of(row);
        let d = if el < 0.0 { eye_h / (-el).tan() } else { sight::horizon(eye_h) };
        for c in 0..r.w {
            let ch = match d {
                d if d < 400.0 => if (c + row) % 3 == 0 { '-' } else { '~' },
                d if d < 2500.0 => if (c * 7 + row * 3) % 5 == 0 { '~' } else { '-' },
                _ => if (c + row) % 4 == 0 { '.' } else { '-' },
            };
            put(f, &mut depth, c, row, f32::MAX, ch, hazed(SEA, d, air.visibility, light));
        }
    }
    // The land.
    let far = (sight::horizon(eye_h) + 4000.0).min(15_000.0);
    let bands: Vec<Vec<Band>> = sight::ground_bands(e, &fld, far, air.sea_level, |x, y| g.sea.ground(x, y));
    for (c, col) in bands.iter().enumerate() {
        for b in col {
            let (ch, fg) = match b.height {
                h if h < 4.0 => ('.', Rgb(214, 196, 140)),
                h if h < 50.0 => ('"', Rgb(124, 160, 84)),
                _ => ('^', Rgb(160, 156, 150)),
            };
            for row in b.top..b.bottom {
                let ch = if row == b.top { ch } else if b.height < 4.0 { '.' } else { ':' };
                put(f, &mut depth, c as i32, row, b.range, ch, hazed(fg, b.range, air.visibility, light));
            }
        }
    }
    // Ships, farthest first.
    let mut order: Vec<usize> = (1..g.ships.len()).collect();
    order.sort_by(|a, b| {
        let d = |i: usize| (g.ships[i].craft.x - e.0).hypot(g.ships[i].craft.y - e.1);
        d(*b).total_cmp(&d(*a))
    });
    for i in order {
        let s = &g.ships[i];
        let seen = look(g, i, gl.power());
        if seen.clarity < 1.0 {
            continue;
        }
        let d = seen.range;
        let faint = seen.clarity < 2.0;
        let shade = |c: Rgb| { let c = hazed(c, d, air.visibility, light); if faint { c.lerp(SKY, 0.5) } else { c } };
        let (deck, top) = heights(s);
        let low = seen.hidden_below - air.sea_level;
        let row_at = |h: f32| fld.row(sight::elevation(eye_h, d, h));
        let col_at = |x: f32, y: f32| fld.column((x - e.0).atan2(-(y - e.1)));
        let (bx, by) = (s.craft.heading.sin(), -s.craft.heading.cos());
        let half = s.class.length_m / 2.0;
        let (sx, sy) = (-by * s.class.beam_m / 2.0, bx * s.class.beam_m / 2.0);
        let ends = [col_at(s.craft.x + bx * half, s.craft.y + by * half), col_at(s.craft.x - bx * half, s.craft.y - by * half), col_at(s.craft.x + sx, s.craft.y + sy), col_at(s.craft.x - sx, s.craft.y - sy)];
        let c0 = ends.iter().cloned().fold(f32::MAX, f32::min).floor() as i32;
        let c1 = (ends.iter().cloned().fold(f32::MIN, f32::max).ceil() as i32 - 1).max(c0);
        // Her hull: a band from the waterline (or what the sea leaves of it) to her rail.
        let (h0, h1) = (row_at(low.max(0.0)).round() as i32, row_at(deck).round() as i32);
        if low < deck {
            let (top, bottom) = (h1.min(h0 - 1), h0.max(h1 + 1));
            for row in top..bottom {
                for c in c0..=c1 {
                    // Her rail as a line when there is room for it under her planking.
                    put(f, &mut depth, c, row, d, if row == top && bottom - top > 2 { '_' } else { '#' }, shade(HULL));
                }
            }
        }
        // Masts, and canvas on them if she has sail set.
        let mid = (s.layout.bow_y + s.layout.stern_y) as f32 / 2.0;
        let yard = s.class.beam_m * 1.8 * (0.4 + 0.6 * aspect(s.craft.heading, seen.bearing).cos().abs());
        for m in &s.layout.masts {
            let along = mid - m.y as f32;
            let (mx, my) = (s.craft.x + bx * along, s.craft.y + by * along);
            let mc = col_at(mx, my).floor() as i32;
            let (t0, t1) = (row_at(top).round() as i32, row_at(deck.max(low)).round() as i32);
            for row in t0..t1 {
                put(f, &mut depth, mc, row, d, '|', shade(MAST));
            }
            if s.set > 0.05 {
                let w = (yard / 2.0 / d / fld.width * fld.cols as f32).max(0.5);
                let (r0, r1) = (row_at(top * 0.92).round() as i32, row_at((deck + 1.5 + (top - deck) * 0.5 * (1.0 - s.set)).max(low)).round() as i32);
                for row in r0..r1 {
                    for c in (mc as f32 - w).round() as i32..=(mc as f32 + w).round() as i32 {
                        put(f, &mut depth, c, row, d - 0.1, if row == r0 { '=' } else { '%' }, shade(CANVAS));
                    }
                }
            }
        }
    }
    // The reticle, on the horizontal down the middle.
    let (mc, mr) = (r.w / 2, (fld.row(0.0).round() as i32).clamp(0, r.h - 3));
    let mark = |f: &mut Frame, c: i32, row: i32, ch: char| {
        if c >= 0 && row >= 0 && c < r.w && row < r.h - 1 {
            f.set(r.x + c, r.y + row, Cell::new(ch, MARK, bg));
        }
    };
    for k in 3..=5 {
        mark(f, mc - k, mr, '-');
        mark(f, mc + k, mr, '-');
    }
    for k in 2..=3 {
        mark(f, mc, mr - k, '|');
        mark(f, mc, mr + k, '|');
    }
    mark(f, mc, mr, '+');
    let note = match gl.hold.and_then(|i| g.ships.get(i)) {
        Some(s) => {
            let b = (s.craft.x - e.0).atan2(-(s.craft.y - e.1));
            format!(" the {}  {}  {} ", s.name, range_words((s.craft.x - e.0).hypot(s.craft.y - e.1)), aspect_short(s.craft.heading, b))
        }
        None => format!(" {} ", relative_short(gl.rel)),
    };
    let ny = mr + 5;
    if ny < r.h - 1 {
        let nx = (mc - note.len() as i32 / 2).clamp(0, (r.w - note.len() as i32).max(0));
        f.text_clip(r.x + nx, r.y + ny, r.w - nx, &note, MARK, bg);
    }
    // The compass along the foot.
    let foot = r.y + r.h - 1;
    f.fill(Rect::new(r.x, foot, r.w, 1), Cell::new('-', Rgb(90, 92, 104), bg));
    for frac in [0.1f32, 0.5, 0.9] {
        let b = fld.bearing_of((frac * r.w as f32) as i32);
        let s = format!(" {} {:03.0} ", points(b), b.to_degrees());
        let x = (frac * r.w as f32) as i32 - s.len() as i32 / 2;
        if x >= 0 && x + s.len() as i32 <= r.w {
            f.text(r.x + x, foot, &s, Rgb(214, 206, 180), bg);
        }
    }
}

/// Mark the field on the chart: its two edges dotted out and the bearing
/// down the middle. `to_screen` maps sea x, y to a chart cell.
pub fn chart_field(g: &Game, gl: &Glass, reach: f32, mut put: impl FnMut(f32, f32, char)) {
    let e = eye(g);
    let b = gl.bearing(g);
    for (a, ch, step) in [(b - gl.field / 2.0, '.', 2), (b + gl.field / 2.0, '.', 2), (b, ':', 3)] {
        for k in 1..=24 {
            if k % step == 0 {
                let d = reach * k as f32 / 24.0;
                put(e.0 + a.sin() * d, e.1 - a.cos() * d, ch);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bearings_in_points_and_aspect() {
        let p = |n: f32| n * POINT;
        assert_eq!(relative_words(0.0), "dead ahead");
        assert_eq!(relative_words(p(3.0)), "three points on the starboard bow");
        assert_eq!(relative_words(-p(8.0)), "on the larboard beam");
        assert_eq!(relative_words(-p(14.0)), "two points on the larboard quarter");
        assert_eq!(relative_words(PI), "right astern");
        assert_eq!(relative_short(p(3.2)), "3pt stbd bow");
        // She heads north, we bear east of her: we see her starboard side.
        assert_eq!(aspect_words(0.0, -PI / 2.0), "broadside on, her starboard side to us");
        assert_eq!(aspect_words(0.0, 0.0), "stern on");
        assert_eq!(aspect_words(PI, 0.0), "bows on");
        assert_eq!(aspect_words(0.0, -PI * 0.7), "her starboard bow to us");
        assert_eq!(range_words(148.0), "about 150 m");
        assert_eq!(range_words(1111.0), "about 6 cables");
    }
}
