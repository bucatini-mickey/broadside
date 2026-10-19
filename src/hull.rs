//! Building a ship from her stat block: her hull, decks and fittings in her
//! own grid (bow toward -y), and where everyone's station is.
//!
//! Levels, from the bottom: open sea under the keel; her bottom planking;
//! the hold (as many levels as her draught, so the waterline falls inside
//! it); one level for each covered gundeck; then the weather deck with its
//! bulwarks. Her sides narrow toward the keel and her waterlines fine away
//! to the bow, so she draws less water forward and her lower holds are
//! narrower than her decks. Gunports are openings in her side at each gun:
//! heel her far enough and the sea comes in through them.

use crate::data::{Battery, Rig, ShipClass};
use tachyon::craft::{Craft, Foil, HullSpec};
use tachyon::prelude::*;

/// Open cells kept all round her (the sea along her side).
pub const MARGIN: i32 = 3;

#[derive(Clone, Debug)]
pub struct GunSlot {
    /// Where the gun stands, and which side it points (+1 starboard, -1 larboard).
    pub pos: Pos,
    pub side: i32,
    /// Index into the class's batteries.
    pub battery: usize,
    /// The opening in her side the muzzle runs out through.
    pub port: Pos,
    /// Where the crew stand, gun captain first.
    pub crew: Vec<Pos>,
    /// Fought on the open deck (seen) or a covered gundeck (below).
    pub weather: bool,
    pub deck: String,
}

#[derive(Clone, Debug, Default)]
pub struct Layout {
    pub deck_z: i32,
    pub keel_z: i32,
    /// A name for each level of her grid ("hold", "lower gundeck", ...).
    pub level_names: Vec<String>,
    pub guns: Vec<GunSlot>,
    pub masts: Vec<Pos>,
    pub wheel: Pos,
    pub helm: Pos,
    pub captain: Pos,
    pub officers: Vec<Pos>,
    pub marines: Vec<Pos>,
    pub topmen: Vec<Pos>,
    pub waist: Vec<Pos>,
    /// Where the watch below sleeps.
    pub berths: Vec<Pos>,
    pub hatches: Vec<(i32, i32)>,
    pub length: i32,
    pub beam: i32,
    /// Bow and stern rows of the hull at the deck.
    pub bow_y: i32,
    pub stern_y: i32,
    pub cx: i32,
}

impl Layout {
    pub fn level_name(&self, z: i32) -> &str {
        self.level_names.get(z as usize).map(|s| s.as_str()).unwrap_or("aloft")
    }
}

/// The kinds of thing aboard (registered in each ship's `Things`).
#[derive(Clone, Copy, Debug)]
pub struct Kinds {
    pub gun: KindId,
    pub carronade: KindId,
    pub mast: KindId,
    pub wheel: KindId,
    pub capstan: KindId,
    pub bowsprit: KindId,
    pub lantern: KindId,
    pub cask: KindId,
    pub powder: KindId,
    pub shot: KindId,
    pub hammock: KindId,
    pub man: KindId,
}

pub fn register(things: &mut Things) -> Kinds {
    Kinds {
        gun: things.add_kind(ThingKind::new("long gun", '=', Rgb(84, 84, 92), Layer::Furniture).blocking()),
        carronade: things.add_kind(ThingKind::new("carronade", '-', Rgb(96, 92, 92), Layer::Furniture).blocking()),
        mast: things.add_kind(ThingKind::new("mast", 'O', Rgb(214, 170, 106), Layer::Furniture).blocking()),
        wheel: things.add_kind(ThingKind::new("ship's wheel", '*', Rgb(196, 144, 82), Layer::Furniture).blocking()),
        capstan: things.add_kind(ThingKind::new("capstan", '0', Rgb(170, 128, 80), Layer::Furniture).blocking()),
        bowsprit: things.add_kind(ThingKind::new("bowsprit", '|', Rgb(200, 158, 100), Layer::Furniture).deck()),
        lantern: things.add_kind(ThingKind::new("lantern", '\'', Rgb(255, 210, 120), Layer::Item).light(Rgb(150, 110, 60), true).flame(Flame::Sheltered)),
        cask: things.add_kind(ThingKind::new("cask of salt beef", '0', Rgb(150, 110, 70), Layer::Item).food(0.3, true).stocked()),
        powder: things.add_kind(ThingKind::new("cask of powder", '0', Rgb(110, 110, 120), Layer::Item)),
        shot: things.add_kind(ThingKind::new("shot garland", ':', Rgb(90, 90, 96), Layer::Item)),
        hammock: things.add_kind(ThingKind::new("hammock", '~', Rgb(170, 160, 130), Layer::Item).bed()),
        man: things.add_kind(ThingKind::new("seaman", 'o', Rgb(220, 210, 190), Layer::Creature)),
    }
}

/// Materials: oak for her sides (a cell of it stands for about 0.6 m of
/// timber against shot), deal planking for decks.
pub fn materials() -> Materials {
    let mut m = Materials::standard();
    let wood = m.get(m.id("wood")).clone();
    m.add(Material { name: "oak".into(), strength: 50.0, fg: Rgb(150, 104, 58), bg: Rgb(58, 38, 22), ..wood.clone() });
    m.add(Material { name: "deal".into(), strength: 40.0, fg: Rgb(176, 140, 92), bg: Rgb(74, 54, 34), floor_glyphs: vec!['.', '.', ',', '.'], ..wood });
    m
}

/// Half-beam (cells) of her waterlines at fraction `s` of her length from
/// the bow, on a level `k` of `depth` levels down from the deck (0 = deck).
fn half_beam(hb: f32, s: f32, k: f32, depth: f32) -> f32 {
    let bow = if s < 0.32 { (s / 0.32 * std::f32::consts::FRAC_PI_2).sin().powf(0.75) } else { 1.0 };
    let stern = if s > 0.9 { 0.82 + 0.18 * (1.0 - s) / 0.1 } else { 1.0 };
    // The section rounds in toward the keel.
    let sect = (1.0 - (k / depth.max(1.0)).powf(2.2) * 0.75).max(0.2);
    hb * bow * stern * sect
}

pub struct Built {
    pub craft: Craft,
    pub layout: Layout,
    pub kinds: Kinds,
}

/// Build a ship of `class` with her pivot at sea-space (x, y), heading `heading`.
pub fn build(class: &ShipClass, x: f32, y: f32, heading: f32, seed: u64) -> Built {
    let len = class.length_m.round() as i32;
    let beam = class.beam_m.round() as i32;
    let hold = (class.draught_m.ceil() as i32).max(2);
    let gundecks = class.gundecks();
    let keel = 1;
    let deck_z = keel + hold + gundecks.len() as i32 + 1;
    let sprit = (class.length_m * 0.22).round() as i32;
    let (w, h, d) = (beam + 2 * MARGIN, len + 2 * MARGIN + sprit, deck_z + 4);
    let mats = materials();
    let (oak, deal) = (mats.id("oak"), mats.id("deal"));
    let mut world = World::new(w, h, d, mats);
    let mut things = Things::new();
    let k = register(&mut things);
    let bow_y = MARGIN + sprit;
    let stern_y = bow_y + len - 1;
    let cx = w / 2;
    let hb = beam as f32 / 2.0;

    let mut level_names = vec!["under her keel".to_string(), "her bottom".to_string()];
    for i in 0..hold {
        level_names.push(if i == hold - 1 && hold > 2 { "orlop".into() } else { "hold".into() });
    }
    for g in &gundecks {
        level_names.push(g.clone());
    }
    level_names.push(if gundecks.is_empty() { "main deck".into() } else { "upper deck".into() });

    // Does cell (x, y) lie inside her on level z?
    let inside = |x: i32, y: i32, z: i32| -> bool {
        if y < bow_y || y > stern_y || z < keel || z > deck_z {
            return false;
        }
        let s = (y - bow_y) as f32 / (len - 1).max(1) as f32;
        let k = (deck_z - z) as f32;
        // The keel rises toward the stem: lower levels end a little short of the bow.
        let rise = ((deck_z - z) as f32 / (deck_z - keel) as f32).powi(2) * 0.08;
        if s < rise {
            return false;
        }
        let half = half_beam(hb, s, k, (deck_z - keel) as f32);
        ((x as f32 + 0.5) - cx as f32).abs() <= half.max(0.6)
    };

    for z in keel..=deck_z {
        for y in 0..h {
            for x in 0..w {
                if !inside(x, y, z) {
                    continue;
                }
                let p = Pos::new(x, y, z);
                let rim = DIRS4.iter().any(|(dx, dy)| !inside(x + dx, y + dy, z));
                if z == keel || rim {
                    world.set_tile(p, Tile::Wall, oak);
                } else if z > keel + 1 {
                    // Every level above the bottom is a planked deck: hold platforms,
                    // the orlop, the gundecks, the weather deck.
                    world.set_tile(p, Tile::Floor, deal);
                }
            }
        }
    }

    // Hatches with ladders, from the weather deck to the bottom of the hold.
    let at = |s: f32| bow_y + (s * (len - 1) as f32).round() as i32;
    let hatches = vec![(cx, at(0.3)), (cx, at(0.52))];
    for &(hx, hy) in &hatches {
        for z in keel + 1..=deck_z {
            let t = if z == deck_z { Tile::StairDown } else if z == keel + 1 { Tile::StairUp } else { Tile::StairUpDown };
            world.set_tile(Pos::new(hx, hy, z), t, deal);
        }
    }

    let mut layout = Layout { deck_z, keel_z: keel, level_names, length: len, beam, bow_y, stern_y, cx, hatches: hatches.clone(), ..Default::default() };

    // Masts.
    let mast_at: Vec<f32> = match class.rig() {
        Rig::Cutter => vec![0.38],
        Rig::Brig => vec![0.28, 0.58],
        Rig::Ship => vec![0.22, 0.48, 0.74],
    };
    for s in &mast_at {
        let p = Pos::new(cx, at(*s), deck_z);
        things.spawn(k.mast, p);
        layout.masts.push(p);
    }
    // The bowsprit runs out ahead of the stem.
    for y in (bow_y - sprit)..bow_y {
        things.spawn(k.bowsprit, Pos::new(cx, y, deck_z));
    }
    // Wheel aft, capstan amidships.
    layout.wheel = Pos::new(cx, at(0.88), deck_z);
    things.spawn(k.wheel, layout.wheel);
    layout.helm = layout.wheel.offset(0, 1, 0);
    if class.rig() != Rig::Cutter {
        things.spawn(k.capstan, Pos::new(cx, at(0.66), deck_z));
    }
    layout.captain = layout.wheel.offset(1, -2, 0);
    layout.officers = vec![layout.wheel.offset(-1, -2, 0), layout.wheel.offset(-2, 0, 0), layout.wheel.offset(2, 0, 0)];

    // Guns: each battery split between the two sides, spread along its deck.
    let gundeck_z = |name: &str| gundecks.iter().position(|g| g == name).map(|i| keel + hold + 1 + i as i32);
    let span = |deck: &str| -> (f32, f32) {
        match deck {
            "quarterdeck" => (0.66, 0.86),
            "forecastle" => (0.1, 0.24),
            _ => (0.14, 0.86),
        }
    };
    let mut taken: Vec<Pos> = layout.masts.clone();
    taken.push(layout.wheel);
    for &(hx, hy) in &hatches {
        taken.push(Pos::new(hx, hy, deck_z));
    }
    for (bi, b) in class.guns.iter().enumerate() {
        let z = gundeck_z(&b.deck).unwrap_or(deck_z);
        let (s0, s1) = span(&b.deck);
        let per_side = (b.count as i32 + 1) / 2;
        for side in [-1i32, 1] {
            let n = if side == 1 { b.count as i32 / 2 } else { per_side };
            for i in 0..n {
                let s = s0 + (s1 - s0) * (i as f32 + 0.5) / n.max(1) as f32;
                let mut gy = at(s);
                // Don't put two guns in one place on this deck.
                while taken.iter().any(|t| t.z == z && t.y == gy && (t.x - cx).signum() == side) && gy < stern_y - 1 {
                    gy += 1;
                }
                // The rim cell on this side of this row, and the gun just inboard of it.
                let mut rx = cx;
                while inside(rx + side, gy, z) {
                    rx += side;
                }
                let port = Pos::new(rx, gy, z);
                let pos = Pos::new(rx - side, gy, z);
                if world.tile(pos) != Tile::Floor {
                    continue;
                }
                // A port in her side: a sill to stand at, no plank to stop the sea.
                world.set_tile(port, Tile::Floor, deal);
                things.spawn(if b.carronade() { k.carronade } else { k.gun }, pos);
                taken.push(pos);
                let mut crew = Vec::new();
                for (dx, dy) in [(-1, 0), (-1, -1), (-1, 1), (-2, 0), (-2, -1), (-2, 1), (-3, 0), (-3, 1)] {
                    let c = Pos::new(pos.x + dx * side, gy + dy, z);
                    if crew.len() < b.crew() && world.tile(c) == Tile::Floor {
                        crew.push(c);
                    }
                }
                layout.guns.push(GunSlot { pos, side, battery: bi, port, crew, weather: b.weather_deck(), deck: b.deck.clone() });
            }
        }
    }

    // Topmen at the masts' feet, marines along the quarterdeck rails, the
    // waisters amidships, berths below.
    for m in &layout.masts {
        for (dx, dy) in [(-1, 0), (1, 0), (0, 1), (-1, 1), (1, 1), (0, -1)] {
            layout.topmen.push(m.offset(dx, dy, 0));
        }
    }
    for i in 0..6 {
        let y = at(0.7 + 0.03 * i as f32);
        for side in [-1, 1] {
            layout.marines.push(Pos::new(cx + side * (beam / 2 - 2).max(1), y, deck_z));
        }
    }
    for y in at(0.36)..at(0.46) {
        for x in cx - 2..=cx + 2 {
            layout.waist.push(Pos::new(x, y, deck_z));
        }
    }
    let berth_z = if gundecks.is_empty() { keel + hold } else { keel + hold + 1 };
    for y in at(0.12)..at(0.5) {
        for x in cx - (beam / 2 - 2).max(1)..=cx + (beam / 2 - 2).max(1) {
            let p = Pos::new(x, y, berth_z);
            if world.standable(p) && !hatches.contains(&(x, y)) {
                layout.berths.push(p);
            }
        }
    }
    // Hammocks slung where the watch below sleeps.
    for p in layout.berths.iter().step_by(3) {
        things.spawn(k.hammock, *p);
    }
    // Stores in the hold, powder in the magazine forward, lanterns below.
    let hz = keel + 1;
    for y in at(0.55)..at(0.8) {
        for x in [cx - 2, cx - 1, cx + 1, cx + 2] {
            if world.standable(Pos::new(x, y, hz)) && (y + x) % 2 == 0 {
                things.spawn(k.cask, Pos::new(x, y, hz));
            }
        }
    }
    for y in at(0.12)..at(0.2) {
        for x in [cx - 1, cx + 1] {
            if world.standable(Pos::new(x, y, hz)) {
                things.spawn(k.powder, Pos::new(x, y, hz));
            }
        }
    }
    for z in keel + 1..deck_z {
        for s in [0.25, 0.45, 0.65, 0.82] {
            let p = Pos::new(cx + 1, at(s), z);
            if world.standable(p) {
                let id = things.spawn(k.lantern, p);
                if let Some(t) = things.get_mut(id) {
                    t.lit = true;
                }
            }
        }
    }

    let mut scene = Scene::new(world, things, Clock::new(1.0, 10.0), seed);
    scene.sim.heat = false;
    let spec = HullSpec { mass: class.displacement(), gm: class.gm(), water: scene.world.mats.id("water"), fouling: 1.0 };
    let mut craft = Craft::new(&class.name, scene, spec, x, y, heading);

    // Canvas: square sails on each mast of a square rig (the courses and
    // topsails together), a jib on the bowsprit, a spanker or mainsail aft.
    let canvas = class.canvas();
    let top = deck_z as f32 + class.length_m * 0.45;
    let mid = (stern_y + bow_y) as f32 / 2.0;
    match class.rig() {
        Rig::Cutter => {
            craft.foils.push(Foil::fore_and_aft("mainsail", [cx as f32 + 0.5, layout.masts[0].y as f32 + 4.0, top * 0.8], canvas * 0.72));
            craft.foils.push(Foil::fore_and_aft("jib", [cx as f32 + 0.5, bow_y as f32 - sprit as f32 * 0.5, top * 0.6], canvas * 0.28));
        }
        rig => {
            let names = if rig == Rig::Brig { vec!["fore", "main"] } else { vec!["fore", "main", "mizzen"] };
            let shares = if rig == Rig::Brig { vec![0.4, 0.42] } else { vec![0.3, 0.36, 0.18] };
            for ((n, m), share) in names.iter().zip(&layout.masts).zip(shares) {
                craft.foils.push(Foil::square_sail(n, [cx as f32 + 0.5, m.y as f32 + 0.5, top], canvas * share));
            }
            craft.foils.push(Foil::fore_and_aft("jib", [cx as f32 + 0.5, bow_y as f32 - sprit as f32 * 0.5, top * 0.6], canvas * 0.08));
            craft.foils.push(Foil::fore_and_aft("spanker", [cx as f32 + 0.5, at(0.85) as f32, top * 0.6], canvas * 0.08));
        }
    }
    let _ = mid;
    craft.foils.push(Foil::rudder([cx as f32 + 0.5, stern_y as f32 + 0.5, (keel + 1) as f32], class.length_m * class.draught_m * 0.06));
    Built { craft, layout, kinds: k }
}

/// The battery a gun belongs to.
pub fn battery<'a>(class: &'a ShipClass, g: &GunSlot) -> &'a Battery {
    &class.guns[g.battery]
}
