#!/usr/bin/env python3
"""Generate the gf180mcuD reference site from docs/cells.json + the rendered videos.

INCREMENTAL BY DESIGN. Re-run it at any point during the (multi-hour) render:
cells whose video does not exist yet are still listed with all their data and a
"rendering" placeholder, so the site is usable from the first minute and simply
fills in. Nothing here re-renders anything.

All facts come from the PDK:
  docs/cells.json                  LEF footprint/site/pins + Liberty area/function
  techfiles/gf180mcuD.txt          layer colours, z heights
  libs.tech/klayout/tech/d25/*     the z heights themselves (quoted in the page)

Usage:  python3 tools/build_site.py [--videos docs/videos] [--out docs]
"""

import argparse
import html
import json
import os
import re

# --- Real process data, sourced not invented -------------------------------
# z heights: libs.tech/klayout/tech/d25/gf180mcu.lyd25   (nm)
STACK = [
    ("Pad",      "37/0",  "#9ea1a8", 6952.5, 300.0,  "Bond pad opening (passivation)"),
    ("Metal5",   "81/0",  "#8f4fd8", 5760.0, 1192.5, "Top metal, 11 kA aluminium"),
    ("Via4",     "41/0",  "#c98a7a", 4860.0, 900.0,  "Metal4 to Metal5"),
    ("FuseTop",  "75/0",  "#f2d94e", 4902.0, 295.0,  "MIM-B top plate"),
    ("Metal4",   "46/0",  "#e5674d", 4310.0, 550.0,  ""),
    ("Via3",     "40/0",  "#b9a06a", 3710.0, 600.0,  "Metal3 to Metal4"),
    ("Metal3",   "42/0",  "#e0a01a", 3160.0, 550.0,  ""),
    ("Via2",     "38/0",  "#9aa5b1", 2560.0, 600.0,  "Metal2 to Metal3"),
    ("Metal2",   "36/0",  "#22a3a3", 2010.0, 550.0,  ""),
    ("Via1",     "35/0",  "#9aa5b1", 1410.0, 600.0,  "Metal1 to Metal2"),
    ("Metal1",   "34/0",  "#3d7fd6",  860.0, 550.0,  ""),
    ("Contact",  "33/0",  "#7a7a7a",    0.0, 860.0,  "Metal1 to active or poly"),
    ("Poly2",    "30/0",  "#b03060",    0.0, 200.0,  "Gate and local interconnect"),
    ("COMP",     "22/0",  "#2f7a4f", -200.0, 200.0,  "Diffusion"),
]

# Most standard-cell and I/O libraries keep every cell in one GDS. Macro and
# primitive libraries instead ship one GDS per cell. These names are kept here
# so the generated cards can show the exact path, relative to gf180mcuD/.
SHARED_GDS = {
    "gf180mcu_fd_io": "gf180mcu_fd_io.gds",
    "gf180mcu_ocd_io": "gf180mcu_ocd_io.gds",
    "gf180mcu_fd_sc_mcu7t5v0": "gf180mcu_fd_sc_mcu7t5v0.gds",
    "gf180mcu_fd_sc_mcu9t5v0": "gf180mcu_fd_sc_mcu9t5v0.gds",
    "gf180mcu_as_sc_mcu7t3v3": "gf180mcu_as_sc_mcu7t3v3.gds",
    "gf180mcu_osu_sc_gp9t3v3": "gf180mcu_osu_sc_gp9t3v3.gds",
    "gf180mcu_osu_sc_gp12t3v3": "gf180mcu_osu_sc_gp12t3v3.gds",
}

# Function-family labels, keyed by the cell-name stem.
FAMILY = {
    "inv":"Inverter","invz":"Tri-state inverter","buf":"Buffer","bufz":"Tri-state buffer",
    "clkbuf":"Clock buffer","clkinv":"Clock inverter","nand2":"2-input NAND",
    "nand3":"3-input NAND","nand4":"4-input NAND","nor2":"2-input NOR","nor3":"3-input NOR",
    "nor4":"4-input NOR","and2":"2-input AND","and3":"3-input AND","and4":"4-input AND",
    "or2":"2-input OR","or3":"3-input OR","or4":"4-input OR","xor2":"2-input XOR",
    "xor3":"3-input XOR","xnor2":"2-input XNOR","xnor3":"3-input XNOR",
    "aoi21":"AND-OR-invert 2-1","aoi22":"AND-OR-invert 2-2","aoi211":"AND-OR-invert 2-1-1",
    "aoi221":"AND-OR-invert 2-2-1","aoi222":"AND-OR-invert 2-2-2",
    "oai21":"OR-AND-invert 2-1","oai22":"OR-AND-invert 2-2","oai211":"OR-AND-invert 2-1-1",
    "oai221":"OR-AND-invert 2-2-1","oai222":"OR-AND-invert 2-2-2",
    "oai31":"OR-AND-invert 3-1","oai32":"OR-AND-invert 3-2","oai33":"OR-AND-invert 3-3",
    "mux2":"2:1 multiplexer","mux4":"4:1 multiplexer","addf":"Full adder","addh":"Half adder",
    "dffq":"D flip-flop","dffnq":"D flip-flop, negedge","dffrnq":"D flip-flop with reset",
    "dffsnq":"D flip-flop with set","dffrsnq":"D flip-flop, set and reset",
    "dffnrnq":"D flip-flop, negedge, reset","dffnsnq":"D flip-flop, negedge, set",
    "dffnrsnq":"D flip-flop, negedge, set and reset",
    "sdffq":"Scan D flip-flop","sdffrnq":"Scan flip-flop with reset",
    "sdffsnq":"Scan flip-flop with set","sdffrsnq":"Scan flip-flop, set and reset",
    "latq":"D latch","latrnq":"D latch with reset","latsnq":"D latch with set",
    "latrsnq":"D latch, set and reset","icgtp":"Clock gate, posedge","icgtn":"Clock gate, negedge",
    "dlya":"Delay cell A","dlyb":"Delay cell B","dlyc":"Delay cell C","dlyd":"Delay cell D",
    "tieh":"Tie high","tiel":"Tie low","fill":"Filler","fillcap":"Decoupling filler",
    "filltie":"Filler with well tie","endcap":"Row end cap","antenna":"Antenna diode",
    "hold":"Hold buffer","bi_t":"Bidirectional pad","bi_24t":"Bidirectional pad, 24 mA",
    "in_c":"CMOS input pad","in_s":"Schmitt input pad","asig_5p0":"Analogue pad",
    "dvdd":"I/O power pad","dvss":"I/O ground pad","vdd":"Core power pad","vss":"Core ground pad",
    "cor":"Corner cell","brk2":"Breaker, 2 um","brk5":"Breaker, 5 um","fillnc":"Non-conducting filler",
}


def stem(short):
    """inv_1 -> inv ; sram64x8m8wm1 -> sram64x8m8wm1"""
    parts = short.rsplit("_", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else short


def prim_family(short):
    """npn_00p54x02p00 -> 'NPN bipolar transistor, 0.54 x 2 um emitter'"""
    m = re.match(r"(npn|pnp)_(\d+)p(\d+)x(\d+)p(\d+)$", short)
    if m:
        a = float("%s.%s" % (m.group(2), m.group(3)))
        b = float("%s.%s" % (m.group(4), m.group(5)))
        return "%s bipolar transistor, %g × %g µm emitter" % (m.group(1).upper(), a, b)
    if short.startswith("efuse"):
        return "eFuse primitive"
    return ""


def gds_source(name, lib, short):
    """Return the cell's source GDS path, relative to gf180mcuD/."""
    if lib == "gf180mcu_fd_io" and name.startswith("gf180mcu_ef_io__"):
        filename = "gf180mcu_ef_io.gds"
    elif lib in SHARED_GDS:
        filename = SHARED_GDS[lib]
    elif lib == "gf180mcu_fd_pr":
        filename = "efuse.gds" if short == "efuse_cell" else short + ".gds"
    elif lib in ("gf180mcu_fd_ip_sram", "gf180mcu_ocd_ip_sram"):
        filename = name + ".gds"
    else:
        filename = short + ".gds"
    return "libs.ref/%s/gds/%s" % (lib, filename)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default="docs/cells.json")
    # Defaults target docs/, which is what GitHub Pages publishes. The videos
    # live INSIDE the output directory rather than beside it: Pages serves the
    # docs/ tree literally and does not follow a symlink out of it, so the mp4s
    # have to be real files under docs/videos/.
    ap.add_argument("--videos", default="docs/videos")
    ap.add_argument("--out", default="docs")
    a = ap.parse_args()

    cells = json.load(open(a.cells))
    os.makedirs(a.out, exist_ok=True)

    have = {}
    for lib in os.listdir(a.videos) if os.path.isdir(a.videos) else []:
        d = os.path.join(a.videos, lib)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".mp4") and os.path.getsize(os.path.join(d, f)) > 5000:
                    have[(lib, f[:-4])] = os.path.join(lib, f)

    recs = []
    for name, c in sorted(cells.items()):
        vid = have.get((c["lib"], c["short"]))
        sz = c["size"] or [0, 0]
        ins = [p["name"] for p in c["pins"] if p["dir"] == "INPUT"]
        outs = [p["name"] for p in c["pins"] if p["dir"] == "OUTPUT"]
        pwr = [p["name"] for p in c["pins"] if p["use"] in ("POWER", "GROUND")]
        bidi = [p["name"] for p in c["pins"]
                if p["dir"] == "INOUT" and p["use"] not in ("POWER", "GROUND")]
        unknown = [p["name"] for p in c["pins"]
                   if p["dir"] not in ("INPUT", "OUTPUT", "INOUT")
                   and p["use"] not in ("POWER", "GROUND")]
        st = stem(c["short"])
        fam = FAMILY.get(st, "")
        if not fam and c["lib"].endswith("_pr"):
            fam = prim_family(c["short"])
        recs.append({
            "n": name, "s": c["short"], "l": c["lib"], "st": st,
            "fam": fam, "w": sz[0], "h": sz[1],
            "site": c["site"] or "", "area": c["area"],
            "i": ins, "o": outs, "p": pwr, "b": bidi, "u": unknown,
            "fn": c["functions"], "v": vid or "",
            "g": gds_source(name, c["lib"], c["short"]),
        })

    libs = sorted({r["l"] for r in recs})
    nvid = sum(1 for r in recs if r["v"])

    stack_rows = "".join(
        '<li class="stack-item"><div class="stack-top">'
        '<span><span class="sw" style="--c:%s"></span>%s</span><code>%s</code></div>'
        '<div class="stack-dims"><span>z&nbsp; %g nm</span><span>thickness&nbsp; %g nm</span></div>'
        '%s</li>'
        % (c, n, g, z, t,
           '<div class="stack-note">%s</div>' % html.escape(d) if d else "")
        for n, g, c, z, t, d in STACK)

    page = TEMPLATE
    page = page.replace("__NCELLS__", str(len(recs)))
    page = page.replace("__NVID__", str(nvid))
    page = page.replace("__NLIB__", str(len(libs)))
    page = page.replace("__STACK__", stack_rows)
    page = page.replace("__LIBOPTS__", "".join(
        '<option value="%s">%s</option>' % (l, l) for l in libs))
    page = page.replace("__DATA__", json.dumps(recs, separators=(",", ":")))
    open(os.path.join(a.out, "index.html"), "w").write(page)

    # The page always asks for videos/<lib>/<cell>.mp4 relative to itself. If
    # the videos are not already inside the output directory, link them in --
    # symlink, never copy, because that is 250 MB.
    link = os.path.join(a.out, "videos")
    if not os.path.exists(link):
        try:
            os.symlink(os.path.abspath(a.videos), link)
        except OSError:
            pass

    # Pages runs Jekyll unless told otherwise, which costs a build step and
    # silently drops anything whose name starts with an underscore.
    nojekyll = os.path.join(a.out, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()

    print("site: %s/index.html   %d cells, %d with video, %d libraries"
          % (a.out, len(recs), nvid, len(libs)))


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gf180mcuD — cell reference</title>
<style>
:root{
  --bg:#0b0d11;--panel:#14171e;--panel2:#191d26;--line:#222732;--line2:#2c3341;
  --fg:#e8eaef;--dim:#8b95a6;--accent:#8f4fd8;--good:#3fb950;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
@media (prefers-color-scheme:light){:root{--bg:#f7f6f4;--panel:#fff;--panel2:#faf9f7;
  --line:#e2e0dc;--line2:#d2cfc9;--fg:#16181d;--dim:#6b7280;--accent:#6d33ad;--good:#1a7f37;}}
:root[data-theme="dark"]{--bg:#0b0d11;--panel:#14171e;--panel2:#191d26;--line:#222732;
  --line2:#2c3341;--fg:#e8eaef;--dim:#8b95a6;--accent:#8f4fd8;--good:#3fb950;}
:root[data-theme="light"]{--bg:#f7f6f4;--panel:#fff;--panel2:#faf9f7;--line:#e2e0dc;
  --line2:#d2cfc9;--fg:#16181d;--dim:#6b7280;--accent:#6d33ad;--good:#1a7f37;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.6}
.layout{display:grid;grid-template-columns:minmax(270px,305px) minmax(0,1fr);max-width:1820px;margin:0 auto}
.page{min-width:0}
.wrap{max-width:1500px;margin:0 auto;padding:0 26px}
header{border-bottom:1px solid var(--line);padding:40px 0 26px}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin-bottom:12px}
h1{font-family:var(--mono);font-size:clamp(22px,3.2vw,32px);font-weight:600;margin:0 0 10px;letter-spacing:-.015em}
h2{font-family:var(--mono);font-size:12px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--dim);font-weight:600;margin:44px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.stack-sidebar{position:sticky;top:0;align-self:start;height:100vh;height:100dvh;overflow-y:auto;
  background:var(--panel);border-right:1px solid var(--line);padding:18px 14px}
.stack-sidebar h2{margin:0 0 7px;padding-bottom:7px}
.stack-lede{color:var(--dim);font-size:10.5px;line-height:1.4;margin:0 0 10px}
.stack-lede code{font-size:9.5px;word-break:break-word}
.stack-list{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:8px;
  overflow:hidden;background:var(--bg)}
.stack-item{padding:5px 8px;border-bottom:1px solid var(--line)}
.stack-item:last-child{border-bottom:0}
.stack-top{display:flex;align-items:center;justify-content:space-between;gap:8px;
  font-family:var(--mono);font-size:11px;color:var(--fg)}
.stack-top code{font-size:9.5px;color:var(--dim);white-space:nowrap}
.stack-dims{display:flex;justify-content:space-between;gap:8px;margin-top:2px;
  color:var(--dim);font-family:var(--mono);font-size:9px;font-variant-numeric:tabular-nums}
.stack-note{color:var(--dim);font-size:8.5px;line-height:1.25;margin:2px 0 0 19px}
.sw{width:9px;height:9px;border-radius:2px;background:var(--c);display:inline-block;
  margin-right:6px;vertical-align:-1px}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
input[type=search],select{background:var(--panel);color:var(--fg);border:1px solid var(--line2);
  border-radius:7px;padding:9px 12px;font-family:var(--mono);font-size:13px;min-width:210px}
input[type=search]:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
.count{font-family:var(--mono);font-size:12px;color:var(--dim);margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;
  display:flex;flex-direction:column;transition:border-color .15s,transform .15s}
.card:hover,.card:focus-within{border-color:var(--accent);transform:translateY(-2px)}
.card-open{appearance:none;background:transparent;border:0;color:inherit;font:inherit;padding:0;
  text-align:left;display:flex;flex:1;flex-direction:column;min-width:0;cursor:pointer}
.card-open:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.thumb{aspect-ratio:1/1;background:#000;position:relative}
.thumb video{width:100%;height:100%;object-fit:cover;display:block}
.pending{display:flex;align-items:center;justify-content:center;height:100%;color:#5b6472;
  font-family:var(--mono);font-size:11.5px;background:var(--panel2)}
.cbody{padding:10px 12px 12px;border-top:1px solid var(--line);width:100%;flex:1}
.cname{font-family:var(--mono);font-size:12.5px;color:var(--accent);font-weight:600;word-break:break-all}
.cfam{font-size:12.5px;color:var(--fg);margin-top:3px}
.cmeta{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:5px;
  font-variant-numeric:tabular-nums}
.csource{font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.4;margin-top:8px;
  padding-top:7px;border-top:1px solid var(--line);overflow-wrap:anywhere}
.csource span{color:var(--fg)}
.card-actions{display:flex;justify-content:flex-end;border-top:1px solid var(--line);padding:5px 9px}
.card-download{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-decoration:none;
  border-radius:4px;padding:2px 5px}
.card-download:hover{color:var(--accent);background:var(--panel2)}
.card-download:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
dialog{border:none;padding:0;background:transparent;width:100%;height:100%;max-width:none;
  max-height:none;margin:0;color:var(--fg)}
dialog::backdrop{background:rgba(5,6,9,.93)}
.modal{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,420px);gap:18px;height:100%;
  align-items:center;padding:26px;max-width:1320px;margin:0 auto}
.viewer{min-width:0}
.modal video{width:100%;max-height:82vh;background:#000;border:1px solid var(--line2);border-radius:9px;
  display:block}
.info{background:var(--panel);border:1px solid var(--line2);border-radius:9px;padding:18px;
  max-height:calc(100vh - 52px);overflow-y:auto}
.info-head{padding-bottom:14px;border-bottom:1px solid var(--line)}
.info .library{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--dim);overflow-wrap:anywhere}
.info h3{font-family:var(--mono);font-size:15px;line-height:1.35;margin:4px 0 2px;color:var(--accent);
  overflow-wrap:anywhere}
.info .fam{color:var(--fg);font-size:12.5px}
.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:14px}
.fact{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:8px 9px;min-width:0}
.fact span,.section-title{display:block;font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--dim)}
.fact strong{display:block;margin-top:2px;font-family:var(--mono);font-size:11px;font-weight:500;
  overflow-wrap:anywhere}
.fact small{display:block;color:var(--dim);font-family:var(--mono);font-size:9.5px;margin-top:2px}
.modal-section{margin-top:16px}
.section-title{margin:0 0 7px}
.pin-groups{display:grid;gap:7px}
.pin-group{border:1px solid var(--line);border-left:3px solid var(--pin);border-radius:6px;padding:7px 8px;
  background:var(--panel2)}
.pin-input{--pin:#3fb950}.pin-output{--pin:#f0883e}.pin-io{--pin:#58a6ff}
.pin-supply{--pin:#8f4fd8}.pin-unknown{--pin:#8b95a6}
.pin-title{display:flex;justify-content:space-between;align-items:center;color:var(--dim);
  font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em}
.pin-title b{font-weight:500;color:var(--fg)}
.pins{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.pins code{font-size:10.5px;color:var(--fg);border:1px solid var(--line);background:var(--bg);
  padding:1px 5px;overflow-wrap:anywhere}
.logic,.source{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:8px 10px;
  font-family:var(--mono);font-size:10.5px;line-height:1.55;overflow-wrap:anywhere}
.logic div+div,.source div+div{border-top:1px solid var(--line);margin-top:5px;padding-top:5px}
.logic i,.source i{color:var(--dim);font-style:normal;margin-right:5px}
.empty{color:var(--dim);font-size:11.5px;border:1px dashed var(--line2);border-radius:6px;padding:8px 10px}
.x{position:fixed;top:16px;right:18px;background:var(--panel);color:var(--fg);border:1px solid var(--line2);
  border-radius:6px;width:34px;height:34px;font-size:17px;cursor:pointer;z-index:2}
.x:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
footer{border-top:1px solid var(--line);margin-top:50px;padding:24px 0 60px;color:var(--dim);font-size:13px}
footer p{max-width:72ch}
code{font-family:var(--mono);font-size:12px;background:var(--panel2);padding:2px 5px;border-radius:4px}
@media(max-width:1200px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:850px){
  .layout{display:block}.stack-sidebar{position:relative;height:auto;max-height:42vh;border-right:0;
    border-bottom:1px solid var(--line)}
  .stack-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
  .stack-item:nth-child(odd){border-right:1px solid var(--line)}
}
@media(max-width:820px){
  dialog{overflow-y:auto}.modal{display:block;height:auto;padding:56px 14px 20px}
  .modal video{max-height:52vh;margin-bottom:12px}.info{max-height:none}
}
@media(max-width:620px){
  .wrap{padding:0 16px}.grid,.stack-list{grid-template-columns:1fr}
  .stack-item:nth-child(odd){border-right:0}
}
@media(prefers-reduced-motion:reduce){.card{transition:none}.card:hover{transform:none}}
</style></head><body>
<div class="layout">
<aside class="stack-sidebar" aria-labelledby="stack">
  <h2 id="stack">Layer stack</h2>
  <p class="stack-lede">Nanometres above the substrate surface, from
  <code>libs.tech/klayout/tech/d25/gf180mcu.lyd25</code>. These values render every cell.</p>
  <ol class="stack-list">__STACK__</ol>
</aside>
<main class="page"><div class="wrap">
<header>
  <div class="eyebrow">GlobalFoundries 0.18 µm · gf180mcuD · 5LM_1TM_11K</div>
  <h1>Placeable cell reference</h1>
</header>

<h2 id="cells">Cell browser</h2>
<div class="controls">
  <input type="search" id="q" placeholder="search name or function…" aria-label="Search cells">
  <select id="lib" aria-label="Filter by library"><option value="">all libraries</option>__LIBOPTS__</select>
  <select id="kind" aria-label="Filter by type">
    <option value="">all types</option><option value="comb">combinational</option>
    <option value="seq">sequential</option><option value="io">I/O</option>
    <option value="phys">physical only</option><option value="macro">macro</option>
    <option value="prim">primitives</option>
  </select>
  <span class="count" id="count"></span>
</div>
<div class="grid" id="grid"></div>

<footer>
  <p><strong>__NCELLS__ cells</strong> across __NLIB__ libraries; __NVID__ rendered so far.
  Videos appear as the background render completes — reload to pick up new ones.</p>
  <p>3D views are exploded by layer and spun 360°, rendered headless via an EGL backend for
  GDS3D. Explode distance is scaled per library: the offset is absolute in microns, so the
  value that suits a 350 µm I/O pad would throw a 3 µm standard cell off screen.</p>
</footer>
</div></main>
</div>

<dialog id="dlg"><button class="x" id="x" aria-label="Close">×</button>
  <div class="modal">
    <div class="viewer"><video id="mv" loop muted playsinline controls></video></div>
    <div class="info" id="info"></div>
  </div>
</dialog>

<script>
const CELLS = __DATA__;
const SEQ = /^(dff|sdff|lat|icgt)/, PHYS = /^(fill|endcap|antenna|tie|hold|ant|decap|tap|diode|brk|cor)/;
function kindOf(r){
  if (r.l.slice(-3) === "_pr") return "prim";
  if (r.l.indexOf("_io") > -1) return "io";
  if (r.l.indexOf("sram") > -1 || r.l.indexOf("efuse") > -1) return "macro";
  if (SEQ.test(r.st)) return "seq";
  if (PHYS.test(r.st)) return "phys";
  return "comb";
}
CELLS.forEach(r => r.k = kindOf(r));

const grid=document.getElementById("grid"), q=document.getElementById("q"),
      lib=document.getElementById("lib"), kind=document.getElementById("kind"),
      count=document.getElementById("count");

// Videos are served from the repo via jsDelivr; the Pages artifact excludes
// them to stay under the 10-minute deployment limit.
const VBASE="https://cdn.jsdelivr.net/gh/agentdavo/GDS3D@master/docs/videos/";

// Load a video only while its card is near the viewport, and fully unload it
// once it scrolls away: with ~700 cells, keeping every decoded stream alive
// exhausts the tab's memory.
const io = new IntersectionObserver(es=>{
  for(const e of es){ const v=e.target;
    if(e.isIntersecting){ if(!v.src && v.dataset.v) v.src=VBASE+v.dataset.v;
      v.play().catch(()=>{}); }
    else if(v.src){ v.pause(); v.removeAttribute("src"); v.load(); } }
},{rootMargin:"250px"});

function render(){
  const t=q.value.trim().toLowerCase(), L=lib.value, K=kind.value;
  const sel = CELLS.filter(r =>
    (!L || r.l===L) && (!K || r.k===K) &&
    (!t || r.s.toLowerCase().includes(t) || (r.fam||"").toLowerCase().includes(t) ||
     Object.values(r.fn||{}).join(" ").toLowerCase().includes(t)));
  count.textContent = sel.length + " of " + CELLS.length;
  grid.innerHTML="";
  const frag=document.createDocumentFragment();
  for(const r of sel){
    const card=document.createElement("article"); card.className="card";
    const b=document.createElement("button"); b.className="card-open";
    b.setAttribute("aria-label","Open "+r.s+" details");
    const thumb = r.v
      ? '<video data-v="'+r.v+'" loop muted playsinline preload="none"></video>'
      : '<div class="pending">rendering…</div>';
    b.innerHTML='<div class="thumb">'+thumb+'</div><div class="cbody">'+
      '<div class="cname">'+r.s+'</div><div class="cfam">'+(r.fam||"&nbsp;")+'</div>'+
      '<div class="cmeta">'+(r.w?r.w.toFixed(3)+" × "+r.h.toFixed(3)+" µm":"")+
      (r.area?" · "+r.area.toFixed(1)+" µm²":"")+'</div>'+
      '<div class="csource">GDS from gf180mcuD/<br><span>'+r.g+'</span></div></div>';
    b.addEventListener("click",()=>open_(r));
    card.appendChild(b);
    if(r.v){
      const actions=document.createElement("div"); actions.className="card-actions";
      const dl=document.createElement("a"); dl.className="card-download";
      dl.href=VBASE+r.v; dl.download=r.s+".mp4";
      dl.setAttribute("aria-label","Download "+r.s+" MP4");
      dl.textContent="↓ download MP4";
      dl.addEventListener("click",e=>downloadVideo(e,r));
      actions.appendChild(dl); card.appendChild(actions);
    }
    frag.appendChild(card);
  }
  grid.appendChild(frag);
  grid.querySelectorAll("video[data-v]").forEach(v=>io.observe(v));
}
async function downloadVideo(e,r){
  e.preventDefault();
  const link=e.currentTarget, label=link.textContent;
  link.textContent="downloading…";
  try{
    const response=await fetch(VBASE+r.v);
    if(!response.ok) throw new Error("HTTP "+response.status);
    const url=URL.createObjectURL(await response.blob());
    const save=document.createElement("a");
    save.href=url; save.download=r.s+".mp4"; save.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(_){ window.open(VBASE+r.v,"_blank","noopener"); }
  finally{ link.textContent=label; }
}
const dlg=document.getElementById("dlg"), mv=document.getElementById("mv"),
      info=document.getElementById("info");
function pinGroup(label,pins,klass){
  if(!pins || !pins.length) return "";
  return '<div class="pin-group '+klass+'"><div class="pin-title"><span>'+label+
    '</span><b>'+pins.length+'</b></div><div class="pins">'+
    pins.map(p=>'<code>'+p+'</code>').join("")+'</div></div>';
}
function open_(r){
  if(r.v){ mv.src=VBASE+r.v; mv.style.display=""; mv.play().catch(()=>{}); }
  else { mv.removeAttribute("src"); mv.style.display="none"; }
  let fn="";
  for(const [p,e] of Object.entries(r.fn||{})) fn+='<div><i>'+p+' =</i> '+e+'</div>';
  const src="libs.ref/"+r.l+"/";
  let facts="";
  if(r.w) facts+='<div class="fact"><span>Dimensions</span><strong>'+r.w.toFixed(3)+' × '+
    r.h.toFixed(3)+' µm</strong><small>'+Math.round(r.w*1000)+' × '+Math.round(r.h*1000)+' nm</small></div>';
  if(r.area) facts+='<div class="fact"><span>Area</span><strong>'+r.area.toFixed(3)+' µm²</strong></div>';
  if(r.site) facts+='<div class="fact"><span>Site</span><strong>'+r.site+'</strong></div>';
  const pins=pinGroup("Inputs",r.i,"pin-input")+pinGroup("Outputs",r.o,"pin-output")+
    pinGroup("Bidirectional",r.b||[],"pin-io")+pinGroup("Supplies",r.p,"pin-supply")+
    pinGroup("Unspecified in LEF",r.u||[],"pin-unknown");
  const sources=r.k==="prim"
    ? '<div><i>GDS</i> gf180mcuD/'+r.g+'</div><div><i>Metadata</i> layout only — no LEF or Liberty</div>'
    : '<div><i>GDS</i> gf180mcuD/'+r.g+'</div><div><i>LEF · dimensions, site, pins</i> gf180mcuD/'+
      src+'lef/</div><div><i>Liberty · area, logic</i> gf180mcuD/'+src+'lib/</div>';
  info.innerHTML='<div class="info-head"><div class="library">'+r.l+'</div><h3>'+r.n+
    '</h3><div class="fam">'+(r.fam||"")+'</div></div>'+
    (facts?'<div class="facts">'+facts+'</div>':'')+
    '<section class="modal-section"><h4 class="section-title">Pins · LEF</h4><div class="pin-groups">'+
      (pins||'<div class="empty">No LEF pin metadata for this layout-only cell.</div>')+'</div></section>'+
    (fn?'<section class="modal-section"><h4 class="section-title">Logic · Liberty</h4><div class="logic">'+
      fn+'</div></section>':'')+
    '<section class="modal-section"><h4 class="section-title">PDK sources</h4><div class="source">'+sources+
      (r.v?'':'<div><i>3D view</i> still rendering</div>')+'</div></section>';
  dlg.showModal();
}
function close_(){ dlg.close(); mv.pause(); mv.removeAttribute("src"); }
document.getElementById("x").addEventListener("click",close_);
dlg.addEventListener("click",e=>{ if(e.target===dlg) close_(); });
dlg.addEventListener("cancel",e=>{ e.preventDefault(); close_(); });
[q,lib,kind].forEach(el=>el.addEventListener("input",render));
render();
</script></body></html>"""


if __name__ == "__main__":
    main()
