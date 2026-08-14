#!/usr/bin/env python3
"""Augment docs/prisms/<cell>.json with LEF pin geometry.

LEF PIN/PORT sections carry the authoritative pin landing shapes
(LAYER + RECT per port). This pass parses each library's LEF, aligns
coordinates to the prism JSON's frame (which is normalized to the GDS
bbox origin), and writes a "pins" array into each v2 cell JSON:

  "pins":[{"n":"D","s":[["Metal1",x0,y0,x1,y1], ...]}, ...]

Run after extract_prisms.py:  python3 add_lef_pins.py
"""
import json, re, sys
from pathlib import Path

try:
    import gdstk
except ImportError:
    sys.exit("needs gdstk")

DOCS = Path(__file__).resolve().parents[1]
PDK = Path.home() / "chdl/ext/gf180mcu-project-template/gf180mcu/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD"

KEEP_LAYERS = {
    "Nwell", "Pwell", "COMP", "Poly2",
    "Metal1", "Metal2", "Metal3", "Metal4", "Metal5",
}

def parse_lef(text):
    """MACRO -> {pin -> [(layer,x0,y0,x1,y1)...]}"""
    out = {}
    block = re.S | re.M
    for mm in re.finditer(
            r"^[ \t]*MACRO[ \t]+(\S+)[ \t]*\r?$(.*?)^[ \t]*END[ \t]+\1[ \t]*\r?$",
            text, block):
        name, body = mm.group(1), mm.group(2)
        pins = {}
        for pm in re.finditer(
                r"^[ \t]*PIN[ \t]+(\S+)[ \t]*\r?$(.*?)^[ \t]*END[ \t]+\1[ \t]*\r?$",
                body, block):
            pname, pbody = pm.group(1), pm.group(2)
            rects = []
            cur = None
            for tok in re.finditer(
                    r"\bLAYER\s+(\S+)\s*;|\bRECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*;",
                    pbody):
                if tok.group(1):
                    cur = tok.group(1)
                elif cur in KEEP_LAYERS:
                    x0, y0, x1, y1 = (float(tok.group(i)) for i in (2, 3, 4, 5))
                    rects.append((cur, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
            if rects:
                pins[pname] = rects
        if pins:
            out[name] = pins
    return out

def main():
    cells = json.load(open(DOCS / "cells.json"))
    libs = sorted({m["lib"] for m in cells.values()})
    patched = nopins = 0
    for lib in libs:
        lefdir = PDK / "libs.ref" / lib / "lef"
        gdsdir = PDK / "libs.ref" / lib / "gds"
        lefpins = {}
        if lefdir.is_dir():
            for f in sorted(lefdir.glob("*.lef")):
                lefpins.update(parse_lef(f.read_text(errors="replace")))
        # bbox origin per cell (prism JSONs are normalized to it)
        origins = {}
        if gdsdir.is_dir():
            for f in sorted(gdsdir.glob("*.gds")):
                try:
                    gl = gdstk.read_gds(str(f))
                except Exception:
                    continue
                for c in gl.cells:
                    if c.name in origins:
                        continue
                    bb = c.bounding_box()
                    if bb:
                        origins[c.name] = bb[0]
        for name, meta in cells.items():
            if meta["lib"] != lib:
                continue
            jf = DOCS / "prisms" / f"{name}.json"
            if not jf.exists():
                continue
            pins = lefpins.get(name)
            if not pins:
                nopins += 1
                continue
            ox, oy = origins.get(name, (0.0, 0.0))
            short = name.split("__", 1)[1] if "__" in name else name
            if name not in origins and short in origins:
                ox, oy = origins[short]
            rec = json.load(open(jf))
            rec["pins"] = [
                {"n": pn, "s": [[l, round(x0 - ox, 3), round(y0 - oy, 3),
                                 round(x1 - ox, 3), round(y1 - oy, 3)]
                                for (l, x0, y0, x1, y1) in rects]}
                for pn, rects in pins.items()]
            jf.write_text(json.dumps(rec, separators=(",", ":")))
            patched += 1
        print(f"== {lib}: lef macros {len(lefpins)}", flush=True)
    print(f"done: {patched} cells gained pins, {nopins} without LEF pins")

if __name__ == "__main__":
    main()
