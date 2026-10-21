#!/usr/bin/env python3
"""Reference models for the HASTE Version-IV RTL.

* mode "fixed": bit-exact integer model of rtl/snn_{lif,izh,hh}.sv (same
  event order, same FIFO order, same truncations/wrap-arounds).  RTL output
  must match it spike-for-spike.
* mode "float": the same network and event schedule in float64 with the
  unquantised weights and ideal arithmetic (HH uses the analytic 1952
  alpha/beta functions).  Used to quantify quantisation / fixed-point effects
  (hardware-vs-software agreement).
* mode "v2compat": re-implementation of the *original* Version-II LIF
  behaviour (leak applied only to neurons 0..9, original weights), used to
  prove the model reproduces Version-II/LIF/res/LIF_Results.txt.

Event schedule (identical in RTL):
  per image: CLEAR; for t in 0..T-1: AXON(j) for each input spike j of step t
  (in file order), then STEP.
  AXON(j): sweep layer 0 with fan-in slot j, then drain the spike FIFO.
  sweep(l, s): for every neuron i of layer l in index order: integrate
      weight W[i, s]; spiking neurons are pushed to the FIFO (hidden layers)
      or emitted as outputs (last layer).
  drain: pop n (FIFO order), sweep(layer(n)+1, n-start(layer(n))).
  STEP: SUBSTEPS times { update dynamics of all neurons in index order,
      pushing/emitting spikes, then drain }.
"""
import argparse
import json
import math
import os
import sys
from collections import deque
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.dirname(HERE)
FIFO_DEPTH = 256


def _data_dir():
    d = os.environ.get("HASTE_DATA", "data")
    return d if os.path.isabs(d) else os.path.join(V4, d)


def wrap32(x):
    return ((x + (1 << 31)) & 0xFFFFFFFF) - (1 << 31)


def s16(x):
    return ((x + 32768) & 0xFFFF) - 32768


def absu16(x):
    """two's-complement magnitude of a signed 16-bit value, as unsigned 16."""
    return np.where(x < 0, (-x) & 0xFFFF, x & 0xFFFF)


def hh_gate_update(g, a, b):
    """ngvUnit: g' = g + alpha/2 - sat(|g|*(a+b) >> 15) (sign restored)."""
    g = np.asarray(g, dtype=np.int64)
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    ab = (a + b) & 0xFFFF
    alpha = s16(a) >> 1
    A = absu16(g)
    t = ((A * ab) >> 15) & 0xFFFF
    t = np.where(t & 0x8000, 0x7FFF, t)
    res = np.where(g < 0, s16(-t), t)
    return s16(alpha - res + g)


def hh_vdf(vk, g1, g2, G):
    """vdfmult: |V|*g1^3*G*g2 with the original bit slices, sign restored."""
    sgn = (vk < 0) ^ (g1 < 0) ^ (g2 < 0)
    a, b, c = absu16(vk), absu16(g1), absu16(g2)
    d = absu16(np.asarray(G, dtype=np.int64))
    t = ((a * b) >> 13) & 0xFFFF
    t = ((t * b) >> 14) & 0xFFFF
    t = ((t * d) >> 15) & 0xFFFF
    t = ((t * b) >> 14) & 0xFFFF
    t = ((t * c) >> 15) & 0xFFFF
    t = np.where(t & 0x8000, 0x7FFF, t)
    return np.where(sgn, s16(-t), t)


class Net:
    def __init__(self, build_dir, mode="fixed", v2_weights=None):
        q = json.load(open(os.path.join(build_dir, "quant.json")))
        self.q = q
        self.model = q["model"]
        self.mode = mode
        self.cfg = q["cfg"]
        self.S = int(self.cfg["SUBSTEPS"])
        self.starts, self.ends = q["starts"], q["ends"]
        self.L = len(self.starts)
        self.N = q["n_neu"]
        self.fanin = q["fanin"]
        self.gains = q["gains_q24"]
        self.wb = int(q.get("weight_bits", 8))
        # synMem
        rows = []
        for line in open(os.path.join(build_dir, "syn.mem")):
            if line.startswith("//") or not line.strip():
                continue
            rows.append([int(x, 16) for x in line.split()])
        W = np.array(rows, dtype=np.int64)
        W = np.where(W >= (1 << (self.wb - 1)), W - (1 << self.wb), W)
        self.Wq = W
        if mode == "float":
            z = np.load(os.path.join(build_dir, "weights_float.npz"))
            Ws = [z["arr_%d" % i] for i in range(len(z.files))]
            Wf = np.zeros(W.shape)
            r = 0
            for Wl, G in zip(Ws, q["G_layers"]):
                Wf[r:r + Wl.shape[0], :Wl.shape[1]] = Wl * G  # mV per spike
                r += Wl.shape[0]
            self.Wf = Wf
        if self.model == "hh":
            self.luts = {}
            for n in ["an", "bn", "am", "bm", "ah", "bh"]:
                self.luts[n] = np.array([int(l, 16) for l in open(os.path.join(build_dir, "lut_%s.mem" % n))
                                         if l.strip()], dtype=np.int64)
        if mode == "v2compat":
            assert self.model == "lif"
            self.Wq = v2_weights
            self.gains = [4096 << 8] * self.L
        # inhibitory floor on V (absent in old builds -> no floor)
        vmin = self.cfg.get("VMIN_MV")
        if vmin is None or self.model == "lif":
            self.vmin = None
        elif mode == "float":
            self.vmin = float(vmin)
        else:
            self.vmin = int(round(vmin * (65536 if self.model == "izh" else 128)))
        self.layer_of = np.zeros(self.N, dtype=np.int64)
        for l, (s, e) in enumerate(zip(self.starts, self.ends)):
            self.layer_of[s:e + 1] = l

    # ------------------------------------------------------------------ state
    def clear(self):
        N, c = self.N, self.cfg
        f = self.mode == "float"
        if self.model == "lif":
            self.v = np.zeros(N) if f else np.zeros(N, dtype=np.int64)
            self.r = np.zeros(N, dtype=np.int64)
        elif self.model == "izh":
            if f:
                self.v = np.full(N, float(c["C_MV"]))
                self.u = self.v * c["B_Q8"] / 256.0
            else:
                self.v = np.full(N, int(round(c["C_MV"] * 65536)), dtype=np.int64)
                self.u = np.full(N, int(c["U_INIT"]), dtype=np.int64)
        else:
            if f:
                self.v = np.zeros(N)
                self.n = np.full(N, c["N_INIT"] / 16384.0)
                self.m = np.full(N, c["M_INIT"] / 16384.0)
                self.h = np.full(N, c["H_INIT"] / 16384.0)
            else:
                self.v = np.zeros(N, dtype=np.int64)
                self.n = np.full(N, c["N_INIT"], dtype=np.int64)
                self.m = np.full(N, c["M_INIT"], dtype=np.int64)
                self.h = np.full(N, c["H_INIT"], dtype=np.int64)
            self.spk = np.zeros(N, dtype=bool)

    def _floor(self, v):
        return v if self.vmin is None else np.maximum(v, self.vmin)

    # ----------------------------------------------------------- integrate
    def _integrate(self, idx, s, l):
        """add synaptic input of slot s to neurons idx (layer l); return spike mask."""
        c = self.cfg
        f = self.mode == "float"
        if f:
            inc = self.Wf[idx, s]
        else:
            inc = (self.Wq[idx, s] * self.gains[l]) >> 8   # Q16.16 mV
        if self.model == "lif":
            ok = self.r[idx] == 0
            vn = self.v[idx] + inc if f else wrap32(self.v[idx] + inc)
            vn = np.where(ok, vn, self.v[idx])
            th = c["THRESH_MV"] if f else int(round(c["THRESH_MV"] * 65536))
            sp = ok & (vn >= th)
            self.v[idx] = np.where(sp, 0, vn)
            self.r[idx] = np.where(sp, c["REFR"], self.r[idx])
            return sp
        if self.model == "izh":
            if f:
                vn = self._floor(self.v[idx] + inc)
                sp = vn >= c["VPEAK_MV"]
                self.v[idx] = np.where(sp, c["C_MV"], vn)
                self.u[idx] = np.where(sp, self.u[idx] + c["D_MV"], self.u[idx])
            else:
                vn = wrap32(self.v[idx] + inc)
                sp = vn >= int(round(c["VPEAK_MV"] * 65536))
                self.v[idx] = np.where(sp, int(round(c["C_MV"] * 65536)), self._floor(vn))
                self.u[idx] = np.where(sp, wrap32(self.u[idx] + int(round(c["D_MV"] * 65536))), self.u[idx])
            return sp
        # hh
        vn = self.v[idx] + inc if f else s16(self.v[idx] + (inc >> 9))  # Q9.7
        return self._hh_spike(idx, vn)

    def _hh_spike(self, idx, vn):
        c = self.cfg
        f = self.mode == "float"
        up = c["UPPER_MV"] if f else c["UPPER_MV"] * 128
        lo = c["LOWER_MV"] if f else c["LOWER_MV"] * 128
        vn = self._floor(vn)
        spk = self.spk[idx]
        sp = (vn >= up) & ~spk
        dn = (vn <= lo) & spk
        self.spk[idx] = np.where(sp, True, np.where(dn, False, spk))
        self.v[idx] = vn
        return sp

    # ------------------------------------------------------------ dynamics
    def _dynamics(self):
        """one sub-step for all neurons; returns spike mask (or None)."""
        c = self.cfg
        f = self.mode == "float"
        if self.model == "lif":
            ok = self.r == 0
            if f:
                self.v = np.where(ok, self.v - self.v / (1 << c["LEAK_SHIFT"]), self.v)
            else:
                self.v = np.where(ok, self.v - (self.v >> c["LEAK_SHIFT"]), self.v)
            self.r = np.maximum(self.r - 1, 0)
            return None
        if self.model == "izh":
            if f:
                dt = 2.0 ** -c["DT_SHIFT"]
                a, b = c["A_Q8"] / 256.0, c["B_Q8"] / 256.0
                v, u = self.v, self.u
                vn = v + dt * (0.04 * v * v + 5 * v + 140 - u)
                un = u + dt * a * (b * v - u)
                sp = vn >= c["VPEAK_MV"]
                self.v = np.where(sp, c["C_MV"], self._floor(vn))
                self.u = np.where(sp, un + c["D_MV"], un)
                return sp
            V, U = self.v, self.u
            q1 = wrap32((V * V) >> 16)
            t2 = wrap32((q1 * 2621) >> 16)
            t3 = wrap32((V * 327680) >> 16)
            bv = wrap32((V * c["B_Q8"]) >> 8)
            du = wrap32((c["A_Q8"] * wrap32(bv - U)) >> 8)
            dv = wrap32(t2 + t3 + (140 << 16) - U)
            vn = wrap32(V + (dv >> c["DT_SHIFT"]))
            un = wrap32(U + (du >> c["DT_SHIFT"]))
            sp = vn >= int(round(c["VPEAK_MV"] * 65536))
            self.v = np.where(sp, int(round(c["C_MV"] * 65536)), self._floor(vn))
            self.u = np.where(sp, wrap32(un + int(round(c["D_MV"] * 65536))), un)
            return sp
        # ---- HH
        idx = np.arange(self.N)
        if f:
            V = self.v
            dt = 1.0 / 128.0
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
            return self._hh_spike(idx, vn)
        V = self.v
        vi = np.clip(V >> 7, -72, 131) + 72
        L = self.luts
        n2 = hh_gate_update(self.n, L["an"][vi], L["bn"][vi])
        m2 = hh_gate_update(self.m, L["am"][vi], L["bm"][vi])
        h2 = hh_gate_update(self.h, L["ah"][vi], L["bh"][vi])
        one = np.full(self.N, 16384, dtype=np.int64)
        FK = hh_vdf(s16(V + 1536), self.n, self.n, c["GK_Q8"])
        FNa = hh_vdf(s16(V - 15360), self.m, self.h, c["GNA_Q8"])
        FL = hh_vdf(s16(V - 1344), one, one, c["GL_Q8"])
        self.n, self.m, self.h = n2, m2, h2
        vn = s16(V - s16(FK + FNa + FL))
        return self._hh_spike(idx, vn)

    # -------------------------------------------------------------- events
    def _emit(self, idx, sp, l):
        for i in idx[sp]:
            if l < self.L - 1:
                if len(self.fifo) < FIFO_DEPTH:
                    self.fifo.append(int(i))
                else:
                    self.ovf = True
                self.hid += 1
            else:
                self.out.append((self.t, int(i) - self.starts[-1]))

    def _sweep(self, l, s):
        idx = np.arange(self.starts[l], self.ends[l] + 1)
        sp = self._integrate(idx, s, l)
        self._emit(idx, sp, l)

    def _drain(self):
        while self.fifo:
            n = self.fifo.popleft()
            l = int(self.layer_of[n])
            self._sweep(l + 1, n - self.starts[l])

    def step(self):
        for _ in range(self.S):
            sp = self._dynamics()
            if sp is not None and sp.any():
                allidx = np.arange(self.N)
                for l in range(self.L):
                    m = (self.layer_of == l)
                    # neurons are visited in index order == layer order
                    self._emit(allidx[m], sp[m], l)
            self._drain()

    def step_v2compat(self):
        # original testbench: TREF(n,2) for n = 0..9 only
        for _ in range(2):
            idx = np.arange(10)
            ok = self.r[idx] == 0
            self.v[idx] = np.where(ok, self.v[idx] - (self.v[idx] >> 4), self.v[idx])
            self.r[idx] = np.maximum(self.r[idx] - 1, 0)

    def run_image(self, rows):
        self.clear()
        self.fifo = deque()
        self.out, self.hid, self.ovf = [], 0, False
        for t, row in enumerate(rows):
            self.t = t
            for j in row:
                if j == 255:
                    break
                self._sweep(0, int(j))
                self._drain()
            if self.mode == "v2compat":
                self.step_v2compat()
            else:
                self.step()
        return self.out, self.hid, self.ovf


def predict(out, n_out=10):
    counts = np.zeros(n_out, dtype=int)
    for _, k in out:
        counts[k] += 1
    return counts


_G = {}


def _worker(args):
    bd, mode, k = args
    if "net" not in _G:
        sys.path.insert(0, HERE)
        _G["net"] = Net(bd, mode)
        _G["sp"] = np.load(os.path.join(_data_dir(), "spikes.npz"))["spikes"]
        if os.environ.get("HASTE_T"):
            _G["sp"] = _G["sp"][:, :int(os.environ["HASTE_T"])]
    out, hid, ovf = _G["net"].run_image(_G["sp"][k])
    return k, out, hid, ovf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir")
    ap.add_argument("--mode", default="fixed", choices=["fixed", "float"])
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default=None)
    ap.add_argument("--T", type=int, default=None, help="simulate only the first T steps of each encoding")
    a = ap.parse_args()
    if a.T:
        os.environ["HASTE_T"] = str(a.T)
    d = np.load(os.path.join(_data_dir(), "spikes.npz"))
    labels = d["labels"]
    ks = list(range(a.start, min(a.start + a.count, len(labels))))
    with Pool(a.jobs) as p:
        res = sorted(p.map(_worker, [(a.build_dir, a.mode, k) for k in ks]))
    outp = a.out or os.path.join(a.build_dir, "ref_%s.txt" % a.mode)
    with open(outp, "w") as f:
        for k, out, hid, ovf in res:
            c = predict(out)
            f.write("IMG %d LABEL %d HID %d OVF %d COUNTS %s\n" % (k, labels[k], hid, int(ovf), " ".join(map(str, c))))
            for t, i in out:
                f.write("SPK %d %d %d\n" % (k, t, i))
    print("wrote", outp)


if __name__ == "__main__":
    main()
