#!/usr/bin/env python3
"""Extend the G grid where hh_failure picked an edge value (14 or 112): keep
stepping x2 outward on data_val until val accuracy stops improving, then re-test
on the 1000 test images if a new G wins. Appends to results/hh_failure_ext.jsonl."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import hh_failure as H


def main():
    fn = os.path.join(H.OUT, "hh_failure.jsonl")
    recs = {json.loads(l)["key"]: json.loads(l) for l in open(fn)}
    out = os.path.join(H.OUT, "hh_failure_ext.jsonl")
    done = {json.loads(l)["key"] for l in open(out)} if os.path.exists(out) else set()
    for v in H.variants():
        k = "%s|%s" % (v["name"], v["topo"]); r = recs[k]
        if k in done or r["G_best"] not in (14.0, 112.0):
            continue
        f = 0.5 if r["G_best"] == 14.0 else 2.0
        val = {float(g): a for g, a in r["val"].items()}
        best_g, best_a, g = r["G_best"], max(val.values()), r["G_best"]
        while True:
            g *= f
            a = H.evaluate(v, g, "data_val", 300)["acc"]; val[g] = a
            print(k, "G=%g val=%.1f" % (g, a), flush=True)
            if a <= best_a:
                break
            best_g, best_a = g, a
        te = r["test"] if best_g == r["G_best"] else H.evaluate(v, best_g, "data", 1000)
        rec = dict(r, G_best=best_g, val={str(x): y for x, y in sorted(val.items())}, test=te, extended=True)
        open(out, "a").write(json.dumps(rec) + "\n")
        print("%s G=%g val=%.1f test=%.1f" % (k, best_g, best_a, te["acc"]), flush=True)


if __name__ == "__main__":
    main()
