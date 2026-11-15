#!/usr/bin/env python3
"""Per-image statistics for the HASTE paper.

All models are evaluated on the same 1000 test images, so model comparisons
are paired: we use the exact McNemar test on the discordant counts
(b = A right & B wrong, c = A wrong & B right) instead of t-tests over
encodings.  "Near-lossless" claims use a paired equivalence test (TOST) with
margin DELTA percentage points.

Outputs (revision2/results/):
  stats_mcnemar.txt  every comparison: accA, accB, b, c, exact p, 95% CI of the
                     paired difference, TOST verdict at +-1 pt
  stats_ties.txt     tie / no-spike rates per configuration, accuracy under
                     three tie rules (lowest index = RTL/score.py, random
                     expectation, count-as-wrong)
  ann_baselines.txt  ANN accuracy on the 1000 images with (a) analog 8x8
                     pixels and (b) Poisson spike rates (the SNN's input)
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.dirname(HERE)
V4 = os.path.dirname(R2)
REPO = os.path.dirname(os.path.dirname(V4))
OUT = os.path.join(R2, "results")
DELTA = 1.0  # equivalence margin, percentage points


# --------------------------------------------------------------------- io
def load_counts(fn):
    lab, C = {}, {}
    for line in open(fn):
        if line.startswith("IMG"):
            p = line.split()
            k = int(p[1])
            lab[k] = int(p[3])
            C[k] = np.array([int(x) for x in p[p.index("COUNTS") + 1:]])
    ks = sorted(lab)
    return np.array(ks), np.array([lab[k] for k in ks]), np.array([C[k] for k in ks])


def correct_lowest(lab, C):
    """RTL/score.py rule: argmax (lowest index on ties); no output spike = wrong."""
    return (C.argmax(1) == lab) & (C.sum(1) > 0)


# ------------------------------------------------------------------ tests
def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def paired_diff_ci(a, b, z):
    """difference of accuracies (a - b) in points with a Wald CI for paired
    proportions (Agresti & Min style variance)."""
    n = len(a)
    b10 = np.sum(a & ~b)
    b01 = np.sum(~a & b)
    d = (b10 - b01) / n
    var = ((b10 + b01) / n - d ** 2) / n
    se = math.sqrt(max(var, 0.0))
    return 100 * d, 100 * (d - z * se), 100 * (d + z * se)


def wilson(k, n, z=1.96):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * (c - h), 100 * (c + h)


def compare(name, a, b):
    b10 = int(np.sum(a & ~b))
    b01 = int(np.sum(~a & b))
    p = mcnemar_exact(b10, b01)
    d, lo, hi = paired_diff_ci(a, b, 1.96)
    _, lo90, hi90 = paired_diff_ci(a, b, 1.645)
    eq = "equivalent" if (lo90 > -DELTA and hi90 < DELTA) else "not shown"
    return "%-44s %6.1f %6.1f  b=%3d c=%3d  p=%.3g  diff %+5.1f [%+5.1f,%+5.1f]  TOST(+-%.0f) %s" % (
        name, 100 * a.mean(), 100 * b.mean(), b10, b01, p, d, lo, hi, DELTA, eq)


# ------------------------------------------------------------------- ANN
def ann_forward(Ws, X):
    h = X
    for i, W in enumerate(Ws):
        h = h @ W.T
        if i < len(Ws) - 1:
            h = np.maximum(h, 0)
    return h


def rate_inputs(data="data"):
    d = np.load(os.path.join(V4, data, "spikes.npz"))
    sp = d["spikes"]
    X = np.zeros((sp.shape[0], 64))
    for j in range(64):
        X[:, j] = (sp == j).sum(axis=(1, 2))
    return X / sp.shape[1], d["labels"], d["names"]


def analog_inputs(names):
    """8x8 bilinear resize of the 1000 test PNGs, same transform as the encoder."""
    import torch
    import torchvision
    from PIL import Image
    tf = torchvision.transforms.Compose([torchvision.transforms.Grayscale(1), torchvision.transforms.ToTensor(),
                                         torchvision.transforms.Resize((8, 8))])
    png = os.path.join(REPO, "Train", "test_images_1k")
    X = np.stack([tf(Image.open(os.path.join(png, str(n) + ".png")).convert("RGB")).view(-1).numpy()
                  for n in names])
    return X.astype(np.float64)


def load_w(fn):
    z = np.load(fn)
    return [z["arr_%d" % i] for i in range(len(z.files))]


def main():
    os.makedirs(OUT, exist_ok=True)
    B = os.path.join(V4, "build")
    topos = ["10", "64x10", "64x64x10"]
    Xr, lab, names = rate_inputs()
    Xa = analog_inputs(names)
    np.save(os.path.join(OUT, "analog_inputs.npy"), Xa)
    ann = {}
    lines = ["ANN baselines on the 1000 hardware test images (same weights as the SNNs)",
             "%-10s %-14s %-14s %s" % ("topology", "analog pixels", "spike rates", "McNemar analog vs rate")]
    for t in topos:
        Ws = load_w(os.path.join(REPO, "Train", "outputs", "weights-%s.npz" % t))
        ca = ann_forward(Ws, Xa).argmax(1) == lab
        cr = ann_forward(Ws, Xr).argmax(1) == lab
        ann[t] = dict(analog=ca, rate=cr)
        lo, hi = wilson(ca.sum(), len(ca))
        lo2, hi2 = wilson(cr.sum(), len(cr))
        b10, b01 = int(np.sum(ca & ~cr)), int(np.sum(~ca & cr))
        lines.append("%-10s %5.1f [%4.1f,%4.1f] %5.1f [%4.1f,%4.1f]  b=%d c=%d p=%.3g" % (
            t, 100 * ca.mean(), lo, hi, 100 * cr.mean(), lo2, hi2, b10, b01, mcnemar_exact(b10, b01)))
    lines.append("CI = Wilson 95%%; the test-subset sampling error alone is about +-%.1f pts at 90%% accuracy" %
                 (196 * math.sqrt(0.9 * 0.1 / 1000)))
    open(os.path.join(OUT, "ann_baselines.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))

    # ---------------------------------------------------- SNN correctness
    cfgs = sorted(d for d in os.listdir(B) if os.path.exists(os.path.join(B, d, "rtl_results.txt")))
    corr, ties = {}, []
    ties.append("%-16s %6s %6s %6s | %8s %8s %8s" % ("config", "acc", "ties", "nospk", "lowest", "random", "tie=wrong"))
    rng_note = "random = expected accuracy if ties are broken uniformly among the tied classes"
    for c in cfgs:
        ks, l2, C = load_counts(os.path.join(B, c, "rtl_results.txt"))
        assert (l2 == lab[ks]).all() and len(ks) == 1000, c
        top = C.max(1, keepdims=True)
        istop = (C == top) & (top > 0)
        ntop = istop.sum(1)
        nos = C.sum(1) == 0
        tie = ntop > 1
        low = correct_lowest(lab, C)
        rnd = np.where(nos, 0.0, istop[np.arange(1000), lab] / np.maximum(ntop, 1))
        strict = low & ~tie
        corr[c] = low
        ties.append("%-16s %6.1f %6d %6d | %8.1f %8.1f %8.1f" % (
            c, 100 * low.mean(), tie.sum(), nos.sum(), 100 * low.mean(), 100 * rnd.mean(), 100 * strict.mean()))
    ties.append(rng_note)
    open(os.path.join(OUT, "stats_ties.txt"), "w").write("\n".join(ties) + "\n")
    print("\n".join(ties))

    # -------------------------------------------------------- comparisons
    L = ["Exact McNemar tests on the same 1000 images (RTL results, B=8 unless noted).",
         "b = first right & second wrong, c = first wrong & second right; diff = first - second (pts), "
         "95%% CI; TOST: 90%% CI inside +-%.0f pt." % DELTA, ""]
    L.append("== SNN vs ANN (same weights)")
    for m in ["lif", "izh", "hh"]:
        for t in topos:
            c = "%s_%s" % (m, t)
            if c in corr:
                L.append(compare("%s vs ANN-rate" % c, corr[c], ann[t]["rate"]))
                L.append(compare("%s vs ANN-analog" % c, corr[c], ann[t]["analog"]))
    L.append("")
    L.append("== neuron model, same topology")
    for t in topos:
        for a, b in [("lif", "izh"), ("lif", "hh"), ("izh", "hh")]:
            ca, cb = "%s_%s" % (a, t), "%s_%s" % (b, t)
            if ca in corr and cb in corr:
                L.append(compare("%s vs %s" % (ca, cb), corr[ca], corr[cb]))
    L.append("")
    L.append("== depth, same model")
    for m in ["lif", "izh", "hh"]:
        for a, b in [("10", "64x10"), ("64x10", "64x64x10")]:
            ca, cb = "%s_%s" % (m, a), "%s_%s" % (m, b)
            if ca in corr and cb in corr:
                L.append(compare("%s vs %s" % (ca, cb), corr[ca], corr[cb]))
    L.append("")
    L.append("== weight precision (vs B=8)")
    for m, t in [("lif", "64x10"), ("izh", "64x10"), ("hh", "10")]:
        for bb in (4, 16):
            cb = "%s_%s_b%d" % (m, t, bb)
            ca = "%s_%s" % (m, t)
            if cb in corr:
                L.append(compare("%s vs %s" % (cb, ca), corr[cb], corr[ca]))
    L.append("")
    L.append("== fixed-point (RTL) vs float reference model, same network")
    for c in cfgs:
        f = os.path.join(B, c, "ref_float.txt")
        if os.path.exists(f):
            ks, l2, C = load_counts(f)
            if len(ks) == 1000:
                L.append(compare("%s RTL vs float" % c, corr[c], correct_lowest(lab, C)))
    open(os.path.join(OUT, "stats_mcnemar.txt"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
