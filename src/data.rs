//! Ship classes, from `data/ships/*.yaml` (the same stat blocks the first
//! Broadside used). Adding a class is a data change: a new file there.
//!
//! The files use a small, flat subset of YAML (scalars, one list of gun
//! batteries, one nested map), read here without a YAML library.

use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub struct Battery {
    pub kind: String,
    pub count: u32,
    pub deck: String,
}

impl Battery {
    /// Weight of the ball, pounds ("32-pounder carronade" -> 32).
    pub fn pounds(&self) -> f32 {
        self.kind.split('-').next().and_then(|s| s.trim().parse().ok()).unwrap_or(6.0)
    }

    pub fn carronade(&self) -> bool {
        self.kind.to_lowercase().contains("carronade")
    }

    /// Ball mass, kg.
    pub fn ball_kg(&self) -> f32 {
        self.pounds() * 0.4536
    }

    /// Muzzle velocity, m/s: long guns ~470, the short carronades ~300.
    pub fn muzzle_speed(&self) -> f32 {
        if self.carronade() { 300.0 } else { 470.0 }
    }

    /// Hands to work one gun: about a man per 500 kg of gun and carriage,
    /// as the period quarter bills had it (a long 32 needed 14 per pair of
    /// guns, one side manned at a time).
    pub fn crew(&self) -> usize {
        let lb = self.pounds();
        let mass = 105.0 * lb * if self.carronade() { 0.3 } else { 1.0 } * 1.25;
        ((mass / 500.0).round() as usize).clamp(3, 8)
    }

    /// Gun and carriage, kg.
    pub fn gun_kg(&self) -> f32 {
        105.0 * self.pounds() * if self.carronade() { 0.3 } else { 1.0 } * 1.25
    }

    /// Fought on the open weather deck rather than a covered gundeck.
    pub fn weather_deck(&self) -> bool {
        matches!(self.deck.as_str(), "main deck" | "upper deck" | "quarterdeck" | "forecastle" | "weather deck")
    }
}

#[derive(Clone, Debug)]
pub struct ShipClass {
    pub key: String,
    pub name: String,
    pub rate: String,
    pub length_m: f32,
    pub beam_m: f32,
    pub draught_m: f32,
    pub tonnage_bm: f32,
    pub max_crew: u32,
    pub guns: Vec<Battery>,
    pub sail_plan: String,
    pub notes: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Rig {
    /// One mast, fore-and-aft (cutter, gunboat).
    Cutter,
    /// Two masts, square on both (brig).
    Brig,
    /// Three masts, square on all (sloop, frigate, ship of the line).
    Ship,
}

impl ShipClass {
    pub fn total_guns(&self) -> u32 {
        self.guns.iter().map(|g| g.count).sum()
    }

    pub fn rig(&self) -> Rig {
        let p = self.sail_plan.to_lowercase();
        if p.contains("single") || p.contains("cutter") || p.contains("lugger") {
            Rig::Cutter
        } else if p.contains("brig") {
            Rig::Brig
        } else {
            Rig::Ship
        }
    }

    /// Covered gundecks (in order from the bottom), each with its batteries.
    pub fn gundecks(&self) -> Vec<String> {
        let order = ["lower gundeck", "middle gundeck", "gundeck", "upper gundeck"];
        order.iter().filter(|d| self.guns.iter().any(|g| g.deck == **d)).map(|d| d.to_string()).collect()
    }

    /// Displacement, kg: the hull's block (length x beam x draught) at a
    /// period block coefficient. A brig comes out near 360 t, a first rate
    /// near 2,900 t.
    pub fn displacement(&self) -> f32 {
        self.length_m * self.beam_m * self.draught_m * 0.5 * 1025.0
    }

    /// Metacentric height, m: stiffer the broader she is.
    pub fn gm(&self) -> f32 {
        (0.11 * self.beam_m).clamp(0.7, 2.0)
    }

    /// Total canvas in a full plan of plain sail, m^2.
    pub fn canvas(&self) -> f32 {
        let k = match self.rig() {
            Rig::Cutter => 0.9,
            Rig::Brig => 0.8,
            Rig::Ship => 0.75,
        };
        k * self.length_m * self.length_m
    }
}

fn scalar(v: &str) -> String {
    let v = v.trim();
    let v = v.strip_prefix('"').and_then(|s| s.strip_suffix('"')).unwrap_or(v);
    v.to_string()
}

/// Read a stat block.
pub fn parse(key: &str, text: &str) -> Result<ShipClass, String> {
    let mut c = ShipClass {
        key: key.to_string(),
        name: key.to_string(),
        rate: "Unrated".into(),
        length_m: 0.0,
        beam_m: 0.0,
        draught_m: 3.0,
        tonnage_bm: 0.0,
        max_crew: 0,
        guns: Vec::new(),
        sail_plan: String::new(),
        notes: String::new(),
    };
    let mut section = "";
    let mut gun: Option<Battery> = None;
    let mut lines = text.lines().peekable();
    while let Some(line) = lines.next() {
        let raw = line.split(" #").next().unwrap_or("");
        if raw.trim_start().starts_with('#') || raw.trim().is_empty() {
            continue;
        }
        let indented = raw.starts_with(' ');
        let t = raw.trim();
        if !indented {
            if let Some(g) = gun.take() {
                c.guns.push(g);
            }
            let (k, v) = t.split_once(':').ok_or_else(|| format!("{key}: cannot read '{t}'"))?;
            section = "";
            match k.trim() {
                "name" => c.name = scalar(v),
                "ship_class" => c.key = scalar(v),
                "rate" => c.rate = scalar(v),
                "length_m" => c.length_m = scalar(v).parse().map_err(|_| format!("{key}: length_m"))?,
                "beam_m" => c.beam_m = scalar(v).parse().map_err(|_| format!("{key}: beam_m"))?,
                "draught_m" => c.draught_m = scalar(v).parse().unwrap_or(3.0),
                "tonnage_bm" => c.tonnage_bm = scalar(v).parse().unwrap_or(0.0),
                "max_crew" => c.max_crew = scalar(v).parse().map_err(|_| format!("{key}: max_crew"))?,
                "sail_plan" => c.sail_plan = scalar(v),
                "guns" => section = "guns",
                "notes" => {
                    // A folded block: the indented lines that follow.
                    let mut s = String::new();
                    while let Some(n) = lines.peek() {
                        if !n.starts_with(' ') && !n.trim().is_empty() {
                            break;
                        }
                        if !s.is_empty() && !n.trim().is_empty() {
                            s.push(' ');
                        }
                        s.push_str(n.trim());
                        lines.next();
                    }
                    c.notes = s.trim().to_string();
                }
                _ => {}
            }
        } else if section == "guns" {
            let item = t.strip_prefix("- ");
            let body = item.unwrap_or(t);
            if item.is_some() {
                if let Some(g) = gun.take() {
                    c.guns.push(g);
                }
                gun = Some(Battery { kind: String::new(), count: 0, deck: "main deck".into() });
            }
            if let (Some(g), Some((k, v))) = (gun.as_mut(), body.split_once(':')) {
                match k.trim() {
                    "type" => g.kind = scalar(v),
                    "count" => g.count = scalar(v).parse().unwrap_or(0),
                    "deck" => g.deck = scalar(v),
                    _ => {}
                }
            }
        }
    }
    if let Some(g) = gun.take() {
        c.guns.push(g);
    }
    if c.length_m <= 0.0 || c.beam_m <= 0.0 {
        return Err(format!("{key}: needs length_m and beam_m"));
    }
    Ok(c)
}

/// Where the ship data lives: next to the executable's crate.
pub fn data_dir() -> PathBuf {
    let here = Path::new(env!("CARGO_MANIFEST_DIR")).join("data").join("ships");
    if here.exists() {
        return here;
    }
    PathBuf::from("data/ships")
}

/// Every ship class, smallest first.
pub fn load_all() -> Vec<ShipClass> {
    let mut out = Vec::new();
    if let Ok(dir) = std::fs::read_dir(data_dir()) {
        for e in dir.flatten() {
            let p = e.path();
            if p.extension().is_some_and(|x| x == "yaml") {
                let key = p.file_stem().unwrap().to_string_lossy().to_string();
                match std::fs::read_to_string(&p).map_err(|e| e.to_string()).and_then(|t| parse(&key, &t)) {
                    Ok(c) => out.push(c),
                    Err(e) => eprintln!("ship data: {e}"),
                }
            }
        }
    }
    out.sort_by(|a, b| a.length_m.total_cmp(&b.length_m));
    out
}

pub fn load(key: &str) -> Option<ShipClass> {
    load_all().into_iter().find(|c| c.key == key)
}
