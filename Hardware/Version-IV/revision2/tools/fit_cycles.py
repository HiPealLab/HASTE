#!/usr/bin/env python3
"""Closed-form cycle model of the three cores, fitted to the RTL cycle counts.

cycles(image) = c_op*n_ops + c_vis*visits + c_sw*sweeps + c_sub*subs + c_upd*upd + c_clr*N_NEU
(features from runner.INet on the same encoding as build/*/rtl_results.txt).
Writes revision2/results/cycle_model.txt and cycle_model.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import runner  # noqa: E402

R2 = runner.R2
V4 = runner.V4
FEAT = ["n_ops", "visits", "sweeps", "subs", "upd", "n_neu"]


def rtl_cycles(fn):
    cyc = {}
    for line in open(fn):
        if line.startswith("IMG"):
            p = line.split()
            cyc[int(p[1])] = int(p[p.index("CYCLES") + 1])
    return cyc


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    B = os.path.join(V4, "build")
    cfgs = {"lif": ["lif_10", "lif_64x10", "lif_64x64x10"],
            "izh": ["izh_10", "izh_64x10", "izh_64x64x10"],
            "hh": ["hh_10", "hh_64x10", "hh_64x64x10"]}
    out, model = [], {}
    for m, cs in cfgs.items():
        X, y, tag = [], [], []
        for c in cs:
            cnt = n if m != "hh" else min(n, 48)
            res = runner.run(os.path.join(B, c), "data", cnt)
            cyc = rtl_cycles(os.path.join(B, c, "rtl_results.txt"))
            for r in res:
                X.append([r[f] for f in FEAT])
                y.append(cyc[r["k"]])
                tag.append(c)
        X, y = np.array(X, float), np.array(y, float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        rc = np.round(coef, 3)
        pred = X @ coef
        err = (pred - y) / y
        model[m] = dict(zip(FEAT, coef.tolist()))
        out.append("%s: %s" % (m, "  ".join("%s=%.3f" % (f, c) for f, c in zip(FEAT, rc))))
        for c in cs:
            mk = np.array(tag) == c
            out.append("   %-14s n=%3d  max|err|=%.3f%%  mean err=%+.4f%%" % (
                c, mk.sum(), 100 * np.abs(err[mk]).max(), 100 * err[mk].mean()))
    txt = "\n".join(out)
    print(txt)
    open(os.path.join(R2, "results", "cycle_model.txt"), "w").write(txt + "\n")
    json.dump(model, open(os.path.join(R2, "results", "cycle_model.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
