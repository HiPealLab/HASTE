#!/usr/bin/env python3
"""Summarise an on-board run: latency (UART log) and power (meter readings).

  python3 board/tools/analyze_board.py uart_50MHz.log
  python3 board/tools/analyze_board.py uart_50MHz.log --readings power_50MHz.csv \
          --vivado board/vivado/out/lif_64x10_50MHz/summary.txt

uart log : as captured from board/sw/main.c (IMG/TIME/SUMMARY/CONT lines).
readings : CSV, one meter reading per line, header either
               state,watts            or      state,volts,amps
           state = a (board on, PL not configured), b (bitstream loaded, core
           idle in reset), c (continuous inference).  3 readings per state.
vivado   : summary.txt of board/vivado/build_board.tcl (vectorless/SAIF power).
The strict CYCLES/COUNTS check against the Verilator golden file is done by
board/tools/compare_results.py (run it too).
"""
import argparse, csv, re, statistics as st, sys


def mean_sd(v):
    return (st.mean(v), st.stdev(v) if len(v) > 1 else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uart")
    ap.add_argument("--readings")
    ap.add_argument("--vivado")
    a = ap.parse_args()

    cyc, xt, hw, duty, cont = {}, {}, {}, [], []
    fclk = None
    for raw in open(a.uart, errors="replace"):
        line = raw.replace("\r", "").strip()
        m = re.search(r"IMG (\d+) .*CYCLES (\d+)", line)
        if m: cyc[int(m.group(1))] = int(m.group(2))
        m = re.search(r"TIME (\d+) XTIME_NS (\d+) HW_NS (\d+)", line)
        if m: xt[int(m.group(1))] = int(m.group(2)); hw[int(m.group(1))] = int(m.group(3))
        m = re.search(r"FCLK measured (\d+) Hz", line)
        if m: fclk = int(m.group(1))
        m = re.search(r"PHASE CONT round (\d+) END images=(\d+) busy_kcycles=(\d+) wall_kcycles=(\d+)", line)
        if m:
            r, n, b, w = map(int, m.groups())
            cont.append((r, n, b * 1e3, w * 1e3))
    if not cyc:
        sys.exit("no IMG lines in " + a.uart)
    ks = sorted(cyc)
    c = [cyc[k] for k in ks]
    print("LATENCY  images=%d  FCLK measured=%s Hz" % (len(ks), fclk))
    print("  CYCLES/img mean=%.1f min=%d max=%d  -> %.4f ms @ 50 MHz nominal" % (st.mean(c), min(c), max(c), st.mean(c) / 50e3))
    if xt:
        x = [xt[k] / 1e3 for k in ks if k in xt]
        h = [hw[k] / 1e3 for k in ks if k in hw]
        ov = [(xt[k] - hw[k]) for k in ks if k in xt]
        print("  wall-clock (XTime, START write -> DONE seen) mean=%.3f us  min=%.3f  max=%.3f" % (st.mean(x), min(x), max(x)))
        print("  CYCLES / f_measured                          mean=%.3f us" % st.mean(h))
        print("  XTime - CYCLES/f (software/AXI overhead)     mean=%.0f ns  min=%d  max=%d" % (st.mean(ov), min(ov), max(ov)))
    for r, n, b, w in cont:
        print("CONT round %d: %d images, duty %.2f %%, %.3f ms wall per image" % (r, n, 100 * b / w, w / n / (fclk or 50e6) * 1e3))
    duty_mean = st.mean([b / w for _, _, b, w in cont]) if cont else None
    t_img_cont = st.mean([w / n / (fclk or 50e6) for _, n, _, w in cont]) if cont else None

    if a.readings:
        vals = {}
        with open(a.readings) as f:
            for row in csv.DictReader(f):
                row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                s = row["state"].lower()[:1]
                p = float(row["watts"]) if "watts" in row and row["watts"] else float(row["volts"]) * float(row["amps"])
                vals.setdefault(s, []).append(p)
        print("POWER (board input)")
        name = {"a": "(a) PL not configured", "b": "(b) bitstream, core idle in reset", "c": "(c) continuous inference"}
        ms = {}
        for s in "abc":
            if s in vals:
                ms[s] = mean_sd(vals[s])
                print("  %-36s %.4f W  (sd %.4f, n=%d)" % (name[s], ms[s][0], ms[s][1], len(vals[s])))
        if "b" in ms and "c" in ms:
            d = ms["c"][0] - ms["b"][0]
            sd = (ms["c"][1] ** 2 + ms["b"][1] ** 2) ** 0.5
            print("  incremental inference power (c)-(b) = %.4f W (+- %.4f)" % (d, sd))
            if duty_mean:
                print("  ... per busy core (divided by duty %.3f)  = %.4f W" % (duty_mean, d / duty_mean))
                print("  incremental energy per image = (c-b) x wall time per image in CONT = %.3f mJ" % (d * t_img_cont * 1e3))
        if "a" in ms and "b" in ms:
            print("  configuration + PS-app power (b)-(a)   = %.4f W" % (ms["b"][0] - ms["a"][0]))
    if a.vivado:
        print("VIVADO (board design):")
        for line in open(a.vivado):
            if line.startswith(("timing", "power", "FCLK", "utilization")):
                print("  " + line.strip())


if __name__ == "__main__":
    main()
