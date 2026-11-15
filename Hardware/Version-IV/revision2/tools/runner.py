#!/usr/bin/env python3
"""Instrumented runs of the bit-exact / float reference model (revision 2).

INet extends tools/ref_model.Net (unchanged) with event counters, so one run
yields accuracy, per-layer firing, and the event counts that determine the
hardware cycle count:
  n_ops    operations issued (1 CLEAR + one AXON per input spike + T STEP)
  visits   neuron integrations in sweeps (layer size per AXON / FIFO pop)
  sweeps   number of sweeps (= input spikes + hidden spikes)
  subs     integration sub-steps (S * T)
  upd      neuron updates in sub-steps (N_NEU * S * T)

Usable as a library (build(), run()) or CLI:
  runner.py BUILD_DIR [--data data] [--count N] [--mode fixed|float] [--out file.json]
"""
import argparse
import json
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.dirname(HERE)
V4 = os.path.dirname(R2)
sys.path.insert(0, os.path.join(V4, "tools"))
import ref_model as rm  # noqa: E402


class INet(rm.Net):
    def run_image(self, rows):
        self.c_vis = self.c_sw = 0
        self.lspk = np.zeros(self.L, dtype=np.int64)
        self.nspk = np.zeros(self.N, dtype=np.int64)
        self.n_in = int(sum(int(np.sum(r != 255)) for r in rows))
        out, hid, ovf = super().run_image(rows)
        return out, hid, ovf

    def _sweep(self, l, s):
        self.c_vis += self.ends[l] - self.starts[l] + 1
        self.c_sw += 1
        super()._sweep(l, s)

    def _emit(self, idx, sp, l):
        self.lspk[l] += int(np.sum(sp))
        self.nspk[idx[sp]] += 1
        super()._emit(idx, sp, l)


_G = {}


def _init(bd, mode, data, T, cls):
    _G["net"] = cls(bd, mode)
    sp = np.load(os.path.join(data, "spikes.npz"))["spikes"]
    _G["sp"] = sp[:, :T] if T else sp


def _work(k):
    net = _G["net"]
    rows = _G["sp"][k]
    out, hid, ovf = net.run_image(rows)
    T = len(rows)
    counts = rm.predict(out, net.ends[-1] - net.starts[-1] + 1)
    return dict(k=int(k), counts=counts.tolist(), hid=int(hid), ovf=int(ovf), lspk=net.lspk.tolist(),
                n_in=net.n_in, n_ops=1 + net.n_in + T, visits=int(net.c_vis), sweeps=int(net.c_sw),
                subs=net.S * T, upd=net.N * net.S * T, n_neu=net.N, nspk=net.nspk.tolist(),
                starts=list(net.starts), ends=list(net.ends))


def data_path(data):
    return data if os.path.isabs(data) else os.path.join(V4, data)


def run(bd, data="data", count=1000, mode="fixed", T=None, jobs=None, cls=INet, start=0):
    dp = data_path(data)
    lab = np.load(os.path.join(dp, "spikes.npz"))["labels"]
    ks = list(range(start, min(start + count, len(lab))))
    with Pool(jobs or os.cpu_count(), initializer=_init, initargs=(bd, mode, dp, T, cls)) as p:
        res = p.map(_work, ks, chunksize=1)
    for r in res:
        r["label"] = int(lab[r["k"]])
    return res


def summarize(res):
    lab = np.array([r["label"] for r in res])
    C = np.array([r["counts"] for r in res])
    nos = C.sum(1) == 0
    top = C.max(1, keepdims=True)
    tie = ((C == top).sum(1) > 1) & ~nos
    corr = (C.argmax(1) == lab) & ~nos
    lspk = np.array([r["lspk"] for r in res])
    out = dict(n=len(res), acc=100 * corr.mean(), ties=int(tie.sum()), nospike=int(nos.sum()),
               spk_per_layer=lspk.mean(0).round(1).tolist(), correct=corr.astype(int).tolist())
    if "nspk" in res[0]:
        # spikes per neuron per time step (T = n_ops - 1 - n_in), mean over images;
        # 10/50/90th percentiles over the neurons of each layer
        T = res[0]["n_ops"] - 1 - res[0]["n_in"]
        rate = np.array([r["nspk"] for r in res], float).mean(0) / T
        out["rate_per_neuron"] = rate.round(4).tolist()
        out["rate_pct"] = [np.percentile(rate[s:e + 1], [10, 50, 90]).round(4).tolist()
                           for s, e in zip(res[0]["starts"], res[0]["ends"])]
    return out


def build(model, Ws_or_topo, out_dir, overrides=None):
    """Write a build directory with tools/gen_mem.py (library call, no edits)."""
    sys.path.insert(0, os.path.join(V4, "tools"))
    import gen_mem
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        if isinstance(Ws_or_topo, str):
            ov = dict(gen_mem.TOPO_OVERRIDES.get((model, Ws_or_topo), {}))
            ov.update(overrides or {})
            gen_mem.write_net_from_weights(model, gen_mem.load_weights(Ws_or_topo), out_dir, ov, Ws_or_topo)
        else:
            gen_mem.write_net_from_weights(model, Ws_or_topo, out_dir, overrides or {}, "custom")
    return out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir")
    ap.add_argument("--data", default="data")
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--mode", default="fixed")
    ap.add_argument("--T", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(a.build_dir, a.data, a.count, a.mode, a.T)
    s = summarize(res)
    print({k: v for k, v in s.items() if k != "correct"})
    if a.out:
        json.dump(res, open(a.out, "w"))


if __name__ == "__main__":
    main()
