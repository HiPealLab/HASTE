#!/usr/bin/env python3
"""Aggregate the training-seed study (scripts/seed_study.sh): seed 0 = build/<cfg>,
seeds 1..4 = build_seeds/<cfg>_s<k>; original encoding, 1000 images."""
import os, re, sys
import numpy as np
V4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(V4, "tools"))
import score
def acc(fn):
    d = score.load(fn); ks = sorted(d)
    return 100.0 * np.mean([int(np.argmax(d[k]["counts"]) == d[k]["label"] and d[k]["counts"].max() > 0) for k in ks])
from train_ann import rate_inputs
X, lab = rate_inputs()
W0 = os.path.join(V4, "..", "..", "Train", "outputs")
def ann_rate(npz):
    z = np.load(npz); h = X
    for i in range(len(z.files)):
        h = h @ z["arr_%d" % i].T
        if i < len(z.files) - 1: h = np.maximum(h, 0)
    return 100.0 * np.mean(h.argmax(1) == lab)
ann = {(t, s): (None, ann_rate(os.path.join(W0, "weights-%s.npz" % t) if s == 0 else os.path.join(W0, "seeds", "weights-%s-s%d.npz" % (t, s))))
       for t in ("10", "64x10", "64x64x10") for s in range(5)}
print("%-14s %-28s %s" % ("config", "per seed 0..4", "mean +- std"))
for t in ("10", "64x10", "64x64x10"):
    a = np.array([ann[(t, s)][1] for s in range(5)])
    print("%-14s %-28s %.1f +- %.1f" % ("ANN-rate " + t, " ".join("%.1f" % x for x in a), a.mean(), a.std(ddof=1)))
    for m in ("lif", "izh", "hh"):
        if m == "hh" and t != "10": continue
        c = "%s_%s" % (m, t)
        v = [acc(os.path.join(V4, "build", c, "rtl_results.txt"))] + \
            [acc(os.path.join(V4, "build_seeds", "%s_s%d" % (c, s), "rtl_results.txt")) for s in range(1, 5)]
        v = np.array(v); gap = v - a
        print("%-14s %-28s %.1f +- %.1f   gap to ANN-rate %.1f +- %.1f" % (c, " ".join("%.1f" % x for x in v), v.mean(), v.std(ddof=1), gap.mean(), gap.std(ddof=1)))
