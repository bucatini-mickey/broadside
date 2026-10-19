//! A ship's company: named men with backgrounds, skills and roles, each a
//! creature aboard with a body, needs and a station.
//!
//! Backgrounds, the crew mix, the fifteen skills and the quarter bill come
//! from the first Broadside (`docs/legacy/11_people.md`). Every man is
//! generated whole; how many are put aboard as creatures is capped for very
//! large ships (the rest are counted, not simulated, until needed).

use tachyon::lang::Culture;
use tachyon::life::species;
use tachyon::prelude::*;

pub const SKILLS: [&str; 15] = [
    "seamanship", "topwork", "helm", "gunnery", "gunlaying", "musketry", "melee", "rigging", "carpentry", "sailmaking", "lookout", "navigation", "leadership", "medicine", "cooking",
];

pub fn skill_index(name: &str) -> usize {
    SKILLS.iter().position(|s| *s == name).unwrap_or(0)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Captain,
    Lieutenant,
    Midshipman,
    GunCaptain,
    Gunner,
    Topman,
    Helmsman,
    BosunsMate,
    Carpenter,
    Marine,
    Boy,
    Waister,
}

impl Role {
    pub fn name(self) -> &'static str {
        match self {
            Role::Captain => "Captain",
            Role::Lieutenant => "Lieutenant",
            Role::Midshipman => "Midshipman",
            Role::GunCaptain => "Gun Captain",
            Role::Gunner => "Gun crew",
            Role::Topman => "Topman",
            Role::Helmsman => "Quartermaster",
            Role::BosunsMate => "Bosun's Mate",
            Role::Carpenter => "Carpenter's Mate",
            Role::Marine => "Marine",
            Role::Boy => "Ship's Boy",
            Role::Waister => "Waister",
        }
    }

    /// How he reads on deck: you are the only `@`.
    pub fn glyph(self) -> char {
        match self {
            Role::Captain => '@',
            Role::Lieutenant | Role::Midshipman => '&',
            Role::GunCaptain => 'g',
            Role::Topman => 't',
            Role::Marine => 'x',
            Role::BosunsMate | Role::Carpenter => 'b',
            Role::Boy => ',',
            _ => 'o',
        }
    }

    pub fn colour(self) -> Rgb {
        match self {
            Role::Captain => Rgb(255, 255, 255),
            Role::Lieutenant | Role::Midshipman => Rgb(120, 170, 255),
            Role::GunCaptain => Rgb(255, 196, 110),
            Role::Gunner => Rgb(220, 200, 170),
            Role::Topman => Rgb(160, 220, 160),
            Role::Marine => Rgb(236, 90, 80),
            Role::Helmsman => Rgb(200, 200, 255),
            Role::BosunsMate | Role::Carpenter => Rgb(200, 170, 120),
            Role::Boy => Rgb(220, 220, 180),
            Role::Waister => Rgb(190, 186, 176),
        }
    }
}

struct Background {
    key: &'static str,
    label: &'static str,
    age: (u32, u32),
    skills: &'static [(&'static str, f32)],
    weight: u32,
}

const BACKGROUNDS: [Background; 10] = [
    Background { key: "career_seaman", label: "career man-of-war's man", age: (20, 45), skills: &[("seamanship", 0.6), ("topwork", 0.55), ("gunnery", 0.55), ("gunlaying", 0.4), ("rigging", 0.45), ("helm", 0.35), ("melee", 0.35)], weight: 22 },
    Background { key: "merchant_seaman", label: "merchant seaman", age: (20, 50), skills: &[("seamanship", 0.65), ("topwork", 0.5), ("helm", 0.45), ("rigging", 0.45), ("lookout", 0.4)], weight: 20 },
    Background { key: "pressed_landsman", label: "pressed landsman", age: (18, 40), skills: &[("seamanship", 0.1)], weight: 16 },
    Background { key: "volunteer_landsman", label: "volunteer landsman", age: (17, 30), skills: &[("seamanship", 0.15), ("musketry", 0.1)], weight: 8 },
    Background { key: "fisherman", label: "fisherman", age: (18, 45), skills: &[("seamanship", 0.45), ("helm", 0.3), ("lookout", 0.45), ("rigging", 0.3)], weight: 6 },
    Background { key: "quota_man", label: "quota man", age: (18, 45), skills: &[("seamanship", 0.05)], weight: 5 },
    Background { key: "ships_boy", label: "ship's boy", age: (11, 16), skills: &[("seamanship", 0.1), ("topwork", 0.15)], weight: 5 },
    Background { key: "foreign_seaman", label: "foreign seaman", age: (20, 45), skills: &[("seamanship", 0.55), ("topwork", 0.45), ("rigging", 0.4)], weight: 8 },
    Background { key: "marine", label: "marine", age: (18, 35), skills: &[("musketry", 0.6), ("melee", 0.5), ("seamanship", 0.1)], weight: 7 },
    Background { key: "tradesman", label: "skilled tradesman", age: (22, 50), skills: &[("seamanship", 0.2), ("carpentry", 0.3), ("sailmaking", 0.3)], weight: 3 },
];

const OFFICER: Background = Background { key: "officer", label: "officer", age: (14, 50), skills: &[("seamanship", 0.5), ("navigation", 0.55), ("leadership", 0.5), ("gunnery", 0.3), ("gunlaying", 0.35), ("melee", 0.35)], weight: 0 };

#[derive(Clone, Debug)]
pub struct Person {
    pub given: String,
    pub family: String,
    /// What his family name means ("Iron-Tide").
    pub meaning: String,
    pub background: &'static str,
    pub age: u32,
    pub years_at_sea: u32,
    pub skills: [f32; 15],
    pub bravery: f32,
    pub discipline: f32,
    pub role: Role,
    /// The gun he fights, and his number in its crew (0 = gun captain).
    pub gun: Option<(usize, usize)>,
    pub thing: Option<ThingId>,
    /// Starboard watch (true) or larboard.
    pub starboard_watch: bool,
}

impl Person {
    pub fn name(&self) -> String {
        format!("{} {}", self.given, self.family)
    }

    pub fn skill(&self, s: &str) -> f32 {
        self.skills[skill_index(s)]
    }

    /// "a career man-of-war's man of 31, 14 years at sea"
    pub fn story(&self) -> String {
        format!("{}, {} years old, {} years at sea", self.background, self.age, self.years_at_sea)
    }
}

fn gauss(rng: &mut Rng) -> f32 {
    (rng.f32() + rng.f32() + rng.f32() - 1.5) / 0.5
}

fn person(culture: &Culture, bg: &Background, rng: &mut Rng) -> Person {
    let (given, family) = culture.person(rng);
    let meaning = culture.meaning(&family).unwrap_or("").to_string();
    let age = rng.range(bg.age.0 as i32, bg.age.1 as i32 + 1) as u32;
    let years = (age.saturating_sub(if bg.key == "ships_boy" { 10 } else { 16 })).max(1);
    let exp = (years as f32 / 5.0).sqrt().min(1.6);
    let mut skills = [0.0f32; 15];
    for (k, base) in bg.skills {
        let i = skill_index(k);
        skills[i] = (base * exp * (1.0 + 0.25 * gauss(rng))).clamp(0.02, 0.98);
    }
    for s in skills.iter_mut() {
        if *s == 0.0 {
            *s = (0.05 * rng.f32()).max(0.01);
        }
    }
    Person {
        given,
        family,
        meaning,
        background: bg.label,
        age,
        years_at_sea: years,
        skills,
        bravery: (0.5 + 0.18 * gauss(rng)).clamp(0.05, 0.95),
        discipline: (0.5 + 0.18 * gauss(rng)).clamp(0.05, 0.95),
        role: Role::Waister,
        gun: None,
        thing: None,
        starboard_watch: rng.chance(0.5),
    }
}

/// Generate a ship's company of `n` men: a captain, officers, and the
/// people, fitted to roles by skill as a quarter bill would.
pub fn company(culture: &Culture, n: usize, guns: usize, crew_per_gun: &[usize], rng: &mut Rng) -> Vec<Person> {
    let mut people = Vec::with_capacity(n);
    let mut cap = person(culture, &OFFICER, rng);
    cap.age = cap.age.max(28);
    cap.role = Role::Captain;
    people.push(cap);
    let officers = (n / 30).clamp(1, 6);
    for i in 0..officers {
        let mut o = person(culture, &OFFICER, rng);
        o.role = if i % 2 == 0 { Role::Lieutenant } else { Role::Midshipman };
        people.push(o);
    }
    let total: u32 = BACKGROUNDS.iter().map(|b| b.weight).sum();
    while people.len() < n {
        let mut r = rng.below(total);
        let bg = BACKGROUNDS.iter().find(|b| {
            if r < b.weight {
                true
            } else {
                r -= b.weight;
                false
            }
        });
        people.push(person(culture, bg.unwrap_or(&BACKGROUNDS[0]), rng));
    }
    // The quarter bill. Marines and boys are what they are.
    for p in people.iter_mut() {
        match p.background {
            "marine" => p.role = Role::Marine,
            "ship's boy" => p.role = Role::Boy,
            _ => {}
        }
    }
    let free = |people: &Vec<Person>| -> Vec<usize> { (0..people.len()).filter(|&i| people[i].role == Role::Waister).collect() };
    let best = |people: &Vec<Person>, skill: &str, k: usize| -> Vec<usize> {
        let mut v = free(people);
        v.sort_by(|&a, &b| people[b].skill(skill).total_cmp(&people[a].skill(skill)));
        v.truncate(k);
        v
    };
    for i in best(&people, "helm", 2) {
        people[i].role = Role::Helmsman;
    }
    // Every gun gets a captain, the best layers first, and its crew.
    for (g, i) in best(&people, "gunlaying", guns).into_iter().enumerate() {
        people[i].role = Role::GunCaptain;
        people[i].gun = Some((g, 0));
    }
    for g in 0..guns {
        let need = crew_per_gun.get(g).copied().unwrap_or(4).saturating_sub(1);
        for (k, i) in best(&people, "gunnery", need).into_iter().enumerate() {
            people[i].role = Role::Gunner;
            people[i].gun = Some((g, k + 1));
        }
    }
    let topmen = (n as f32 * 0.18).round() as usize;
    for i in best(&people, "topwork", topmen) {
        people[i].role = Role::Topman;
    }
    for i in best(&people, "rigging", (n / 40).max(1)) {
        people[i].role = Role::BosunsMate;
    }
    for i in best(&people, "carpentry", (n / 60).max(1)) {
        people[i].role = Role::Carpenter;
    }
    people
}

/// Register the trade kinds in a ship's things (one per role, so each reads
/// by its own glyph), and return a lookup.
pub fn kinds(things: &mut Things) -> Vec<(Role, KindId)> {
    let roles = [
        Role::Captain, Role::Lieutenant, Role::Midshipman, Role::GunCaptain, Role::Gunner, Role::Topman, Role::Helmsman, Role::BosunsMate, Role::Carpenter, Role::Marine, Role::Boy, Role::Waister,
    ];
    roles.iter().map(|&r| (r, things.add_kind(ThingKind::new(r.name(), r.glyph(), r.colour(), Layer::Creature)))).collect()
}

/// Put a man aboard as a creature at `at`, under `control`.
pub fn embark(scene: &mut Scene, kinds: &[(Role, KindId)], p: &mut Person, at: Pos, control: Control, faction: u16) -> ThingId {
    let kind = kinds.iter().find(|(r, _)| *r == p.role).map(|(_, k)| *k).unwrap_or(kinds[0].1);
    let id = scene.things.spawn(kind, at);
    if let Some(t) = scene.things.get_mut(id) {
        t.name = Some(p.name());
    }
    let sp = match scene.life.find_species("human") {
        Some(s) => s,
        None => scene.life.add_species(species::human()),
    };
    scene.life.add(id, sp, control, faction);
    p.thing = Some(id);
    id
}
