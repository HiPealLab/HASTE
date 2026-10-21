#!/usr/bin/env python3
"""T-sweep statistics over the available T=200 encodings (s1..s5; prefixes 20/50/100/200).
Prints mean/std per config and T, and pgfplots coordinates with y error bars for
Fig. acc_vs_T (x = T) and Fig. pareto (x = energy, mJ = cycles/5e7 * P_total[mW])."""
import os, sys
import numpy as np
V4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(V4, "tools"))
import score
P = dict(lif_10=92, lif_64x10=93, lif_64x64x10=94, izh_10=97, izh_64x10=97, izh_64x64x10=98, hh_10=95)
for c in P:
    accs, cyc, used = {}, {}, []
    for s in range(1, 6):
        fs = [os.path.join(V4, "build", c, "rtl_results_s%d_T200_T%d.txt" % (s, T)) for T in (20, 50, 100, 200)]
        if not all(os.path.exists(f) for f in fs):
            continue
        used.append(s)
        for T, f in zip((20, 50, 100, 200), fs):
            d = score.load(f); ks = sorted(d)
            a = 100.0 * np.mean([int(np.argmax(d[k]["counts"]) == d[k]["label"] and d[k]["counts"].max() > 0) for k in ks])
            accs.setdefault(T, []).append(a); cyc.setdefault(T, []).append(np.mean([d[k]["cyc"] for k in ks]))
    if not used:
        continue
    m = {T: np.mean(v) for T, v in accs.items()}; sd = {T: (np.std(v, ddof=1) if len(v) > 1 else 0.0) for T, v in accs.items()}
    E = {T: np.mean(cyc[T]) / 5e7 * P[c] for T in cyc}
    print("%-13s seeds %s  " % (c, used) + "  ".join("T%d %.1f+-%.1f" % (T, m[T], sd[T]) for T in sorted(m)))
    print("   accT:   " + " ".join("(%d,%.1f) +- (0,%.1f)" % (T, m[T], sd[T]) for T in sorted(m)))
    print("   pareto: " + " ".join("(%.4g,%.1f) +- (0,%.1f)" % (E[T], m[T], sd[T]) for T in sorted(m)))
