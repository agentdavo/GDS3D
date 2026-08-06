#!/usr/bin/env python3
"""Extract per-cell extruded-prism JSON for the interactive 3D cell reference.

Replaces the spin-video pipeline's raster output with geometry: for every cell
in docs/cells.json, find its GDS in the gf180mcuD PDK, flatten, merge polygons
per layer, attach the lyd25 z-stack, and write docs/prisms/<name>.json.

Level-of-detail: cells whose merged prism count exceeds CAP keep their CAP
largest-area prisms (small vias/contacts vanish first — invisible at card
scale anyway); the JSON records shown/total so the viewer can say so.

Usage:  python3 extract_prisms.py [--pdk PDKROOT/gf180mcuD] [--only LIB]
"""
import argparse, json, sys
from pathlib import Path

try:
    import gdstk
except ImportError:
    sys.exit("needs gdstk (pip install gdstk)")

DOCS = Path(__file__).resolve().parents[1]
DEFAULT_PDK = Path.home() / "chdl/ext/gf180mcu-project-template/gf180mcu/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD"

# (layer, datatype) -> (name, z0_um, z1_um) — from libs.tech/klayout/tech/d25/gf180mcu.lyd25
Z = {
    (22, 0): ("COMP",   -0.30, 0.00),
    (30, 0): ("Poly2",   0.00, 0.20),
    (33, 0): ("Contact", 0.00, 0.86),
    (34, 0): ("Metal1",  0.86, 1.41),
    (35, 0): ("Via1",    1.41, 2.01),
    (36, 0): ("Metal2",  2.01, 2.56),
    (38, 0): ("Via2",    2.56, 3.16),
    (42, 0): ("Metal3",  3.16, 3.71),
    (40, 0): ("Via3",    3.71, 4.31),
    (46, 0): ("Metal4",  4.31, 4.86),
    (75, 0): ("FuseTop", 4.90, 5.20),
    (41, 0): ("Via4",    4.86, 5.76),
    (81, 0): ("Metal5",  5.76, 6.95),
    (37, 0): ("Pad",     6.95, 7.25),
}
CAP = 20000
ROUND = 3

MERGE_LIMIT = 20000   # layers with more polygons skip the (slow) merge
VIA_LAYERS = {"Contact", "Via1", "Via2", "Via3", "Via4"}
VIA_KEEP_ALL = 1000    # layers up to this keep every via
VIA_MAX = 60000        # per-layer ceiling; above keep-all, stride >= 10
import math
_HEX = [(math.cos(math.radians(60 * i + 30)), math.sin(math.radians(60 * i + 30)))
        for i in range(6)]

def cell_to_prisms(cell):
    bylayer = {}
    for p in cell.get_polygons(depth=None):
        k = (p.layer, p.datatype)
        if k in Z:
            bylayer.setdefault(k, []).append(p)
    prisms = []
    via_prisms = []
    via_total = 0
    max_stride = 1
    for k, polys in bylayer.items():
        name, z0, z1 = Z[k]
        if name in VIA_LAYERS:
            # vias: equal-area hexagon extrusions, spatially-even sampling,
            # exempt from the area-LOD cull so they never disappear
            via_total += len(polys)
            if len(polys) > VIA_KEEP_ALL:
                stride = max(10, -(-len(polys) // VIA_MAX))
                max_stride = max(max_stride, stride)
                centers = []
                for q in polys:
                    (x0, y0), (x1, y1) = q.bounding_box()
                    centers.append(((x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)))
                centers.sort(key=lambda c: (round(c[1], 0), c[0]))
                sampled = centers[::stride]
            else:
                sampled = []
                for q in polys:
                    (x0, y0), (x1, y1) = q.bounding_box()
                    sampled.append(((x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)))
            for cx, cy, side in sampled:
                r = 0.62 * side
                via_prisms.append({
                    "l": name,
                    "p": [[round(cx + r * hx, ROUND), round(cy + r * hy, ROUND)]
                          for hx, hy in _HEX],
                    "z0": z0, "z1": z1,
                })
            continue
        merged = polys if len(polys) > MERGE_LIMIT else gdstk.boolean(polys, [], "or")
        for m in merged:
            pts = m.points
            if len(pts) < 3:
                continue
            prisms.append({
                "l": name,
                "p": [[round(float(x), ROUND), round(float(y), ROUND)] for x, y in pts],
                "z0": z0, "z1": z1,
                "_a": abs(m.area()),
            })
    return prisms, via_prisms, via_total, max_stride

def poly_area_sort_lod(prisms):
    total = len(prisms)
    if total > CAP:
        prisms.sort(key=lambda pr: -pr["_a"])
        prisms = prisms[:CAP]
    for pr in prisms:
        del pr["_a"]
    return prisms, total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk", type=Path, default=DEFAULT_PDK)
    ap.add_argument("--only", default=None, help="restrict to one library")
    args = ap.parse_args()

    cells = json.load(open(DOCS / "cells.json"))
    outdir = DOCS / "prisms"
    outdir.mkdir(exist_ok=True)

    import gc
    libs = sorted({meta["lib"] for meta in cells.values()})
    index = {}
    idxfile = outdir / "index.json"
    if idxfile.exists():
        index = json.load(open(idxfile))
    done = miss = 0
    for libname in libs:
        if args.only and libname != args.only:
            continue
        gdsdir = args.pdk / "libs.ref" / libname / "gds"
        if not gdsdir.is_dir():
            print(f"!! no gds dir for {libname}", file=sys.stderr, flush=True)
            continue
        libcells = {}
        keep = [gl for gl in ()]  # hold gdstk libraries alive while processing
        _libs_alive = []
        for f in sorted(gdsdir.glob("*.gds")):
            try:
                gl = gdstk.read_gds(str(f))
            except Exception as e:
                print(f"!! {f.name}: {e}", file=sys.stderr, flush=True)
                continue
            _libs_alive.append(gl)
            for c in gl.cells:
                libcells.setdefault(c.name, c)
        print(f"== {libname}: {len(libcells)} gds cells loaded", flush=True)
        for name, meta in sorted(cells.items()):
            if meta["lib"] != libname:
                continue
            cell = libcells.get(name)
            if cell is None and "__" in name:
                cell = libcells.get(name.split("__", 1)[1])
            if cell is None:
                miss += 1
                continue
            try:
                prisms, via_prisms, via_total, via_stride = cell_to_prisms(cell)
            except Exception as e:
                print(f"!! {name}: {e}", file=sys.stderr, flush=True)
                miss += 1
                continue
            prisms, nonvia_total = poly_area_sort_lod(prisms)
            total = nonvia_total + via_total
            bb = cell.bounding_box()
            w = round(bb[1][0] - bb[0][0], 3) if bb else 0
            h = round(bb[1][1] - bb[0][1], 3) if bb else 0
            if bb:
                ox, oy = bb[0]
                for pr in prisms:
                    pr["p"] = [[round(x - ox, ROUND), round(y - oy, ROUND)] for x, y in pr["p"]]
                # via hex points must ride the SAME bbox-origin shift as the
                # metals, or vias land offset by (ox,oy) on any cell whose
                # geometry doesn't start at (0,0) — e.g. std cells at -0.43.
                for vp in via_prisms:
                    vp["p"] = [[x - ox, y - oy] for x, y in vp["p"]]
            # v2 format: per-layer grouping, flat coordinate arrays,
            # vias as bare hex centers (JS reconstructs the hexagons)
            layers = {}
            for pr in prisms:
                a = layers.setdefault(pr["l"], {"l": pr["l"], "z0": pr["z0"],
                                                "z1": pr["z1"], "ps": []})
                flat = []
                for x, y in pr["p"]:
                    flat.append(x); flat.append(y)
                a["ps"].append(flat)
            for vp in via_prisms:
                a = layers.setdefault(vp["l"], {"l": vp["l"], "z0": vp["z0"],
                                                "z1": vp["z1"], "ps": []})
                if "hx" not in a:
                    a["hx"] = []
                    # recover radius from the first hexagon (distance c->vertex)
                    cx = sum(pt[0] for pt in vp["p"]) / 6
                    cy = sum(pt[1] for pt in vp["p"]) / 6
                    a["hr"] = round(((vp["p"][0][0]-cx)**2 + (vp["p"][0][1]-cy)**2) ** 0.5, 3)
                cx = round(sum(pt[0] for pt in vp["p"]) / 6, ROUND)
                cy = round(sum(pt[1] for pt in vp["p"]) / 6, ROUND)
                a["hx"].append(cx); a["hx"].append(cy)
            nshown = len(prisms) + len(via_prisms)
            lod = {"shown": nshown, "total": total}
            if via_stride > 1:
                lod["vias"] = "1:%d" % via_stride
            rec = {"v": 2, "w": w, "h": h, "zmax": 7.25, "lod": lod,
                   "layers": list(layers.values())}
            out = outdir / f"{name}.json"
            out.write_text(json.dumps(rec, separators=(",", ":")))
            index[name] = {"f": out.name, "n": nshown, "t": total,
                           "b": out.stat().st_size}
            done += 1
            if done % 50 == 0:
                print(f"{done} cells done…", flush=True)
        del libcells, _libs_alive
        gc.collect()

    (outdir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    big = sorted(index.items(), key=lambda kv: -kv[1]["b"])[:8]
    tot = sum(v["b"] for v in index.values())
    print(f"done: {done} cells, {miss} missing, {tot/1e6:.1f} MB total")
    for n, v in big:
        lod = "" if v["n"] == v["t"] else f"  LOD {v['n']}/{v['t']}"
        print(f"  {v['b']/1e3:8.0f} kB  {n}{lod}")

if __name__ == "__main__":
    main()
