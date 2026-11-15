#!/usr/bin/env python3
"""Integration-step / sub-step sweeps.

For every point: G_SCALE is chosen on the tuning set data_val (300 MNIST
training images) from a small grid, then the point is evaluated once on the
1000 test images.  Latency = exact cycle formula (check_cycles.py, verified
against the RTL) / 50 MHz.  Results are appended to results/<name>.jsonl and
the script resumes where it stopped.

  sweep_dt.py izh_dt   IZH: fixed model time per step 0.25 ms, dt = 2^-4..2^-8 ms
  sweep_dt.py izh_tau  IZH: dt = 1/128 ms, model time per step 0.0625..1 ms
  sweep_dt.py hh_tau   HH (fixed point, dt = 1/128 ms): sub-steps 16..300
  sweep_dt.py hh_dt    HH float model: dt = 1/128..1/16 ms at ~2.34 ms per step
  sweep_dt.py lif_sub  LIF: 1, 2, 4 sub-steps at equal leak per time step
"""
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import runner  # noqa: E402
import check_cycles  # noqa: E402

OUT = os.path.join(runner.R2, "results")


class FloatDtNet(runner.INet):
    """float HH with a configurable Euler step (cfg FLOAT_DT_MS), otherwise
    identical to ref_model.Net float mode."""

    def _dynamics(self):
        if not (self.model == "hh" and self.mode == "float"):
            return super()._dynamics()
        c = self.cfg
        dt = float(c.get("FLOAT_DT_MS", 1.0 / 128.0))
        V = self.v
        an = np.where(np.abs(10 - V) < 1e-7, 0.1, 0.01 * (10 - V) / np.expm1((10 - V) / 10))
        bn = 0.125 * np.exp(-V / 80)
        am = np.where(np.abs(25 - V) < 1e-7, 1.0, 0.1 * (25 - V) / np.expm1((25 - V) / 10))
        bm = 4 * np.exp(-V / 18)
        ah = 0.07 * np.exp(-V / 20)
        bh = 1 / (np.exp((30 - V) / 10) + 1)
        n, m, h = self.n, self.m, self.h
        gk, gna, gl = c["GK_Q8"] / 256, c["GNA_Q8"] / 256, c["GL_Q8"] / 256
        I = gk * n ** 4 * (V + 12) + gna * m ** 3 * h * (V - 120) + gl * (V - 10.5)
        self.n = n + dt * (an * (1 - n) - bn * n)
        self.m = m + dt * (am * (1 - m) - bm * m)
        self.h = h + dt * (ah * (1 - h) - bh * h)
        vn = V - dt * I
        return self._hh_spike(np.arange(self.N), vn)


def points(name):
    P = []
    if name == "izh_dt":
        for topo in ["10", "64x10", "64x64x10"]:
            for S, D in [(4, 4), (8, 5), (16, 6), (32, 7), (64, 8)]:
                P.append(dict(model="izh", topo=topo, set=dict(SUBSTEPS=S, DT_SHIFT=D),
                              G=[14.0, 20.0, 28.0, 40.0, 56.0]))
    elif name == "izh_tau":
        for topo in ["10", "64x10", "64x64x10"]:
            for S in [8, 16, 32, 64, 128]:
                P.append(dict(model="izh", topo=topo, set=dict(SUBSTEPS=S, DT_SHIFT=7),
                              G=[14.0, 20.0, 28.0, 40.0, 56.0]))
    elif name == "hh_tau":
        for topo in ["10", "64x10", "64x64x10"]:
            for S in [16, 32, 64, 128, 300]:
                P.append(dict(model="hh", topo=topo, set=dict(SUBSTEPS=S),
                              G=[20.0, 28.0, 40.0, 56.0, 80.0]))
    elif name == "hh_dt":
        for k, S in [(128, 300), (64, 150), (32, 75), (16, 38)]:
            P.append(dict(model="hh", topo="10", set=dict(SUBSTEPS=S, FLOAT_DT_MS=1.0 / k), mode="float",
                          G=[20.0, 28.0, 40.0]))
    elif name == "lif_sub":
        for topo in ["10", "64x10", "64x64x10"]:
            for S, L in [(1, 5), (2, 6), (4, 7)]:
                P.append(dict(model="lif", topo=topo, set=dict(SUBSTEPS=S, LEAK_SHIFT=L),
                              G=[20.0, 28.0, 40.0]))
    else:
        raise SystemExit("unknown sweep " + name)
    return P


def key(p):
    return json.dumps([p["model"], p["topo"], p["set"], p.get("mode", "fixed")], sort_keys=True)


def evaluate(p, g, data, count):
    d = tempfile.mkdtemp(prefix="r2_")
    s = dict(p["set"])
    s["G_SCALE"] = g
    runner.build(p["model"], p["topo"], d, s)
    res = runner.run(d, data, count, p.get("mode", "fixed"), cls=FloatDtNet)
    sm = runner.summarize(res)
    cyc = np.array([check_cycles.cycles(r, p["model"]) for r in res])
    sm["cycles"] = float(cyc.mean())
    sm["ms_50MHz"] = float(cyc.mean() / 50e3)
    return sm


def main():
    name = sys.argv[1]
    fn = os.path.join(OUT, "sweep_%s.jsonl" % name)
    done = set()
    if os.path.exists(fn):
        done = {json.loads(l)["key"] for l in open(fn)}
    for p in points(name):
        k = key(p)
        if k in done:
            continue
        val = []
        for g in p["G"]:
            sm = evaluate(p, g, "data_val", 300)
            val.append((sm["acc"], -abs(g - 28.0), g, sm["acc"]))
        best = max(val)[2]
        te = evaluate(p, best, "data", 1000)
        rec = dict(key=k, model=p["model"], topo=p["topo"], set=p["set"], mode=p.get("mode", "fixed"),
                   val={str(v[2]): v[3] for v in val}, G_best=best, test=te)
        with open(fn, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print("%s %s %s G=%g val=%.1f test acc=%.1f ties=%d ms=%.2f" % (
            p["model"], p["topo"], p["set"], best, max(val)[0], te["acc"], te["ties"], te["ms_50MHz"]), flush=True)


if __name__ == "__main__":
    main()
