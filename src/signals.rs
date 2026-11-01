//! The code book of numbered signals (`docs/legacy/17` s3, `19` s3).
//!
//! The twelve flags and what each asks of the captain who reads it, how long
//! a hand takes to bend on and hoist them, and how long an order holds a
//! captain. Hoisting by a real hand, reading through fog, misreading and
//! refusal are not wired yet: this is the book itself.

/// What a signal asks of the ship that reads it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Effect {
    /// More aggression (x100), and engage the nearest enemy known.
    Engage(i32),
    FormLine,
    AllSail,
    Nothing,
    TackInSuccession,
    WearTogether,
    ComeWithinHail,
    ReportDamage,
    Discontinue,
    Anchor,
    PrepareToBoard,
    WellDone,
}

#[derive(Clone, Copy, Debug)]
pub struct Signal {
    pub number: u8,
    pub text: &'static str,
    pub effect: Effect,
}

pub const BOOK: [Signal; 12] = [
    Signal { number: 1, text: "Engage the enemy more closely", effect: Effect::Engage(25) },
    Signal { number: 2, text: "Form line of battle", effect: Effect::FormLine },
    Signal { number: 3, text: "Make all sail", effect: Effect::AllSail },
    Signal { number: 4, text: "Enemy in sight", effect: Effect::Nothing },
    Signal { number: 5, text: "Tack in succession", effect: Effect::TackInSuccession },
    Signal { number: 6, text: "Wear together", effect: Effect::WearTogether },
    Signal { number: 7, text: "Come within hail", effect: Effect::ComeWithinHail },
    Signal { number: 8, text: "Report your damage", effect: Effect::ReportDamage },
    Signal { number: 9, text: "Discontinue the action", effect: Effect::Discontinue },
    Signal { number: 10, text: "Anchor", effect: Effect::Anchor },
    Signal { number: 11, text: "Prepare to board", effect: Effect::PrepareToBoard },
    Signal { number: 12, text: "Well done", effect: Effect::WellDone },
];

/// Who a signal is made to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Addressee {
    Ship(usize),
    Squadron,
}

impl Addressee {
    pub fn includes(self, ship: usize) -> bool {
        match self {
            Addressee::Ship(s) => s == ship,
            Addressee::Squadron => true,
        }
    }
}

/// The signal flown as number `n` (1..=12).
pub fn by_number(n: u8) -> Option<&'static Signal> {
    BOOK.iter().find(|s| s.number == n)
}

/// Seconds for a hand to bend on and hoist: 8 for the best, 20 for a landsman.
pub fn hoist_seconds(skill: f32) -> f32 {
    20.0 - 12.0 * skill.clamp(0.0, 1.0)
}

/// Seconds an order holds a captain before he returns to his own judgement:
/// one minute for the undisciplined, six for the strict.
pub fn hold_seconds(discipline: f32) -> f32 {
    60.0 + 300.0 * discipline.clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_book_is_numbered_one_to_twelve() {
        for (i, s) in BOOK.iter().enumerate() {
            assert_eq!(s.number as usize, i + 1);
            assert_eq!(by_number(s.number).unwrap().text, s.text);
        }
        assert!(by_number(0).is_none() && by_number(13).is_none());
        assert_eq!(by_number(9).unwrap().effect, Effect::Discontinue);
    }

    #[test]
    fn hoisting_and_holding_times_follow_the_men() {
        assert_eq!(hoist_seconds(1.0), 8.0);
        assert_eq!(hoist_seconds(0.0), 20.0);
        assert_eq!(hold_seconds(0.0), 60.0);
        assert_eq!(hold_seconds(1.0), 360.0);
        assert!(Addressee::Squadron.includes(3) && Addressee::Ship(2).includes(2) && !Addressee::Ship(2).includes(3));
    }
}
