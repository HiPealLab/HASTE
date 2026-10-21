#!/usr/bin/env python3
"""Accuracy / agreement report for result files written by the RTL testbench
(tb/tb_snn.sv) or by tools/ref_model.py (same format).

  python3 tools/score.py A.txt            -> accuracy of A
  python3 tools/score.py A.txt B.txt      -> accuracy of both + agreement A vs B
                                             (class agreement and exact spike-train equality)
Prediction = argmax of output spike counts; images with no output spike are
counted as wrong (reported separately); ties are reported."""
import sys
import numpy as np

def load(fn):
    img, spk = {}, {}
    for line in open(fn):
        p = line.split()
        if not p: continue
        if p[0] == "IMG":
            k = int(p[1]); d = dict(zip(p[2::2], p[3::2]))
            c = np.array([int(x) for x in p[p.index("COUNTS") + 1:]])
            img[k] = dict(label=int(p[3]), counts=c, spk=[], cyc=int(d.get("CYCLES", 0)), hid=int(d.get("HID", 0)), ovf=int(d.get("OVF", 0)))
        elif p[0] == "SPK":
            spk.setdefault(int(p[1]), []).append((int(p[2]), int(p[3])))
    for k in img:
        img[k]["spk"] = spk.get(k, [])
    return img

def summary(name, d):
    ks = sorted(d); n = len(ks)
    lab = np.array([d[k]["label"] for k in ks]); C = np.array([d[k]["counts"] for k in ks])
    nos = C.sum(1) == 0; pred = C.argmax(1)
    top = C.max(1, keepdims=True); tie = ((C == top).sum(1) > 1) & ~nos
    corr = (pred == lab) & ~nos
    cyc = np.array([d[k]["cyc"] for k in ks])
    print("%s: n=%d  acc=%.2f%%  (no-spike=%d, ties=%d, acc excl. no-spike=%.2f%%)  hid/img=%.1f  ovf=%d%s" % (
        name, n, 100 * corr.mean(), nos.sum(), tie.sum(), 100 * corr[~nos].mean() if (~nos).any() else 0,
        np.mean([d[k]["hid"] for k in ks]), sum(d[k]["ovf"] for k in ks),
        ("  cycles/img mean=%.0f (%.2f ms @50MHz)" % (cyc.mean(), cyc.mean() / 50e3)) if cyc.any() else ""))
    return pred, nos

if __name__ == "__main__":
    A = load(sys.argv[1]); pa, na = summary(sys.argv[1], A)
    if len(sys.argv) > 2:
        B = load(sys.argv[2]); ks = sorted(set(A) & set(B))
        B = {k: B[k] for k in ks}; A2 = {k: A[k] for k in ks}
        pa, na = summary(sys.argv[1] + " (common)", A2); pb, nb = summary(sys.argv[2] + " (common)", B)
        same_cls = ((pa == pb) & (na == nb)) | (na & nb)
        exact = np.mean([A2[k]["spk"] == B[k]["spk"] for k in ks])
        print("agreement on %d images: class %.2f%%, exact spike trains %.2f%%" % (len(ks), 100 * same_cls.mean(), 100 * exact))
