#!/usr/bin/env bash
# Revision runs: T sweep on encodings s2..s5 (T=200 encodings, prefixes 20/50/100/200),
# then the two deep HH networks on re-encodings s1..s5.
set -uo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"; cd "$V4"
while pgrep -f seed_study.sh > /dev/null; do sleep 60; done
J=${JOBS:-10}
for s in 2 3 4 5; do
  [ -f data_s${s}_T200/spikes.mem ] || python3 tools/gen_mem.py spikes --seed $s --T 200 > /dev/null
  for c in lif_10 lif_64x10 lif_64x64x10 izh_10 izh_64x10 izh_64x64x10 hh_10; do
    for T in 20 50 100 200; do
      f=rtl_results_s${s}_T200_T$T.txt
      [ -f build/$c/$f ] && continue
      scripts/run_rtl_dir.sh build/$c ${c%%_*} data_s${s}_T200 $J $f 1000 $T > /dev/null
      echo "[T] $c s$s T$T $(python3 tools/score.py build/$c/$f | head -1 | sed 's/.*acc=/acc=/')"
    done
  done
done
for s in 1 2 3 4 5; do
  for c in hh_64x10 hh_64x64x10; do
    f=rtl_results_s$s.txt
    [ -f build/$c/$f ] && continue
    scripts/run_rtl_dir.sh build/$c hh data_s$s $J $f > /dev/null
    echo "[HH] $c s$s $(python3 tools/score.py build/$c/$f | head -1 | sed 's/.*acc=/acc=/')"
  done
done
echo DONE
