#!/usr/bin/env python3
"""Tables from results/sweep_*.jsonl: accuracy, ties, latency per point, and an
exact McNemar test of each point against the paper's operating point (same
model and topology), on the same 1000 test images.
Writes results/sweeps_summary.txt."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stats import mcnemar_exact  # noqa: E402

R = os.path.join(os.path.dirname(HERE), "results")
PAPER = {"lif": dict(SUBSTEPS=2), "izh": dict(SUBSTEPS=32, DT_SHIFT=7), "hh": dict(SUBSTEPS=300)}
NAMES = {"lif_sub": "LIF: sub-steps at equal leak per step",
         "izh_dt": "IZH: dt sweep at 0.25 ms model time per step",
         "izh_tau": "IZH: model time per step (dt = 1/128 ms)",
         "hh_tau": "HH fixed point: sub-steps per step (dt = 1/128 ms)",
         "hh_dt": "HH float model, hh_10: dt sweep at ~2.34 ms per step"}


def model_time(m, s):
    if m == "izh":
        return s["SUBSTEPS"] * 2.0 ** -s["DT_SHIFT"]
    if m == "hh":
        return s["SUBSTEPS"] * s.get("FLOAT_DT_MS", 1 / 128)
    return None


def main():
    L = []
    for name in ["lif_sub", "izh_dt", "izh_tau", "hh_tau", "hh_dt"]:
        fn = os.path.join(R, "sweep_%s.jsonl" % name)
        if not os.path.exists(fn):
            continue
        recs = [json.loads(l) for l in open(fn)]
        L += ["", "== " + NAMES[name],
              "%-9s %-28s %6s %5s %6s %10s %6s  %s" % ("topo", "setting", "G", "acc", "ties", "ms@50MHz", "t/step",
                                                      "vs paper point (b, c, p)")]
        for topo in ["10", "64x10", "64x64x10"]:
            rs = [r for r in recs if r["topo"] == topo]
            if not rs:
                continue
            ref = [r for r in rs if all(r["set"].get(k) == v for k, v in PAPER[r["model"]].items())
                   and "FLOAT_DT_MS" not in r["set"] or r["set"].get("FLOAT_DT_MS") == 1 / 128]
            ref = ref[0] if ref else None
            for r in rs:
                c = np.array(r["test"]["correct"], bool)
                cmp = ""
                if ref is not None and r is not ref:
                    c0 = np.array(ref["test"]["correct"], bool)
                    b, cc = int(np.sum(c & ~c0)), int(np.sum(~c & c0))
                    cmp = "b=%d c=%d p=%.3g" % (b, cc, mcnemar_exact(b, cc))
                elif r is ref:
                    cmp = "(paper setting)"
                mt = model_time(r["model"], r["set"])
                st = " ".join("%s=%s" % (k, ("%.4g" % v) if isinstance(v, float) else v) for k, v in r["set"].items())
                L.append("%-9s %-28s %6g %5.1f %6d %10.2f %6s  %s" % (
                    topo, st, r["G_best"], r["test"]["acc"], r["test"]["ties"], r["test"]["ms_50MHz"],
                    ("%.3g" % mt) if mt else "-", cmp))
    txt = "\n".join(L[1:])
    open(os.path.join(R, "sweeps_summary.txt"), "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
