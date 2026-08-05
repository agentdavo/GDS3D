#!/usr/bin/env python3
"""Collect per-cell facts for the gf180mcuD reference site.

Everything here is READ FROM THE PDK, never invented:
  LEF     footprint (SIZE), placement site, pin names/direction/use
  Liberty cell area and the BOOLEAN FUNCTION of each output pin
  GDS     which layers the cell actually uses

Liberty is parsed with a small brace-depth scanner rather than a full parser:
these files are ~100 MB and only three fields are needed, so a real parse would
cost far more than it returns. The scanner tracks nesting so a `function` inside
pin(X) is attributed to X and not to a neighbouring pin.

Writes docs/cells.json, published alongside the site as a machine-readable
version of everything the page shows.
"""

import json
import os
import re
import sys

PDK = ("/home/djs/chdl/ext/gf180mcu-project-template/gf180mcu/ciel/gf180mcu/"
       "versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.ref")

LIBS = ["gf180mcu_fd_io", "gf180mcu_ocd_io",
        "gf180mcu_fd_sc_mcu7t5v0", "gf180mcu_fd_sc_mcu9t5v0",
        "gf180mcu_as_sc_mcu7t3v3",
        "gf180mcu_osu_sc_gp9t3v3", "gf180mcu_osu_sc_gp12t3v3",
        "gf180mcu_fd_ip_sram", "gf180mcu_ocd_ip_sram", "gf180mcu_re_efuse"]

# Libraries that ship layout only -- no LEF, no Liberty. One device per .gds;
# the record carries just name and library, which is all the PDK provides.
# The map renames gds files whose top cell (and rendered video) is called
# something else.
GDS_ONLY = {"gf180mcu_fd_pr": {"efuse": "efuse_cell"}}

# Preferred typical-corner liberty per library, by filename fragment.
TT_HINTS = ["tt_025C_5v00", "tt_025C_3v30", "tt_025C_1v80", "tt_025C", "tt_"]


def parse_lef(path):
    out, macro = {}, None
    pin = None
    for raw in open(path, errors="replace"):
        s = raw.strip()
        if s.startswith("MACRO "):
            macro = s.split()[1]
            out[macro] = {"size": None, "site": None, "pins": []}
        elif macro and s.startswith("SIZE "):
            m = re.match(r"SIZE ([\d.]+) BY ([\d.]+)", s)
            if m:
                out[macro]["size"] = [float(m.group(1)), float(m.group(2))]
        elif macro and s.startswith("SITE "):
            out[macro]["site"] = s.split()[1].rstrip(";").strip()
        elif macro and s.startswith("PIN "):
            pin = {"name": s.split()[1], "dir": None, "use": None}
            out[macro]["pins"].append(pin)
        elif pin is not None and s.startswith("DIRECTION "):
            pin["dir"] = s.split()[1].rstrip(";")
        elif pin is not None and s.startswith("USE "):
            pin["use"] = s.split()[1].rstrip(";")
        elif macro and s.startswith("END ") and s.split()[1] == macro:
            macro, pin = None, None
    return out


def parse_liberty(path):
    """-> {cell: {"area": float, "functions": {pin: expr}}}"""
    res, cell, pin, depth = {}, None, None, 0
    cell_depth = pin_depth = -1
    with open(path, errors="replace") as f:
        for line in f:
            s = line.strip()
            m = re.match(r"cell\s*\(([^)]+)\)", s)
            if m and cell is None:
                cell = m.group(1).strip()
                res[cell] = {"area": None, "functions": {}}
                cell_depth = depth
            elif cell is not None:
                mp = re.match(r"pin\s*\(([^)]+)\)", s)
                if mp:
                    pin = mp.group(1).strip()
                    pin_depth = depth
                elif s.startswith("area"):
                    mv = re.search(r"area\s*:\s*([\d.]+)", s)
                    if mv:
                        res[cell]["area"] = float(mv.group(1))
                elif s.startswith("function") and pin:
                    mv = re.search(r'function\s*:\s*"([^"]*)"', s)
                    if mv:
                        res[cell]["functions"][pin] = mv.group(1)
            depth += line.count("{") - line.count("}")
            if pin is not None and depth <= pin_depth:
                pin = None
            if cell is not None and depth <= cell_depth:
                cell = None
    return res


def pick_liberty(libdir):
    if not os.path.isdir(libdir):
        return None
    files = [f for f in os.listdir(libdir) if f.endswith(".lib")]
    for hint in TT_HINTS:
        for f in sorted(files):
            if hint in f:
                return os.path.join(libdir, f)
    return os.path.join(libdir, sorted(files)[0]) if files else None


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "docs/cells.json"
    data = {}
    for lib in LIBS:
        base = os.path.join(PDK, lib)
        if not os.path.isdir(base):
            continue
        lefs = []
        ld = os.path.join(base, "lef")
        if os.path.isdir(ld):
            lefs = [os.path.join(ld, f) for f in sorted(os.listdir(ld))
                    if f.endswith(".lef")]
        macros = {}
        for lf in lefs:
            macros.update(parse_lef(lf))
        lib_path = pick_liberty(os.path.join(base, "lib"))
        libdata = parse_liberty(lib_path) if lib_path else {}
        n = 0
        for cell, info in macros.items():
            # Do NOT require the macro name to start with the library name.
            # gf180mcu_re_efuse ships LEF whose macros are called
            # efuse_wb_mem_1024x32 etc, with no library prefix -- filtering on
            # the prefix silently dropped all 7 of them.
            if cell in data:
                continue
            lb = libdata.get(cell, {})
            data[cell] = {
                "lib": lib,
                "short": cell.split("__")[-1],
                "size": info["size"],
                "site": info["site"],
                "pins": info["pins"],
                "area": lb.get("area"),
                "functions": lb.get("functions", {}),
            }
            n += 1
        print("%-26s %4d macros   liberty: %s"
              % (lib, n, os.path.basename(lib_path) if lib_path else "none"))
    for lib, renames in GDS_ONLY.items():
        gd = os.path.join(PDK, lib, "gds")
        if not os.path.isdir(gd):
            continue
        n = 0
        for f in sorted(os.listdir(gd)):
            if not f.endswith(".gds"):
                continue
            short = renames.get(f[:-4], f[:-4])
            name = "%s__%s" % (lib, short)
            if name in data:
                continue
            data[name] = {"lib": lib, "short": short, "size": None,
                          "site": None, "pins": [], "area": None,
                          "functions": {}}
            n += 1
        print("%-26s %4d devices  (GDS only)" % (lib, n))
    json.dump(data, open(out_path, "w"), indent=0)
    withfn = sum(1 for v in data.values() if v["functions"])
    print("\n%d cells written to %s (%d with boolean functions)"
          % (len(data), out_path, withfn))


if __name__ == "__main__":
    main()
