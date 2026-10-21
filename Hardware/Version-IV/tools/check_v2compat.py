#!/usr/bin/env python3
"""Proves ref_model reproduces the ORIGINAL Version-II LIF results
(Version-II/LIF/res/LIF_Results.txt) when run in v2compat mode."""
import os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import ref_model as rm
V4 = os.path.dirname(HERE); V2 = os.path.join(os.path.dirname(V4), "Version-II")
t = open(os.path.join(V2, "LIF/src/dendrites.svh")).read()
W = []
for m in re.finditer(r"reg \[7:0\] Den(\d+)\[64\] = '\{(.*?)\};", t, re.S):
    v = [int(b, 2) for b in re.findall(r"8'b([01]{8})", m.group(2))]
    W.append([x - 256 if x > 127 else x for x in v])
net = rm.Net(os.path.join(V4, "build/lif_64x10"), "v2compat", np.array(W, dtype=np.int64))
sp = np.load(os.path.join(V4, "data/spikes.npz"))["spikes"]
blocks, cur = [], []
for l in open(os.path.join(V2, "LIF/res/LIF_Results.txt")):
    l = l.strip()
    if l.startswith("---"): blocks.append(cur); cur = []
    elif l.startswith("din"): cur.append(int(l.split("=")[1]))
n = int(sys.argv[1]) if len(sys.argv) > 1 else len(blocks)
ok = 0
for k in range(n):
    out, _, _ = net.run_image(sp[k])
    got = [i for _, i in out]
    ok += got == blocks[k]
    if got != blocks[k] and k < 5: print("mismatch img", k, got, blocks[k])
print("v2compat: %d/%d images identical to Version-II LIF_Results.txt" % (ok, n))
