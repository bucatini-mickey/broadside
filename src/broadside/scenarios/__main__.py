# Command line for the scenario library.
#
#   python -m broadside.scenarios list
#   python -m broadside.scenarios run <key>              play it in the terminal
#   python -m broadside.scenarios check [keys] [--quick] run headless, verify expectations
#   python -m broadside.scenarios snapshot <key> [--ansi] print checkpoint frames
#   python -m broadside.scenarios replay [keys] [--out replays]   HTML replays

from __future__ import annotations

import argparse
import sys

from broadside.scenarios.base import all_scenarios, get


def _utf8_stdout() -> None:
    # Windows consoles default to a legacy code page; the frames are full of
    # box-drawing and block characters.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cmd_list(_args) -> int:
    for s in all_scenarios():
        print(f"{s.key:<22} {s.title}{'  (slow)' if s.slow else ''}")
        print(f"{'':<22} {s.summary}")
    return 0


def cmd_run(args) -> int:
    from broadside.ui.app import run_interactive

    scn = get(args.key)
    run = scn.build(args.seed) if args.seed is not None else scn.build()
    return run_interactive(run, scn)


def cmd_check(args) -> int:
    from broadside.scenarios.runner import play

    scns = [get(k) for k in args.keys] if args.keys else all_scenarios()
    if args.quick:
        scns = [s for s in scns if not s.slow]
    failed = 0
    for s in scns:
        pb = play(s, frames=False)
        mark = "PASS" if pb.passed else "FAIL"
        print(f"{mark}  {s.key:<22} ({pb.wall_s:.1f}s wall, {s.duration_s:.0f}s sim)")
        for r in pb.results:
            print(f"      t={r.time_s:6.1f}  {'ok  ' if r.ok else 'FAIL'}  {r.label}   [{r.detail}]")
        failed += 0 if pb.passed else 1
    print(f"\n{len(scns) - failed}/{len(scns)} scenarios passed")
    return 1 if failed else 0


def cmd_snapshot(args) -> int:
    from broadside.scenarios.runner import play
    from broadside.view.export import to_ansi, to_text

    pb = play(get(args.key), width=args.width, height=args.height)
    for f in pb.frames:
        if args.at is not None and abs(f.time_s - args.at) > 0.51:
            continue
        print(to_ansi(f.buffer) if args.ansi else to_text(f.buffer))
        for r in f.results:
            print(f"  {'ok  ' if r.ok else 'FAIL'} {r.label} [{r.detail}]")
        print()
    return 0


def cmd_replay(args) -> int:
    from broadside.scenarios.replay import export_all

    keys = args.keys or None
    paths = export_all(args.out, keys=keys, every_s=args.every, width=args.width, height=args.height, progress=print)
    print(f"\nWrote {len(paths)} files. Open {args.out}/index.html in a browser.")
    return 0


def main(argv=None) -> int:
    _utf8_stdout()
    p = argparse.ArgumentParser(prog="python -m broadside.scenarios", description="Broadside scenario library.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list scenarios").set_defaults(fn=cmd_list)
    r = sub.add_parser("run", help="play a scenario in the terminal")
    r.add_argument("key")
    r.add_argument("--seed", type=int)
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check", help="run headless and verify expectations")
    c.add_argument("keys", nargs="*")
    c.add_argument("--quick", action="store_true", help="skip slow scenarios")
    c.set_defaults(fn=cmd_check)
    s = sub.add_parser("snapshot", help="print checkpoint frames")
    s.add_argument("key")
    s.add_argument("--at", type=float, help="only the checkpoint(s) at this time")
    s.add_argument("--ansi", action="store_true", help="colour output (needs a true-colour terminal)")
    s.add_argument("--width", type=int, default=190)
    s.add_argument("--height", type=int, default=64)
    s.set_defaults(fn=cmd_snapshot)
    x = sub.add_parser("replay", help="export HTML replays")
    x.add_argument("keys", nargs="*")
    x.add_argument("--out", default="replays")
    x.add_argument("--every", type=float, default=5.0, help="seconds between regular frames")
    x.add_argument("--width", type=int, default=190)
    x.add_argument("--height", type=int, default=64)
    x.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
