#!/usr/bin/env python3
"""Brian2 simulation of exactly the network the RTL runs (software baseline).

Same float weights (x per-layer gain G_l, mV), same pre-encoded spike trains
(data/spikes.npz), same neuron equations and constants as the RTL, but in
floating point, time-driven (Brian2 scheduling), with the analytic HH rates.
Many images are simulated at once (block-diagonal network) for speed.

  python3 tools/brian2_ref.py build/lif_64x10 [--count 1000] [--batch 100]
  -> build/lif_64x10/ref_brian2.txt   (same format as rtl_results.txt)
  python3 tools/score.py build/lif_64x10/rtl_results.txt build/lif_64x10/ref_brian2.txt

V is floored at VMIN_MV (IZH, HH) exactly where the RTL floors it.

Known, intended differences to the RTL (they are what the agreement figure
measures): float vs fixed point, analytic HH rates (on the LUT's clamped
voltage range [-72, 131] mV) vs 1-mV LUT, and Brian2's
schedule (a hidden spike reaches the next layer one Brian2 time step later,
whereas the RTL delivers it within the same time step).
"""
import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.dirname(HERE)


def run_batch(bd, q, Ws, spikes, T=100):
    import brian2 as b2
    b2.prefs.codegen.target = "numpy"
    b2.start_scope()
    c = q["cfg"]
    model = q["model"]
    B = spikes.shape[0]
    n_in = Ws[0].shape[1]
    sizes = [W.shape[0] for W in Ws]
    S = int(c["SUBSTEPS"])
    if model == "lif":
        # V -= V>>>LEAK_SHIFT twice per step  <=>  exponential decay, 1 step = 1 ms
        dt_sub = 1.0 * b2.ms / S
        keep = (1 - 2.0 ** -c["LEAK_SHIFT"]) ** S
        tau = -1.0 / np.log(keep) * b2.ms
        eqs = "dv/dt = -v/tau : volt"
        kw = dict(threshold="v >= %g*mV" % c["THRESH_MV"], reset="v = 0*mV", method="exact")
        ns = dict(tau=tau)
    elif model == "izh":
        dt_sub = 2.0 ** -c["DT_SHIFT"] * b2.ms
        eqs = """dv/dt = (0.04*v**2/mV + 5*v + 140*mV - u)/ms : volt
                 du/dt = a*(b*v - u)/ms : volt"""
        kw = dict(threshold="v >= %g*mV" % c["VPEAK_MV"],
                  reset="v = %g*mV; u += %g*mV" % (c["C_MV"], c["D_MV"]), method="euler")
        ns = dict(a=c["A_Q8"] / 256.0, b=c["B_Q8"] / 256.0)
    else:
        dt_sub = b2.ms / 128.0
        eqs = """dv/dt = -(gK*n**4*(v+12*mV) + gNa*m**3*h*(v-120*mV) + gL*(v-10.5*mV))/(msiemens*ms) : volt
                 dn/dt = alphan*(1-n) - betan*n : 1
                 dm/dt = alpham*(1-m) - betam*m : 1
                 dh/dt = alphah*(1-h) - betah*h : 1
                 vr = clip(v/mV, -72, 131) : 1   # same voltage range as the RTL rate LUTs
                 alphan = 0.1/exprel((10-vr)/10)/ms : Hz
                 betan  = 0.125*exp(-vr/80)/ms : Hz
                 alpham = 1.0/exprel((25-vr)/10)/ms : Hz
                 betam  = 4*exp(-vr/18)/ms : Hz
                 alphah = 0.07*exp(-vr/20)/ms : Hz
                 betah  = 1/(exp((30-vr)/10)+1)/ms : Hz"""
        kw = dict(threshold="v >= %g*mV" % c["UPPER_MV"], refractory="v > %g*mV" % c["LOWER_MV"],
                  method="euler")
        ns = dict(gK=c["GK_Q8"] / 256 * b2.msiemens, gNa=c["GNA_Q8"] / 256 * b2.msiemens,
                  gL=c["GL_Q8"] / 256 * b2.msiemens)
    vmin = c.get("VMIN_MV") if model != "lif" else None
    if vmin is not None:
        ns["vmin"] = vmin * b2.mV
    step = dt_sub * S
    b2.defaultclock.dt = dt_sub

    # inputs: every (image, t, j) spike at t*step, before the dynamics of step t
    ii, tt = [], []
    for k in range(B):
        for t in range(T):
            for j in spikes[k, t]:
                if j == 255:
                    break
                ii.append(k * n_in + int(j))
                tt.append(t)
    inp = b2.SpikeGeneratorGroup(B * n_in, np.array(ii, dtype=int), np.array(tt) * step)
    groups, syns = [], []
    prev, prev_n = inp, n_in
    for l, (W, G) in enumerate(zip(Ws, q["G_layers"])):
        g = b2.NeuronGroup(B * sizes[l], eqs, namespace=ns, **kw)
        if model == "izh":
            g.v = c["C_MV"] * b2.mV
            g.u = c["C_MV"] * c["B_Q8"] / 256.0 * b2.mV
        elif model == "hh":
            g.v = 0 * b2.mV
            vr = 0.0
            an, bn = 0.01 * 10 / (np.exp(1) - 1), 0.125
            am, bm = 0.1 * 25 / (np.exp(2.5) - 1), 4.0
            ah, bh = 0.07, 1 / (np.exp(3) + 1)
            g.n, g.m, g.h = an / (an + bn), am / (am + bm), ah / (ah + bh)
        if vmin is not None:
            # inhibitory floor, as in the RTL: after each sub-step and each synaptic jump
            g.run_regularly("v = clip(v, vmin, 1e6*mV)", when="before_thresholds")
        s = b2.Synapses(prev, g, "w : volt", namespace=ns,
                        on_pre="v_post = clip(v_post + w, vmin, 1e6*mV)" if vmin is not None else "v_post += w")
        src, dst, w = [], [], []
        o, i_ = np.meshgrid(np.arange(sizes[l]), np.arange(prev_n), indexing="ij")
        for k in range(B):
            src.append(k * prev_n + i_.ravel())
            dst.append(k * sizes[l] + o.ravel())
            w.append((W * G).ravel())
        s.connect(i=np.concatenate(src), j=np.concatenate(dst))
        s.w = np.concatenate(w) * b2.mV
        groups.append(g)
        syns.append(s)
        prev, prev_n = g, sizes[l]
    hid = [b2.SpikeMonitor(g) for g in groups[:-1]]
    mon = b2.SpikeMonitor(groups[-1])
    net = b2.Network(inp, *groups, *syns, mon, *hid)
    net.run(T * step)
    n_out = sizes[-1]
    res = []
    it = np.array(mon.i)
    ts = np.floor(np.array(mon.t / step) + 1e-9).astype(int)
    hid_counts = np.zeros(B, dtype=int)
    for l, h in enumerate(hid):
        hid_counts += np.bincount(np.array(h.i) // sizes[l], minlength=B)
    for k in range(B):
        sel = (it // n_out) == k
        out = sorted(zip(ts[sel], it[sel] % n_out))
        res.append((out, int(hid_counts[k])))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    q = json.load(open(os.path.join(a.build_dir, "quant.json")))
    z = np.load(os.path.join(a.build_dir, "weights_float.npz"))
    Ws = [z["arr_%d" % i] for i in range(len(z.files))]
    dd = os.environ.get("HASTE_DATA", "data")
    d = np.load(os.path.join(dd if os.path.isabs(dd) else os.path.join(V4, dd), "spikes.npz"))
    sp, labels = d["spikes"], d["labels"]
    if os.environ.get("HASTE_T"):
        sp = sp[:, :int(os.environ["HASTE_T"])]
    outp = a.out or os.path.join(a.build_dir, "ref_brian2.txt")
    end = min(a.start + a.count, len(labels))
    with open(outp, "w") as f:
        for s0 in range(a.start, end, a.batch):
            s1 = min(s0 + a.batch, end)
            res = run_batch(a.build_dir, q, Ws, sp[s0:s1], T=sp.shape[1])
            for k, (out, hid) in zip(range(s0, s1), res):
                cnt = np.zeros(Ws[-1].shape[0], dtype=int)
                for _, cl in out:
                    cnt[cl] += 1
                f.write("IMG %d LABEL %d HID %d OVF 0 COUNTS %s\n" % (k, labels[k], hid, " ".join(map(str, cnt))))
                for t, cl in out:
                    f.write("SPK %d %d %d\n" % (k, t, cl))
            f.flush()
            print("brian2: images %d..%d done" % (s0, s1 - 1), flush=True)
    print("wrote", outp)


if __name__ == "__main__":
    main()
