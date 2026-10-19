# Generate a world and look at it.
#
#   python -m broadside.worldgen --seed 1805
#   python -m broadside.worldgen --seed 7 --captain "Jack Aubrey" --ship Surprise --nation Albion --out world
#
# Prints a summary and the political map to the terminal; with --out,
# writes map.html (political and terrain maps) and chronicle.md (the
# world's history) to that folder.

from __future__ import annotations

import argparse
import html
import os
import sys

from broadside.render.buffer import ScreenBuffer
from broadside.view.export import to_ansi, to_html
from broadside.worldgen.world import CampaignSetup, generate_world, render_map


def chronicle_md(world) -> str:
    p = world.player_nation
    lines = [f"# Chronicle of world {world.seed}", "", world.summary(), "", "## Nations", ""]
    for n in world.nations:
        ports = world.places_of(n.id)
        cap = world.settlement(n.capital).name if n.capital >= 0 else "-"
        tag = " (you)" if n.player else ""
        lines.append(f"- **{n.name}**{tag} - {n.adjective} {n.government}; seat {cap}; {len(ports)} ports; navy ~{n.navy} ships of force.")
    lines += ["", "## Famous ships", ""]
    for name, nid, launched, fate in world.history.ships[-25:]:
        lines.append(f"- *{name}* ({world.nations[nid].name}, launched {launched}){' - ' + fate if fate else ''}")
    lines += ["", "## Admirals", ""]
    for f in world.history.figures[-20:]:
        lines.append(f"- {f.name} of {world.nations[f.nation].name}{' - ' + '; '.join(f.deeds) if f.deeds else ''}")
    lines += ["", "## Events", ""]
    for e in world.history.events:
        lines.append(f"- **{e.year}** {e.text}")
    lines.append("")
    del p
    return "\n".join(lines)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="python -m broadside.worldgen")
    ap.add_argument("--seed", type=int, default=1805)
    ap.add_argument("--captain")
    ap.add_argument("--ship")
    ap.add_argument("--nation")
    ap.add_argument("--out", help="folder to write map.html and chronicle.md")
    ap.add_argument("--width", type=int, default=180, help="terminal map width")
    ap.add_argument("--ansi", action="store_true", help="colour map in the terminal")
    args = ap.parse_args(argv)
    world = generate_world(args.seed, CampaignSetup(captain=args.captain, ship=args.ship, nation=args.nation))
    print(world.summary())
    w = args.width
    h = max(10, int(w * world.geo.shape[0] / world.geo.shape[1] / 2.0))
    buf = ScreenBuffer(w, h)
    render_map(buf, world, mode="political")
    if args.ansi:
        print(to_ansi(buf))
    for n in world.nations:
        print(f"  {n.name:<34} {n.adjective:<10} {n.government:<26} {len(world.places_of(n.id)):>3} ports{'  <- you' if n.player else ''}")
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        big_w = world.geo.shape[1]
        big_h = world.geo.shape[0] // 2 * 2 // 2 * 2 // 2  # rows ~ half, cells are tall
        pages = []
        for mode in ("political", "terrain"):
            b = ScreenBuffer(big_w, big_h)
            render_map(b, world, mode=mode)
            pages.append(f"<h2>{mode.title()} map</h2><pre style='font:10px/1.0 Cascadia Mono,Consolas,monospace'>{to_html(b)}</pre>")
        legend = "".join(
            f"<li><span style='color:rgb{n.color}'>&#9632;</span> {html.escape(n.name)} - {html.escape(n.adjective)} {html.escape(n.government)}{' (you)' if n.player else ''}</li>"
            for n in world.nations
        )
        with open(os.path.join(args.out, "map.html"), "w", encoding="utf-8") as f:
            f.write(f"<!doctype html><meta charset='utf-8'><title>World {world.seed}</title><body style='background:#0b0c10;color:#ddd;font-family:system-ui'>"
                    f"<h1>World {world.seed}</h1><p>{html.escape(world.summary())}</p><ul>{legend}</ul>"
                    f"<p>Settlements: * capital, &#9632; fortress, &#9679; port, &middot; village</p>{''.join(pages)}</body>")
        with open(os.path.join(args.out, "chronicle.md"), "w", encoding="utf-8") as f:
            f.write(chronicle_md(world))
        print(f"Wrote {args.out}/map.html and {args.out}/chronicle.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
