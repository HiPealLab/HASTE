#!/usr/bin/env bash
# Build (Verilator) and run the RTL testbench for one configuration.
# usage: scripts/run_rtl.sh <lif|izh|hh> <10|64x10|64x64x10> [START] [COUNT] [JOBS]
# Images are split over JOBS parallel simulator processes; results are merged
# into build/<model>_<topo>/rtl_results.txt
set -euo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"
MODEL=$1; TOPO=$2; START=${3:-0}; COUNT=${4:-1000}; JOBS=${5:-1}
B="$V4/build/${MODEL}_${TOPO}"
[ -f "$B/params.svh" ] || python3 "$V4/tools/gen_mem.py" net --model "$MODEL" --topo "$TOPO"
[ -f "$V4/data/spikes.mem" ] || python3 "$V4/tools/gen_mem.py" spikes
DEF=$(echo "MODEL_${MODEL}" | tr a-z A-Z)
cd "$B"
verilator --binary --timing -O3 -j 0 --Mdir obj_dir -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
  +define+$DEF -I"$B" --top-module tb_snn \
  "$V4/rtl/snn_fifo.sv" "$V4/rtl/snn_${MODEL}.sv" "$V4/tb/tb_snn.sv" > build.log 2>&1 || { cat build.log; exit 1; }
PER=$(( (COUNT + JOBS - 1) / JOBS )); pids=()
for ((p=0; p<JOBS; p++)); do
  S=$((START + p*PER)); N=$PER
  (( S + N > START + COUNT )) && N=$((START + COUNT - S))
  (( N <= 0 )) && break
  ./obj_dir/Vtb_snn +SPIKES="$V4/data/spikes.mem" +LABELS="$V4/data/labels.mem" +START=$S +COUNT=$N +OUT="part_$p.txt" > "sim_$p.log" 2>&1 &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done
cat part_*.txt > rtl_results.txt && rm -f part_*.txt
echo "wrote $B/rtl_results.txt"
