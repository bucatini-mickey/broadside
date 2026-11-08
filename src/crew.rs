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
    /// The rest of the temperament (`bravery` and `discipline` stay above).
    pub traits: Traits,
    /// Why he is here and to whom he holds.
    pub allegiance: Allegiance,
    /// Drink and tobacco.
    pub cravings: Cravings,
    /// Earned from an extreme trait, if any ("Lion", "Sly").
    pub nickname: Option<&'static str>,
}

/// The other six traits of legacy `11` (0..1, 0.5 is the common run of men).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Traits {
    pub sociability: f32,
    pub temper: f32,
    pub ambition: f32,
    pub honesty: f32,
    pub optimism: f32,
    pub resilience: f32,
}

/// What brought him aboard.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Cause {
    /// The King's service as a calling.
    Service,
    /// Wages and prize money.
    Pay,
    /// Taken by the press or the quota; he would be elsewhere.
    Pressed,
    /// A foreigner serving for his own reasons.
    Stranger,
}

/// Allegiance: the cause, and how firmly he holds to his captain and his ship.
/// The nation is not tracked yet: it needs a generated world (WLD-05).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Allegiance {
    pub cause: Cause,
    pub captain: f32,
    pub ship: f32,
}

/// Cravings: 0 is none, 1 cannot go without.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Cravings {
    pub drink: f32,
    pub tobacco: f32,
}

/// A nickname from the most extreme trait, when it is extreme enough.
pub fn nickname(p: &Person) -> Option<&'static str> {
    let t = &p.traits;
    let marks: [(f32, &'static str, &'static str); 7] = [
        (p.bravery, "Lion", "Mouse"),
        (t.temper, "Hotspur", "Lamb"),
        (t.sociability, "Hearty", "Hermit"),
        (t.honesty, "Honest", "Sly"),
        (t.optimism, "Lucky", "Gloomy"),
        (t.ambition, "Striver", "Idler"),
        (p.discipline, "Steady", "Rascal"),
    ];
    marks
        .iter()
        .map(|&(v, hi, lo)| if v >= 0.5 { (v - 0.5, hi) } else { (0.5 - v, lo) })
        .filter(|(d, _)| *d >= 0.32)
        .max_by(|a, b| a.0.total_cmp(&b.0))
        .map(|(_, n)| n)
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
        match self.nickname {
            Some(n) => format!("\"{n}\", {}, {} years old, {} years at sea", self.background, self.age, self.years_at_sea),
            None => format!("{}, {} years old, {} years at sea", self.background, self.age, self.years_at_sea),
        }
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
    // The new attributes come from their own stream, so the rest of a
    // company (and every scenario's dice) is unchanged by them.
    let seed = given.bytes().fold(17u64, |h, b| h.wrapping_mul(131).wrapping_add(b as u64)) ^ family.bytes().fold(5u64, |h, b| h.wrapping_mul(257).wrapping_add(b as u64)) ^ ((age as u64) << 32);
    let mut own = Rng::new(seed);
    let mut t = |r: &mut Rng| (0.5 + 0.18 * gauss(r)).clamp(0.02, 0.98);
    let traits = Traits { sociability: t(&mut own), temper: t(&mut own), ambition: t(&mut own), honesty: t(&mut own), optimism: t(&mut own), resilience: t(&mut own) };
    let cause = match bg.key {
        "pressed_landsman" | "quota_man" => Cause::Pressed,
        "foreign_seaman" => Cause::Stranger,
        "career_seaman" | "officer" | "marine" => Cause::Service,
        _ => Cause::Pay,
    };
    let hold = if cause == Cause::Pressed { 0.15 } else { 0.4 };
    let allegiance = Allegiance { cause, captain: (hold + 0.3 * own.f32()).clamp(0.0, 1.0), ship: (hold + 0.3 * own.f32() + if cause == Cause::Service { 0.2 } else { 0.0 }).clamp(0.0, 1.0) };
    let sea = (years as f32 / 20.0).min(1.0);
    let cravings = Cravings {
        drink: (0.15 + 0.4 * sea * own.f32() + 0.3 * (1.0 - traits.resilience) * own.f32()).clamp(0.0, 1.0),
        tobacco: if bg.key == "ships_boy" { 0.0 } else { (0.6 * own.f32() * (0.4 + sea)).clamp(0.0, 1.0) },
    };
    let mut me = Person {
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
        traits,
        allegiance,
        cravings,
        nickname: None,
    };
    me.nickname = nickname(&me);
    me
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

/// Practice teaches (`docs/legacy/02` s3): a man's skill creeps up the more he
/// does the work, fast while he is raw, slowly as he nears mastery, and more
/// slowly in older men. `effort` is the work done, in rough "turns of the
/// job" (one round fired, one minute at the helm of a quiet watch...).
pub fn practise(p: &mut Person, skill: &str, effort: f32) {
    let i = skill_index(skill);
    let youth = (1.3 - p.age as f32 / 60.0).clamp(0.4, 1.2);
    let gain = 0.0008 * effort.max(0.0) * youth * (1.0 - p.skills[i]);
    p.skills[i] = (p.skills[i] + gain).min(0.98);
}

/// Resting pulse is about 65. Work (fatigue 0..1), pain and blood lost quicken
/// it; very little blood left and the heart flags. Beats per minute.
pub fn pulse_bpm(fatigue: f32, pain: f32, blood: f32, pumping: f32) -> u32 {
    let lost = (1.0 - blood).clamp(0.0, 1.0);
    let mut rate = 65.0 + 45.0 * fatigue.clamp(0.0, 1.0) + 6.0 * pain.clamp(0.0, 10.0) + 150.0 * lost;
    if blood < 0.4 {
        // The heart can no longer keep up.
        rate *= (blood / 0.4).clamp(0.3, 1.0);
    }
    (rate * pumping.clamp(0.2, 1.0).sqrt()).clamp(20.0, 200.0).round() as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn practice_teaches_with_diminishing_returns() {
        let culture = Culture::new(5);
        let mut rng = Rng::new(3);
        let mut raw = person(&culture, &BACKGROUNDS[2], &mut rng);
        let mut old_hand = raw.clone();
        raw.skills[skill_index("gunnery")] = 0.1;
        old_hand.skills[skill_index("gunnery")] = 0.9;
        let (r0, o0) = (raw.skill("gunnery"), old_hand.skill("gunnery"));
        for _ in 0..200 {
            practise(&mut raw, "gunnery", 1.0);
            practise(&mut old_hand, "gunnery", 1.0);
        }
        assert!(raw.skill("gunnery") - r0 > 5.0 * (old_hand.skill("gunnery") - o0), "the raw man learns faster");
        assert!(old_hand.skill("gunnery") <= 0.98);
        let mut p = raw.clone();
        p.age = 20;
        let mut q = raw.clone();
        q.age = 55;
        practise(&mut p, "helm", 50.0);
        practise(&mut q, "helm", 50.0);
        assert!(p.skill("helm") > q.skill("helm"), "young men learn quicker");
    }

    #[test]
    fn temperament_allegiance_cravings_and_nicknames_are_generated() {
        let culture = Culture::new(5);
        let mut rng = Rng::new(9);
        let crew = company(&culture, 200, 20, &[6; 20], &mut rng);
        for p in &crew {
            let t = p.traits;
            for v in [t.sociability, t.temper, t.ambition, t.honesty, t.optimism, t.resilience, p.cravings.drink, p.cravings.tobacco, p.allegiance.captain, p.allegiance.ship] {
                assert!((0.0..=1.0).contains(&v));
            }
            assert_eq!(p.nickname, nickname(p));
        }
        let pressed: Vec<_> = crew.iter().filter(|p| p.allegiance.cause == Cause::Pressed).collect();
        let service: Vec<_> = crew.iter().filter(|p| p.allegiance.cause == Cause::Service).collect();
        assert!(!pressed.is_empty() && !service.is_empty());
        let mean = |v: &[&Person]| v.iter().map(|p| p.allegiance.ship).sum::<f32>() / v.len() as f32;
        assert!(mean(&service) > mean(&pressed), "pressed men hold less to the ship");
        let named = crew.iter().filter(|p| p.nickname.is_some()).count();
        assert!(named > 0 && named < crew.len() / 2, "some men earn a name, most do not ({named})");
        let mut m = crew[5].clone();
        m.bravery = 0.95;
        m.discipline = 0.5;
        m.traits = Traits { sociability: 0.5, temper: 0.5, ambition: 0.5, honesty: 0.5, optimism: 0.5, resilience: 0.5 };
        assert_eq!(nickname(&m), Some("Lion"));
        m.bravery = 0.5;
        assert_eq!(nickname(&m), None);
    }

    #[test]
    fn the_pulse_quickens_with_work_and_pain_and_fails_with_blood() {
        let rest = pulse_bpm(0.0, 0.0, 1.0, 1.0);
        assert!((60..=70).contains(&rest));
        assert!(pulse_bpm(0.8, 0.0, 1.0, 1.0) > rest + 25);
        assert!(pulse_bpm(0.0, 4.0, 1.0, 1.0) > rest + 15);
        assert!(pulse_bpm(0.0, 0.0, 0.75, 1.0) > pulse_bpm(0.0, 0.0, 0.9, 1.0));
        assert!(pulse_bpm(0.0, 0.0, 0.2, 1.0) < pulse_bpm(0.0, 0.0, 0.6, 1.0), "nearly bled out: it flags");
    }
}
