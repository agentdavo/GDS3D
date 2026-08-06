#!/usr/bin/env python3
"""Extract extruded-prism JSON for the bitcell comparison page.

Three cells, same z-stack, same units, so they can be shown side by side to
scale: the shipped foundry 5 V cell and our drawn 3.3 V 6T and 8T cells.

Usage: python3 extract_bitcell_pair.py [--out ../bitcell_pair.json]
                                       [--html ../bitcell_compare.html]
"""
import argparse, glob, json, math, sys
from pathlib import Path

import gdstk

# Pitches are read from generated array placement/boundary geometry, never
# imported from the builders and never hardcoded here.  This prevents source
# comments or Python bytecode metadata from becoming page data.

HOME = Path.home()
PDK = HOME / ("chdl/ext/gf180mcu-project-template/gf180mcu/ciel/gf180mcu/versions/"
              "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7")
FTL = HOME / "chdl/ext/gf180mcu-project-template/ip/gf180mcu_ftl_ip_sram"

# (layer, datatype) -> (name, z0, z1).
#
# Poly2 upward is transcribed from libs.tech/klayout/tech/d25/gf180mcu.lyd25 and
# matches its arithmetic exactly (Metal1 860 nm + 550, Via1 +600, and so on).
#
# Nwell and COMP are NOT in that file -- KLayout's 2.5D view starts at poly and
# says nothing about the silicon below it. Those two z ranges are mine, chosen
# to read sensibly under the stack; do not cite them as PDK data.
Z = {
    (21, 0): ("Nwell",  -0.90, -0.30),   # not from the PDK -- see above
    (22, 0): ("COMP",   -0.30,  0.00),   # not from the PDK -- see above
    (30, 0): ("Poly2",   0.00,  0.20),
    (33, 0): ("Contact", 0.00,  0.86),   # the "not over poly" case; see CONTACT_ON_POLY
    (34, 0): ("Metal1",  0.86,  1.41),
    (35, 0): ("Via1",    1.41,  2.01),
    (36, 0): ("Metal2",  2.01,  2.56),
    (38, 0): ("Via2",    2.56,  3.16),
    (42, 0): ("Metal3",  3.16,  3.71),
}
# The lyd25 splits Contact in two: a contact landing on Poly2 starts at the TOP
# of the poly (200 nm) and is 660 nm tall; one landing on diffusion starts at 0
# and is 860 nm. Flattening both to 0..0.86 sinks the gate contacts through the
# poly they sit on, which is exactly what you see on a 6T cell's two gate taps.
CONTACT_ON_POLY = (0.20, 0.86)
VIA_LAYERS = {"Contact", "Via1", "Via2"}
_HEX = [(math.cos(math.radians(60 * i + 30)), math.sin(math.radians(60 * i + 30)))
        for i in range(6)]
R = 4


def prisms_of(cell, dx=0.0, dy=0.0):
    """Merge per layer, extrude, and render vias as hexagons (as index3d does)."""
    poly = gdstk.boolean([p for p in cell.get_polygons(depth=None)
                          if (p.layer, p.datatype) == (30, 0)], [], "or")
    bylayer = {}
    for p in cell.get_polygons(depth=None):
        k = (p.layer, p.datatype)
        if k in Z:
            bylayer.setdefault(k, []).append(p)
    out = []
    for k, polys in sorted(bylayer.items()):
        name, z0, z1 = Z[k]
        if name in VIA_LAYERS:
            for q in polys:
                (x0, y0), (x1, y1) = q.bounding_box()
                # test against the poly in the ORIGINAL frame, then shift --
                # `poly` has not been translated by (dx, dy)
                ox, oy = (x0 + x1) / 2, (y0 + y1) / 2
                cx, cy = ox - dx, oy - dy
                r = 0.62 * max(x1 - x0, y1 - y0)
                za, zb = (z0, z1)
                if name == "Contact" and gdstk.inside([(ox, oy)], poly)[0]:
                    za, zb = CONTACT_ON_POLY      # sits on top of the poly
                out.append({"l": name, "z0": za, "z1": zb,
                            "p": [[round(cx + r * hx, R), round(cy + r * hy, R)]
                                  for hx, hy in _HEX]})
            continue
        for m in gdstk.boolean(polys, [], "or"):
            pts = m.points
            if len(pts) >= 3:
                out.append({"l": name, "z0": z0, "z1": z1,
                            "p": [[round(float(x) - dx, R), round(float(y) - dy, R)]
                                  for x, y in pts]})
    return out


def pack(cell, label, sub, pitch, note):
    (x0, y0), (x1, y1) = cell.bounding_box()
    return {"label": label, "sub": sub, "note": note,
            "bbox": [round(x1 - x0, R), round(y1 - y0, R)],
            "pitch": pitch, "area": round(pitch[0] * pitch[1], 4),
            "prisms": prisms_of(cell, x0, y0)}


def placed_pitch(lib, primitive):
    """Derive x pitch and row height from the generated array itself."""
    parents = [c for c in lib.cells
               if any(r.cell.name == primitive for r in c.references)]
    if len(parents) != 1:
        raise RuntimeError(f"expected one array parent for {primitive}")
    parent = parents[0]
    refs = [r for r in parent.references if r.cell.name == primitive]
    if len(refs) < 4:
        raise RuntimeError(f"not enough {primitive} references to derive pitch")

    def step(values):
        values = sorted(set(round(float(v), R) for v in values))
        deltas = [round(b - a, R) for a, b in zip(values, values[1:]) if b > a]
        if not deltas:
            raise RuntimeError(f"no non-zero placement step for {primitive}")
        return min(deltas)

    x_pitch = step(r.origin[0] for r in refs)
    cols = len(set(round(float(r.origin[0]), R) for r in refs))
    rows = len(refs) // cols
    boundary = [p for p in parent.polygons
                if (p.layer, p.datatype) == (0, 0)]
    if len(boundary) != 1:
        raise RuntimeError(f"expected one pr_bndry polygon for {primitive}")
    (_, y0), (_, y1) = boundary[0].bounding_box()
    return [x_pitch, round(float(y1 - y0) / rows, R)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "bitcell_pair.json"))
    ap.add_argument("--html", default=None,
                    help="also replace the inline DATA object in this comparison page")
    a = ap.parse_args()

    fd_gds = sorted(glob.glob(str(PDK / "*/libs.ref/gf180mcu_fd_ip_sram/gds/"
                                        "gf180mcu_fd_ip_sram__sram512x8m8wm1.gds")))[0]
    fd = {c.name: c for c in gdstk.read_gds(fd_gds).cells}["018SRAM_cell1_512x8m81"]
    ftl_gds = FTL / "build/gds/gf180mcu_ftl_ip_sram__array6t_16x16.gds"
    ftl_lib = gdstk.read_gds(str(ftl_gds))
    ftl_pitch = placed_pitch(ftl_lib, "gf180mcu_ftl_ip_sram__cell6t_03v3")
    ftl = {c.name: c for c in ftl_lib.cells}[
        "gf180mcu_ftl_ip_sram__cell6t_03v3"]
    e8_gds = FTL / "build/gds/gf180mcu_ftl_ip_sram__array8t_8x8.gds"
    e8lib = gdstk.read_gds(str(e8_gds))
    e8_pitch = placed_pitch(e8lib, "gf180mcu_ftl_ip_sram__cell8t_03v3")
    e8 = {c.name: c for c in e8lib.cells}["gf180mcu_ftl_ip_sram__cell8t_03v3"]
    e8.flatten()                      # it references the 6T core by reference

    data = {
        "fd": pack(fd, "gf180mcu_fd_ip_sram", "018SRAM_cell1 — 5 V foundry cell",
                   [3.68, 4.84],
                   "Shipped in the PDK. Array pitch is 4.84 um, not the 5.18 um "
                   "bbox: vertically mirrored rows overlap by 0.68 um where they "
                   "share the VDD source."),
        "ftl": pack(ftl, "gf180mcu_ftl_ip_sram",
                    "cell6t_03v3 — 3.3 V, drawn here", ftl_pitch,
                    "Same topology, redrawn against the 3.3 V rules with the "
                    "SramCore relaxations. Pitch IS the bbox in x; in y the rows "
                    "share the VDD contact at the cell edge."),
        "ftl8": pack(e8, "gf180mcu_ftl_ip_sram",
                     "cell8t_03v3 \u2014 3.3 V 8T, the MXFP4 array cell", e8_pitch,
                     "The 6T core plus an isolated read stack ordered "
                     "RBL-MRD(QB)-MRS(RWL)-VSS. RBL shares the alternate-row "
                     "boundary and read VSS joins core VSS locally; minimum-width "
                     "M2 tracks widen only at their Via1 landings."),
    }
    encoded = json.dumps(data, separators=(",", ":"))
    Path(a.out).write_text(encoded)
    if a.html:
        html = Path(a.html)
        text = html.read_text()
        start_token = "<script>const DATA = "
        end_token = ";\n\nconst LAYERS = ["
        start = text.index(start_token) + len(start_token)
        end = text.index(end_token, start)
        html.write_text(text[:start] + encoded + text[end:])
        print("updated inline DATA in", html)
    for k, v in data.items():
        n = len(v["prisms"])
        print(f"{k}: {v['bbox'][0]} x {v['bbox'][1]} um bbox, pitch {v['pitch']}, "
              f"{v['area']} um2/bit, {n} prisms")
    print("wrote", a.out, Path(a.out).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
