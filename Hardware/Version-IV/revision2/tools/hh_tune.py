#!/usr/bin/env python3
"""Can deep HH networks be tuned without changing the RTL?  (follow-up to hh_failure)

Stage 'gain': per-layer synaptic gain.  J_l = largest jump (mV) of layer l.
  Implemented with NORM=global on pre-scaled weights (W_l * J_l / max|W_l|,
  G_SCALE = max_l J_l): the RTL quantises every layer relative to its own max,
  so this is exactly 'layer' normalisation with a different G_SCALE per layer.
  Search on data_val (300 training images) in the float model, then the best
  point is confirmed on the 1000 test images in float AND fixed point (= RTL).
  64x10: full grid; 64x64x10: coordinate descent (factors x2, then x sqrt2).

Stage 'train': HH-aware fine-tuning (weights only, RTL unchanged).
  The per-layer conversion G_l (mV per weight unit) from the best 'gain' point is
  kept fixed.  Each round: run the float HH net on a fit set (500 MNIST training
  images, not in data_val), measure per layer the transfer curve
  rate_out = f_l(x), x = W_l . (measured input rates), as a monotone binned
  median; fine-tune the ANN with f_l as the activation (CE on 20*f_L(x_L));
  rebuild, score on data_val.  3 rounds, best val round confirmed on test
  (float + fixed point).

  hh_tune.py gain   -> results/hh_tune_gain.jsonl
  hh_tune.py train  -> results/hh_tune_train.jsonl, results/hh_tune_weights_<topo>.npz
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
sys.path.insert(0, os.path.join(runner.V4, "tools"))
import gen_mem  # noqa: E402

OUT = os.path.join(runner.R2, "results")
BASE = dict(UPPER_MV=80, LOWER_MV=0, VMIN_MV=-72, SUBSTEPS=300, NORM="global")


def scaled(Ws, J):
    return [W * (j / float(np.max(np.abs(W)))) for W, j in zip(Ws, J)]


def evaluate(Ws, J, data, count, mode="float"):
    d = tempfile.mkdtemp(prefix="r2tune_")
    runner.build("hh", scaled(Ws, J), d, dict(BASE, G_SCALE=float(max(J))))
    cls = sweep_dt.FloatDtNet if mode == "float" else runner.INet
    return runner.summarize(runner.run(d, data, count, mode, cls=cls))


class Cache:
    def __init__(self, fn, topo):
        self.fn, self.topo = fn, topo
        self.d = {}
        if os.path.exists(fn):
            for l in open(fn):
                r = json.loads(l)
                if r["topo"] == topo and r["stage"] == "val":
                    self.d[tuple(r["J"])] = r["acc"]

    def val(self, Ws, J):
        J = tuple(float(round(j, 3)) for j in J)
        if J not in self.d:
            s = evaluate(Ws, J, "data_val", 300)
            self.d[J] = s["acc"]
            open(self.fn, "a").write(json.dumps(dict(topo=self.topo, stage="val", J=J, acc=s["acc"],
                                                     spk=s["spk_per_layer"])) + "\n")
            print(self.topo, "J=%s val=%.1f spk=%s" % (J, s["acc"], s["spk_per_layer"]), flush=True)
        return self.d[J]


def gain():
    fn = os.path.join(OUT, "hh_tune_gain.jsonl")
    for topo in ["64x10", "64x64x10"]:
        Ws = gen_mem.load_weights(topo)
        c = Cache(fn, topo)
        L = len(Ws)
        if L == 2:
            for j1 in [14, 28, 56, 112, 224]:
                for j2 in [14, 28, 56, 112, 224]:
                    c.val(Ws, (j1, j2))
        J = [112.0] * L
        for f in [2.0, 2 ** 0.5]:
            best = c.val(Ws, J) if L > 2 else max(c.d.values())
            if L == 2:
                J = list(max(c.d, key=c.d.get))
            improved = True
            while improved:
                improved = False
                for l in range(L):
                    for m in [f, 1 / f]:
                        Jn = list(J)
                        Jn[l] *= m
                        a = c.val(Ws, Jn)
                        if a > best:
                            best, J, improved = a, Jn, True
        J = tuple(float(round(j, 3)) for j in J)
        print(topo, "best J=%s val=%.1f" % (J, c.d[J]), flush=True)
        for mode in ["float", "fixed"]:
            s = evaluate(Ws, J, "data", 1000, mode)
            open(fn, "a").write(json.dumps(dict(topo=topo, stage="test_" + mode, J=J, val=c.d[J], acc=s["acc"],
                                                ties=s["ties"], spk=s["spk_per_layer"],
                                                correct=s["correct"])) + "\n")
            print(topo, mode, "test=%.1f ties=%d spk=%s" % (s["acc"], s["ties"], s["spk_per_layer"]), flush=True)


def best_gain(topo):
    recs = [json.loads(l) for l in open(os.path.join(OUT, "hh_tune_gain.jsonl"))]
    return [r for r in recs if r["topo"] == topo and r["stage"] == "test_float"][-1]["J"]


def encode_fit(n=500, seed=99, T=100):
    out = os.path.join(runner.R2, "data_fit")
    if os.path.exists(os.path.join(out, "spikes.npz")):
        return out
    import torch
    import torchvision
    tf = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Resize((8, 8))])
    ds = torchvision.datasets.MNIST(os.path.join(gen_mem.REPO, "Train", "datasets", "mnist"), train=True,
                                    download=False, transform=tf)
    g = torch.Generator().manual_seed(seed)
    arr = np.full((n, T, 64), 255, dtype=np.int64)
    lab = []
    for r in range(n):
        img, y = ds[r]
        img = img.view(-1)
        for t in range(T):
            idx = torch.nonzero(torch.rand(64, generator=g) < img).view(-1).numpy()
            arr[r, t, :len(idx)] = idx
        lab.append(int(y))
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, "spikes.npz"), spikes=arr, labels=np.array(lab))
    return out


def measure(Ws, Gl, data):
    """per-layer (x, y): x = W_l . input rate (weight units), y = HH output rate per step."""
    J = [g * float(np.max(np.abs(W))) for g, W in zip(Gl, Ws)]
    d = tempfile.mkdtemp(prefix="r2tune_")
    runner.build("hh", scaled(Ws, J), d, dict(BASE, G_SCALE=float(max(J))))
    res = runner.run(d, data, 10 ** 9, "float", cls=sweep_dt.FloatDtNet)
    sp = np.load(os.path.join(data, "spikes.npz"))["spikes"]
    T = sp.shape[1]
    rin = np.zeros((len(res), 64))
    for k in range(len(res)):
        v = sp[k][sp[k] != 255]
        np.add.at(rin[k], v, 1)
    rin /= T
    rates = np.array([r["nspk"] for r in res], float) / T
    st, en = res[0]["starts"], res[0]["ends"]
    xs, ys, prev = [], [], rin
    for l, W in enumerate(Ws):
        y = rates[:, st[l]:en[l] + 1]
        xs.append(prev @ W.T)
        ys.append(y)
        prev = y
    return xs, ys, runner.summarize(res)


def fit_curve(x, y, nb=40):
    x, y = x.ravel(), y.ravel()
    q = np.unique(np.quantile(x, np.linspace(0, 1, nb + 1)))
    cx, cy = [], []
    for a, b in zip(q[:-1], q[1:]):
        m = (x >= a) & (x <= b)
        if m.sum() >= 20:
            cx.append(float(np.median(x[m])))
            cy.append(float(np.median(y[m])))
    cy = np.maximum.accumulate(np.array(cy))
    return np.array(cx), cy


def mnist_xy(train):
    import torch
    import torchvision
    tf = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Resize((8, 8))])
    ds = torchvision.datasets.MNIST(os.path.join(gen_mem.REPO, "Train", "datasets", "mnist"), train=train,
                                    download=False, transform=tf)
    X = torch.stack([ds[k][0].view(-1) for k in range(len(ds))])
    Y = torch.tensor([int(ds.targets[k]) for k in range(len(ds))])
    return X, Y


def finetune(Ws, curves, X, Y, epochs=5, lr=1e-4, scale=20.0, seed=0):
    import torch
    torch.manual_seed(seed)
    P = [torch.nn.Parameter(torch.tensor(W, dtype=torch.float32)) for W in Ws]
    C = [(torch.tensor(cx, dtype=torch.float32), torch.tensor(cy, dtype=torch.float32)) for cx, cy in curves]

    def act(x, cx, cy):
        xc = x.clamp(cx[0].item(), cx[-1].item())
        i = torch.searchsorted(cx, xc.detach().contiguous()).clamp(1, len(cx) - 1)
        x0, x1, y0, y1 = cx[i - 1], cx[i], cy[i - 1], cy[i]
        y = y0 + (y1 - y0) * (xc - x0) / (x1 - x0 + 1e-12)
        return y + 1e-2 * (x - x.detach())  # small surrogate slope in flat regions

    def fwd(xb):
        h = xb
        for W, (cx, cy) in zip(P, C):
            h = act(h @ W.T, cx, cy)
        return h * scale

    opt = torch.optim.Adam(P, lr=lr)
    n = len(X)
    for ep in range(epochs):
        perm = torch.randperm(n)
        for b in range(0, n, 128):
            idx = perm[b:b + 128]
            loss = torch.nn.functional.cross_entropy(fwd(X[idx]), Y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
    with torch.no_grad():
        acc = float((fwd(X[-10000:]).argmax(1) == Y[-10000:]).float().mean()) * 100
    return [p.detach().double().numpy() for p in P], acc


def train():
    fn = os.path.join(OUT, "hh_tune_train.jsonl")
    fit = encode_fit()
    X, Y = mnist_xy(True)
    for topo in ["64x10", "64x64x10"]:
        W0 = gen_mem.load_weights(topo)
        J0 = best_gain(topo)
        Gl = [j / float(np.max(np.abs(W))) for j, W in zip(J0, W0)]
        Ws, best = W0, (-1, None, None)
        for rnd in range(1, 4):
            xs, ys, _ = measure(Ws, Gl, fit)
            curves = [fit_curve(x, y) for x, y in zip(xs, ys)]
            Ws, sim_acc = finetune(Ws, curves, X, Y)
            J = [g * float(np.max(np.abs(W))) for g, W in zip(Gl, Ws)]
            s = evaluate(Ws, J, "data_val", 300)
            rec = dict(topo=topo, stage="round", round=rnd, J=J, val=s["acc"], ann_hh_act=sim_acc,
                       spk=s["spk_per_layer"], curves=[[c[0].tolist(), c[1].tolist()] for c in curves])
            open(fn, "a").write(json.dumps(rec) + "\n")
            print(topo, "round %d: HH-activation ANN %.1f %%, SNN val %.1f %%, spk=%s" % (
                rnd, sim_acc, s["acc"], s["spk_per_layer"]), flush=True)
            if s["acc"] > best[0]:
                best = (s["acc"], [W.copy() for W in Ws], J)
        np.savez(os.path.join(OUT, "hh_tune_weights_%s.npz" % topo), *best[1])
        for mode in ["float", "fixed"]:
            s = evaluate(best[1], best[2], "data", 1000, mode)
            open(fn, "a").write(json.dumps(dict(topo=topo, stage="test_" + mode, J=best[2], val=best[0],
                                                acc=s["acc"], ties=s["ties"], spk=s["spk_per_layer"],
                                                correct=s["correct"])) + "\n")
            print(topo, mode, "test=%.1f ties=%d spk=%s" % (s["acc"], s["ties"], s["spk_per_layer"]), flush=True)


if __name__ == "__main__":
    {"gain": gain, "train": train}[sys.argv[1]]()
