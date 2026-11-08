//! Fouling: two ships that meet slowly, rails to rails, are lashed and
//! grappled together where they touch. They then move as one pair until
//! hands at the rails cut the lines (a timed job done by the men sent, not
//! a flag). Hard collisions are not fouls: they damage and part as before.
//!
//! Engine-general (for Tachyon, not built): a rigid-pair constraint between
//! two crafts (shared velocity and yaw, fixed relative pose) and a
//! slow-contact event; the rails, the hands and the cutting are naval.

use crate::ship::{wrap, Ship};
use std::f32::consts::TAU;
use tachyon::craft::{Craft, CraftEvent, Floating};
use tachyon::prelude::*;

/// Closing speed (m/s) below which a meeting at the rails fouls (about 2.3 kt).
pub const FOUL_SPEED: f32 = 1.2;
/// Work in man-seconds to cut a pair of ships apart (lashings, grapnels, boarding lines).
pub const LINES: f32 = 60.0;
/// Hands sent from each ship that is ordered to cut free.
pub const CUTTERS: usize = 8;
/// Seconds after parting during which the pair can't foul again.
pub const COOLDOWN: f64 = 30.0;
/// Seconds fouled before an AI captain gives the order to cut free.
pub const AI_PATIENCE: f64 = 45.0;

/// Two ships made fast to each other.
#[derive(Clone, Debug)]
pub struct Foul {
    /// Indices into the ships, a < b.
    pub a: usize,
    pub b: usize,
    /// Where b's pivot lies from a's, along a's fore and starboard axes (m).
    pub off: (f32, f32),
    /// b's heading less a's.
    pub dh: f32,
    /// The rail cell each ship's hands work at, nearest the contact.
    pub rails: [Pos; 2],
    /// People (indices in each ship's `people`) sent to cut.
    pub cutters: [Vec<usize>; 2],
    /// Man-seconds of cutting done.
    pub work: f32,
    pub since: f64,
    /// Each ship's boarding party, if ordered (`board.rs`).
    pub party: [Option<crate::board::Party>; 2],
}

impl Foul {
    pub fn has(&self, i: usize, j: usize) -> bool {
        (self.a, self.b) == (i.min(j), i.max(j))
    }
}

/// The rail cell (weather-deck standing place) nearest a point in her grid.
fn rail_near(s: &Ship, at: [f32; 3]) -> Option<Pos> {
    let z = s.layout.deck_z;
    let (cx, cy) = (at[0].floor() as i32, at[1].floor() as i32);
    let mut best: Option<(i32, Pos)> = None;
    for dy in -8..=8 {
        for dx in -8..=8 {
            let p = Pos::new(cx + dx, cy + dy, z);
            if s.craft.in_footprint(p.x, p.y) && s.craft.scene.world.standable(p) {
                let d = dx * dx + dy * dy;
                if best.map_or(true, |(bd, _)| d < bd) {
                    best = Some((d, p));
                }
            }
        }
    }
    best.map(|b| b.1)
}

/// Try to foul ships `i` < `j` that have just touched at world `at` with
/// closing speed `closing` (m/s). Needs rails on both sides at the contact.
pub fn try_foul(ships: &[Ship], i: usize, j: usize, at: (f32, f32), closing: f32, time: f64) -> Option<Foul> {
    if closing >= FOUL_SPEED {
        return None;
    }
    let (a, b) = (&ships[i], &ships[j]);
    let rail = |s: &Ship| rail_near(s, s.craft.placement().to_local([at.0, at.1, s.craft.z]));
    let (ra, rb) = (rail(a)?, rail(b)?);
    let (fwd, stb) = a.craft.axes();
    let (dx, dy) = (b.craft.x - a.craft.x, b.craft.y - a.craft.y);
    Some(Foul {
        a: i,
        b: j,
        off: (dx * fwd.0 + dy * fwd.1, dx * stb.0 + dy * stb.1),
        dh: wrap(b.craft.heading - a.craft.heading),
        rails: [ra, rb],
        cutters: [Vec::new(), Vec::new()],
        work: 0.0,
        since: time,
        party: [None, None],
    })
}

/// Did this craft just get a collision event from `other`? Returns the point.
pub fn new_contact(c: &Craft, from: usize) -> Option<(f32, f32)> {
    c.events[from..].iter().find_map(|e| match e {
        CraftEvent::Collided { at, .. } => Some(*at),
        _ => None,
    })
}

/// Hold a fouled pair rigid: one velocity, one yaw rate, the same relative
/// pose, found by weighing each ship's own motion this tick by her mass.
pub fn lock(a: &mut Craft, b: &mut Craft, f: &Foul) {
    let (ma, mb) = (a.mass + a.water_inside, b.mass + b.water_inside);
    let (wa, wb) = (ma / (ma + mb), mb / (ma + mb));
    let theta = a.heading + wb * wrap(b.heading - f.dh - a.heading);
    let (s, c) = theta.sin_cos();
    let (fwd, stb) = ((s, -c), (c, s));
    let o = (f.off.0 * fwd.0 + f.off.1 * stb.0, f.off.0 * fwd.1 + f.off.1 * stb.1);
    let ca = (a.x + wb * o.0, a.y + wb * o.1);
    let cb = (b.x - wa * o.0, b.y - wa * o.1);
    let cm = (wa * ca.0 + wb * cb.0, wa * ca.1 + wb * cb.1);
    a.x = cm.0 - wb * o.0;
    a.y = cm.1 - wb * o.1;
    b.x = cm.0 + wa * o.0;
    b.y = cm.1 + wa * o.1;
    a.heading = theta.rem_euclid(TAU);
    b.heading = (theta + f.dh).rem_euclid(TAU);
    let v = (wa * a.vx + wb * b.vx, wa * a.vy + wb * b.vy);
    let yaw = wa * a.yaw_rate + wb * b.yaw_rate;
    a.vx = v.0;
    a.vy = v.1;
    b.vx = v.0;
    b.vy = v.1;
    a.yaw_rate = yaw;
    b.yaw_rate = yaw;
}

/// Is either ship past holding on (foundered, or aground)?
pub fn broken(a: &Ship, b: &Ship) -> bool {
    a.craft.state == Floating::Foundered || b.craft.state == Floating::Foundered
}
