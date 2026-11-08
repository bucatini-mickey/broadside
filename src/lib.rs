//! Broadside: Napoleonic naval command, Dwarf Fortress style, on the
//! Tachyon engine. The game is a library (so it can be tested headless)
//! with a thin executable in `main.rs`.
//!
//! - `data`: ship classes from `data/ships/*.yaml`
//! - `hull`: a ship's grid, decks, fittings and stations, built from her class
//! - `crew`: her company: names, backgrounds, skills, roles; men aboard as creatures
//! - `drill`: the gun drill, step by step
//! - `board`: boarders away: the quarter bill's party crosses between fouled ships
//! - `foul`: ships that meet slowly are made fast, and cut apart by hands at the rails
//! - `ship`: a ship in commission: orders, helm, sail, quarters, guns
//! - `ai`: captains for the ships you don't command
//! - `game`: the world at sea, shot and its consequences, scenarios
//! - `signals`: the code book of numbered signals
//! - `contacts`: what a ship knows of the others (seen, hull down, lost)
//! - `glass`: a first-person look along a bearing, and the words for what is seen
//! - `screen`: the command screen

pub mod ai;
pub mod board;
pub mod contacts;
pub mod crew;
pub mod data;
pub mod drill;
pub mod foul;
pub mod game;
pub mod glass;
pub mod hull;
pub mod screen;
pub mod signals;
pub mod ship;
