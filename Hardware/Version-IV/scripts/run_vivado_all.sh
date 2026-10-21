#!/usr/bin/env bash
# Vivado implementation + reports for every configuration (run on a machine
# with Vivado in PATH).  SAIF=1 additionally captures switching activity with
# xsim (first 10 images) and uses it for report_power.
# Result table -> vivado/out/summary_all.txt
set -uo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"; cd "$V4"
CFGS=${CFGS:-"lif_10 lif_64x10 lif_64x64x10 izh_10 izh_64x10 izh_64x64x10 hh_10 hh_64x10 hh_64x64x10 lif_64x10_b4 lif_64x10_b16 izh_64x10_b4 izh_64x10_b16 hh_10_b4 hh_10_b16"}
mkdir -p vivado/out
for c in $CFGS; do
  m=${c%%_*}; t=${c#*_}
  if [ ! -f build/$c/params.svh ]; then
    case $t in *_b*) python3 tools/gen_mem.py net --model $m --topo ${t%_b*} --out build/$c --set WEIGHT_BITS=${t##*_b};;
               *) python3 tools/gen_mem.py net --model $m --topo $t;; esac
  fi
  S=""
  if [ "${SAIF:-0}" = 1 ]; then
    vivado -mode batch -nojournal -log vivado/out/saif_$c.log -source vivado/saif.tcl -tclargs $m $t 10 && S=vivado/out/$c/activity.saif
  fi
  vivado -mode batch -nojournal -log vivado/out/impl_$c.log -source vivado/impl.tcl -tclargs $m $t $S
done
cat vivado/out/*/summary.txt > vivado/out/summary_all.txt; cat vivado/out/summary_all.txt
