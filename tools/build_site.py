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

LIB_INFO = {
    "gf180mcu_fd_io":          ("I/O", "5 V wide-range inline non-CUP GPIO. 75 x 350 um cells on GF_IO_Site."),
    "gf180mcu_ocd_io":         ("I/O", "OCD variant with split power domains and independent VDD/VSS cells."),
    "gf180mcu_fd_sc_mcu7t5v0": ("Standard cells", "5 V, 7-track. The template default digital library."),
    "gf180mcu_fd_sc_mcu9t5v0": ("Standard cells", "5 V, 9-track. Taller cells, more drive per area."),
    "gf180mcu_as_sc_mcu7t3v3": ("Standard cells", "3.3 V, 7-track."),
    "gf180mcu_osu_sc_gp9t3v3": ("Standard cells", "3.3 V, 9-track, OSU general purpose."),
    "gf180mcu_osu_sc_gp12t3v3":("Standard cells", "3.3 V, 12-track, OSU general purpose."),
    "gf180mcu_fd_pr":          ("Primitives", "Bipolar NPN/PNP devices and the eFuse primitive. Layout only - no LEF or Liberty."),
    "gf180mcu_fd_ip_sram":     ("Macro", "Single-port SRAM, 8-bit words with byte write mask."),
    "gf180mcu_ocd_ip_sram":    ("Macro", "OCD single-port SRAM."),
    "gf180mcu_re_efuse":       ("Macro", "One-time-programmable eFuse arrays and wrappers."),
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
        st = stem(c["short"])
        fam = FAMILY.get(st, "")
        if not fam and c["lib"].endswith("_pr"):
            fam = prim_family(c["short"])
        recs.append({
            "n": name, "s": c["short"], "l": c["lib"], "st": st,
            "fam": fam, "w": sz[0], "h": sz[1],
            "site": c["site"] or "", "area": c["area"],
            "i": ins, "o": outs, "p": pwr, "b": bidi,
            "fn": c["functions"], "v": vid or "",
        })

    libs = sorted({r["l"] for r in recs})
    nvid = sum(1 for r in recs if r["v"])

    stack_rows = "".join(
        '<tr><td><span class="sw" style="--c:%s"></span>%s</td><td class="m">%s</td>'
        '<td class="m n">%g</td><td class="m n">%g</td><td class="d">%s</td></tr>'
        % (c, n, g, z, t, html.escape(d)) for n, g, c, z, t, d in STACK)

    lib_rows = "".join(
        '<tr><td class="m">%s</td><td>%s</td><td class="n">%d</td><td class="d">%s</td></tr>'
        % (l, LIB_INFO.get(l, ("", ""))[0], sum(1 for r in recs if r["l"] == l),
           html.escape(LIB_INFO.get(l, ("", ""))[1])) for l in libs)

    page = TEMPLATE
    page = page.replace("__NCELLS__", str(len(recs)))
    page = page.replace("__NVID__", str(nvid))
    page = page.replace("__NLIB__", str(len(libs)))
    page = page.replace("__STACK__", stack_rows)
    page = page.replace("__LIBS__", lib_rows)
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
.wrap{max-width:1500px;margin:0 auto;padding:0 26px}
header{border-bottom:1px solid var(--line);padding:40px 0 26px}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin-bottom:12px}
h1{font-family:var(--mono);font-size:clamp(22px,3.2vw,32px);font-weight:600;margin:0 0 10px;letter-spacing:-.015em}
.lede{color:var(--dim);max-width:66ch;margin:0}
nav{display:flex;gap:4px;margin-top:22px;flex-wrap:wrap}
nav a{font-family:var(--mono);font-size:12px;color:var(--dim);text-decoration:none;
  padding:7px 12px;border:1px solid var(--line);border-radius:6px}
nav a:hover,nav a:focus-visible{color:var(--fg);border-color:var(--accent);outline:none}
h2{font-family:var(--mono);font-size:12px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--dim);font-weight:600;margin:44px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-family:var(--mono);font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--dim);font-weight:600;padding:7px 10px;border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid var(--line)}
td.m{font-family:var(--mono);font-size:12.5px}
td.n{text-align:right;font-variant-numeric:tabular-nums}
td.d{color:var(--dim);font-size:13px}
.sw{width:11px;height:11px;border-radius:2px;background:var(--c);display:inline-block;
  margin-right:8px;vertical-align:-1px}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.tblwrap table td:first-child,.tblwrap table th:first-child{padding-left:14px}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
input[type=search],select{background:var(--panel);color:var(--fg);border:1px solid var(--line2);
  border-radius:7px;padding:9px 12px;font-family:var(--mono);font-size:13px;min-width:210px}
input[type=search]:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
.count{font-family:var(--mono);font-size:12px;color:var(--dim);margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;
  display:flex;flex-direction:column;cursor:pointer;text-align:left;color:inherit;font:inherit;padding:0;
  transition:border-color .15s,transform .15s}
.card:hover,.card:focus-visible{border-color:var(--accent);transform:translateY(-2px);outline:none}
.thumb{aspect-ratio:1/1;background:#000;position:relative}
.thumb video{width:100%;height:100%;object-fit:cover;display:block}
.pending{display:flex;align-items:center;justify-content:center;height:100%;color:#5b6472;
  font-family:var(--mono);font-size:11.5px;background:var(--panel2)}
.cbody{padding:10px 12px 12px;border-top:1px solid var(--line)}
.cname{font-family:var(--mono);font-size:12.5px;color:var(--accent);font-weight:600;word-break:break-all}
.cfam{font-size:12.5px;color:var(--fg);margin-top:3px}
.cmeta{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:5px;
  font-variant-numeric:tabular-nums}
dialog{border:none;padding:0;background:transparent;width:100%;height:100%;max-width:none;
  max-height:none;margin:0;color:var(--fg)}
dialog::backdrop{background:rgba(5,6,9,.93)}
.modal{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:22px;height:100%;
  align-items:center;padding:26px;max-width:1250px;margin:0 auto}
@media(max-width:820px){.modal{grid-template-columns:1fr;align-content:center}}
.modal video{width:100%;max-height:78vh;background:#000;border:1px solid var(--line2);border-radius:7px}
.info h3{font-family:var(--mono);font-size:15px;margin:0 0 4px;color:var(--accent);word-break:break-all}
.info .fam{color:var(--fg);margin-bottom:16px}
.info dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:13px;margin:0}
.info dt{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
.info dd{margin:0;font-family:var(--mono);font-size:12.5px;word-break:break-all}
.fn{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:9px 11px;
  margin-top:14px;font-family:var(--mono);font-size:12.5px;line-height:1.7;overflow-x:auto}
.fn i{color:var(--dim);font-style:normal}
.x{position:fixed;top:16px;right:18px;background:var(--panel);color:var(--fg);border:1px solid var(--line2);
  border-radius:6px;width:34px;height:34px;font-size:17px;cursor:pointer}
.x:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
footer{border-top:1px solid var(--line);margin-top:50px;padding:24px 0 60px;color:var(--dim);font-size:13px}
footer p{max-width:72ch}
code{font-family:var(--mono);font-size:12px;background:var(--panel2);padding:2px 5px;border-radius:4px}
@media(prefers-reduced-motion:reduce){.card{transition:none}.card:hover{transform:none}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">GlobalFoundries 0.18 µm · gf180mcuD · 5LM_1TM_11K</div>
  <h1>Placeable cell reference</h1>
  <p class="lede">Every placeable cell in the gf180mcuD PDK — I/O, standard cells and macros —
  with its footprint, pins and logic function read from the LEF and Liberty, and a 3D view
  rendered from the GDS with the foundry's own layer heights.</p>
  <nav>
    <a href="#stack">Layer stack</a>
    <a href="#libs">Libraries</a><a href="#cells">Cell browser</a>
  </nav>
</header>

<h2 id="stack">Layer stack</h2>
<p class="lede">Heights in nanometres above the substrate surface, from the PDK's own KLayout
2.5D definition <code>libs.tech/klayout/tech/d25/gf180mcu.lyd25</code>. These are the values
used to render every cell below.</p>
<div class="tblwrap"><table>
<tr><th>Layer</th><th>GDS</th><th>Height</th><th>Thickness</th><th>Note</th></tr>
__STACK__
</table></div>

<h2 id="libs">Libraries</h2>
<div class="tblwrap"><table>
<tr><th>Library</th><th>Kind</th><th>Cells</th><th>Description</th></tr>
__LIBS__
</table></div>

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
</div>

<dialog id="dlg"><button class="x" id="x" aria-label="Close">×</button>
  <div class="modal">
    <div><video id="mv" loop muted playsinline controls></video></div>
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
    const b=document.createElement("button"); b.className="card";
    b.setAttribute("aria-label","Open "+r.s);
    const thumb = r.v
      ? '<video data-v="'+r.v+'" loop muted playsinline preload="none"></video>'
      : '<div class="pending">rendering…</div>';
    b.innerHTML='<div class="thumb">'+thumb+'</div><div class="cbody">'+
      '<div class="cname">'+r.s+'</div><div class="cfam">'+(r.fam||"&nbsp;")+'</div>'+
      '<div class="cmeta">'+(r.w?r.w.toFixed(2)+" × "+r.h.toFixed(2)+" µm":"")+
      (r.area?" · "+r.area.toFixed(1)+" µm²":"")+'</div></div>';
    b.addEventListener("click",()=>open_(r));
    frag.appendChild(b);
  }
  grid.appendChild(frag);
  grid.querySelectorAll("video[data-v]").forEach(v=>io.observe(v));
}
const dlg=document.getElementById("dlg"), mv=document.getElementById("mv"),
      info=document.getElementById("info");
function open_(r){
  if(r.v){ mv.src=VBASE+r.v; mv.style.display=""; mv.play().catch(()=>{}); }
  else { mv.removeAttribute("src"); mv.style.display="none"; }
  let fn="";
  for(const [p,e] of Object.entries(r.fn||{})) fn+='<div><i>'+p+'</i> = '+e+'</div>';
  const src="gf180mcuD/libs.ref/"+r.l+"/";
  info.innerHTML='<h3>'+r.n+'</h3><div class="fam">'+(r.fam||"")+'</div><dl>'+
    '<dt>Library</dt><dd>'+r.l+'</dd>'+
    (r.w?'<dt>Size</dt><dd>'+r.w.toFixed(3)+' × '+r.h.toFixed(3)+' µm</dd>':'')+
    (r.area?'<dt>Area</dt><dd>'+r.area.toFixed(3)+' µm²</dd>':'')+
    (r.site?'<dt>Site</dt><dd>'+r.site+'</dd>':'')+
    (r.i.length?'<dt>Inputs</dt><dd>'+r.i.join(", ")+'</dd>':'')+
    (r.o.length?'<dt>Outputs</dt><dd>'+r.o.join(", ")+'</dd>':'')+
    ((r.b||[]).length?'<dt>Bidirectional</dt><dd>'+r.b.join(", ")+'</dd>':'')+
    (r.p.length?'<dt>Supplies</dt><dd>'+r.p.join(", ")+'</dd>':'')+
    '</dl>'+(fn?'<div class="fn">'+fn+'</div>':'')+
    (r.k==="prim"
      ? '<div class="fn"><i>source</i> '+src+'gds/ — per-device GDS, no LEF/Liberty</div>'
      : '<div class="fn"><i>source</i> '+src+'<br>'+
        '<i>pins</i> lef/'+r.l+'.lef · <i>area, function</i> lib/ · '+
        '<i>3D view</i> gds/'+r.l+'.gds</div>')+
    (r.v?'':'<div class="fn"><i>3D view still rendering</i></div>');
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
