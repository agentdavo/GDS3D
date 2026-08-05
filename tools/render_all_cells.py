#!/usr/bin/env python3
"""Render a spin video for every placeable cell in the gf180mcuD PDK.

RESUMABLE BY DESIGN. The full run is ~688 cells and several hours, so it skips
any cell whose output already exists and is non-trivial in size. Kill it and
re-run and it picks up where it stopped; delete a file to force one re-render.

EXPLODE MUST SCALE WITH CELL SIZE. GDS3D translates each layer by
1.5 * layer.Height * Unitu * fraction, which is an ABSOLUTE distance in microns
and takes no account of how big the cell is. A fraction of 11 suits a 350 um
I/O pad; on a 3.4 um standard cell it lifts Metal2 33 um -- ten times the cell's
own width -- and the cell renders as a speck. So the fraction is chosen per
library from the cell pitch, not fixed.

Usage:
    python3 tools/render_all_cells.py [--out DIR] [--size N] [--seconds S]
    python3 tools/render_all_cells.py --list        # enumerate, render nothing
"""

import argparse
import os
import struct
import subprocess
import sys
import time

PDK = ("/home/djs/chdl/ext/gf180mcu-project-template/gf180mcu/ciel/gf180mcu/"
       "versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.ref")
GDS3D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TECH = os.path.join(GDS3D, "techfiles", "gf180mcuD.txt")
BIN = os.path.join(GDS3D, "linux_egl", "GDS3D_egl")

# (library, gds file, cell-name prefix, explode fraction)
# Explode is tuned to the library's cell height: I/O cells are 350 um deep and
# take a large fraction; standard cells are a few microns and take a small one.
LIBS = [
    ("gf180mcu_fd_io",           "gf180mcu_fd_io.gds",           "gf180mcu_fd_io__",           11.0),
    ("gf180mcu_ocd_io",          "gf180mcu_ocd_io.gds",          "gf180mcu_ocd_io__",          11.0),
    ("gf180mcu_fd_sc_mcu7t5v0",  "gf180mcu_fd_sc_mcu7t5v0.gds",  "gf180mcu_fd_sc_mcu7t5v0__",   0.8),
    ("gf180mcu_fd_sc_mcu9t5v0",  "gf180mcu_fd_sc_mcu9t5v0.gds",  "gf180mcu_fd_sc_mcu9t5v0__",   0.8),
    ("gf180mcu_as_sc_mcu7t3v3",  "gf180mcu_as_sc_mcu7t3v3.gds",  "gf180mcu_as_sc_mcu7t3v3__",   0.8),
    ("gf180mcu_osu_sc_gp9t3v3",  "gf180mcu_osu_sc_gp9t3v3.gds",  "gf180mcu_osu_sc_gp9t3v3__",   0.8),
    ("gf180mcu_osu_sc_gp12t3v3", "gf180mcu_osu_sc_gp12t3v3.gds", "gf180mcu_osu_sc_gp12t3v3__",  0.8),
]
# Macro libraries: one GDS per macro, top cell named after the file.
MACRO_LIBS = [("gf180mcu_fd_ip_sram", 6.0), ("gf180mcu_ocd_ip_sram", 6.0),
              ("gf180mcu_re_efuse", 3.0), ("gf180mcu_fd_pr", 1.5)]


def gds_cells(path, prefix):
    """Structure names in a GDS, by record scan -- no KLayout needed."""
    data = open(path, "rb").read()
    i, out = 0, set()
    while i < len(data) - 3:
        ln, rt, dt = struct.unpack(">HBB", data[i:i + 4])
        if ln < 4:
            break
        if rt == 0x06 and dt == 0x06:
            n = data[i + 4:i + ln].rstrip(b"\x00").decode("ascii", "replace")
            if n.startswith(prefix):
                out.add(n)
        i += ln
    return sorted(out)


def top_cells(path):
    """Structures never referenced by an SREF/AREF -- i.e. candidate tops."""
    data = open(path, "rb").read()
    i, names, refs = 0, [], set()
    while i < len(data) - 3:
        ln, rt, dt = struct.unpack(">HBB", data[i:i + 4])
        if ln < 4:
            break
        b = data[i + 4:i + ln]
        if rt == 0x06 and dt == 0x06:
            names.append(b.rstrip(b"\x00").decode("ascii", "replace"))
        elif rt == 0x12:
            refs.add(b.rstrip(b"\x00").decode("ascii", "replace"))
        i += ln
    return [n for n in names if n not in refs and not n.startswith("(")]


def build_worklist():
    work = []
    for lib, fname, prefix, expl in LIBS:
        path = os.path.join(PDK, lib, "gds", fname)
        if not os.path.exists(path):
            print("  skip %s (no %s)" % (lib, fname), file=sys.stderr)
            continue
        for c in gds_cells(path, prefix):
            work.append((lib, path, c, expl))
    for lib, expl in MACRO_LIBS:
        d = os.path.join(PDK, lib, "gds")
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".gds"):
                continue
            path = os.path.join(d, f)
            tops = top_cells(path)
            # Prefer a top whose name matches the file; else the first top.
            stem = f[:-4]
            cell = stem if stem in tops else (tops[0] if tops else None)
            if cell:
                work.append((lib, path, cell, expl))
    return work


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(GDS3D, "docs", "videos"))
    ap.add_argument("--size", type=int, default=720)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--ssaa", type=int, default=2)
    ap.add_argument("--margin", type=float, default=0.9)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    work = build_worklist()
    print("placeable cells found: %d" % len(work))
    if a.list:
        for lib, _, c, e in work:
            print("  %-26s %-44s explode %.1f" % (lib, c, e))
        return

    t0 = time.time()
    done = skipped = failed = 0
    for k, (lib, path, cell, expl) in enumerate(work, 1):
        outdir = os.path.join(a.out, lib)
        os.makedirs(outdir, exist_ok=True)
        short = cell.split("__")[-1] if "__" in cell else cell
        dst = os.path.join(outdir, short + ".mp4")
        if os.path.exists(dst) and os.path.getsize(dst) > 5000:
            skipped += 1
            continue
        cmd = [BIN, "-p", TECH, "-i", path, "-t", cell,
               "--egl-size", str(a.size), str(a.size),
               "--egl-view", "-58", "0", "--egl-fit",
               "--egl-margin", str(a.margin), "--egl-explode", str(expl),
               "--egl-ssaa", str(a.ssaa),
               "--egl-video", dst, "--egl-seconds", str(a.seconds),
               "--egl-fps", str(a.fps), "--egl-spin", "360"]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=600, cwd=GDS3D)
        except subprocess.TimeoutExpired:
            pass
        if os.path.exists(dst) and os.path.getsize(dst) > 5000:
            done += 1
        else:
            failed += 1
            print("  FAILED %s / %s" % (lib, cell), flush=True)
        if k % 10 == 0 or k == len(work):
            el = time.time() - t0
            rate = el / max(done, 1)
            left = (len(work) - k) * rate
            print("[%4d/%d] done %d skip %d fail %d  %.1f s/cell  eta %.1f h"
                  % (k, len(work), done, skipped, failed, rate, left / 3600),
                  flush=True)
    print("finished: %d rendered, %d skipped, %d failed, %.1f h"
          % (done, skipped, failed, (time.time() - t0) / 3600))


if __name__ == "__main__":
    main()
