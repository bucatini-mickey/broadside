# Frame exporters: a ScreenBuffer as plain text, ANSI-coloured text, or an
# HTML <pre> block. Used by the headless scenario runner, the HTML replay
# viewer and tests - the same composed frames the terminal shows.

from __future__ import annotations

import html

from broadside.render.buffer import ScreenBuffer

DEFAULT_BG = (6, 7, 10)


def to_text(buf: ScreenBuffer) -> str:
    return "\n".join("".join(buf.get(x, y).glyph for x in range(buf.width)).rstrip() for y in range(buf.height))


def to_ansi(buf: ScreenBuffer) -> str:
    out = []
    for y in range(buf.height):
        line = []
        last = None
        for x in range(buf.width):
            cell = buf.get(x, y)
            key = (cell.fg, cell.bg)
            if key != last:
                bg = cell.bg or DEFAULT_BG
                line.append(f"\x1b[38;2;{cell.fg[0]};{cell.fg[1]};{cell.fg[2]}m\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m")
                last = key
            line.append(cell.glyph)
        line.append("\x1b[0m")
        out.append("".join(line))
    return "\n".join(out)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


def to_html(buf: ScreenBuffer) -> str:
    """Rows of spans, one span per run of identical colours."""
    rows = []
    for y in range(buf.height):
        parts = []
        run = []
        last = None
        for x in range(buf.width):
            cell = buf.get(x, y)
            key = (cell.fg, cell.bg)
            if key != last and run:
                parts.append(_span(last, "".join(run)))
                run = []
            last = key
            run.append(cell.glyph)
        if run:
            parts.append(_span(last, "".join(run)))
        rows.append("".join(parts))
    return "\n".join(rows)


def _span(key, text: str) -> str:
    fg, bg = key
    bg = bg or DEFAULT_BG
    return f'<span style="color:{_hex(fg)};background:{_hex(bg)}">{html.escape(text)}</span>'
