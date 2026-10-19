//! The world at sea: ships, the sea itself, shot in flight, and what each
//! hit does to timber and to men.

use crate::ai::{self, Captain, Contact};
use crate::crew::Role;
use crate::data::{self, ShipClass};
use crate::ship::{Fire, Mark, Ship};
use tachyon::ballistics::{Ballistics, Body, ShotEvent, V3};
use tachyon::craft::{self, CraftEvent};
use tachyon::lang::Culture;
use tachyon::life::body::{DamageKind, Height, WoundKind};
use tachyon::life::LifeEvent;
use tachyon::prelude::*;
use tachyon::sea::{Sea, SeaSettings, Whirlpool};
use tachyon::sight::Murk;
use tachyon::ui::Log;

/// Game seconds per tick.
pub const SECS: f64 = 0.5;

/// A flash, a splash, a strike: drawn for a moment where it happened.
#[derive(Clone, Copy, Debug)]
pub struct Mark2 {
    pub at: V3,
    pub ch: char,
    pub fg: Rgb,
    pub ttl: f32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scenario {
    /// A brig against a brig, off an island.
    Action,
    /// Two frigates.
    FrigateDuel,
    /// A sloop against a brig and a cutter.
    Odds,
    /// Two 74s.
    TheLine,
    /// A ship of your choice, the sea, nobody else.
    FreeSailing(usize),
}

impl Scenario {
    pub fn title(self) -> String {
        match self {
            Scenario::Action => "Single action: brig against brig".into(),
            Scenario::FrigateDuel => "Frigate duel".into(),
            Scenario::Odds => "Against the odds: your sloop, a brig and a cutter".into(),
            Scenario::TheLine => "Ship of the line: 74 against 74".into(),
            Scenario::FreeSailing(_) => "Free sailing".into(),
        }
    }
}

pub struct Game {
    pub sea: Sea,
    pub ships: Vec<Ship>,
    pub captains: Vec<Option<Captain>>,
    pub shots: Ballistics,
    pub smoke: Vec<(Murk, f32)>,
    pub marks: Vec<Mark2>,
    pub log: Log,
    pub wind: (f32, f32),
    pub cultures: Vec<Culture>,
    pub rng: Rng,
    pub time: f64,
    pub over: Option<String>,
    pub classes: Vec<ShipClass>,
}

/// Bathymetry for the scenarios: open water, a high island to the north
/// with a reef off its point, and a smaller one to the east.
fn depth(x: f32, y: f32) -> f32 {
    let isle = |cx: f32, cy: f32, r: f32, h: f32| {
        let d = ((x - cx).powi(2) + (y - cy).powi(2)).sqrt() / r;
        if d < 1.0 { h * (1.0 - d * d) } else { 0.0 }
    };
    let land = isle(3000.0, 2400.0, 1200.0, 110.0).max(isle(6200.0, 3000.0, 700.0, 40.0));
    let reef = isle(4300.0, 3300.0, 260.0, 58.0);
    if land > 0.0 {
        let coast = 1.0 - (land / 8.0).min(1.0);
        -land + coast * 12.0 - 2.0
    } else {
        60.0 - reef
    }
}

impl Game {
    pub fn new(scenario: Scenario, seed: u64) -> Game {
        let classes = data::load_all();
        let class = |k: &str| classes.iter().find(|c| c.key == k).cloned().unwrap_or_else(|| classes[0].clone());
        let settings = SeaSettings { res: 16.0, tide_range: 2.0, tidal_stream: (0.4, -0.2), steady: (0.05, 0.0), eddy_threshold: 0.8, seed: seed as u32, ..Default::default() };
        let mut sea = Sea::new(512, 512, settings, depth);
        sea.add_whirlpool(Whirlpool::new(4800.0, 2600.0, 40.0, 3.0, 1.0));
        let wind = (2.0, -8.5);
        sea.set_time(10.0 * 3600.0);
        sea.settle(wind);
        let cultures = vec![Culture::new(seed.wrapping_mul(31) + 1), Culture::new(seed.wrapping_mul(31) + 2)];
        let mut g = Game {
            sea,
            ships: Vec::new(),
            captains: Vec::new(),
            shots: Ballistics::new(seed),
            smoke: Vec::new(),
            marks: Vec::new(),
            log: Log::new(400),
            wind,
            cultures,
            rng: Rng::new(seed),
            time: 10.0 * 3600.0,
            over: None,
            classes: classes.clone(),
        };
        let (you, them): (Vec<(&str, f32, f32, f32)>, Vec<(&str, f32, f32, f32)>) = match scenario {
            Scenario::Action => (vec![("brig_14", 3000.0, 5000.0, 0.4)], vec![("brig_14", 3900.0, 4300.0, 4.7)]),
            Scenario::FrigateDuel => (vec![("frigate_38", 2800.0, 5200.0, 0.4)], vec![("frigate_38", 4000.0, 4200.0, 4.5)]),
            Scenario::Odds => (vec![("sloop_18", 3000.0, 5200.0, 0.3)], vec![("brig_14", 4000.0, 4300.0, 4.6), ("cutter_8", 4400.0, 4700.0, 4.9)]),
            Scenario::TheLine => (vec![("ship_of_the_line_74", 2900.0, 5300.0, 0.4)], vec![("ship_of_the_line_74", 4100.0, 4200.0, 4.5)]),
            Scenario::FreeSailing(i) => (vec![(classes.get(i).map(|c| c.key.as_str()).unwrap_or("brig_14"), 3000.0, 5000.0, 0.4)], vec![]),
        };
        for (k, x, y, h) in you {
            g.add_ship(&class(k), 0, x, y, h, true);
        }
        for (k, x, y, h) in them {
            g.add_ship(&class(k), 1, x, y, h, false);
        }
        let you = &g.ships[0];
        let line = format!("You command the {} \"{}\", {} ({} guns, {} men). Your people are the {}.", you.name, you.meaning, you.class.name, you.guns.len(), you.class.max_crew, g.cultures[0].adjective);
        g.say(line, Rgb(236, 222, 180));
        if g.ships.len() > 1 {
            let names: Vec<String> = g.ships[1..].iter().map(|s| format!("the {} ({})", s.name, s.class.name)).collect();
            g.say(format!("{} of the {} in sight to the north-east.", names.join(" and "), g.cultures[1].name), Rgb(236, 222, 180));
            g.say("Beat to quarters (b), name your mark (n), and fire as they bear (f) or by broadside ([ and ]).", Rgb(170, 170, 180));
        }
        g
    }

    fn add_ship(&mut self, class: &ShipClass, faction: u16, x: f32, y: f32, heading: f32, player: bool) {
        let id = self.ships.len();
        let seed = self.rng.next_u64();
        let cap = if player { 220 } else { 130 };
        let mut s = Ship::new(id, class, &self.cultures[faction as usize], faction, x, y, heading, seed, cap, player);
        s.craft.z = self.sea.tide();
        s.craft.scene.clock = Clock::new(SECS, 10.0);
        // Every ship keeps the same time.
        s.craft.scene.clock.start_secs = self.time;
        let cap = if player { None } else { Some(Captain::from(&s.people[0])) };
        self.ships.push(s);
        self.captains.push(cap);
    }

    pub fn say(&mut self, s: impl Into<String>, c: Rgb) {
        let h = (self.time / 3600.0) % 24.0;
        let stamp = format!("{:02}:{:02} ", h as u32, ((h.fract()) * 60.0) as u32);
        self.log.push(stamp + &s.into(), c);
    }

    pub fn you(&self) -> &Ship {
        &self.ships[0]
    }

    pub fn mark_of(&self, id: usize) -> Option<Mark> {
        let s = self.ships.get(id)?;
        Some(Mark { x: s.craft.x, y: s.craft.y, vx: s.craft.vx, vy: s.craft.vy, z: self.sea.tide() })
    }

    /// Advance the world one tick.
    pub fn tick(&mut self) {
        let dt = SECS as f32;
        self.time += SECS;
        self.sea.step(dt, self.wind);
        // Captains decide.
        let contacts: Vec<Contact> = self.ships.iter().map(|s| Contact { id: s.id, x: s.craft.x, y: s.craft.y, faction: s.faction, struck: s.struck }).collect();
        for i in 0..self.ships.len() {
            if let Some(cap) = self.captains[i].as_mut() {
                ai::command(cap, &mut self.ships[i], &contacts, &self.sea, self.wind, dt);
            }
        }
        // Ships work: helm, sail, guns.
        let marks: Vec<Option<Mark>> = (0..self.ships.len()).map(|i| self.ships[i].orders.target.and_then(|t| self.mark_of(t))).collect();
        for i in 0..self.ships.len() {
            let fired = self.ships[i].step(dt, &self.sea, self.wind, marks[i]);
            for s in fired {
                self.marks.push(Mark2 { at: s.pos, ch: '*', fg: Rgb(255, 214, 120), ttl: 1.0 });
                self.smoke.push((Murk { x: s.pos[0], y: s.pos[1], radius: 10.0, top: 20.0, visibility: 40.0 }, 90.0));
                self.shots.fire(s);
            }
        }
        // Hulls float, sail and roll; their people live.
        for s in &mut self.ships {
            s.craft.step(&self.sea, self.wind);
        }
        collide_ships(&mut self.ships);
        // Shot in flight.
        {
            let mut bodies: Vec<Body> = self.ships.iter_mut().map(|s| s.craft.body(s.id)).collect();
            self.shots.step(dt, Some(&self.sea), self.wind, &mut bodies);
        }
        let events = std::mem::take(&mut self.shots.events);
        for s in self.ships.iter_mut() {
            s.craft.take_hits(s.id, &events, &self.sea);
        }
        self.hits(&events);
        self.news();
        // Smoke drifts and thins; flashes fade.
        for (m, ttl) in &mut self.smoke {
            m.x += self.wind.0 * dt;
            m.y += self.wind.1 * dt;
            m.radius += 0.25 * dt;
            *ttl -= dt;
        }
        self.smoke.retain(|(_, t)| *t > 0.0);
        for m in &mut self.marks {
            m.ttl -= dt;
        }
        self.marks.retain(|m| m.ttl > 0.0);
        self.check_end();
    }

    /// What shot did: splinters among the men, guns dismounted, men struck.
    fn hits(&mut self, events: &[ShotEvent]) {
        let mut struck = vec![0u32; self.ships.len()];
        for e in events {
            match e {
                ShotEvent::Struck { body, cell, energy, through, .. } => {
                    struck[*body] += 1;
                    let at = self.ships[*body].craft.placement().cell_to_world(*cell);
                    self.marks.push(Mark2 { at, ch: '#', fg: Rgb(255, 150, 60), ttl: 3.0 });
                    // Splinters: a ball through oak throws a spray of jagged
                    // wood inboard, which did more killing than the shot.
                    if *through || *energy > 30_000.0 {
                        let n = (energy / 40_000.0).clamp(0.5, 6.0);
                        self.splinters(*body, *cell, n);
                    }
                }
                ShotEvent::HitThing { body, thing, cell, energy, .. } => {
                    let ship = &mut self.ships[*body];
                    let kind = ship.craft.scene.things.get(*thing).map(|t| ship.craft.scene.things.kind_of(t).name.clone());
                    match kind.as_deref() {
                        Some("long gun") | Some("carronade") => {
                            if let Some(g) = ship.layout.guns.iter().position(|g| g.pos == *cell) {
                                if *energy > 60_000.0 && !ship.guns[g].disabled {
                                    ship.guns[g].disabled = true;
                                    let msg = format!("A gun of the {} is dismounted.", ship.name);
                                    self.say(msg, Rgb(240, 160, 90));
                                }
                            }
                        }
                        _ if ship.craft.scene.life.get(*thing).is_some() => {
                            // He soaks up little of the ball's energy, but it takes off what it touches.
                            let force = (400.0 + energy / 20.0).min(3000.0);
                            if let Some(what) = wound(ship, *thing, DamageKind::Blunt, force, &mut self.rng) {
                                let who = ship.craft.scene.life.name(&ship.craft.scene.things, *thing);
                                ship.notes.push(crate::ship::Note { text: format!("{who} is struck by round shot: {what}."), urgent: false });
                            }
                        }
                        _ => {}
                    }
                }
                ShotEvent::Splash { at, .. } => self.marks.push(Mark2 { at: *at, ch: 'o', fg: Rgb(225, 240, 250), ttl: 3.0 }),
                ShotEvent::Ricochet { at, .. } => self.marks.push(Mark2 { at: *at, ch: '^', fg: Rgb(225, 240, 250), ttl: 2.0 }),
                _ => {}
            }
        }
        for (i, n) in struck.iter().enumerate() {
            if *n > 0 {
                let c = if i == 0 { Rgb(240, 140, 110) } else { Rgb(230, 200, 140) };
                let msg = format!("The {} is struck {} time{}.", self.ships[i].name, n, if *n > 1 { "s" } else { "" });
                self.say(msg, c);
            }
        }
    }

    /// Splinters fly from a struck cell into the men near it.
    fn splinters(&mut self, ship: usize, cell: Pos, intensity: f32) {
        let s = &mut self.ships[ship];
        // The men on that deck near the hole, nearest first.
        let mut near: Vec<(ThingId, i32)> = s
            .craft
            .scene
            .life
            .creatures
            .iter()
            .filter(|c| c.alive)
            .filter_map(|c| s.craft.scene.things.get(c.thing).map(|t| (c.thing, t.pos())))
            .filter(|(_, p)| p.z == cell.z && p.dist2d(cell) <= 2)
            .map(|(id, p)| (id, p.dist2d(cell)))
            .collect();
        near.sort_by_key(|(_, d)| *d);
        let most = intensity.ceil().clamp(1.0, 3.0) as usize;
        let mut hit = 0;
        for (id, d) in near {
            if hit >= most {
                break;
            }
            if self.rng.chance(0.3 * intensity.min(2.0) / (1.0 + d as f32)) {
                let force = 8.0 + self.rng.f32() * 28.0 * intensity.min(2.0);
                if let Some(what) = wound(s, id, DamageKind::Point, force, &mut self.rng) {
                    let who = s.craft.scene.life.name(&s.craft.scene.things, id);
                    s.notes.push(crate::ship::Note { text: format!("{who} is struck by a splinter: {what}."), urgent: false });
                }
                hit += 1;
            }
        }
    }

    /// Pass on what happened aboard the player's ship (and the big news from others).
    fn news(&mut self) {
        let mut lines: Vec<(String, Rgb)> = Vec::new();
        for (i, s) in self.ships.iter_mut().enumerate() {
            for n in s.notes.drain(..) {
                if i == 0 || n.urgent {
                    lines.push((n.text, if n.urgent { Rgb(255, 200, 120) } else { Rgb(200, 200, 210) }));
                }
            }
            for e in s.craft.events.drain(..) {
                let t = match e {
                    CraftEvent::Grounded { speed, .. } => Some(format!("The {} takes the ground at {:.1} knots!", s.name, speed * 1.944)),
                    CraftEvent::Refloated => Some(format!("The {} floats off.", s.name)),
                    CraftEvent::Foundered => Some(format!("The {} is going down!", s.name)),
                    CraftEvent::Holed { below_water: true, .. } => Some(format!("The {} is holed below the waterline.", s.name)),
                    CraftEvent::Collided { impulse, .. } if impulse > 2e4 => Some(format!("The {} runs aboard another ship!", s.name)),
                    _ => None,
                };
                if let Some(t) = t {
                    lines.push((t, Rgb(255, 170, 110)));
                }
            }
            let life_events = std::mem::take(&mut s.craft.scene.life.events);
            for e in &life_events {
                let show = match e {
                    LifeEvent::Died { .. } => true,
                    LifeEvent::Collapsed(_) => i == 0,
                    _ => false,
                };
                if show {
                    let t = s.craft.scene.life.narrate(&s.craft.scene.things, e);
                    let ship = if i == 0 { String::new() } else { format!(" (the {})", s.name) };
                    lines.push((format!("{t}{ship}"), Rgb(230, 110, 100)));
                }
            }
        }
        for (t, c) in lines {
            self.say(t, c);
        }
    }

    fn check_end(&mut self) {
        if self.over.is_some() || self.ships.len() < 2 {
            return;
        }
        let you = &self.ships[0];
        if you.craft.state == tachyon::craft::Floating::Foundered {
            self.over = Some(format!("The {} has gone down under you.", you.name));
        } else if you.struck {
            self.over = Some("You have struck your colours.".into());
        } else if self.ships[1..].iter().all(|s| s.struck || s.craft.state == tachyon::craft::Floating::Foundered) {
            self.over = Some("The enemy has struck to you. A victory!".into());
        }
        if let Some(o) = self.over.clone() {
            self.say(o, Rgb(255, 230, 150));
        }
    }

    /// The player strikes his colours.
    pub fn strike(&mut self) {
        self.ships[0].struck = true;
        self.ships[0].orders.fire = Fire::Hold;
    }
}

/// Put a shot or splinter wound into a man's body; says what it did.
pub fn wound(ship: &mut Ship, id: ThingId, kind: DamageKind, force: f32, rng: &mut Rng) -> Option<String> {
    let life = &mut ship.craft.scene.life;
    let ci = life.creatures.iter().position(|c| c.thing == id && c.alive)?;
    let sp = life.creatures[ci].species as usize;
    let plan = life.species[sp].plan.clone();
    let c = &mut life.creatures[ci];
    let part = c.body.pick_part(&plan, Height::High, rng)?;
    let inj = c.body.strike(&plan, part, kind, force, rng);
    c.mind.alarmed = true;
    let name = |i: usize| plan.parts[i].name.clone();
    Some(match (inj.severed, inj.organ, inj.worst()) {
        (Some(p), _, _) => format!("his {} is carried away", name(p)),
        (None, Some(o), _) => format!("through the {} into the {}", name(part), name(o)),
        (None, None, Some((p, k, _, sev))) => {
            let how = match k {
                WoundKind::Bruise => "bruised",
                WoundKind::Cut => "cut",
                WoundKind::Puncture => "pierced",
                WoundKind::Fracture => "broken",
                WoundKind::Burn => "burned",
            };
            let deep = if sev > 0.6 { "badly " } else if sev < 0.25 { "lightly " } else { "" };
            format!("the {} {deep}{how}", name(p))
        }
        _ => "a graze".into(),
    })
}

/// Ships that run aboard each other are knocked apart.
fn collide_ships(ships: &mut [Ship]) {
    let mut crafts: Vec<&mut tachyon::craft::Craft> = ships.iter_mut().map(|s| &mut s.craft).collect();
    craft::collide(&mut crafts);
}

#[allow(dead_code)]
pub fn role_name(r: Role) -> &'static str {
    r.name()
}
