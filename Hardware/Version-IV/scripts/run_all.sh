#!/usr/bin/env bash
# Full campaign: 3 models x 3 topologies x 1000 test images.
#   RTL (Verilator)  -> build/<cfg>/rtl_results.txt
#   bit-exact model  -> build/<cfg>/ref_fixed.txt   (must equal RTL spike-for-spike)
#   float model      -> build/<cfg>/ref_float.txt   (unquantised weights, ideal arithmetic)
# Summary -> results/summary.txt
set -uo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"; cd "$V4"
J=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc)}
N=${COUNT:-1000}
MODELS=${MODELS:-"lif izh hh"}; TOPOS=${TOPOS:-"10 64x10 64x64x10"}
mkdir -p results
[ -f data/spikes.mem ] || python3 tools/gen_mem.py spikes
PREC=${PREC:-"4 16"}   # extra weight widths, on topology 64x10
for m in $MODELS; do for t in $TOPOS; do
  python3 tools/gen_mem.py net --model $m --topo $t > /dev/null
  echo "[$(date +%T)] RTL $m $t"; scripts/run_rtl.sh $m $t 0 $N $J
done; done
for m in $MODELS; do for b in $PREC; do
  python3 tools/gen_mem.py net --model $m --topo 64x10 --out build/${m}_64x10_b$b --set WEIGHT_BITS=$b > /dev/null
  echo "[$(date +%T)] RTL $m 64x10 B=$b"; scripts/run_rtl.sh $m 64x10_b$b 0 $N $J
done; done
for m in $MODELS; do for t in $TOPOS; do
  echo "[$(date +%T)] ref $m $t"
  python3 tools/ref_model.py build/${m}_$t --mode fixed --count $N --jobs $J > /dev/null
  python3 tools/ref_model.py build/${m}_$t --mode float --count $N --jobs $J > /dev/null
done; done
for m in $MODELS; do for b in $PREC; do
  echo "[$(date +%T)] ref $m 64x10 B=$b"
  python3 tools/ref_model.py build/${m}_64x10_b$b --mode fixed --count $N --jobs $J > /dev/null
done; done
{
for m in $MODELS; do for t in $TOPOS; do
  echo "=== $m $t (B=8)"
  python3 tools/score.py build/${m}_$t/rtl_results.txt build/${m}_$t/ref_fixed.txt | tail -1 | sed 's/^/RTL vs fixed-point model: /'
  python3 tools/score.py build/${m}_$t/rtl_results.txt build/${m}_$t/ref_float.txt | sed -n '1p;$p' | sed 's/^agreement/RTL vs float model agreement/'
done; done
for m in $MODELS; do for b in $PREC; do
  echo "=== $m 64x10 (B=$b)"
  python3 tools/score.py build/${m}_64x10_b$b/rtl_results.txt build/${m}_64x10_b$b/ref_fixed.txt | sed -n '1p;$p' | sed 's/^agreement/RTL vs fixed-point model agreement/'
done; done
} > results/summary.txt
echo "[$(date +%T)] done"; cat results/summary.txt
