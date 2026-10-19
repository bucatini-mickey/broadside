//! Working a gun: the drill, step by step, by named men.
//!
//! Nobody stands beside a cannon while a bar fills. A gun is fought by a
//! crew with numbered stations, each with his own job, and every job takes
//! the time it takes the man doing it: his skill, how tired and how hurt he
//! is, the weight of the ball he lifts and of the gun he hauls, and how many
//! hands are left to haul it. Short-handed, the same men do each other's
//! jobs, slower. A ship's rate of fire is not a number anywhere; it is what
//! her people manage. (After `docs/legacy/17_drill_signals_and_tutorial.md`.)

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mass {
    None,
    Shot,
    Gun,
}

#[derive(Clone, Copy, Debug)]
pub struct Step {
    pub label: &'static str,
    /// Whose job: his number in the crew (0 = gun captain, 1 = rammer and
    /// sponger, 2 = loader, 3 = tackle).
    pub station: usize,
    pub skill: &'static str,
    pub base_s: f32,
    /// 0 = deft work, 1 = heavy hauling.
    pub effort: f32,
    pub mass: Mass,
    /// A store it takes from the magazine or the garland.
    pub takes: Option<Store>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Store {
    Powder,
    Shot,
}

/// The period sequence for a gun that has fired and lies recoiled inboard.
pub const DRILL: [Step; 9] = [
    Step { label: "sponge out", station: 1, skill: "gunnery", base_s: 5.0, effort: 0.3, mass: Mass::None, takes: None },
    Step { label: "load a cartridge", station: 2, skill: "gunnery", base_s: 4.0, effort: 0.1, mass: Mass::None, takes: Some(Store::Powder) },
    Step { label: "ram the charge home", station: 1, skill: "gunnery", base_s: 3.0, effort: 0.4, mass: Mass::None, takes: None },
    Step { label: "wad", station: 2, skill: "gunnery", base_s: 2.0, effort: 0.1, mass: Mass::None, takes: None },
    Step { label: "load round shot", station: 2, skill: "gunnery", base_s: 3.5, effort: 0.6, mass: Mass::Shot, takes: Some(Store::Shot) },
    Step { label: "ram the shot home", station: 1, skill: "gunnery", base_s: 3.5, effort: 0.5, mass: Mass::Shot, takes: None },
    Step { label: "run out", station: 3, skill: "seamanship", base_s: 7.0, effort: 1.0, mass: Mass::Gun, takes: None },
    Step { label: "prime the vent", station: 0, skill: "gunnery", base_s: 3.0, effort: 0.0, mass: Mass::None, takes: None },
    Step { label: "lay the gun", station: 0, skill: "gunlaying", base_s: 4.0, effort: 0.2, mass: Mass::None, takes: None },
];

/// The step a freshly fired gun starts from, and the one that leaves it ready.
pub const READY: usize = DRILL.len();

/// Seconds for one man of this ability to do this job now.
#[allow(clippy::too_many_arguments)]
pub fn step_time(step: &Step, skill: f32, fatigue: f32, physique: f32, shot_kg: f32, gun_kg: f32, hands: usize, own_station: bool) -> f32 {
    let mut t = step.base_s * (0.6 + (1.0 - skill.clamp(0.0, 1.0)));
    match step.mass {
        Mass::Shot => t *= (shot_kg / 5.4).powf(0.4),
        // Everyone at the gun tails on to the side tackles: a tonne a man is
        // the difference between a gun run out briskly and one that crawls.
        Mass::Gun => t *= (gun_kg / (hands.max(1) as f32 * 750.0)).clamp(0.5, 3.5),
        Mass::None => {}
    }
    t *= 1.0 + 0.6 * fatigue.max(0.0) * (0.3 + step.effort);
    t /= physique.max(0.2).powf(0.3 + step.effort);
    if !own_station {
        t *= 1.2; // doing another man's job, in his way
    }
    t.max(0.8)
}

/// A gun's state in its drill.
#[derive(Clone, Debug)]
pub struct GunState {
    /// The next step to do (READY when she is loaded, run out and laid).
    pub step: usize,
    /// Seconds put into the current step so far.
    pub done: f32,
    /// How long the current step takes the man doing it.
    pub needs: f32,
    /// Who is doing it (index into the ship's company).
    pub by: Option<usize>,
    /// Training (radians toward the bow) and elevation she is laid at.
    pub train: f32,
    pub elevation: f32,
    /// The range the gun captain judged, and when.
    pub judged: f32,
    /// Rounds fired.
    pub fired: u32,
    /// Out of action (a dismounted gun).
    pub disabled: bool,
    /// Why she is waiting, for the orders panel.
    pub waiting: &'static str,
}

impl Default for GunState {
    fn default() -> Self {
        // Guns are kept loaded at sea; she needs running out, priming and laying.
        GunState { step: 6, done: 0.0, needs: 0.0, by: None, train: 0.0, elevation: 0.0, judged: 0.0, fired: 0, disabled: false, waiting: "" }
    }
}

impl GunState {
    pub fn ready(&self) -> bool {
        self.step >= READY && !self.disabled
    }

    pub fn loaded(&self) -> bool {
        self.step >= 6
    }

    pub fn next(&self) -> Option<&'static Step> {
        DRILL.get(self.step)
    }

    /// She has fired and recoiled inboard: all of it again.
    pub fn fire(&mut self) {
        self.step = 0;
        self.done = 0.0;
        self.by = None;
        self.fired += 1;
    }

    /// What she is doing, for the panels.
    pub fn status(&self) -> String {
        if self.disabled {
            "dismounted".into()
        } else if self.ready() {
            "ready".into()
        } else if !self.waiting.is_empty() {
            self.waiting.to_string()
        } else {
            let s = &DRILL[self.step];
            format!("{} ({:.0}%)", s.label, 100.0 * self.done / self.needs.max(0.1))
        }
    }
}

/// Largest training either way of the beam, and the elevation limits.
pub const MAX_TRAIN: f32 = 12.0 * std::f32::consts::PI / 180.0;
pub const MAX_ELEV: f32 = 8.0 * std::f32::consts::PI / 180.0;
pub const MIN_ELEV: f32 = -4.0 * std::f32::consts::PI / 180.0;
