//! A ship in commission: her hull and rig (a [`Craft`]), her company, her
//! guns, and the orders she is under.
//!
//! Orders are a captain's, not a puppeteer's. You order a course; the
//! quartermaster at the wheel steers it (if he is there, and alive). You
//! order sail; the topmen set it, as fast as there are topmen to do it. You
//! beat to quarters; every man goes to his station along the decks and
//! ladders, and the guns are fought by whoever reached them.

use crate::crew::{self, Person, Role};
use crate::data::ShipClass;
use crate::drill::{self, GunState, Store, DRILL, READY};
use crate::hull::{self, GunSlot, Kinds, Layout};
use std::f32::consts::{PI, TAU};
use tachyon::ballistics::{elevation_for, Shot};
use tachyon::craft::Craft;
use tachyon::lang::Culture;
use tachyon::life::mind::{Goal, Routine, Task};
use tachyon::prelude::*;
use tachyon::sea::Sea;

#[inline]
pub fn wrap(a: f32) -> f32 {
    (a + PI).rem_euclid(TAU) - PI
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fire {
    /// Hold fire.
    Hold,
    /// Each gun fires when ready and her mark bears, on the roll.
    AtWill,
    /// Every loaded gun on one side, now (a ripple down her length).
    Broadside(i32),
}

#[derive(Clone, Debug)]
pub struct Orders {
    /// The course to steer (compass radians); None leaves the helm lashed.
    pub course: Option<f32>,
    /// Sail ordered: 0 furled .. 1 all plain sail.
    pub sail: f32,
    pub quarters: bool,
    pub fire: Fire,
    /// The ship the guns are to be laid on.
    pub target: Option<usize>,
}

/// Something that happened aboard, for the log.
#[derive(Clone, Debug)]
pub struct Note {
    pub text: String,
    pub urgent: bool,
}

pub struct Ship {
    pub id: usize,
    pub class: ShipClass,
    pub name: String,
    /// What her name means.
    pub meaning: String,
    pub faction: u16,
    pub craft: Craft,
    pub layout: Layout,
    pub kinds: Kinds,
    pub crew_kinds: Vec<(Role, KindId)>,
    pub people: Vec<Person>,
    pub guns: Vec<GunState>,
    pub orders: Orders,
    /// Canvas actually set, 0..1.
    pub set: f32,
    pub powder: u32,
    pub shot: u32,
    pub struck: bool,
    /// Guns waiting to fire in a ripple: (gun, seconds).
    pub ripple: Vec<(usize, f32)>,
    /// The captain is the player.
    pub player: bool,
    pub notes: Vec<Note>,
    pub rng: Rng,
    rudder: f32,
    last_quarters: bool,
    last_watch: i32,
}

/// What a ship's guns need to know about the mark: where she is, how she
/// moves, and how high her hull stands (sea space).
#[derive(Clone, Copy, Debug)]
pub struct Mark {
    pub x: f32,
    pub y: f32,
    pub vx: f32,
    pub vy: f32,
    pub z: f32,
}

impl Ship {
    /// Fit out and man a ship of `class`.
    #[allow(clippy::too_many_arguments)]
    pub fn new(id: usize, class: &ShipClass, culture: &Culture, faction: u16, x: f32, y: f32, heading: f32, seed: u64, cap: usize, player: bool) -> Ship {
        let mut rng = Rng::new(seed);
        let built = hull::build(class, x, y, heading, seed);
        let (mut craft, layout, kinds) = (built.craft, built.layout, built.kinds);
        let (name, meaning) = culture.ship(&mut rng);
        craft.name = name.clone();
        let crew_kinds = crew::kinds(&mut craft.scene.things);
        let per_gun: Vec<usize> = layout.guns.iter().map(|g| hull::battery(class, g).crew()).collect();
        let mut people = crew::company(culture, class.max_crew as usize, layout.guns.len(), &per_gun, &mut rng);
        let guns = vec![GunState::default(); layout.guns.len()];
        let mut ship = Ship {
            id,
            class: class.clone(),
            name,
            meaning,
            faction,
            craft,
            layout,
            kinds,
            crew_kinds,
            people: Vec::new(),
            guns,
            orders: Orders { course: Some(heading), sail: 0.75, quarters: false, fire: Fire::Hold, target: None },
            set: 0.75,
            powder: 0,
            shot: 0,
            struck: false,
            ripple: Vec::new(),
            player,
            notes: Vec::new(),
            rng,
            rudder: 0.0,
            last_quarters: false,
            last_watch: -1,
        };
        ship.powder = ship.guns.len() as u32 * 40;
        ship.shot = ship.guns.len() as u32 * 40;
        // Embark the company, the men who matter on deck first.
        let order = |p: &Person| match p.role {
            Role::Captain => 0,
            Role::Lieutenant | Role::Midshipman => 1,
            Role::Helmsman => 2,
            Role::GunCaptain | Role::Gunner => 3,
            Role::Topman => 4,
            Role::Marine => 5,
            _ => 6,
        };
        let mut idx: Vec<usize> = (0..people.len()).collect();
        idx.sort_by_key(|&i| order(&people[i]));
        let mut used: Vec<Pos> = Vec::new();
        for (n, i) in idx.into_iter().enumerate() {
            if n >= cap {
                break;
            }
            let want = ship.station_of(&people[i], true).unwrap_or(ship.layout.captain);
            let Some(at) = ship.free_spot(want, &used) else { continue };
            used.push(at);
            let control = if player && people[i].role == Role::Captain { Control::Player } else { Control::Ai };
            crew::embark(&mut ship.craft.scene, &ship.crew_kinds, &mut people[i], at, control, faction);
        }
        ship.people = people;
        ship.craft.scene.clock = Clock::new(1.0, 10.0);
        ship.assign(false);
        ship
    }

    /// The nearest free standing place to `want` (within a few cells).
    fn free_spot(&self, want: Pos, used: &[Pos]) -> Option<Pos> {
        let w = &self.craft.scene.world;
        for r in 0..4 {
            for dy in -r..=r {
                for dx in -r..=r {
                    let p = want.offset(dx, dy, 0);
                    if w.standable(p) && !used.contains(&p) && !self.craft.scene.things.blocks_move(p) && self.craft.in_hull_or_deck(p) {
                        return Some(p);
                    }
                }
            }
        }
        // A crowded little ship: anywhere aboard there is room, deck first, then below.
        for z in (1..=self.layout.deck_z).rev() {
            for y in 0..w.h {
                for x in 0..w.w {
                    let p = Pos::new(x, y, z);
                    if w.standable(p) && !used.contains(&p) && !self.craft.scene.things.blocks_move(p) && self.craft.in_hull_or_deck(p) {
                        return Some(p);
                    }
                }
            }
        }
        None
    }

    pub fn captain(&self) -> &Person {
        &self.people[0]
    }

    /// The player's own creature (the captain), if the player commands her.
    pub fn you(&self) -> Option<ThingId> {
        if self.player { self.people[0].thing } else { None }
    }

    pub fn alive(&self, p: &Person) -> bool {
        match p.thing {
            Some(id) => self.craft.scene.life.get(id).is_some_and(|c| c.alive),
            None => true,
        }
    }

    pub fn able(&self, p: &Person) -> bool {
        match p.thing {
            Some(id) => self.craft.scene.life.get(id).is_some_and(|c| c.alive && !c.out),
            None => true,
        }
    }

    pub fn pos_of(&self, p: &Person) -> Option<Pos> {
        p.thing.and_then(|id| self.craft.scene.things.get(id)).map(|t| t.pos())
    }

    /// Men fit for duty, and the dead.
    pub fn muster(&self) -> (usize, usize, usize) {
        let mut fit = 0;
        let mut hurt = 0;
        let mut dead = 0;
        for p in &self.people {
            match p.thing.and_then(|id| self.craft.scene.life.get(id)) {
                Some(c) if !c.alive => dead += 1,
                Some(c) if c.out || c.caps.moving < 0.5 || c.body.bleeding() > 0.0 => hurt += 1,
                _ => fit += 1,
            }
        }
        (fit, hurt, dead)
    }

    /// Where a man should be: at quarters, or about the ship in his watch.
    pub fn station_of(&self, p: &Person, quarters: bool) -> Option<Pos> {
        let l = &self.layout;
        let ix = |v: &Vec<Pos>, k: usize| if v.is_empty() { None } else { Some(v[k % v.len()]) };
        let k = self.people.iter().position(|q| q.thing == p.thing && q.given == p.given).unwrap_or(0);
        match p.role {
            Role::Captain => Some(l.captain),
            Role::Lieutenant | Role::Midshipman => ix(&l.officers, k),
            Role::Helmsman => Some(if k % 2 == 1 || !quarters { l.helm } else { l.helm.offset(0, 1, 0) }),
            Role::GunCaptain | Role::Gunner if quarters => {
                let (g, n) = p.gun?;
                let slot = l.guns.get(g)?;
                Some(slot.crew.get(n).copied().unwrap_or(slot.crew.first().copied().unwrap_or(slot.pos)))
            }
            Role::Topman => ix(&l.topmen, k),
            Role::Marine if quarters => ix(&l.marines, k),
            _ => ix(&l.waist, k),
        }
    }

    /// Send everyone to their places: stations at quarters; otherwise the
    /// watch on deck about the ship, the watch below in their hammocks.
    pub fn assign(&mut self, quarters: bool) {
        let watch = (self.craft.scene.clock.hour() / 4.0) as i32 % 2;
        let mut berth = 0usize;
        for i in 0..self.people.len() {
            let p = self.people[i].clone();
            let Some(id) = p.thing else { continue };
            if self.player && p.role == Role::Captain {
                continue;
            }
            let on_deck = quarters || matches!(p.role, Role::Captain | Role::Lieutenant | Role::Midshipman | Role::Helmsman) || (p.starboard_watch == (watch == 0));
            let task = if on_deck {
                match self.station_of(&p, quarters) {
                    Some(at) if quarters => Task::Stay { at },
                    Some(at) => Task::Work { at, radius: 1 },
                    None => continue,
                }
            } else {
                let at = self.layout.berths.get(berth % self.layout.berths.len().max(1)).copied();
                berth += 1;
                Task::Sleep { at }
            };
            if let Some(c) = self.craft.scene.life.get_mut(id) {
                c.mind.routine = Routine::new().with(0.0, 24.0, task);
                c.mind.next_plan = 0;
                c.mind.next_think = 0;
                c.mind.path.clear();
                c.mind.goal = Goal::Idle(0);
                if quarters {
                    c.mind.asleep = false;
                }
            }
        }
        // Lower-deck ports are opened for action and shut at sea.
        for g in &self.layout.guns {
            if !g.weather {
                let t = if quarters { Tile::Floor } else { Tile::Wall };
                let m = self.craft.scene.world.mats.id(if quarters { "deal" } else { "oak" });
                self.craft.scene.world.set_tile(g.port, t, m);
            }
        }
    }

    /// Is this man where his job is (within reach of it)?
    fn at_post(&self, p: &Person, post: Pos) -> bool {
        match self.pos_of(p) {
            Some(q) => q.z == post.z && q.dist2d(post) <= 1,
            None => true, // not embarked: counted as doing his duty below
        }
    }

    fn physique(&self, p: &Person) -> (f32, f32) {
        match p.thing.and_then(|id| self.craft.scene.life.get(id)) {
            Some(c) => (0.45 * c.caps.grasp + 0.35 * c.caps.grasp.min(c.caps.moving) + 0.2 * c.caps.moving, c.needs.fatigue),
            None => (1.0, 0.2),
        }
    }

    fn note(&mut self, text: impl Into<String>, urgent: bool) {
        self.notes.push(Note { text: text.into(), urgent });
    }

    /// One tick of command, crew and guns (`dt` seconds). Returns the shot
    /// she fires. `mark` describes the ship her guns are laid on.
    pub fn step(&mut self, dt: f32, sea: &Sea, wind: (f32, f32), mark: Option<Mark>) -> Vec<Shot> {
        let mut fired = Vec::new();
        if self.craft.state == tachyon::craft::Floating::Foundered {
            return fired;
        }
        // Quarters: send them to their stations when the order changes, and
        // change the watch every four hours.
        let watch = (self.craft.scene.clock.hour() / 4.0) as i32;
        if self.orders.quarters != self.last_quarters || (!self.orders.quarters && watch != self.last_watch) {
            if self.orders.quarters && !self.last_quarters {
                self.note("The drum beats to quarters.", false);
            } else if !self.orders.quarters && self.last_quarters {
                self.note("Stand down from quarters.", false);
            }
            self.assign(self.orders.quarters);
            self.last_quarters = self.orders.quarters;
            self.last_watch = watch;
        }

        self.steer(dt);
        self.make_sail(dt, wind);
        if self.orders.quarters {
            self.drill(dt, mark);
        }
        self.fire(dt, sea, mark, &mut fired);
        fired
    }

    /// The quartermaster steers the ordered course from the wheel.
    fn steer(&mut self, dt: f32) {
        let helm = self.layout.helm;
        let wheel = self.people.iter().find(|p| p.role == Role::Helmsman && self.able(p) && self.at_post(p, helm)).cloned();
        let Some(course) = self.orders.course else {
            self.craft.helm(self.rudder);
            return;
        };
        match wheel {
            Some(q) => {
                let err = wrap(course - self.craft.heading);
                let skill = q.skill("helm");
                let want = (1.3 * err - (3.0 + 2.0 * skill) * self.craft.yaw_rate).clamp(-0.6, 0.6);
                // A green hand puts the helm over late and in jerks.
                let rate = (0.4 + skill) * dt;
                self.rudder += (want - self.rudder).clamp(-rate, rate);
            }
            None => {
                // Nobody at the wheel: she steers herself, badly.
                self.rudder *= 1.0 - 0.1 * dt;
            }
        }
        self.craft.helm(self.rudder);
    }

    /// Topmen set and take in canvas; the bosun trims the yards to the wind.
    fn make_sail(&mut self, dt: f32, wind: (f32, f32)) {
        let mut topwork = 0.0;
        for p in &self.people {
            if p.role == Role::Topman && self.able(p) {
                topwork += 0.5 + p.skill("topwork");
            }
        }
        let need = (self.class.max_crew as f32 * 0.18).max(4.0);
        // A full company sets her whole plan in about half a minute.
        let rate = (topwork / need).min(1.5) / 30.0;
        let d = self.orders.sail - self.set;
        self.set += d.clamp(-rate * dt * 1.5, rate * dt);
        let set = self.set;
        let (fwd, stb) = self.craft.axes();
        let (ax, ay) = (wind.0 - self.craft.vx, wind.1 - self.craft.vy);
        let m = ax.hypot(ay).max(1e-3);
        let (nx, ny) = (ax / m + fwd.0, ay / m + fwd.1);
        let mut a = (-(nx * fwd.0 + ny * fwd.1)).atan2(nx * stb.0 + ny * stb.1);
        if a > PI / 2.0 {
            a -= PI;
        } else if a <= -PI / 2.0 {
            a += PI;
        }
        let square = if a >= 0.0 { a.clamp(0.95, PI / 2.0) } else { a.clamp(-PI / 2.0, -0.95) };
        // Fore-and-aft sails sheeted to the wind on the lee side.
        let rel = wrap(ay.atan2(ax) - (fwd.1.atan2(fwd.0)));
        let sheet = (rel.abs().min(PI) * 0.45).clamp(0.1, 1.3) * if rel > 0.0 { -1.0 } else { 1.0 };
        for f in self.craft.foils.iter_mut().filter(|f| f.medium == tachyon::craft::Medium::Air) {
            f.set = set;
            if matches!(f.name.as_str(), "fore" | "main" | "mizzen") {
                f.angle = square;
            } else {
                f.angle = sheet;
            }
        }
    }

    /// The gun crews at work.
    fn drill(&mut self, dt: f32, mark: Option<Mark>) {
        let place = self.craft.placement();
        for g in 0..self.guns.len() {
            if self.guns[g].disabled || self.guns[g].step >= READY {
                // A ready gun is relaid if her mark has moved on.
                if self.guns[g].step >= READY {
                    if let Some(m) = mark {
                        let (train, range) = self.bearing_to(g, &place, m);
                        let off = (train - self.guns[g].train).abs() > 0.05 || (range - self.guns[g].judged).abs() > 0.15 * range;
                        if train.abs() <= drill::MAX_TRAIN && off {
                            self.guns[g].step = READY - 1;
                            self.guns[g].done = 0.0;
                        }
                    }
                }
                continue;
            }
            let slot = self.layout.guns[g].clone();
            let step = &DRILL[self.guns[g].step];
            // The crew of this gun who are at it.
            let crew: Vec<usize> = (0..self.people.len())
                .filter(|&i| self.people[i].gun.is_some_and(|(gg, _)| gg == g) && self.able(&self.people[i]))
                .filter(|&i| {
                    let post = self.station_of(&self.people[i], true).unwrap_or(slot.pos);
                    self.at_post(&self.people[i], post)
                })
                .collect();
            if crew.is_empty() {
                self.guns[g].waiting = "no crew at her";
                continue;
            }
            if let Some(store) = step.takes {
                let left = if store == Store::Powder { self.powder } else { self.shot };
                if left == 0 && self.guns[g].done == 0.0 {
                    self.guns[g].waiting = if store == Store::Powder { "no powder" } else { "no shot" };
                    continue;
                }
            }
            self.guns[g].waiting = "";
            // The man whose job it is, or whoever is nearest to doing it.
            let own = crew.iter().copied().find(|&i| self.people[i].gun.unwrap().1 == step.station);
            let who = own.unwrap_or_else(|| *crew.iter().min_by_key(|&&i| (self.people[i].gun.unwrap().1 as i32 - step.station as i32).abs()).unwrap());
            if self.guns[g].by != Some(who) || self.guns[g].needs <= 0.0 {
                let p = &self.people[who];
                let (phys, fat) = self.physique(p);
                let b = hull::battery(&self.class, &slot);
                self.guns[g].needs = drill::step_time(step, p.skill(step.skill), fat, phys, b.ball_kg(), b.gun_kg(), crew.len(), own.is_some());
                self.guns[g].by = Some(who);
            }
            self.guns[g].done += dt;
            if self.guns[g].done >= self.guns[g].needs {
                match step.takes {
                    Some(Store::Powder) => self.powder = self.powder.saturating_sub(1),
                    Some(Store::Shot) => self.shot = self.shot.saturating_sub(1),
                    None => {}
                }
                if self.guns[g].step == READY - 1 {
                    self.lay(g, &place, mark, who);
                }
                self.guns[g].step += 1;
                self.guns[g].done = 0.0;
                self.guns[g].needs = 0.0;
                self.guns[g].by = None;
            }
        }
    }

    /// Training needed (radians, + toward the bow) and range to the mark.
    fn bearing_to(&self, g: usize, place: &tachyon::ballistics::Placement, m: Mark) -> (f32, f32) {
        let slot = &self.layout.guns[g];
        let muzzle = place.to_world([slot.port.x as f32 + 0.5, slot.port.y as f32 + 0.5, slot.port.z as f32 + 0.7]);
        let (dx, dy) = (m.x - muzzle[0], m.y - muzzle[1]);
        let range = dx.hypot(dy);
        let l = place.dir_to_local([dx / range.max(1.0), dy / range.max(1.0), 0.0]);
        // Local +x is starboard; the bow is -y.
        let train = (-l[1]).atan2(l[0] * slot.side as f32);
        (train, range)
    }

    /// The gun captain lays his piece: trains it on the mark if she is in
    /// its arc, judges the range by eye (as well as his skill lets him), and
    /// elevates for it.
    fn lay(&mut self, g: usize, place: &tachyon::ballistics::Placement, mark: Option<Mark>, who: usize) {
        let slot = self.layout.guns[g].clone();
        let b = hull::battery(&self.class, &slot);
        let Some(m) = mark else {
            self.guns[g].train = 0.0;
            self.guns[g].elevation = 0.01;
            return;
        };
        let (train, range) = self.bearing_to(g, place, m);
        if train.abs() > PI / 2.0 {
            // Her mark is on the other side: this gun is laid level and waits.
            self.guns[g].train = 0.0;
            self.guns[g].elevation = 0.01;
            self.guns[g].judged = range;
            return;
        }
        if train.abs() > drill::MAX_TRAIN || range > 2500.0 {
            self.guns[g].train = train.clamp(-drill::MAX_TRAIN, drill::MAX_TRAIN);
            self.guns[g].elevation = 0.01;
            self.guns[g].judged = range;
            return;
        }
        let skill = self.people[who].skill("gunlaying");
        let err = (self.rng.f32() + self.rng.f32() - 1.0) * 0.25 * (1.0 - skill);
        let judged = range * (1.0 + err);
        let muzzle_z = place.to_world([slot.port.x as f32 + 0.5, slot.port.y as f32 + 0.5, slot.port.z as f32 + 0.7])[2];
        let e = elevation_for(b.ball_kg(), b.muzzle_speed(), judged, muzzle_z - (m.z + 1.0)).unwrap_or(drill::MAX_ELEV);
        // Lead her a little for her motion across the line of fire.
        let tof = judged / (b.muzzle_speed() * 0.8);
        let lead = {
            let (fwd, _) = self.craft.axes();
            let along = (m.vx - self.craft.vx) * fwd.0 + (m.vy - self.craft.vy) * fwd.1;
            (along * tof / judged.max(1.0)).atan()
        };
        self.guns[g].train = (train + lead).clamp(-drill::MAX_TRAIN, drill::MAX_TRAIN);
        self.guns[g].elevation = e.clamp(drill::MIN_ELEV, drill::MAX_ELEV);
        self.guns[g].judged = range;
    }

    fn fire(&mut self, dt: f32, _sea: &Sea, mark: Option<Mark>, out: &mut Vec<Shot>) {
        if let Fire::Broadside(side) = self.orders.fire {
            let mut n = 0;
            for g in 0..self.guns.len() {
                if self.layout.guns[g].side == side && self.guns[g].ready() && !self.ripple.iter().any(|(r, _)| *r == g) {
                    let delay = n as f32 * 0.35 + self.rng.f32() * 0.3;
                    self.ripple.push((g, delay));
                    n += 1;
                }
            }
            self.orders.fire = Fire::Hold;
            if n == 0 {
                self.note("No gun on that side is ready.", false);
            }
        }
        if self.orders.fire == Fire::AtWill {
            let place = self.craft.placement();
            for g in 0..self.guns.len() {
                if !self.guns[g].ready() || self.ripple.iter().any(|(r, _)| *r == g) {
                    continue;
                }
                let Some(m) = mark else { continue };
                let (train, range) = self.bearing_to(g, &place, m);
                // He fires as she comes level on the roll, his mark in the arc.
                if train.abs() <= drill::MAX_TRAIN && range < 1800.0 && self.craft.roll.abs() < 0.035 {
                    self.ripple.push((g, self.rng.f32() * 0.5));
                }
            }
        }
        let mut i = 0;
        while i < self.ripple.len() {
            self.ripple[i].1 -= dt;
            if self.ripple[i].1 <= 0.0 {
                let g = self.ripple[i].0;
                self.ripple.swap_remove(i);
                if self.guns[g].ready() {
                    out.push(self.discharge(g));
                }
            } else {
                i += 1;
            }
        }
    }

    /// One gun goes off.
    fn discharge(&mut self, g: usize) -> Shot {
        let place = self.craft.placement();
        let slot: GunSlot = self.layout.guns[g].clone();
        let b = hull::battery(&self.class, &slot);
        let side = slot.side as f32;
        let (t, e) = (self.guns[g].train, self.guns[g].elevation);
        let jit = |r: &mut Rng| (r.f32() - 0.5) * 0.01;
        let (t, e) = (t + jit(&mut self.rng), e + jit(&mut self.rng));
        let local = [side * e.cos() * t.cos(), -e.cos() * t.sin(), e.sin()];
        let d = place.dir_to_world(local);
        let muzzle = place.to_world([slot.port.x as f32 + 0.5 + side * 1.2, slot.port.y as f32 + 0.5, slot.port.z as f32 + 0.7]);
        let v = b.muzzle_speed();
        // Smoke in her own grid at the port, drifting on the wind she feels.
        if let Some(smoke) = self.craft.scene.world.mats.find("smoke") {
            self.craft.scene.world.add_gas(slot.port, smoke, 230);
        }
        self.guns[g].fire();
        Shot::ball(b.ball_kg(), muzzle, [self.craft.vx + d[0] * v, self.craft.vy + d[1] * v, d[2] * v]).from(self.id)
    }

    /// A hand to steer her for the player: the course as ordered, nudged.
    pub fn alter_course(&mut self, by: f32) {
        let c = self.orders.course.unwrap_or(self.craft.heading);
        self.orders.course = Some((c + by).rem_euclid(TAU));
    }

    /// The guns that bear on a side and are ready, and how many there are.
    pub fn battery_state(&self, side: i32) -> (usize, usize) {
        let mut ready = 0;
        let mut total = 0;
        for (g, s) in self.layout.guns.iter().zip(&self.guns) {
            if s.disabled || g.side != side {
                continue;
            }
            total += 1;
            if s.ready() {
                ready += 1;
            }
        }
        (ready, total)
    }
}

/// Whether a cell of her grid is part of her (hull, decks) rather than the
/// sea round her: for putting men aboard.
trait Aboard {
    fn in_hull_or_deck(&self, p: Pos) -> bool;
}

impl Aboard for Craft {
    fn in_hull_or_deck(&self, p: Pos) -> bool {
        self.in_footprint(p.x, p.y)
    }
}
