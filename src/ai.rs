//! Captains' minds, for every ship you don't command.
//!
//! After `docs/legacy/19_fleet_and_captains.md`: a captain is a person with
//! parameters (skill, wit, aggression, caution) drawn from his own sheet.
//! He chooses a mission and carries it out with exactly the orders a player
//! has (course, sail, quarters, fire, target), so he can do nothing you
//! cannot. A dull captain thinks less often, and so is always a little
//! behind the action.

use crate::crew::Person;
use crate::ship::{wrap, Fire, Ship};
use std::f32::consts::PI;
use tachyon::sea::Sea;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Mission {
    /// Hold her course and keep a lookout.
    Cruise,
    /// Close and fight (with the ship's index).
    Engage(usize),
    /// Break off and run.
    Flee(usize),
    /// Colours struck.
    Struck,
}

#[derive(Clone, Debug)]
pub struct Captain {
    pub skill: f32,
    pub wit: f32,
    pub aggression: f32,
    pub caution: f32,
    pub mission: Mission,
    /// Which beam he likes to fight on (+1 starboard).
    pub side: f32,
    next_think: f32,
}

impl Captain {
    pub fn from(p: &Person) -> Captain {
        Captain {
            skill: (p.skill("seamanship") + p.skill("leadership")) / 2.0,
            wit: p.skill("navigation").max(0.3),
            aggression: p.bravery,
            caution: 1.0 - p.bravery * 0.5 - p.discipline * 0.3,
            mission: Mission::Cruise,
            side: 1.0,
            next_think: 0.0,
        }
    }

    pub fn describe(&self) -> String {
        let m = match self.mission {
            Mission::Cruise => "cruising",
            Mission::Engage(_) => "engaging",
            Mission::Flee(_) => "breaking off",
            Mission::Struck => "struck",
        };
        format!("{m}; skill {:.0}%, wit {:.0}%, dash {:.0}%, caution {:.0}%", self.skill * 100.0, self.wit * 100.0, self.aggression * 100.0, self.caution * 100.0)
    }
}

/// What a captain can see of another ship.
#[derive(Clone, Copy, Debug)]
pub struct Contact {
    pub id: usize,
    pub x: f32,
    pub y: f32,
    pub faction: u16,
    pub struck: bool,
}

/// How hurt a ship is, 0..1: water in her, men down, guns lost.
pub fn hurt(ship: &Ship) -> f32 {
    let (fit, hurt, dead) = ship.muster();
    let men = (hurt + 2 * dead) as f32 / (fit + hurt + dead).max(1) as f32;
    let water = ship.craft.water_inside / ship.craft.mass.max(1.0) * 4.0;
    let guns = ship.guns.iter().filter(|g| g.disabled).count() as f32 / ship.guns.len().max(1) as f32;
    (0.5 * men + 0.35 * water + 0.25 * guns).min(1.0)
}

/// Think (now and then) and set orders.
pub fn command(cap: &mut Captain, ship: &mut Ship, others: &[Contact], sea: &Sea, wind: (f32, f32), dt: f32) {
    if ship.struck {
        cap.mission = Mission::Struck;
    }
    cap.next_think -= dt;
    if cap.next_think <= 0.0 {
        cap.next_think = 3.0 + 12.0 * (1.0 - cap.wit);
        decide(cap, ship, others);
    }
    let foe = |id: usize| others.iter().find(|c| c.id == id).copied();
    match cap.mission {
        Mission::Struck => {
            ship.orders.fire = Fire::Hold;
            ship.orders.sail = 0.0;
            ship.orders.quarters = false;
        }
        Mission::Cruise => {
            ship.orders.fire = Fire::Hold;
            ship.orders.sail = 0.75;
        }
        Mission::Engage(id) => {
            let Some(f) = foe(id) else { return };
            let (dx, dy) = (f.x - ship.craft.x, f.y - ship.craft.y);
            let range = dx.hypot(dy);
            let bearing = dx.atan2(-dy);
            // Far off, steer for her; close in, bring her abeam at his range.
            let close = 250.0 + 500.0 * (1.0 - cap.aggression);
            let k = ((close * 2.5 - range) / (close * 1.5)).clamp(0.0, 1.0);
            let ideal = bearing - cap.side * (PI / 2.0) * k;
            ship.orders.course = Some(sailable(ideal, ship, sea, wind));
            ship.orders.sail = if range < 1500.0 { 0.65 } else { 1.0 };
            ship.orders.quarters = range < 3000.0;
            ship.orders.target = Some(id);
            ship.orders.fire = if range < 1600.0 { Fire::AtWill } else { Fire::Hold };
        }
        Mission::Flee(id) => {
            let Some(f) = foe(id) else { return };
            let away = (ship.craft.x - f.x).atan2(-(ship.craft.y - f.y));
            ship.orders.course = Some(sailable(away, ship, sea, wind));
            ship.orders.sail = 1.0;
            ship.orders.fire = Fire::AtWill;
        }
    }
}

fn decide(cap: &mut Captain, ship: &mut Ship, others: &[Contact]) {
    if cap.mission == Mission::Struck {
        return;
    }
    let me = (ship.craft.x, ship.craft.y);
    let enemy = others
        .iter()
        .filter(|c| c.faction != ship.faction && !c.struck)
        .map(|c| (c, (c.x - me.0).hypot(c.y - me.1)))
        .filter(|(_, r)| *r < 8000.0)
        .min_by(|a, b| a.1.total_cmp(&b.1));
    let h = hurt(ship);
    cap.mission = match enemy {
        None => Mission::Cruise,
        Some((c, r)) => {
            if h > 0.7 - 0.25 * cap.caution && r < 900.0 {
                ship.struck = true;
                ship.notes.push(crate::ship::Note { text: format!("{} strikes her colours!", ship.name), urgent: true });
                Mission::Struck
            } else if h > 0.55 - 0.3 * cap.caution {
                Mission::Flee(c.id)
            } else {
                Mission::Engage(c.id)
            }
        }
    };
}

/// The nearest course to `want` she can lay (nothing within 67 degrees of
/// the wind for a square-rigger) with clear water ahead for a few cables.
pub fn sailable(want: f32, ship: &Ship, sea: &Sea, wind: (f32, f32)) -> f32 {
    let from_wind = wind.0.atan2(-wind.1) + PI;
    let close = if ship.class.rig() == crate::data::Rig::Cutter { 50f32 } else { 67f32 }.to_radians();
    let draft = ship.craft.draft() + 1.5;
    let (x, y) = (ship.craft.x, ship.craft.y);
    let clear = |h: f32| (1..=16).all(|s| sea.water_depth(x + h.sin() * 30.0 * s as f32, y - h.cos() * 30.0 * s as f32) > draft);
    for k in 0..13 {
        let step = 15f32.to_radians() * ((k + 1) / 2) as f32 * if k % 2 == 0 { 1.0 } else { -1.0 };
        let h = want + step;
        if wrap(h - from_wind).abs() >= close && clear(h) {
            return h.rem_euclid(std::f32::consts::TAU);
        }
    }
    want
}
