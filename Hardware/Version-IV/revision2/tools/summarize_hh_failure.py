#!/usr/bin/env python3
"""Table from results/hh_failure.jsonl with exact McNemar of each variant vs the
hh baseline (same topology, same 1000 test images). Writes results/hh_failure_summary.txt."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from stats import mcnemar_exact
R = os.path.join(os.path.dirname(HERE), "results")
recs = {json.loads(l)["key"]: json.loads(l) for l in open(os.path.join(R, "hh_failure.jsonl"))}
ext = os.path.join(R, "hh_failure_ext.jsonl")  # grid extended where G was at an edge
if os.path.exists(ext):
    recs.update({json.loads(l)["key"]: json.loads(l) for l in open(ext)})
recs = list(recs.values())
L = ["%-8s %-9s %5s %5s %5s %6s  %-26s %s" % ("variant", "topo", "G", "val", "test", "ties", "vs hh (b, c, p)", "spikes/layer/image")]
for topo in ["10", "64x10", "64x64x10"]:
    rs = [r for r in recs if r["topo"] == topo]
    c0 = np.array([r for r in rs if r["variant"] == "hh"][0]["test"]["correct"], bool)
    for r in rs:
        c = np.array(r["test"]["correct"], bool)
        b, cc = int(np.sum(c & ~c0)), int(np.sum(~c & c0))
        cmp = "(baseline)" if r["variant"] == "hh" else "b=%d c=%d p=%.2g" % (b, cc, mcnemar_exact(b, cc))
        edge = "+" if r.get("extended") else " "
        L.append("%-8s %-9s %4g%s %5.1f %5.1f %6d  %-26s %s" % (r["variant"], topo, r["G_best"], edge,
                 max(r["val"].values()), r["test"]["acc"], r["test"]["ties"], cmp,
                 " ".join("%.0f" % x for x in r["test"]["spk_per_layer"])))
L.append("+ grid {14,28,56,112} extended x2 outward until val accuracy stopped improving (hh_failure_ext.py)")
txt = "\n".join(L); open(os.path.join(R, "hh_failure_summary.txt"), "w").write(txt + "\n"); print(txt)
