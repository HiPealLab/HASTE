#!/usr/bin/env bash
# Verilator check of the on-board wrapper (no Vivado needed).
# usage: board/tb/run_board_sim.sh [COUNT=50] [JOBS=4] [CFG=lif_64x10]
# Builds board/tb/tb_board.sv + board/rtl/* + the unchanged core, runs the
# first COUNT images of data/spikes.mem split over JOBS processes, writes
# board/sim/<cfg>/board_results.txt and compares it with the shipped
# golden build/<cfg>/rtl_results.txt (every field incl. CYCLES and spike train).
set -euo pipefail
V4="$(cd "$(dirname "$0")/../.." && pwd)"
COUNT=${1:-50}; JOBS=${2:-4}; CFG=${3:-lif_64x10}
MODEL=${CFG%%_*}
B="$V4/build/$CFG"
S="$V4/board/sim/$CFG"
mkdir -p "$S"
DEF=$(echo "MODEL_${MODEL}" | tr a-z A-Z)
cd "$S"
cp "$B/syn.mem" "$B/layer.mem" .   # the core $readmemh's them from the cwd
verilator --binary --timing -O3 -j 4 --Mdir obj_dir -Wall -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
  -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY \
  +define+$DEF -I"$B" --top-module tb_board \
  "$V4/rtl/snn_fifo.sv" "$V4/rtl/snn_${MODEL}.sv" "$V4/board/rtl/snn_board.sv" "$V4/board/rtl/snn_board_top.v" \
  "$V4/board/tb/tb_board.sv" > build.log 2>&1 || { cat build.log; exit 1; }
grep -E "%Warning" build.log | grep -v "/rtl/snn_" | head -20 || true
PER=$(( (COUNT + JOBS - 1) / JOBS )); pids=()
for ((p=0; p<JOBS; p++)); do
  ST=$((p*PER)); N=$PER
  (( ST + N > COUNT )) && N=$((COUNT - ST))
  (( N <= 0 )) && break
  ./obj_dir/Vtb_board +SPIKES="$V4/data/spikes.mem" +LABELS="$V4/data/labels.mem" +START=$ST +COUNT=$N \
    +SEED=$((p+1)) +OUT="part_$p.txt" > "sim_$p.log" 2>&1 &
  pids+=($!)
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
cat sim_*.log
(( rc == 0 )) || { echo "simulation failed"; exit 1; }
cat $(ls part_*.txt | sort -t_ -k2 -n) > board_results.txt && rm -f part_*.txt
echo "wrote $S/board_results.txt"
python3 "$V4/board/tools/compare_results.py" board_results.txt "$B/rtl_results.txt"
