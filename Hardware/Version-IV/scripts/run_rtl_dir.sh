#!/usr/bin/env bash
# Build (Verilator) and run the RTL testbench for an arbitrary build directory.
# usage: scripts/run_rtl_dir.sh <build_dir> <lif|izh|hh> [DATA_DIR=data] [JOBS=12] [OUT=rtl_results.txt] [COUNT=1000] [T]
set -euo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"
B=$(cd "$1" && pwd); MODEL=$2; D=${3:-data}; JOBS=${4:-12}; OUTF=${5:-rtl_results.txt}; COUNT=${6:-1000}; T=${7:-}
case "$D" in /*) ;; *) D="$V4/$D";; esac
DEF=$(echo "MODEL_${MODEL}" | tr a-z A-Z)
cd "$B"
[ -x obj_dir/Vtb_snn ] || verilator --binary --timing -O3 -j 0 --Mdir obj_dir -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
  +define+$DEF -I"$B" --top-module tb_snn \
  "$V4/rtl/snn_fifo.sv" "$V4/rtl/snn_${MODEL}.sv" "$V4/tb/tb_snn.sv" > build.log 2>&1 || { cat build.log; exit 1; }
EXTRA=(); [ -n "$T" ] && EXTRA+=(+T=$T +TDATA=200)
PER=$(( (COUNT + JOBS - 1) / JOBS )); pids=()
for ((p=0; p<JOBS; p++)); do
  S=$((p*PER)); N=$PER
  (( S + N > COUNT )) && N=$((COUNT - S))
  (( N <= 0 )) && break
  ./obj_dir/Vtb_snn +SPIKES="$D/spikes.mem" +LABELS="$D/labels.mem" +START=$S +COUNT=$N ${EXTRA[@]+"${EXTRA[@]}"} +OUT="part_$p.txt" > "sim_$p.log" 2>&1 &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done
cat $(ls part_*.txt | sort -t_ -k2 -n) > "$OUTF" && rm -f part_*.txt
echo "wrote $B/$OUTF"
