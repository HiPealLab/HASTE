#!/usr/bin/env python3
"""Train a small bias-free LeNet-style CNN on MNIST resized to 8x8 and unroll it
into dense layers that the unchanged Version-IV core can execute.

  python tools/train_cnn.py --arch c6-p-f --out Train/outputs/weights-cnn-c6-p-f.npz
  python tools/train_cnn.py --arch c6-c12-p-f --out Train/outputs/weights-cnn-c6-c12-p-f.npz

--arch: dash-separated layers. cN = conv 3x3, N channels, stride 1, no padding,
        followed by ReLU; p = avg-pool 2x2; f = fully connected to 10 classes.
        c6-p-f: 8x8 -> 6x6x6 -> 3x3x6 -> 10;  c6-c12-p-f: 8x8 -> 6x6x6 -> 4x4x12 -> 2x2x12 -> 10.
The convolution and the pooling are linear and bias-free, so each is exactly a
dense matrix (built by pushing the unit basis through the layer).  The saved npz
holds arr_0 (CH*36 x 64), arr_1 (CH*9 x CH*36), arr_2 (10 x CH*9), the format of
tools/gen_mem.py --npz.  The core runs these as dense layers: it does not exploit
weight sharing or sparsity (zero weights still occupy synMem and cost cycles).
Every conv and pooling layer becomes one spiking layer (pooling: average of four inputs).
"""
import argparse
import os
import sys

import numpy as np

V4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(V4))
sys.path.insert(0, os.path.join(V4, "tools"))
from train_ann import rate_inputs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="c6-p-f")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--data", default=os.path.join(REPO, "Train", "datasets", "mnist"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import torch
    import torch.nn as nn
    import torchvision
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    tf = torchvision.transforms.Compose([torchvision.transforms.ToTensor(),
                                         torchvision.transforms.Resize((8, 8), antialias=True)])
    tr = torchvision.datasets.MNIST(a.data, train=True, download=True, transform=tf)
    te = torchvision.datasets.MNIST(a.data, train=False, download=True, transform=tf)
    dl = torch.utils.data.DataLoader(tr, batch_size=a.batch, shuffle=True)
    dt = torch.utils.data.DataLoader(te, batch_size=1000)
    mods, lin, shape = [], [], (1, 8, 8)
    for tok in a.arch.split("-"):
        if tok[0] == "c":
            m = nn.Conv2d(shape[0], int(tok[1:]), 3, bias=False)
            shape = (int(tok[1:]), shape[1] - 2, shape[2] - 2)
            mods += [m, nn.ReLU()]
        elif tok == "p":
            m = nn.AvgPool2d(2)
            shape = (shape[0], shape[1] // 2, shape[2] // 2)
            mods += [m]
        elif tok == "f":
            m = nn.Linear(int(np.prod(shape)), 10, bias=False)
            mods += [nn.Flatten(), m]
            shape = (10,)
        else:
            raise SystemExit("bad --arch token " + tok)
        lin.append((m, shape))
    net = nn.Sequential(*mods)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)
    lossf = nn.CrossEntropyLoss()

    def test():
        net.eval()
        c = n = 0
        with torch.no_grad():
            for x, y in dt:
                c += (net(x).argmax(1) == y).sum().item()
                n += len(y)
        net.train()
        return 100.0 * c / n

    for ep in range(a.epochs):
        for x, y in dl:
            opt.zero_grad()
            lossf(net(x), y).backward()
            opt.step()
        sched.step()
        print("epoch %d  MNIST-test(8x8) acc %.2f%%" % (ep + 1, test()), flush=True)

    # unroll: dense matrix of a bias-free linear layer = its response to the unit basis
    Ws, in_shape = [], (1, 8, 8)
    with torch.no_grad():
        for m, out_shape in lin:
            n_in = int(np.prod(in_shape))
            E = torch.eye(n_in).reshape(n_in, *in_shape)
            if isinstance(m, nn.Linear):
                E = E.reshape(n_in, -1)
            W = m(E).reshape(n_in, -1).T.numpy().astype(np.float64)
            W[np.abs(W) < 1e-6 * np.abs(W).max()] = 0.0   # float residue of the conv kernels
            Ws.append(W)
            in_shape = out_shape
    # check the unrolled network (ReLU after every layer except the last) against the CNN
    X, lab = rate_inputs()
    h = X
    for i, W in enumerate(Ws):
        h = h @ W.T
        if i < len(Ws) - 1:
            h = np.maximum(h, 0)
    with torch.no_grad():
        ref = net(torch.tensor(X, dtype=torch.float32).reshape(-1, 1, 8, 8)).numpy()
    err = float(np.max(np.abs(ref - h)))
    assert err < 1e-4, "unrolled network differs from the CNN (max err %g)" % err
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    np.savez(a.out, *Ws)
    nz = sum(int((W != 0).sum()) for W in Ws)
    tot = sum(W.size for W in Ws)
    print("saved %s  layers %s  nonzero weights %d of %d dense (unroll check max err %.1e)"
          % (a.out, [W.shape for W in Ws], nz, tot, err))
    print("ANN acc: MNIST test (8x8) %.2f%%, 1000 hardware images (rate input) %.2f%%" % (
        test(), 100.0 * (h.argmax(1) == lab).mean()))


if __name__ == "__main__":
    main()
