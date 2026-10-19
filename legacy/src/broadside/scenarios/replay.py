# HTML replay export: every scenario rendered headless into a self-contained
# web page you can scrub through - the same full-screen frames (scene +
# HUD) the terminal shows, with each checkpoint's caption and pass/fail.
#
# Frames are stored compactly (a shared colour palette and runs of
# same-coloured text) and drawn by a few lines of JavaScript, so a whole
# scenario is a megabyte or two rather than tens.

from __future__ import annotations

import html
import json
import os
from typing import Callable, Optional

from broadside.render.buffer import ScreenBuffer
from broadside.scenarios.base import Scenario, all_scenarios, get
from broadside.scenarios.runner import Playback, play

DEFAULT_BG = (6, 7, 10)


class _Palette:
    def __init__(self) -> None:
        self.index: dict = {}
        self.colors: list = []

    def __call__(self, rgb) -> int:
        rgb = tuple(int(v) for v in (rgb or DEFAULT_BG))
        i = self.index.get(rgb)
        if i is None:
            i = len(self.colors)
            self.index[rgb] = i
            self.colors.append("#%02x%02x%02x" % rgb)
        return i


def encode_frame(buf: ScreenBuffer, pal: _Palette) -> list:
    rows = []
    for y in range(buf.height):
        runs = []
        text = []
        key = None
        for x in range(buf.width):
            cell = buf.get(x, y)
            k = (pal(cell.fg), pal(cell.bg))
            if k != key and text:
                runs.append(["".join(text), key[0], key[1]])
                text = []
            key = k
            text.append(cell.glyph)
        if text:
            runs.append(["".join(text), key[0], key[1]])
        rows.append(runs)
    return rows


def playback_json(pb: Playback) -> dict:
    pal = _Palette()
    frames = []
    for f in pb.frames:
        frames.append(
            {
                "t": round(f.time_s, 2),
                "caption": f.caption,
                "checkpoint": f.checkpoint,
                "results": [{"label": r.label, "ok": r.ok, "detail": r.detail} for r in f.results],
                "rows": encode_frame(f.buffer, pal),
            }
        )
    s = pb.scenario
    return {
        "key": s.key,
        "title": s.title,
        "summary": s.summary,
        "look_for": s.look_for,
        "passed": pb.passed,
        "palette": pal.colors,
        "frames": frames,
    }


def export_scenario(pb: Playback, out_dir: str) -> str:
    data = playback_json(pb)
    path = os.path.join(out_dir, f"{pb.scenario.key}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_PAGE.replace("__TITLE__", html.escape(pb.scenario.title)).replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    return path


def export_all(out_dir: str, *, keys: Optional[list] = None, every_s: float = 5.0, width: int = 190, height: int = 64, progress: Optional[Callable[[str], None]] = None) -> list:
    os.makedirs(out_dir, exist_ok=True)
    # Named keys are exported whatever they are; a bare run skips the
    # interactive missions, which have nobody at the wheel.
    scns: list[Scenario] = [get(k) for k in keys] if keys else [s for s in all_scenarios() if not s.interactive]
    paths = []
    summary = []
    for s in scns:
        pb = play(s, every_s=every_s, width=width, height=height)
        paths.append(export_scenario(pb, out_dir))
        summary.append((s, pb))
        if progress:
            progress(f"{'PASS' if pb.passed else 'FAIL'}  {s.key:<22} {len(pb.frames)} frames, {pb.wall_s:.1f}s")
    if not keys:
        paths.append(_write_index(out_dir, summary))
    return paths


def _write_index(out_dir: str, summary) -> str:
    items = []
    for s, pb in summary:
        checks = sum(len(f.results) for f in pb.frames)
        ok = sum(1 for f in pb.frames for r in f.results if r.ok)
        badge = f'<span class="badge {"ok" if pb.passed else "bad"}">{ok}/{checks} checks</span>'
        looks = "".join(f"<li>{html.escape(x)}</li>" for x in s.look_for)
        items.append(
            f'<a class="card" href="{s.key}.html"><h2>{html.escape(s.title)} {badge}</h2>'
            f"<p>{html.escape(s.summary)}</p><ul>{looks}</ul>"
            f'<code>python -m broadside.scenarios run {s.key}</code></a>'
        )
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_INDEX.replace("__ITEMS__", "\n".join(items)))
    return path


_STYLE = """
:root{--bg:#0b0c10;--panel:#14161d;--ink:#e6e6ea;--dim:#9a9aa6;--acc:#f0d27a;--ok:#6ec98c;--bad:#e06a5a;--line:#262a36}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
a{color:inherit}
code,pre{font-family:"Cascadia Mono","Cascadia Code",Consolas,"DejaVu Sans Mono",Menlo,monospace}
"""

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ - Broadside replay</title>
<style>""" + _STYLE + """
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:18px;margin:0;color:var(--acc)}
header a{color:var(--dim);text-decoration:none}
main{display:flex;gap:16px;padding:12px 16px;flex-wrap:wrap}
#screenwrap{overflow:auto;max-width:100%;border:1px solid var(--line);background:#06070a}
#screen{margin:0;font-size:12px;line-height:1.0;white-space:pre;letter-spacing:0}
aside{flex:1;min-width:280px;max-width:520px}
.controls{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}
button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
input[type=range]{flex:1;min-width:160px}
.caption{background:var(--panel);border-left:3px solid var(--acc);padding:8px 10px;margin:8px 0;min-height:2.6em}
.res{margin:2px 0;font-size:13px}.res.ok::before{content:"\\2713  ";color:var(--ok)}.res.bad::before{content:"\\2717  ";color:var(--bad)}
.cps{list-style:none;padding:0;margin:0}.cps li{padding:4px 6px;border-radius:4px;cursor:pointer;font-size:13px;color:var(--dim)}
.cps li:hover,.cps li.cur{background:var(--panel);color:var(--ink)}
.cps li b{color:var(--acc);font-weight:600;margin-right:6px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin:16px 0 6px}
ul.look{padding-left:18px;margin:0;font-size:13px;color:var(--dim)}
.size{color:var(--dim);font-size:12px}
</style></head><body>
<header><a href="index.html">&larr; all scenarios</a><h1 id="title"></h1><span id="status"></span></header>
<main>
<div style="flex:0 1 auto;max-width:100%">
<div class="controls"><button id="play">&#9654; Play</button><button id="prev">&lsaquo;</button><button id="next">&rsaquo;</button>
<input type="range" id="slider" min="0" value="0"><span id="time"></span>
<span class="size">text size <button id="smaller">-</button><button id="bigger">+</button></span></div>
<div id="screenwrap"><pre id="screen"></pre></div>
<div class="caption" id="caption"></div><div id="results"></div>
</div>
<aside><p id="summary"></p><h3>What to look for</h3><ul class="look" id="look"></ul>
<h3>Checkpoints</h3><ul class="cps" id="cps"></ul>
<h3>Play it yourself</h3><code id="cmd"></code></aside>
</main>
<script>
const D=__DATA__;
const P=D.palette;const esc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const screen=document.getElementById('screen'),slider=document.getElementById('slider');
document.getElementById('title').textContent=D.title;
document.getElementById('status').innerHTML=D.passed?'<span style="color:var(--ok)">all checks pass</span>':'<span style="color:var(--bad)">some checks fail</span>';
document.getElementById('summary').textContent=D.summary;
document.getElementById('cmd').textContent='python -m broadside.scenarios run '+D.key;
const look=document.getElementById('look');D.look_for.forEach(t=>{const li=document.createElement('li');li.textContent=t;look.appendChild(li)});
slider.max=D.frames.length-1;
const cps=document.getElementById('cps');
D.frames.forEach((f,i)=>{if(!f.checkpoint)return;const li=document.createElement('li');li.dataset.i=i;li.innerHTML='<b>t='+f.t+'s</b>'+esc(f.caption);li.onclick=()=>show(i);cps.appendChild(li)});
function show(i){i=Math.max(0,Math.min(D.frames.length-1,i));slider.value=i;const f=D.frames[i];
screen.innerHTML=f.rows.map(r=>r.map(([t,a,b])=>'<span style="color:'+P[a]+';background:'+P[b]+'">'+esc(t)+'</span>').join('')).join('\\n');
document.getElementById('time').textContent='t = '+f.t.toFixed(1)+' s  ('+(i+1)+'/'+D.frames.length+')';
document.getElementById('caption').textContent=f.caption||'';
document.getElementById('results').innerHTML=f.results.map(r=>'<div class="res '+(r.ok?'ok':'bad')+'">'+esc(r.label)+' <span style="color:var(--dim)">['+esc(r.detail)+']</span></div>').join('');
[...cps.children].forEach(li=>li.classList.toggle('cur',+li.dataset.i===i));}
let timer=null;const btn=document.getElementById('play');
function toggle(){if(timer){clearInterval(timer);timer=null;btn.innerHTML='&#9654; Play';return}
btn.innerHTML='&#10074;&#10074; Pause';timer=setInterval(()=>{let i=+slider.value+1;if(i>=D.frames.length){toggle();return}show(i)},700)}
btn.onclick=toggle;slider.oninput=()=>show(+slider.value);
document.getElementById('prev').onclick=()=>show(+slider.value-1);document.getElementById('next').onclick=()=>show(+slider.value+1);
let fs=12;const setfs=()=>screen.style.fontSize=fs+'px';
document.getElementById('smaller').onclick=()=>{fs=Math.max(6,fs-1);setfs()};document.getElementById('bigger').onclick=()=>{fs=Math.min(20,fs+1);setfs()};
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(+slider.value+1);else if(e.key==='ArrowLeft')show(+slider.value-1);else if(e.key===' '){e.preventDefault();toggle()}});
const first=D.frames.findIndex(f=>f.checkpoint);show(first<0?0:first);
</script></body></html>"""

_INDEX = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Broadside scenarios</title>
<style>""" + _STYLE + """
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px}
h1{color:var(--acc);margin:0 0 4px}
.lede{color:var(--dim);margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;text-decoration:none}
.card:hover{border-color:var(--acc)}
.card h2{font-size:16px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}
.card p{margin:0 0 8px;color:var(--ink);font-size:14px}
.card ul{margin:0 0 10px;padding-left:18px;color:var(--dim);font-size:13px}
.card code{font-size:12px;color:var(--dim)}
.badge{font-size:12px;font-weight:500;border-radius:10px;padding:1px 8px;white-space:nowrap;align-self:flex-start}
.badge.ok{background:#1d3a28;color:var(--ok)}.badge.bad{background:#3d1f1b;color:var(--bad)}
</style></head><body><div class="wrap">
<h1>Broadside - scenario replays</h1>
<p class="lede">Headless runs of every test environment: captain's-eye line of sight, fog, smoke, terrain, the 1&nbsp;m deck view and the macro view. Each replay shows the same frames the terminal game draws, with checkpoints and their automated checks.</p>
<div class="grid">
__ITEMS__
</div></div></body></html>"""
