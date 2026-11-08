//! Broadside: Napoleonic naval command, Dwarf Fortress style.
//!
//!     cargo run --release
//!     cargo run --release -- --scenario action --ticks 600 --snapshot out.html
//!     cargo run --release -- --scenario action --bench 600
//!
//! Scenarios: action, frigates, odds, line, free (a brig; --class <key> for another).


use broadside::game::{Game as World_, Scenario, SECS};
use broadside::glass::{self, Glass};
use broadside::{ai, data, screen};
use broadside::screen::{Mode, Panel, Ui};
use broadside::ship::Fire;
use std::io;
use std::time::Instant;
use tachyon::prelude::*;
use tachyon::ui::{self, panel, paragraph, Menu, Pick, Theme};

const TITLE: [&str; 6] = [
    r" ____  ____   ___    _    ____   ____ ___ ____  _____ ",
    r"| __ )|  _ \ / _ \  / \  |  _ \ / ___|_ _|  _ \| ____|",
    r"|  _ \| |_) | | | |/ _ \ | | | |\___ \| || | | |  _|  ",
    r"| |_) |  _ <| |_| / ___ \| |_| | ___) | || |_| | |___ ",
    r"|____/|_| \_\\___/_/   \_\____/ |____/___|____/|_____|",
    r"",
];

enum State {
    Menu,
    Ships,
    Help,
    Playing,
}

struct App {
    state: State,
    menu: Menu,
    ships: Menu,
    game: Option<World_>,
    ui: Option<Ui>,
    paused: bool,
    speed: f64,
    theme: Theme,
    seed: u64,
}

fn main_menu() -> Menu {
    Menu::new(vec![
        ("Single action: brig against brig".into(), "Two 14-gun brigs off an island, a fresh breeze from the south-west. Beat to quarters, close her, and fight her guns with yours.".into()),
        ("Frigate duel".into(), "Two 38-gun frigates, 284 men apiece: the classic single-ship action of the age.".into()),
        ("Against the odds".into(), "Your 18-gun sloop against a brig and a cutter that mean to take you between them.".into()),
        ("Ship of the line".into(), "A 74 against a 74: three decks of guns, a battery below you cannot see, and six hundred men.".into()),
        ("Free sailing".into(), "Any ship you like, the sea, the tide and the wind, and nobody telling you what to do.".into()),
        ("Help: how to command".into(), "The keys, and the few worth remembering.".into()),
        ("Quit".into(), "Leave the ship.".into()),
    ])
}

impl App {
    fn new(seed: u64) -> App {
        let classes = data::load_all();
        let ships = Menu::new(classes.iter().map(|c| (format!("{} ({})", c.name, c.rate), format!("{:.1} m, {} guns, {} men. {}", c.length_m, c.total_guns(), c.max_crew, c.notes))).collect());
        App { state: State::Menu, menu: main_menu(), ships, game: None, ui: None, paused: false, speed: 2.0, theme: Theme::default(), seed }
    }

    fn start(&mut self, s: Scenario) {
        let g = World_::new(s, self.seed);
        self.ui = Some(Ui::new(&g));
        self.game = Some(g);
        self.state = State::Playing;
        self.paused = false;
        self.seed = self.seed.wrapping_add(1);
    }

    fn play_key(&mut self, k: KeyEvent) -> Flow {
        let (Some(g), Some(ui)) = (self.game.as_mut(), self.ui.as_mut()) else { return Flow::Continue };
        ui.message.clear();
        if ui.confirm_strike {
            ui.confirm_strike = false;
            if k.key == Key::Char('S') {
                g.strike();
            }
            return Flow::Continue;
        }
        // The glass takes the arrows, Tab, f and the field; t/T and Esc put it down.
        if ui.mode == Mode::Glass {
            let gl = &mut ui.glass;
            let mut handled = true;
            match k.key {
                Key::Left => gl.sweep(-1.0),
                Key::Right => gl.sweep(1.0),
                Key::Up => gl.tilt(gl.field / 8.0),
                Key::Down => gl.tilt(-gl.field / 8.0),
                Key::Char('+') | Key::Char('=') => gl.zoom(true),
                Key::Char('-') => gl.zoom(false),
                Key::Char('f') => gl.ahead(),
                Key::Tab => match gl.next(g) {
                    Some(i) => {
                        let line = glass::report_one(g, i, gl.power()).unwrap_or_default();
                        g.say(format!("The {}: {line}.", g.ships[i].name), Rgb(236, 222, 180));
                    }
                    None => ui.message = "No ship in sight.".into(),
                },
                Key::Esc => ui.mode = Mode::Command,
                Key::Char('t') | Key::Char('T') if gl.glass == (k.key == Key::Char('t')) => ui.mode = Mode::Command,
                Key::Char('t') | Key::Char('T') => *gl = Glass { rel: gl.rel, pitch: gl.pitch, hold: gl.hold, ..Glass::new(k.key == Key::Char('t')) },
                _ => handled = false,
            }
            if handled {
                return Flow::Continue;
            }
        }
        // Walk and look modes take the arrows.
        if matches!(ui.mode, Mode::Walk | Mode::Look) {
            let dir = match k.key {
                Key::Up | Key::Char('k') => Some((0, -1)),
                Key::Down | Key::Char('j') => Some((0, 1)),
                Key::Left | Key::Char('h') => Some((-1, 0)),
                Key::Right | Key::Char('l') if ui.mode == Mode::Walk => Some((1, 0)),
                Key::Right => Some((1, 0)),
                Key::Char('y') => Some((-1, -1)),
                Key::Char('u') => Some((1, -1)),
                Key::Char('b') if ui.mode == Mode::Walk => Some((-1, 1)),
                Key::Char('n') if ui.mode == Mode::Walk => Some((1, 1)),
                _ => None,
            };
            if k.key == Key::Esc || (ui.mode == Mode::Walk && k.key == Key::Char('m')) || (ui.mode == Mode::Look && k.key == Key::Char('l')) {
                ui.mode = Mode::Command;
                ui.level = g.you().layout.deck_z;
                return Flow::Continue;
            }
            if let Some((dx, dy)) = dir {
                match ui.mode {
                    Mode::Walk => {
                        if let Some(id) = g.ships[0].you() {
                            let s = &mut g.ships[0].craft.scene;
                            movement::step(&s.world, &mut s.things, id, dx, dy);
                        }
                    }
                    _ => ui.cursor = ui.cursor.offset(dx, dy, 0),
                }
                return Flow::Continue;
            }
            match k.key {
                Key::Char('<') | Key::Char('>') if ui.mode == Mode::Walk => {
                    if let Some(id) = g.ships[0].you() {
                        let s = &mut g.ships[0].craft.scene;
                        if movement::climb(&s.world, &mut s.things, id, k.key == Key::Char('<')).is_none() {
                            ui.message = "There is no ladder here.".into();
                        }
                    }
                    return Flow::Continue;
                }
                Key::PageUp if ui.mode == Mode::Look => {
                    ui.cursor.z = (ui.cursor.z + 1).min(g.you().layout.deck_z + 1);
                    return Flow::Continue;
                }
                Key::PageDown if ui.mode == Mode::Look => {
                    ui.cursor.z = (ui.cursor.z - 1).max(1);
                    return Flow::Continue;
                }
                _ => {}
            }
        }
        // The crew roster takes the arrows when it is showing.
        if ui.panel == Panel::Crew && ui.mode == Mode::Command {
            let n = g.you().people.len();
            match ui.crew.list.key(&k, n, 10) {
                Pick::Moved => return Flow::Continue,
                Pick::Chosen(i) => {
                    let you = g.you();
                    if let Some(p) = you.people.get(i).and_then(|p| you.pos_of(p)) {
                        ui.mode = Mode::Look;
                        ui.cursor = p;
                    } else {
                        ui.message = "He is below, not aboard in the simulation.".into();
                    }
                    return Flow::Continue;
                }
                _ => {}
            }
        }
        let you = &mut g.ships[0];
        match k.key {
            Key::Char('q') => {
                self.state = State::Menu;
                return Flow::Continue;
            }
            Key::Tab => {
                ui.panel = match ui.panel {
                    Panel::Log => Panel::Crew,
                    Panel::Crew => Panel::Orders,
                    Panel::Orders => Panel::Ship,
                    Panel::Ship => Panel::Keys,
                    Panel::Keys => Panel::Log,
                }
            }
            Key::Char('1') => ui.panel = Panel::Log,
            Key::Char('2') => ui.panel = Panel::Crew,
            Key::Char('3') => ui.panel = Panel::Orders,
            Key::Char('4') => ui.panel = Panel::Ship,
            Key::Char('5') => ui.panel = Panel::Keys,
            Key::Char('a') => you.alter_course(-5f32.to_radians()),
            Key::Char('d') => you.alter_course(5f32.to_radians()),
            Key::Char('A') => you.alter_course(-30f32.to_radians()),
            Key::Char('D') => you.alter_course(30f32.to_radians()),
            Key::Char('x') => you.orders.course = Some(you.craft.heading),
            Key::Char('c') => {
                you.orders.cut_free = !you.orders.cut_free;
                ui.message = if you.orders.cut_free { "Cut us free: hands to the rails (if we are fouled).".into() } else { "Belay cutting.".into() };
            }
            Key::Char('w') => you.orders.sail = (you.orders.sail + 0.25).min(1.0),
            Key::Char('s') => you.orders.sail = (you.orders.sail - 0.25).max(0.0),
            Key::Char('b') => you.orders.quarters = !you.orders.quarters,
            Key::Char('f') => {
                you.orders.fire = if you.orders.fire == Fire::AtWill { Fire::Hold } else { Fire::AtWill };
                if you.orders.target.is_none() {
                    ui.message = "Name a mark first (n), or the guns are laid level.".into();
                }
            }
            Key::Char('[') => you.orders.fire = Fire::Broadside(-1),
            Key::Char(']') => you.orders.fire = Fire::Broadside(1),
            Key::Char('n') => {
                let n = g.ships.len();
                if n > 1 {
                    let cur = g.ships[0].orders.target.unwrap_or(0);
                    let mut next = cur;
                    for k in 1..=n {
                        let c = (cur + k) % n;
                        if c != 0 && !g.ships[c].struck {
                            next = c;
                            break;
                        }
                    }
                    if next != 0 {
                        g.ships[0].orders.target = Some(next);
                        let name = g.ships[next].name.clone();
                        g.say(format!("The guns are to be laid on the {name}."), Rgb(232, 196, 96));
                    }
                }
            }
            Key::Char('m') => {
                ui.mode = Mode::Walk;
            }
            Key::Char('t') | Key::Char('T') => {
                // Taking up the glass puts you down out of walk mode: the arrows are the glass's.
                ui.mode = Mode::Glass;
                let gl = &ui.glass;
                ui.glass = Glass { rel: gl.rel, pitch: gl.pitch, hold: gl.hold, ..Glass::new(k.key == Key::Char('t')) };
                for line in glass::report(g, &ui.glass) {
                    g.say(line, Rgb(236, 222, 180));
                }
            }
            Key::Char('l') => {
                ui.mode = Mode::Look;
                ui.cursor.z = ui.level;
            }
            Key::PageUp => ui.level = (ui.level + 1).min(g.ships[0].layout.deck_z + 1),
            Key::PageDown => ui.level = (ui.level - 1).max(1),
            Key::Char('+') | Key::Char('=') => ui.mpc = (ui.mpc / 1.5).max(2.0),
            Key::Char('-') => ui.mpc = (ui.mpc * 1.5).min(200.0),
            Key::Char(' ') => self.paused = !self.paused,
            Key::Char(',') => self.speed = (self.speed / 2.0).max(0.5),
            Key::Char('.') => self.speed = (self.speed * 2.0).min(32.0),
            Key::Char('S') => ui.confirm_strike = true,
            Key::Esc => ui.mode = Mode::Command,
            _ => {}
        }
        Flow::Continue
    }
}

impl tachyon::app::Game for App {
    fn tick(&mut self) {
        if let (State::Playing, Some(g)) = (&self.state, self.game.as_mut()) {
            if !self.paused && g.over.is_none() {
                g.tick();
            }
        }
    }

    fn on_key(&mut self, k: KeyEvent) -> Flow {
        match self.state {
            State::Menu => match self.menu.key(&k) {
                Pick::Chosen(0) => self.start(Scenario::Action),
                Pick::Chosen(1) => self.start(Scenario::FrigateDuel),
                Pick::Chosen(2) => self.start(Scenario::Odds),
                Pick::Chosen(3) => self.start(Scenario::TheLine),
                Pick::Chosen(4) => self.state = State::Ships,
                Pick::Chosen(5) => self.state = State::Help,
                Pick::Chosen(6) | Pick::Back => return Flow::Quit,
                _ => {}
            },
            State::Ships => match self.ships.key(&k) {
                Pick::Chosen(i) => self.start(Scenario::FreeSailing(i)),
                Pick::Back => self.state = State::Menu,
                _ => {}
            },
            State::Help => self.state = State::Menu,
            State::Playing => return self.play_key(k),
        }
        Flow::Continue
    }

    fn draw(&mut self, f: &mut Frame, _stats: &LoopStats) {
        let t = self.theme;
        match self.state {
            State::Playing => {
                if let (Some(g), Some(ui)) = (self.game.as_ref(), self.ui.as_mut()) {
                    screen::draw(f, g, ui);
                    if self.paused {
                        f.text(1, f.height() - 3, " PAUSED - space to resume ", t.pick_fg, t.pick_bg);
                    }
                }
            }
            State::Menu | State::Ships | State::Help => {
                f.clear(t.bg);
                let w = f.width();
                for (k, l) in TITLE.iter().enumerate() {
                    let x = (w - l.chars().count() as i32).max(0) / 2;
                    f.text(x, 1 + k as i32, l, t.title, t.bg);
                }
                let sub = "Napoleonic naval command, on the Tachyon engine";
                f.text((w - sub.len() as i32).max(0) / 2, 7, sub, t.dim, t.bg);
                let bw = 72.min(w - 4);
                let r = Rect::new((w - bw) / 2, 9, bw, (f.height() - 11).clamp(8, 22));
                match self.state {
                    State::Menu => {
                        let inner = panel(f, r, "Choose", &t);
                        self.menu.draw(f, inner, &t);
                    }
                    State::Ships => {
                        let inner = panel(f, r, "Free sailing: choose your ship (Esc back)", &t);
                        self.ships.draw(f, inner, &t);
                    }
                    _ => {
                        let inner = panel(f, r, "How to command (any key)", &t);
                        let y = paragraph(f, inner, "You command from the quarterdeck: you give orders, and your people carry them out, as fast as they can. The quartermaster steers the course you set; the topmen set the sail you call for; at quarters every gun is fought by its own crew, step by step, and fires when it is loaded, laid and you give the word.", t.text, t.bg);
                        for (k, (key, what)) in screen::KEYS.iter().enumerate() {
                            let yy = inner.y + y + 1 + k as i32 / 2;
                            let x = inner.x + if k % 2 == 0 { 0 } else { inner.w / 2 };
                            if yy < inner.bottom() {
                                f.text_clip(x, yy, 11, key, t.title, t.bg);
                                f.text_clip(x + 11, yy, inner.w / 2 - 12, what, t.text, t.bg);
                            }
                        }
                    }
                }
            }
        }
        let _ = ui::wrap;
    }

    fn ticks_per_second(&self) -> f64 {
        if matches!(self.state, State::Playing) && !self.paused { self.speed / SECS } else { 0.0 }
    }
}

fn scenario_from(s: &str, class: Option<&str>) -> Scenario {
    match s {
        "frigates" => Scenario::FrigateDuel,
        "odds" => Scenario::Odds,
        "line" => Scenario::TheLine,
        "free" => {
            let classes = data::load_all();
            let i = class.and_then(|k| classes.iter().position(|c| c.key == k)).unwrap_or(2);
            Scenario::FreeSailing(i)
        }
        _ => Scenario::Action,
    }
}

fn main() -> io::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let arg = |name: &str| args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned();
    let flag = |name: &str| args.iter().any(|a| a == name);
    let seed: u64 = arg("--seed").and_then(|s| s.parse().ok()).unwrap_or(1805);

    if let Some(n) = arg("--bench").and_then(|s| s.parse::<u32>().ok()) {
        let s = scenario_from(&arg("--scenario").unwrap_or_default(), arg("--class").as_deref());
        let t = Instant::now();
        let mut g = World_::new(s, seed);
        if flag("--auto") {
            g.captains[0] = Some(ai::Captain::from(&g.ships[0].people[0]));
        }
        println!("{} built in {:.0} ms; {} creatures aboard", s.title(), t.elapsed().as_secs_f64() * 1000.0, g.ships.iter().map(|s| s.craft.scene.life.creatures.len()).sum::<usize>());
        let t = Instant::now();
        for _ in 0..n {
            g.tick();
        }
        let el = t.elapsed().as_secs_f64();
        println!("{n} ticks ({:.0} game s) in {el:.2} s: {:.2} ms a tick", n as f64 * SECS, el * 1000.0 / n as f64);
        if flag("--log") {
            for (l, _) in &g.log.lines {
                println!("  {l}");
            }
        }
        return Ok(());
    }

    if let Some(path) = arg("--snapshot") {
        let s = scenario_from(&arg("--scenario").unwrap_or_default(), arg("--class").as_deref());
        let ticks: usize = arg("--ticks").and_then(|s| s.parse().ok()).unwrap_or(60);
        let mut g = World_::new(s, seed);
        let mut ui = Ui::new(&g);
        if flag("--auto") {
            g.captains[0] = Some(ai::Captain::from(&g.ships[0].people[0]));
        }
        if flag("--quarters") {
            g.ships[0].orders.quarters = true;
            g.ships[0].orders.target = Some(1).filter(|_| g.ships.len() > 1);
            g.ships[0].orders.fire = Fire::AtWill;
        }
        if let Some(p) = arg("--panel") {
            ui.panel = match p.as_str() {
                "crew" => Panel::Crew,
                "orders" => Panel::Orders,
                "ship" => Panel::Ship,
                "keys" => Panel::Keys,
                _ => Panel::Log,
            };
        }
        if let Some(l) = arg("--level").and_then(|s| s.parse().ok()) {
            ui.level = l;
        }
        if flag("--walk") {
            ui.mode = Mode::Walk;
        }
        let t = Instant::now();
        for _ in 0..ticks {
            g.tick();
        }
        let per = t.elapsed().as_secs_f64() * 1000.0 / ticks.max(1) as f64;
        // --glass / --eye look out: along --rel degrees off her head, or held on --hold <ship> (default the first stranger).
        if flag("--glass") || flag("--eye") {
            ui.mode = Mode::Glass;
            ui.glass = Glass::new(flag("--glass"));
            if let Some(r) = arg("--rel").and_then(|s| s.parse::<f32>().ok()) {
                ui.glass.rel = r.to_radians();
            } else if g.ships.len() > 1 {
                ui.glass.hold = Some(arg("--hold").and_then(|s| s.parse().ok()).unwrap_or(1).min(g.ships.len() - 1));
            }
            ui.glass.follow(&g);
            for line in glass::report(&g, &ui.glass) {
                println!("  glass: {line}");
            }
        }
        let (fw, fh) = arg("--frame")
            .and_then(|s| {
                let v: Vec<u16> = s.split('x').filter_map(|p| p.parse().ok()).collect();
                (v.len() == 2).then(|| (v[0], v[1]))
            })
            .unwrap_or((180, 56));
        let mut f = Frame::new(fw, fh);
        screen::draw(&mut f, &g, &mut ui);
        tachyon::display::Display::from_env().apply(&mut f);
        std::fs::write(&path, f.to_html())?;
        std::fs::write(format!("{path}.txt"), f.to_text())?;
        println!("{}: {ticks} ticks at {per:.2} ms; wrote {path}", s.title());
        for (l, _) in g.log.lines.iter().rev().take(25).collect::<Vec<_>>().into_iter().rev() {
            println!("  {l}");
        }
        return Ok(());
    }

    let mut app = App::new(seed);
    tachyon::app::run(&mut app, 60)
}
