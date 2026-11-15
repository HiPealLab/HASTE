#!/usr/bin/env bash
# Build (Verilator) and run the ANN baseline testbench on the 1000 test images,
# then compare with the bit-exact model (ref_int.txt): PRED and SCORES must match.
# usage: revision2/scripts/run_ann.sh <10|64x10|64x64x10>
set -euo pipefail
R2="$(cd "$(dirname "$0")/.." && pwd)"
TOPO=$1
B="$R2/build_ann/ann_${TOPO}"
cd "$B"
verilator --binary --timing -O3 -j 0 --Mdir obj_dir -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
  -I"$B" --top-module tb_ann "$R2/rtl/ann_q8.sv" "$R2/tb/tb_ann.sv" > build.log 2>&1 || { cat build.log; exit 1; }
./obj_dir/Vtb_ann +INPUTS="$R2/build_ann/inputs.mem" +LABELS="$R2/build_ann/labels.mem" +OUT=rtl_results.txt > sim.log 2>&1
python3 - "$B" <<'EOF'
import sys
b = sys.argv[1]
def rd(fn, rtl):
    d = {}
    for l in open(fn):
        p = l.split()
        if p and p[0] == "IMG":
            d[int(p[1])] = (int(p[3]), int(p[5]), p[p.index("SCORES") + 1:], int(p[7]) if rtl else None)
    return d
R, M = rd(b + "/rtl_results.txt", True), rd(b + "/ref_int.txt", False)
assert sorted(R) == sorted(M) == list(range(1000)), "image count"
same = sum(R[k][1] == M[k][1] and R[k][2] == M[k][2] for k in R)
acc = sum(R[k][1] == R[k][0] for k in R) / 10
cyc = sorted(set(R[k][3] for k in R))
print("%s: RTL == bit-exact model on %d/1000 images (pred + all scores), acc %.1f%%, cycles/img %s" % (b.split('/')[-1], same, acc, cyc))
EOF
