#!/usr/bin/env python3
"""Operating-point sweep with the bit-exact reference model (fast, no RTL).
usage: sweep.py MODEL TOPO N_IMAGES KEY=v1,v2 [KEY=v1,v2 ...] [--float]
TOPO is a key of gen_mem.TOPOS or a path to a weights .npz.
Per point: accuracy of the fixed-point model, ties (several classes share the
maximum count), no-spike images, spikes per image; with --float also the
float64 model's accuracy and the fixed-vs-float class agreement."""
import itertools, os, subprocess, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); V4 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import score
args = [x for x in sys.argv[1:] if x != "--float"]
with_float = "--float" in sys.argv
model, topo, n = args[0], args[1], int(args[2])
src = ["--npz", topo] if topo.endswith(".npz") else ["--topo", topo]
keys, vals = [], []
for kv in args[3:]:
    k, v = kv.split("="); keys.append(k); vals.append(v.split(","))


def load(path):
    A = score.load(path)
    ks = sorted(A)
    lab = np.array([A[k]["label"] for k in ks]); C = np.array([A[k]["counts"] for k in ks])
    nos = C.sum(1) == 0
    pred = np.where(nos, -1, C.argmax(1))
    ties = ((C == C.max(1, keepdims=True)).sum(1) > 1) & ~nos
    return A, ks, lab, C, nos, pred, ties


for combo in itertools.product(*vals):
    d = tempfile.mkdtemp()
    sets = ["%s=%s" % kv for kv in zip(keys, combo)]
    subprocess.run([sys.executable, os.path.join(HERE, "gen_mem.py"), "net", "--model", model] + src + ["--out", d, "--set"] + sets, check=True, capture_output=True)
    subprocess.run([sys.executable, os.path.join(HERE, "ref_model.py"), d, "--count", str(n)], check=True, capture_output=True)
    A, ks, lab, C, nos, pred, ties = load(os.path.join(d, "ref_fixed.txt"))
    line = "%-40s acc=%.1f%% ties=%d nospike=%d hid/img=%.0f out/img=%.1f" % (
        " ".join(sets), 100 * (pred == lab).mean(), ties.sum(), nos.sum(), np.mean([A[k]["hid"] for k in ks]), C.sum(1).mean())
    if with_float:
        subprocess.run([sys.executable, os.path.join(HERE, "ref_model.py"), d, "--mode", "float", "--count", str(n)], check=True, capture_output=True)
        _, _, labf, Cf, nosf, predf, _ = load(os.path.join(d, "ref_float.txt"))
        line += "  float acc=%.1f%% agree=%.1f%%" % (100 * (predf == labf).mean(), 100 * (pred == predf).mean())
    print(line, flush=True)
