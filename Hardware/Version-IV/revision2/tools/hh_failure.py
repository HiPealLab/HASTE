#!/usr/bin/env python3
"""Why do multi-layer HH networks fail?

Candidate causes, each tested in isolation in the float model (same event
schedule, same detector, same T, gain G_SCALE re-tuned on data_val):
  hh        baseline: HH, delta (voltage-jump) synapses, weight-max normalisation
  hh_cur    HH with current-based exponential synapses (tau_s = 2 ms, same charge)
  wb        class-I conductance neuron (Wang & Buzsaki 1996), delta synapses
  wb_cur    class-I neuron + current-based synapses
  hh_data   HH with data-based normalisation (Diehl et al. 2015: layer l scaled by
            lambda_{l-1}/lambda_l, lambda = 99.9th pct ReLU activation on training images)
Fixed-point truncation is excluded separately: the float HH model fails equally
(build/hh_64x10 ref_float 30.2 % vs RTL 30.4 %).
Also: single-neuron transfer curves (output rate vs Poisson input rate) for
LIF / IZH / HH / WB with the network's jump size (fI).

  hh_failure.py nets      -> results/hh_failure.jsonl
  hh_failure.py fI        -> results/hh_fI.txt
"""
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import runner  # noqa: E402
import sweep_dt  # noqa: E402

OUT = os.path.join(runner.R2, "results")
TAU_S = 2.0  # ms, synaptic current time constant
DT = 1.0 / 128.0

# Wang-Buzsaki (1996), voltages absolute (mV); the network uses V relative to rest
WB = dict(gNa=35.0, ENa=55.0, gK=9.0, EK=-90.0, gL=0.1, EL=-65.0, phi=5.0)


def wb_rates(V):
    am = 0.1 * (V + 35) / (1 - np.exp(-(V + 35) / 10))
    bm = 4 * np.exp(-(V + 60) / 18)
    ah = 0.07 * np.exp(-(V + 58) / 20)
    bh = 1 / (1 + np.exp(-(V + 28) / 10))
    an = 0.01 * (V + 34) / (1 - np.exp(-(V + 34) / 10))
    bn = 0.125 * np.exp(-(V + 44) / 80)
    return am, bm, ah, bh, an, bn


def wb_rest():
    V, h, n = -65.0, 0.6, 0.3
    for _ in range(200000):
        am, bm, ah, bh, an, bn = wb_rates(V)
        m = am / (am + bm)
        I = WB["gNa"] * m ** 3 * h * (V - WB["ENa"]) + WB["gK"] * n ** 4 * (V - WB["EK"]) + WB["gL"] * (V - WB["EL"])
        h += 0.01 * WB["phi"] * (ah * (1 - h) - bh * h)
        n += 0.01 * WB["phi"] * (an * (1 - n) - bn * n)
        V -= 0.01 * I
    return V, h, n


WB_REST = wb_rest()


class VarNet(sweep_dt.FloatDtNet):
    """float network with VARIANT in cfg: hh | hh_cur | wb | wb_cur"""

    def clear(self):
        super().clear()
        var = self.cfg.get("VARIANT", "hh")
        if var.startswith("wb"):
            _, h0, n0 = WB_REST
            self.h = np.full(self.N, h0)
            self.n = np.full(self.N, n0)
        self.isyn = np.zeros(self.N)

    def _integrate(self, idx, s, l):
        var = self.cfg.get("VARIANT", "hh")
        if var.endswith("_cur"):
            # same total charge as a jump of Wf mV: I += J / tau_s (mV/ms)
            self.isyn[idx] += self.Wf[idx, s] / TAU_S
            return np.zeros(len(idx), dtype=bool)
        return super()._integrate(idx, s, l)

    def _dynamics(self):
        var = self.cfg.get("VARIANT", "hh")
        cur = var.endswith("_cur")
        if var.startswith("wb"):
            V0 = WB_REST[0]
            Va = self.v + V0
            am, bm, ah, bh, an, bn = wb_rates(Va)
            m = am / (am + bm)
            I = WB["gNa"] * m ** 3 * self.h * (Va - WB["ENa"]) + WB["gK"] * self.n ** 4 * (Va - WB["EK"]) + \
                WB["gL"] * (Va - WB["EL"])
            self.h = self.h + DT * WB["phi"] * (ah * (1 - self.h) - bh * self.h)
            self.n = self.n + DT * WB["phi"] * (an * (1 - self.n) - bn * self.n)
            vn = self.v - DT * I
            if cur:
                vn = vn + DT * self.isyn
                self.isyn *= np.exp(-DT / TAU_S)
            return self._hh_spike(np.arange(self.N), vn)
        if cur:
            # HH float update (parent) plus the synaptic current
            self.v = self.v + DT * self.isyn
            self.isyn *= np.exp(-DT / TAU_S)
        return super()._dynamics()


def data_norm_weights(topo):
    """Diehl et al. (2015) data-based normalisation on 2000 MNIST training images."""
    import gen_ann
    import gen_mem
    Ws = gen_mem.load_weights(topo)
    X = gen_ann.calib_inputs()
    h, lam_prev, out = X, 1.0, []
    for l, W in enumerate(Ws):
        h = h @ W.T
        if l < len(Ws) - 1:
            h = np.maximum(h, 0)
        lam = float(np.percentile(h[h > 0], 99.9))
        out.append(W * lam_prev / lam)
        lam_prev = lam
    return out


def variants():
    V = []
    hh_det = dict(UPPER_MV=80, LOWER_MV=0, VMIN_MV=-72)
    wb_det = dict(UPPER_MV=60, LOWER_MV=10, VMIN_MV=-25)  # WB spike peaks ~95 mV above rest; floor = E_K
    for topo in ["10", "64x10", "64x64x10"]:
        for var, det in [("hh", hh_det), ("hh_cur", hh_det), ("wb", wb_det), ("wb_cur", wb_det)]:
            V.append(dict(name=var, topo=topo, set=dict(det, VARIANT=var, SUBSTEPS=300, NORM="layer"),
                          G=[14.0, 28.0, 56.0, 112.0]))
        V.append(dict(name="hh_data", topo=topo, set=dict(hh_det, VARIANT="hh", SUBSTEPS=300, NORM="global"),
                      G=[14.0, 28.0, 56.0, 112.0], data_norm=True))
    return V


def evaluate(v, g, data, count):
    d = tempfile.mkdtemp(prefix="r2hh_")
    s = dict(v["set"], G_SCALE=g)
    src = data_norm_weights(v["topo"]) if v.get("data_norm") else v["topo"]
    runner.build("hh", src, d, s)
    res = runner.run(d, data, count, "float", cls=VarNet)
    return runner.summarize(res)


def nets():
    fn = os.path.join(OUT, "hh_failure.jsonl")
    done = {json.loads(l)["key"] for l in open(fn)} if os.path.exists(fn) else set()
    for v in variants():
        k = "%s|%s" % (v["name"], v["topo"])
        if k in done:
            continue
        val = [(evaluate(v, g, "data_val", 300)["acc"], g) for g in v["G"]]
        best = max(val)[1]
        te = evaluate(v, best, "data", 1000)
        rec = dict(key=k, variant=v["name"], topo=v["topo"], G_best=best, val={str(g): a for a, g in val}, test=te)
        open(fn, "a").write(json.dumps(rec) + "\n")
        print("%-8s %-9s G=%g val=%.1f test=%.1f ties=%d spk/layer=%s" % (
            v["name"], v["topo"], best, max(val)[0], te["acc"], te["ties"], te["spk_per_layer"]), flush=True)


def fI():
    """one neuron, Poisson input with fixed jump J mV (J = G_SCALE*0.5, a typical
    weight), input rate r spikes/step; output spikes/step over 200 steps."""
    rng = np.random.default_rng(0)
    lines = ["# single-neuron transfer curve: output spikes per step vs input spikes per step",
             "# jump J = 14 mV (half the largest jump, G_SCALE=28), T = 200 steps, float models"]
    rates = [0.25, 0.5, 1, 2, 4, 8, 16]
    import gen_mem
    for model, var in [("lif", None), ("izh", None), ("hh", "hh"), ("hh", "wb"), ("hh", "hh_cur"), ("hh", "wb_cur")]:
        d = tempfile.mkdtemp(prefix="r2fi_")
        s = {}
        if var:
            det = dict(UPPER_MV=60, LOWER_MV=10, VMIN_MV=-25) if var.startswith("wb") else {}
            s = dict(det, VARIANT=var)
        Ws = [np.ones((1, 64))]
        with open(os.devnull, "w") as dn:
            old = sys.stdout
            sys.stdout = dn
            gen_mem.write_net_from_weights(model, Ws, d, dict(s, G_SCALE=14.0, NORM="global"), "fI")
            sys.stdout = old
        row = []
        for r in rates:
            net = VarNet(d, "float")
            rows = np.full((200, 64), 255, dtype=np.int64)
            for t in range(200):
                k = min(64, rng.poisson(r))
                rows[t, :k] = rng.integers(64, size=k)
            net.run_image(rows)
            row.append(len(net.out) / 200)
        lines.append("%-8s " % (var or model) + " ".join("r=%g:%.2f" % (r, o) for r, o in zip(rates, row)))
        print(lines[-1], flush=True)
    open(os.path.join(OUT, "hh_fI.txt"), "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    {"nets": nets, "fI": fI}[sys.argv[1]]()
