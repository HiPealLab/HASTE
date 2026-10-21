#!/usr/bin/env python3
"""Train a bias-free ReLU MLP on MNIST resized to 8x8 (the hardware input
format) and save it in the format the generator expects.

  python tools/train_ann.py --hidden 64 64 --epochs 30 --out Train/outputs/weights-64x64x10.npz
  python tools/gen_mem.py net --model lif --npz Train/outputs/weights-64x64x10.npz   # -> build/lif_weights-64x64x10

Output npz: arr_0 .. arr_{L-1}, arr_l has shape (out_l, in_l) (torch Linear layout).
Reported accuracies:
  * MNIST test set (10k, 8x8 bilinear resize, as in Train/ANN2SNN.ipynb)
  * the 1000 hardware test images, using their Poisson spike *rates* from
    data/spikes.npz as input (= the input the SNN actually sees)
"""
import argparse
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(V4))


def rate_inputs():
    d = np.load(os.path.join(V4, "data", "spikes.npz"))
    sp, lab = d["spikes"], d["labels"]
    X = np.zeros((len(lab), 64))
    for k in range(len(lab)):
        for t in range(sp.shape[1]):
            for j in sp[k, t]:
                if j == 255:
                    break
                X[k, j] += 1
    return X / sp.shape[1], lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hidden", type=int, nargs="*", default=[64, 64], help="hidden layer sizes ([] = 64->10)")
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
    sizes = [64] + a.hidden + [10]
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1], bias=False))  # hardware has no bias
        if i < len(sizes) - 2:
            layers.append(nn.ReLU())
    net = nn.Sequential(nn.Flatten(), *layers)
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
    Ws = [m.weight.detach().numpy().astype(np.float64) for m in net if isinstance(m, nn.Linear)]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    np.savez(a.out, *Ws)
    X, lab = rate_inputs()
    h = X
    for i, W in enumerate(Ws):
        h = h @ W.T
        if i < len(Ws) - 1:
            h = np.maximum(h, 0)
    print("saved %s  topology %s" % (a.out, "x".join(map(str, sizes[1:]))))
    print("ANN acc: MNIST test (8x8) %.2f%%, 1000 hardware images (rate input) %.2f%%" % (
        test(), 100.0 * (h.argmax(1) == lab).mean()))


if __name__ == "__main__":
    main()
