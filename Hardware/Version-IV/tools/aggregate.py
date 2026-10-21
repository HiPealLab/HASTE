#!/usr/bin/env python3
"""Aggregate multi-seed and T-sweep RTL results into the tables for the paper.

  python3 tools/aggregate.py seeds [--sim verilator]   -> results/seeds_<sim>.md
  python3 tools/aggregate.py tsweep [--sim verilator]  -> results/tsweep_<sim>.md

seeds : for every configuration, accuracy on the original encoding (data/) and on
        the re-encodings data_s1..data_s5; mean, sample std and a 95 % t-interval
        over the available encodings, plus paired comparisons between models on
        the same topology (mean difference over seeds, paired t-test p-value).
tsweep: accuracy / cycles / latency for T = 20, 50, 100, 200 (prefixes of the
        T=200 encoding data_s1_T200), one row per configuration.
"""
import argparse
import glob
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import score  # noqa: E402

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def acc_cyc(path):
    A = score.load(path)
    ks = sorted(A)
    lab = np.array([A[k]["label"] for k in ks])
    C = np.array([A[k]["counts"] for k in ks])
    ok = (C.argmax(1) == lab) & (C.sum(1) > 0)
    return 100.0 * ok.mean(), float(np.mean([A[k]["cyc"] for k in ks])), len(ks)


def fname(sim, tag):
    return ("rtl_results%s.txt" if sim == "verilator" else "rtl_" + sim + "%s.txt") % tag


def pvalue_paired(d):
    """two-sided paired t-test p-value (normal approximation of the t tail for
    small n is too optimistic, so use the exact Student-t CDF via the
    regularised incomplete beta function)."""
    n = len(d)
    if n < 2 or np.std(d, ddof=1) == 0:
        return float("nan")
    t = np.mean(d) / (np.std(d, ddof=1) / math.sqrt(n))
    df = n - 1
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


def _betainc(a, b, x, it=200):
    # continued fraction (Numerical Recipes betacf) for I_x(a, b)
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _betainc(b, a, 1 - x, it)
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / d if abs(d) > 1e-30 else 1e30
    h = d
    for m in range(1, it):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / d if abs(d) > 1e-30 else 1e30
        c = 1 + aa / c if abs(c) > 1e-30 else 1e30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / d if abs(d) > 1e-30 else 1e30
        c = 1 + aa / c if abs(c) > 1e-30 else 1e30
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return math.exp(lbeta) * h / a


def seeds(sim):
    rows, per = [], {}
    for B in sorted(glob.glob(os.path.join(V4, "build", "*"))):
        cfg = os.path.basename(B)
        accs = {}
        for tag, name in [("", "orig")] + [("_s%d" % s, "s%d" % s) for s in range(1, 10)]:
            f = os.path.join(B, fname(sim, tag))
            if os.path.exists(f):
                accs[name] = acc_cyc(f)[0]
        if len(accs) < 2:
            continue
        v = np.array(list(accs.values()))
        n = len(v)
        sd = v.std(ddof=1)
        hw = T95.get(n - 1, 1.96) * sd / math.sqrt(n)
        per[cfg] = accs
        rows.append("| %s | %d | %s | **%.2f ± %.2f** | [%.2f, %.2f] |" % (
            cfg, n, " ".join("%.1f" % x for x in v), v.mean(), sd, v.mean() - hw, v.mean() + hw))
    out = ["# Multi-seed accuracy (%s RTL, 1000 MNIST test images per encoding, T = 100)" % sim, "",
           "Encodings: the original spike trains (data/) and Poisson re-encodings with seeds 1-5 (data_s1..s5).",
           "Mean ± sample std; 95 % t-interval of the mean.", "",
           "| config | encodings | accuracies (%) | mean ± std | 95 % CI |", "|---|---|---|---|---|"] + rows
    # paired model comparisons on the same topology / precision
    out += ["", "## Paired model comparisons (same encodings)", "",
            "| comparison | mean difference (pts) | paired t-test p |", "|---|---|---|"]
    for cfg in sorted(per):
        m, rest = cfg.split("_", 1)
        for other in ("izh", "hh"):
            o = "%s_%s" % (other, rest)
            if m == "lif" and o in per:
                common = sorted(set(per[cfg]) & set(per[o]))
                d = np.array([per[cfg][k] - per[o][k] for k in common])
                out.append("| %s − %s | %+.2f | %.2g |" % (cfg, o, d.mean(), pvalue_paired(d)))
    path = os.path.join(V4, "results", "seeds_%s.md" % sim)
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))


def tsweep(sim):
    rows = []
    for B in sorted(glob.glob(os.path.join(V4, "build", "*"))):
        cfg = os.path.basename(B)
        pts = []
        for f in glob.glob(os.path.join(B, fname(sim, "_s1_T200_T*"))):
            T = int(re.search(r"_T(\d+)\.txt$", f).group(1))
            a, c, n = acc_cyc(f)
            pts.append((T, a, c))
        if not pts:
            continue
        for T, a, c in sorted(pts):
            rows.append("| %s | %d | %.1f | %.0f | %.2f |" % (cfg, T, a, c, c / 50e3))
    out = ["# Time-window sweep (%s RTL, 1000 MNIST test images, encoding data_s1_T200, first T steps)" % sim, "",
           "| config | T | acc % | cycles/img | latency ms @ 50 MHz |", "|---|---|---|---|---|"] + rows
    path = os.path.join(V4, "results", "tsweep_%s.md" % sim)
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["seeds", "tsweep"])
    ap.add_argument("--sim", default="verilator")
    a = ap.parse_args()
    seeds(a.sim) if a.what == "seeds" else tsweep(a.sim)
