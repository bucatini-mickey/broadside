# Broadside

Napoleonic naval command, Dwarf Fortress style: a pure-ASCII terminal game on the [Tachyon](https://github.com/bucatini-mickey/tachyon) engine.

## Layout
```
Cargo.toml, src/, tests/   the game (Rust, on Tachyon)
data/ships/                ship classes (YAML)
docs/legacy/               the original design docs, the spec for what is still to port
legacy/                    the first Broadside (Python); kept until everything is ported, then deleted
```

## Run
Tachyon must be checked out beside this repo (`../Tachyon`).
```
cargo run --release
cargo run --release -- --scenario action --ticks 600 --quarters --snapshot snaps/bs.html
cargo test --release
```
Scenarios: `action`, `frigates`, `odds`, `line`, `free --class <key>`.

The legacy game: `cd legacy`, then `python -m venv .venv`, `pip install -r requirements.txt`, and `PYTHONPATH=src python -m broadside.main` (see `legacy/README.md`).
