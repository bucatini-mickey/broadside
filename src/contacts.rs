//! Contact records: what a ship knows of other ships (`docs/legacy/07`,
//! "Contacts"). Knowledge, not truth: a ship out of sight is kept at her last
//! known position, marked lost, and the macro chart draws the record.
//!
//! A contact is `Hull` when her hull shows, `Topsails` when only her masts
//! do (hull down), and `Lost` once she has not been seen for three seconds.
//! Not yet wired: the game does not feed these from the lookouts, and the AI
//! still uses true positions.

use tachyon::sight::Seen;

/// Seconds unseen before a contact is lost.
pub const LOST_AFTER: f64 = 3.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Hull,
    Topsails,
    Lost,
}

#[derive(Clone, Copy, Debug)]
pub struct Record {
    pub ship: usize,
    pub kind: Kind,
    pub x: f32,
    pub y: f32,
    pub heading: f32,
    /// Game time last seen.
    pub seen_at: f64,
}

/// What a look shows: a hull, topsails only, or nothing.
pub fn classify(s: &Seen) -> Option<Kind> {
    if s.clarity < 1.0 {
        None
    } else if s.hull_down {
        Some(Kind::Topsails)
    } else {
        Some(Kind::Hull)
    }
}

#[derive(Clone, Debug, Default)]
pub struct Book {
    pub records: Vec<Record>,
}

impl Book {
    /// Note what one look at `ship` showed, her true state being `x, y, heading`.
    pub fn observe(&mut self, ship: usize, seen: Option<Kind>, x: f32, y: f32, heading: f32, now: f64) {
        let Some(kind) = seen else { return };
        let r = Record { ship, kind, x, y, heading, seen_at: now };
        match self.records.iter_mut().find(|r| r.ship == ship) {
            Some(old) => *old = r,
            None => self.records.push(r),
        }
    }

    /// Age the book: anything unseen for `LOST_AFTER` seconds becomes `Lost`,
    /// keeping its last known position.
    pub fn age(&mut self, now: f64) {
        for r in &mut self.records {
            if now - r.seen_at >= LOST_AFTER {
                r.kind = Kind::Lost;
            }
        }
    }

    pub fn get(&self, ship: usize) -> Option<&Record> {
        self.records.iter().find(|r| r.ship == ship)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seen(clarity: f32, hull_down: bool) -> Seen {
        Seen { clarity, hull_down, ..Default::default() }
    }

    #[test]
    fn hull_topsails_then_lost_at_the_last_known_place() {
        assert_eq!(classify(&seen(0.5, false)), None);
        assert_eq!(classify(&seen(2.0, false)), Some(Kind::Hull));
        assert_eq!(classify(&seen(2.0, true)), Some(Kind::Topsails));
        let mut b = Book::default();
        b.observe(4, classify(&seen(2.0, true)), 100.0, 200.0, 1.0, 10.0);
        assert_eq!(b.get(4).unwrap().kind, Kind::Topsails);
        b.observe(4, classify(&seen(2.0, false)), 110.0, 210.0, 1.0, 11.0);
        assert_eq!(b.records.len(), 1);
        assert_eq!(b.get(4).unwrap().kind, Kind::Hull);
        b.age(13.0);
        assert_eq!(b.get(4).unwrap().kind, Kind::Hull);
        b.age(14.5);
        let r = b.get(4).unwrap();
        assert_eq!((r.kind, r.x, r.y), (Kind::Lost, 110.0, 210.0));
        b.observe(4, None, 999.0, 999.0, 0.0, 15.0);
        assert_eq!(b.get(4).unwrap().x, 110.0, "unseen: the record does not move");
    }
}
