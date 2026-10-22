#!/usr/bin/env python3
"""Hardware table from the post-route Vivado reports in results/vivado/<cfg>/ (Tables hw, hw-precision).
LUT/FF/BRAM/DSP from utilization.rpt (Slice LUTs, Slice Registers, Block RAM Tile, DSPs), power from
power.rpt, and the internal F_max = 1/(20 ns - WNS_reg), where WNS_reg is the worst setup slack among the
reported max-delay paths that start and end at a cell (register-to-register). The overall WNS also covers
the I/O ports, whose out-of-context budget (8 ns output delay) is not a property of the core.
usage: python3 tools/hw_report.py [results/vivado]"""
import os, re, sys
V4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(V4, "results", "vivado")
CFGS = ["lif_10", "lif_64x10", "lif_64x64x10", "izh_10", "izh_64x10", "izh_64x64x10",
        "hh_10", "hh_64x10", "hh_64x64x10", "lif_64x10_b4", "lif_64x10_b16",
        "izh_64x10_b4", "izh_64x10_b16", "hh_10_b4", "hh_10_b16", "lif_cnn"]

def field(pat, txt):
    m = re.search(pat, txt, re.M)
    return m.group(1) if m else "?"

print("%-15s %6s %4s %5s %3s %8s %8s %6s %6s %6s  %s" % ("config", "LUT", "FF", "BRAM", "DSP", "WNS", "WNS_reg", "Fmax", "P_tot", "P_dyn", "netlist"))
for c in CFGS:
    d = os.path.join(root, c)
    if not os.path.isdir(d):
        continue
    u = open(os.path.join(d, "utilization.rpt")).read()
    t = open(os.path.join(d, "timing.rpt")).read()
    p = open(os.path.join(d, "power.rpt")).read()
    mx = t.split("Max Delay Paths")[1].split("Min Delay Paths")[0]
    paths = [(float(s), a, b) for s, a, b in re.findall(
        r"Slack \((?:MET|VIOLATED)\) :\s*(-?[\d.]+)ns.*?\n\s*Source:\s*(\S+).*?\n\s*Destination:\s*(\S+)", mx, re.S)]
    reg = [s for s, a, b in paths if "/" in a and "/" in b]
    chk = os.path.join(d, "netlist_check.txt")
    nl = open(chk).read().split("--")[0].split(":")[-1].strip() if os.path.exists(chk) else "-"
    print("%-15s %6s %4s %5s %3s %8.3f %8.3f %6.1f %6.0f %6.0f  %s" % (
        c, field(r"^\| Slice LUTs\*?\s*\|\s*(\d+)", u), field(r"^\| Slice Registers\s*\|\s*(\d+)", u),
        field(r"^\| Block RAM Tile\s*\|\s*([\d.]+)", u), field(r"^\| DSPs\s*\|\s*(\d+)", u),
        min(s for s, _, _ in paths), min(reg), 1000.0 / (20.0 - min(reg)),
        1000 * float(field(r"^\| Total On-Chip Power \(W\)\s*\|\s*([\d.]+)", p)),
        1000 * float(field(r"^\| Dynamic \(W\)\s*\|\s*([\d.]+)", p)), nl))
