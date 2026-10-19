//! Broadside: Napoleonic naval command, Dwarf Fortress style, on the
//! Tachyon engine. The game is a library (so it can be tested headless)
//! with a thin executable in `main.rs`.
//!
//! - `data`: ship classes from `data/ships/*.yaml`
//! - `hull`: a ship's grid, decks, fittings and stations, built from her class
//! - `crew`: her company: names, backgrounds, skills, roles; men aboard as creatures
//! - `drill`: the gun drill, step by step
//! - `ship`: a ship in commission: orders, helm, sail, quarters, guns
//! - `ai`: captains for the ships you don't command
//! - `game`: the world at sea, shot and its consequences, scenarios
//! - `screen`: the command screen

pub mod ai;
pub mod crew;
pub mod data;
pub mod drill;
pub mod game;
pub mod hull;
pub mod screen;
pub mod ship;
