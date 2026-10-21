#!/usr/bin/env python3
"""ANN ablation behind the deep-HH limitation: replace every hidden ReLU of the
trained MLP by an on/off step and measure the accuracy that is left.
usage: ablate_binary.py [TOPO ...]          (default: 64x10 64x64x10)
Inputs are the spike rates of the encoded images in $HASTE_DATA (default
data_val/, the 300-image tuning set of MNIST training images), i.e. what the
SNN actually sees.  Activations per hidden layer:
  relu          max(a, 0)                       (the trained network)
  step>0        1 if a > 0                      (an on/off unit, e.g. HH)
  step>q*max    1 if a > q * max_j a_j          (on/off with a raised threshold)"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); V4 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gen_mem


def rates(data_dir):
    d = np.load(os.path.join(V4, data_dir, "spikes.npz"))
    S, y = d["spikes"], d["labels"]
    x = np.zeros((len(S), gen_mem.N_IN))
    for i, img in enumerate(S):
        for row in img:
            for j in row:
                if j == 255:
                    break
                x[i, j] += 1
    return x / S.shape[1], y


def accuracy(Ws, x, y, act):
    h = x
    for W in Ws[:-1]:
        h = act(h @ W.T)
    return 100 * ((h @ Ws[-1].T).argmax(1) == y).mean()


def main():
    topos = sys.argv[1:] or ["64x10", "64x64x10"]
    dd = os.environ.get("HASTE_DATA", "data_val")
    x, y = rates(dd)
    acts = [("relu", lambda a: np.maximum(a, 0)),
            ("step>0", lambda a: (a > 0).astype(float))]
    for q in (0.1, 0.3):
        acts.append(("step>%.1f*max" % q, lambda a, q=q: (a > q * a.max(1, keepdims=True)).astype(float)))
    print("%d images from %s/" % (len(y), dd))
    for t in topos:
        Ws = gen_mem.load_weights(t)
        print("%-10s " % t + "  ".join("%s %.1f%%" % (n, accuracy(Ws, x, y, f)) for n, f in acts))


if __name__ == "__main__":
    main()
