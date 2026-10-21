#!/usr/bin/env bash
# Training-seed study: retrain the source ANNs with seeds 1..4 and run the RTL
# (== bit-exact model) for LIF/IZH (all topologies) and HH 10 on the original encoding.
set -uo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"; cd "$V4"
W="$V4/../../Train/outputs/seeds"; mkdir -p "$W" results/seed_study
for s in 1 2 3 4; do
  for t in 10 64x10 64x64x10; do
    case $t in 10) H="";; 64x10) H="64";; 64x64x10) H="64 64";; esac
    npz="$W/weights-$t-s$s.npz"
    [ -f "$npz" ] || python3 tools/train_ann.py --hidden $H --epochs 30 --seed $s --out "$npz" 2>/dev/null | grep -a "ANN acc" | sed "s/^/[ann $t s$s] /"
    for m in lif izh hh; do
      [ $m = hh ] && [ $t != 10 ] && continue
      B="build_seeds/${m}_${t}_s$s"
      [ -f "$B/rtl_results.txt" ] && continue
      python3 tools/gen_mem.py net --model $m --npz "$npz" --out "$B" > /dev/null
      scripts/run_rtl_dir.sh "$B" $m data 8 > /dev/null && echo "[rtl] $B $(python3 tools/score.py $B/rtl_results.txt | head -3 | tr '\n' ' ')"
    done
  done
done
echo DONE
