#!/usr/bin/env python3
"""HASTE Version-IV memory-image generator.

Emits, for one (model, topology) configuration, everything the parameterised
RTL needs.  The RTL itself is never edited per network:

  syn.mem     synaptic memory image ("synMem"): B-bit weights, row-major
              [neuron][fan-in slot], padded to FANIN slots per neuron
  layer.mem   layer descriptor image ("layerMem"): {start, end, gain} per layer
  params.svh  sizes + neuron-model constants (localparams included by the RTL)
  quant.json  the quantisation record (per-layer scale alpha, gain, G, ...)
  lut_*.mem   (HH only) the six alpha/beta gating look-up tables

Quantisation (symmetric, per layer, B = WEIGHT_BITS in {4, 8, 16}, default 8):
  m_l     = max|W_l|,  QMAX = 2^(B-1) - 1
  q       = clip(round(W_l / m_l * QMAX), -QMAX, QMAX)       (B-bit, synMem)
  alpha_l = m_l / QMAX                                         (float scale)
  gain_l  = round(G_l * alpha_l * 2^24)                        (Q8.24, layerMem)
The RTL applies  dV = (q * gain_l) >>> 8  (Q16.16 mV), i.e. dV ~= G_l * W  in mV, so the
per-layer scale is undone in hardware and the membrane/threshold regime is
the same for every layer (threshold co-scaling is exact up to rounding).
G = G_SCALE / max_l m_l  (G_SCALE mV = size of the largest synaptic jump).

Usage examples (run from Hardware/Version-IV):
  python3 tools/gen_mem.py spikes                       # data/spikes.mem, labels.mem
  python3 tools/gen_mem.py net --model lif --topo 64x10 # build/lif_64x10/*
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(V4))
V2 = os.path.join(REPO, "Hardware", "Version-II")

N_IN = 64
T_STEPS = 100

TOPOS = {
    # name : (npz file in Train/outputs, list of array keys in layer order)
    # retrained with tools/train_ann.py (bias-free ReLU MLP, 8x8 MNIST, seed 0, 30 epochs)
    "10": ("weights-10.npz", ["arr_0"]),
    "64x10": ("weights-64x10.npz", ["arr_0", "arr_1"]),
    "64x64x10": ("weights-64x64x10.npz", ["arr_0", "arr_1", "arr_2"]),
    # the original weights used for the first submission (Version-II)
    "legacy-10": ("weights-1layer-63.npz", ["arr_0"]),
    "legacy-64x10": ("weights-2layer-53.npz", ["arr_0", "arr_1"]),
    "legacy-128x32x10": ("weights-3layer-31.npz", ["arr_0", "arr_1", "arr_2"]),
}

# ---------------------------------------------------------------- defaults
DEFAULTS = {
    # operating points chosen with tools/sweep.py on the tuning set data_val/
    # (300 MNIST *training* images), never on the test images; see results/sweeps/
    "lif": dict(NORM="layer", G_SCALE=28.0, SUBSTEPS=2, THRESH_MV=50.0, LEAK_SHIFT=6, REFR=0),
    # Izhikevich fast-spiking (FS) preset: a=26/256 (~0.1), b=50/256 (~0.2), c=-65 mV,
    # d=2, v_peak=30 mV; dt = 2^-DT_SHIFT ms per sub-step.  The regular-spiking preset
    # of Version-II (a=5/256, d=8) adapts strongly and loses 20+ points in deep nets
    # (results/sweeps/sweep_izh3.txt).
    # VMIN_MV: inhibitory floor on V (keeps v^2 inside 32 bits, |V| < 181 mV)
    "izh": dict(NORM="layer", G_SCALE=28.0, SUBSTEPS=32, A_Q8=26, B_Q8=50, C_MV=-65, D_MV=2,
                VPEAK_MV=30, DT_SHIFT=7, VMIN_MV=-150),
    # HH: LUT-based Euler integrator from Version-II, 300 sub-steps per step
    # VMIN_MV: floor on V = lower edge of the rate LUTs (keeps Q9.7 from wrapping)
    "hh": dict(NORM="layer", G_SCALE=28.0, SUBSTEPS=300, UPPER_MV=80, LOWER_MV=0,
               GK_Q8=36 * 256, GNA_Q8=120 * 256, GL_Q8=76, VMIN_MV=-72),
}

# per-topology operating-point overrides (tuning set data_val/, results/sweeps/sweep_hh*.txt).
# HH is the only model whose best synaptic gain depends on depth.
TOPO_OVERRIDES = {
    ("hh", "64x10"): dict(G_SCALE=40.0),
    ("hh", "64x64x10"): dict(G_SCALE=56.0),
}


# standard campaign: every model x topology at B=8, plus B=4/16 on 64x10
# precision sweep (B = 4/16) on 64x10 for LIF/IZH, and on 10 for HH (the only HH network
# above chance level; deep HH is a documented limitation, see PROGRESS.md)
ALL_CONFIGS = [(m, t, 8) for m in ("lif", "izh", "hh") for t in ("10", "64x10", "64x64x10")] + \
              [(m, "64x10", b) for m in ("lif", "izh") for b in (4, 16)] + \
              [("hh", "10", b) for b in (4, 16)]


def load_weights(topo):
    fn, keys = TOPOS[topo]
    z = np.load(os.path.join(REPO, "Train", "outputs", fn))
    Ws = [np.asarray(z[k], dtype=np.float64) for k in keys]
    prev = N_IN
    for W in Ws:
        assert W.shape[1] == prev, (topo, W.shape, prev)
        prev = W.shape[0]
    return Ws


def quantise(Ws, g_scale, norm="global", bits=8, g_scale_out=None):
    """norm='global': one G for all layers (G = G_SCALE / max_l m_l).
    norm='layer' : per-layer weight normalisation, G_l = G_SCALE / m_l, i.e.
                   the largest weight of every layer is a G_SCALE-mV jump.
    g_scale_out (norm='layer' only): G_SCALE of the output layer, if different."""
    ms = [float(np.max(np.abs(W))) for W in Ws]
    G = g_scale / max(ms)
    qs, gains, alphas, Gs = [], [], [], []
    for l, (W, m) in enumerate(zip(Ws, ms)):
        if norm == "layer":
            gs = g_scale_out if (g_scale_out is not None and l == len(Ws) - 1) else g_scale
            G = gs / m
        Gs.append(G)
        qmax = 2 ** (bits - 1) - 1
        q = np.clip(np.round(W / m * qmax), -qmax, qmax).astype(np.int64)
        alpha = m / qmax
        gain = int(round(G * alpha * (1 << 24)))
        assert 0 < gain < (1 << 32), "gain must fit Q8.24; lower G_SCALE"
        qs.append(q)
        gains.append(gain)
        alphas.append(alpha)
    return qs, gains, alphas, Gs


def hex_w(v, bits):
    return format(int(v) & ((1 << bits) - 1), "0%dx" % ((bits + 3) // 4))


def parse_lut_tables():
    """Extract the six 204-entry tables from the Version-II ngvLut.sv."""
    t = open(os.path.join(V2, "HH", "src", "util", "ngvLut.sv")).read()
    out = {}
    for name in ["an", "bn", "am", "bm", "ah", "bh"]:
        m = re.search(r"reg \[15:0\] %s_mem\[204\] = '\{(.*?)\};" % name, t, re.S)
        vals = [int(b, 2) for b in re.findall(r"16'b([01]{16})", m.group(1))]
        assert len(vals) == 204, (name, len(vals))
        out[name] = vals
    return out


def hh_rest_state(luts, gk=None):
    """Fixed point of the integer gating update with V held at 0 mV."""
    import ref_model as rm  # local module
    idx = 0 + 72
    st = []
    for k, (a, b) in enumerate([("an", "bn"), ("am", "bm"), ("ah", "bh")]):
        g = 0
        for _ in range(20000):
            g2 = rm.hh_gate_update(np.array([g]), luts[a][idx], luts[b][idx])[0]
            if g2 == g:
                break
            g = int(g2)
        st.append(int(g))
    return st


def layer_tab_line(words, nw):
    """layerMem as a compile-time constant (same words as layer.mem, LAYER_TAB[0] = layer 0).
    The cores read this instead of $readmemh(layer.mem): from the $readmemh registers,
    Vivado 2022.2 synthesised the next-layer start load as 0 (gate-level check, 2026-10-21)."""
    w = 2 * nw + 32
    return ("localparam logic [N_LAYERS-1:0][%d:0] LAYER_TAB = {%s};  // {start, end, gain}, last layer first"
            % (w - 1, ", ".join("%d'h%s" % (w, hex_w(x, w)) for x in reversed(words))))


def write_net(model, topo, out_dir, overrides):
    """Build the images for a trained network in Train/outputs (see TOPOS)."""
    ov = dict(TOPO_OVERRIDES.get((model, topo), {}))
    ov.update(overrides or {})
    return write_net_from_weights(model, load_weights(topo), out_dir, ov, topo)


def write_net_from_weights(model, Ws, out_dir, overrides=None, label="custom"):
    """Build the images for any fully-connected network.
    Ws: list of float arrays, Ws[l] has shape (neurons of layer l, fan-in);
        Ws[0].shape[1] is the number of input channels (<= 255).
    This is the entry point used by the GUI (App/SNN/hardwareController.py)."""
    cfg = dict(DEFAULTS[model])
    cfg.update(overrides or {})
    Ws = [np.asarray(W, dtype=np.float64) for W in Ws]
    for a, b in zip(Ws[:-1], Ws[1:]):
        assert b.shape[1] == a.shape[0], "layer sizes do not chain"
    n_in = Ws[0].shape[1]
    assert n_in <= 255, "input index 255 is reserved as the padding marker"
    topo = label
    wb = int(cfg.get("WEIGHT_BITS", 8))
    assert wb in (4, 8, 16), "WEIGHT_BITS must be 4, 8 or 16"
    cfg["WEIGHT_BITS"] = wb
    qs, gains, alphas, G = quantise(Ws, cfg["G_SCALE"], cfg.get("NORM", "global"), wb,
                                 cfg.get("G_SCALE_OUT"))
    sizes = [W.shape[0] for W in Ws]
    fanins = [W.shape[1] for W in Ws]
    n_neu = sum(sizes)
    fanin = max(fanins)
    nw = max(8, int(np.ceil(np.log2(n_neu + 1))))
    n_layers = len(Ws)
    os.makedirs(out_dir, exist_ok=True)
    np.savez(os.path.join(out_dir, "weights_float.npz"), *Ws)

    # synMem ------------------------------------------------------------
    with open(os.path.join(out_dir, "syn.mem"), "w") as f:
        f.write("// synMem: int%d weights, addr = neuron*%d + slot\n" % (wb, fanin))
        for q in qs:
            for row in q:
                padded = list(row) + [0] * (fanin - len(row))
                f.write(" ".join(hex_w(v, wb) for v in padded) + "\n")
    # layerMem ----------------------------------------------------------
    starts, ends = [], []
    s = 0
    for n in sizes:
        starts.append(s)
        ends.append(s + n - 1)
        s += n
    with open(os.path.join(out_dir, "layer.mem"), "w") as f:
        f.write("// layerMem: {start[%d], end[%d], gain[32] (Q8.24)}\n" % (nw, nw))
        for st, en, g in zip(starts, ends, gains):
            word = (st << (nw + 32)) | (en << 32) | g
            f.write(hex_w(word, 2 * nw + 32) + "\n")
    layer_words = [(st << (nw + 32)) | (en << 32) | g for st, en, g in zip(starts, ends, gains)]

    # params ------------------------------------------------------------
    p = []
    p.append("// generated by tools/gen_mem.py -- do not edit")
    p.append("// model=%s topology=%s" % (model, topo))
    p.append("localparam int N_IN     = %d;" % n_in)
    p.append("localparam int N_NEU    = %d;" % n_neu)
    p.append("localparam int N_LAYERS = %d;" % n_layers)
    p.append("localparam int FANIN    = %d;" % fanin)
    p.append("localparam int NW       = %d;" % nw)
    p.append("localparam int N_OUT    = %d;" % sizes[-1])
    p.append("localparam int WB       = %d;  // weight bits" % wb)
    p.append("localparam int SUBSTEPS = %d;" % cfg["SUBSTEPS"])
    q16 = lambda mv: int(round(mv * 65536))
    if model == "lif":
        p.append("localparam logic signed [31:0] THRESH = 32'sd%d;" % q16(cfg["THRESH_MV"]))
        p.append("localparam int LEAK_SHIFT = %d;" % cfg["LEAK_SHIFT"])
        p.append("localparam int REFR_STEPS = %d;" % cfg["REFR"])
    elif model == "izh":
        p.append("localparam logic signed [31:0] VPEAK = 32'sd%d;" % q16(cfg["VPEAK_MV"]))
        p.append("localparam logic signed [31:0] VRESET = -32'sd%d;" % q16(-cfg["C_MV"]))
        p.append("localparam logic signed [31:0] DRESET = 32'sd%d;" % q16(cfg["D_MV"]))
        p.append("localparam int A_Q8 = %d;" % cfg["A_Q8"])
        p.append("localparam int B_Q8 = %d;" % cfg["B_Q8"])
        p.append("localparam int DT_SHIFT = %d;" % cfg["DT_SHIFT"])
        assert -181 < cfg["VMIN_MV"] < cfg["C_MV"], "VMIN_MV must lie in (-181, C_MV) mV"
        p.append("localparam logic signed [31:0] VMIN = -32'sd%d;" % q16(-cfg["VMIN_MV"]))
        # rest state: v=c, u=b*c
        u0 = (q16(cfg["C_MV"]) * cfg["B_Q8"]) >> 8
        p.append("localparam logic signed [31:0] U_INIT = %s32'sd%d;" % ("-" if u0 < 0 else "", abs(u0)))
        cfg["U_INIT"] = u0
    elif model == "hh":
        luts = parse_lut_tables()
        for name, vals in luts.items():
            with open(os.path.join(out_dir, "lut_%s.mem" % name), "w") as f:
                f.write("\n".join(hex_w(v, 16) for v in vals) + "\n")
        sys.path.insert(0, HERE)
        n0, m0, h0 = hh_rest_state(luts)
        cfg.update(N_INIT=n0, M_INIT=m0, H_INIT=h0)
        p.append("localparam logic signed [15:0] UPPER = 16'sd%d;" % (cfg["UPPER_MV"] * 128))
        p.append("localparam logic signed [15:0] LOWER = 16'sd%d;" % (cfg["LOWER_MV"] * 128))
        assert -256 < cfg["VMIN_MV"] < 0, "VMIN_MV must lie in (-256, 0) mV"
        p.append("localparam logic signed [15:0] VMIN = -16'sd%d;" % int(round(-cfg["VMIN_MV"] * 128)))
        p.append("localparam logic [15:0] GK  = 16'd%d;" % cfg["GK_Q8"])
        p.append("localparam logic [15:0] GNA = 16'd%d;" % cfg["GNA_Q8"])
        p.append("localparam logic [15:0] GL  = 16'd%d;" % cfg["GL_Q8"])
        p.append("localparam logic signed [15:0] N_INIT = 16'sd%d;" % n0)
        p.append("localparam logic signed [15:0] M_INIT = 16'sd%d;" % m0)
        p.append("localparam logic signed [15:0] H_INIT = 16'sd%d;" % h0)
    p.append(layer_tab_line(layer_words, nw))
    with open(os.path.join(out_dir, "params.svh"), "w") as f:
        f.write("\n".join(p) + "\n")

    rec = dict(model=model, topology=topo, n_in=n_in, sizes=sizes, fanins=fanins,
               n_neu=n_neu, fanin=fanin, nw=nw, starts=starts, ends=ends,
               gains_q24=gains, alphas=alphas, G_layers=G, cfg=cfg,
               weight_bits=wb, weight_rounding="round-half-even, clip +-(2^(B-1)-1)")
    with open(os.path.join(out_dir, "quant.json"), "w") as f:
        json.dump(rec, f, indent=1)
    print("wrote", out_dir, "N_NEU=%d FANIN=%d layers=%s gains=%s" % (n_neu, fanin, sizes, gains))
    return rec


def write_spikes(out_dir):
    """Convert the Version-II spikes.svh (1000 Poisson-encoded test images,
    T=100, 64 slots/step, 0xFF padded) into flat $readmemh images."""
    src = os.path.join(V2, "LIF", "src", "spikes.svh")
    t = open(src).read()
    heads = list(re.finditer(r"reg \[7:0\] (\w+) \[100\]\[64\] = '\{", t))
    os.makedirs(out_dir, exist_ok=True)
    labels = []
    arr = np.full((len(heads), T_STEPS, N_IN), 255, dtype=np.int64)
    for k, h in enumerate(heads):
        end = heads[k + 1].start() if k + 1 < len(heads) else len(t)
        body = t[h.end():end]
        rows = re.findall(r"'\{([^}]*)\}", body)
        assert len(rows) == T_STEPS
        for r, row in enumerate(rows):
            v = [int(x) for x in re.findall(r"8'd(\d+)", row)]
            arr[k, r, :len(v)] = v
        labels.append(int(h.group(1).split("_")[-1]))
    with open(os.path.join(out_dir, "spikes.mem"), "w") as f:
        for k in range(arr.shape[0]):
            for r in range(T_STEPS):
                f.write(" ".join("%02x" % v for v in arr[k, r]) + "\n")
    with open(os.path.join(out_dir, "labels.mem"), "w") as f:
        f.write("\n".join("%x" % l for l in labels) + "\n")
    np.savez_compressed(os.path.join(out_dir, "spikes.npz"), spikes=arr, labels=np.array(labels),
                        names=np.array([h.group(1) for h in heads]))
    print("wrote %d images to %s" % (len(labels), out_dir))


def encode_pngs(png_dir, out_dir, seed, T=T_STEPS):
    """Re-encode the 1000 test PNGs with a seeded Bernoulli/Poisson encoder
    (same as spikingjelly PoissonEncoder: spike ~ Bernoulli(pixel), pixel in
    [0,1] after 8x8 bilinear resize), for multi-seed statistics.  Image order
    and labels follow data/spikes.npz, so results stay comparable."""
    import torch
    import torchvision
    from PIL import Image
    names = list(np.load(os.path.join(V4, "data", "spikes.npz"))["names"])
    tf = torchvision.transforms.Compose([torchvision.transforms.Grayscale(1), torchvision.transforms.ToTensor(),
                                         torchvision.transforms.Resize((8, 8))])
    g = torch.Generator().manual_seed(seed)
    arr = np.full((len(names), T, N_IN), 255, dtype=np.int64)
    labels = []
    for k, nm in enumerate(names):
        img = tf(Image.open(os.path.join(png_dir, str(nm) + ".png")).convert("RGB")).view(-1)
        for t in range(T):
            idx = torch.nonzero(torch.rand(N_IN, generator=g) < img).view(-1).numpy()
            arr[k, t, :len(idx)] = idx
        labels.append(int(str(nm).split("_")[-1]))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "spikes.mem"), "w") as f:
        for k in range(arr.shape[0]):
            for r in range(T):
                f.write(" ".join("%02x" % v for v in arr[k, r]) + "\n")
    with open(os.path.join(out_dir, "labels.mem"), "w") as f:
        f.write("\n".join("%x" % l for l in labels) + "\n")
    np.savez_compressed(os.path.join(out_dir, "spikes.npz"), spikes=arr, labels=np.array(labels), names=np.array(names))
    print("wrote %d images (seed %d) to %s" % (len(names), seed, out_dir))


def encode_val(out_dir, n=300, seed=1234, T=T_STEPS):
    """Tuning set: n MNIST *training* images (the last n of the training split),
    encoded exactly like encode_pngs.  Operating points (G_SCALE, VMIN_MV, ...)
    are chosen on this set, never on the 1000 test images."""
    import torch
    import torchvision
    tf = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Resize((8, 8))])
    ds = torchvision.datasets.MNIST(os.path.join(REPO, "Train", "datasets", "mnist"), train=True, download=True,
                                    transform=tf)
    g = torch.Generator().manual_seed(seed)
    ks = range(len(ds) - n, len(ds))
    arr = np.full((n, T, N_IN), 255, dtype=np.int64)
    labels, names = [], []
    for r, k in enumerate(ks):
        img, y = ds[k]
        img = img.view(-1)
        for t in range(T):
            idx = torch.nonzero(torch.rand(N_IN, generator=g) < img).view(-1).numpy()
            arr[r, t, :len(idx)] = idx
        labels.append(int(y))
        names.append("train_%d_%d" % (k, y))
    os.makedirs(out_dir, exist_ok=True)
    np.savez_compressed(os.path.join(out_dir, "spikes.npz"), spikes=arr, labels=np.array(labels), names=np.array(names))
    print("wrote %d training images (tuning set) to %s" % (n, out_dir))


def data_dir():
    """data directory used by all tools; override with env HASTE_DATA (e.g. data_s1)."""
    d = os.environ.get("HASTE_DATA", "data")
    return d if os.path.isabs(d) else os.path.join(V4, d)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("spikes", help="data/ from Version-II spikes.svh, or re-encode PNGs with --seed")
    s1.add_argument("--out", default=None)
    s1.add_argument("--seed", type=int, default=None, help="re-encode Train/test_images_1k with this seed")
    s1.add_argument("--png", default=os.path.join(REPO, "Train", "test_images_1k"))
    s1.add_argument("--val", type=int, default=None, help="write a tuning set of N MNIST training images (data_val/)")
    s1.add_argument("--T", type=int, default=T_STEPS, help="time steps per image (with --seed; max 200)")
    s2 = sub.add_parser("net")
    s2.add_argument("--model", choices=["lif", "izh", "hh"], required=True)
    s2.add_argument("--topo", default=None, help="one of %s (weights from Train/outputs)" % list(TOPOS))
    s2.add_argument("--npz", default=None, help="custom weights: npz with arr_0..arr_{L-1}, arr_l shape (out, in)")
    s2.add_argument("--out", default=None)
    s2.add_argument("--set", nargs="*", default=[], help="override cfg, e.g. SUBSTEPS=128 WEIGHT_BITS=4")
    s3 = sub.add_parser("prepare", help="data/ + every standard build directory (all models/topologies/precisions)")
    a = ap.parse_args()
    if a.cmd == "spikes":
        if a.val:
            encode_val(a.out or os.path.join(V4, "data_val"), a.val)
        elif a.seed is None:
            write_spikes(a.out or os.path.join(V4, "data"))
        else:
            out = a.out or os.path.join(V4, "data_s%d" % a.seed + ("" if a.T == T_STEPS else "_T%d" % a.T))
            encode_pngs(a.png, out, a.seed, a.T)
    elif a.cmd == "prepare":
        if not os.path.exists(os.path.join(V4, "data", "spikes.mem")):
            write_spikes(os.path.join(V4, "data"))
        for c in ALL_CONFIGS:
            m, t, b = c
            name = "%s_%s" % (m, t) + ("" if b == 8 else "_b%d" % b)
            write_net(m, t, os.path.join(V4, "build", name), {"WEIGHT_BITS": b})
    elif a.npz:
        ov = {}
        for kv in a.set:
            k, v = kv.split("=")
            try:
                ov[k] = float(v) if "." in v else int(v)
            except ValueError:
                ov[k] = v
        z = np.load(a.npz)
        Ws = [z["arr_%d" % i] for i in range(len(z.files))]
        label = os.path.splitext(os.path.basename(a.npz))[0]
        out = a.out or os.path.join(V4, "build", "%s_%s" % (a.model, label))
        write_net_from_weights(a.model, Ws, out, ov, label)
    else:
        assert a.topo in TOPOS, "--topo must be one of %s (or use --npz)" % list(TOPOS)
        ov = {}
        for kv in a.set:
            k, v = kv.split("=")
            try:
                ov[k] = float(v) if "." in v else int(v)
            except ValueError:
                ov[k] = v
        out = a.out or os.path.join(V4, "build", "%s_%s" % (a.model, a.topo))
        write_net(a.model, a.topo, out, ov)


if __name__ == "__main__":
    main()
