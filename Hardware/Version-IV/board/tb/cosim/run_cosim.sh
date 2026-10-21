#!/usr/bin/env bash
# Host co-simulation: board/sw/main.c (unchanged, mock BSP) + Verilated PL wrapper.
# usage: board/tb/cosim/run_cosim.sh [COUNT=50] [CFG=lif_64x10]
# Writes board/sim/<cfg>/cosim_uart.log (= what the UART would print) and
# compares it with build/<cfg>/rtl_results.txt.
set -euo pipefail
V4="$(cd "$(dirname "$0")/../../.." && pwd)"
COUNT=${1:-50}; CFG=${2:-lif_64x10}
MODEL=${CFG%%_*}; B="$V4/build/$CFG"; S="$V4/board/sim/$CFG/cosim"; C="$V4/board/tb/cosim"
mkdir -p "$S"; cd "$S"
cp "$B/syn.mem" "$B/layer.mem" .
python3 "$V4/board/tools/make_bin.py" --count "$COUNT" --out "$S" > /dev/null
DEFS="-DSNN_BASE=0x43C00000u -DSPIKES_ADDR=0x08000000u -DLABELS_ADDR=0x0F000000u -DAPP_MAIN=app_main \
 -DPOWER_ROUNDS=1 -DIDLE_MS=30u -DCONT_MS=60u -DPROGRESS_MS=20u -DFCLK_MEAS_MS=2u"
cc -O2 -Wall -Wextra -I"$C/mock" $DEFS '-DDDR_PTR(a)=cosim_ddr(a)' -c "$V4/board/sw/main.c" -o main_host.o
DEF=$(echo "MODEL_${MODEL}" | tr a-z A-Z)
rm -f obj_dir/Vsnn_board_top   # relink with the fresh main_host.o
verilator --cc --exe --build -O3 -j 4 --Mdir obj_dir -Wno-fatal -Wno-lint -Wno-TIMESCALEMOD +define+$DEF -I"$B" \
  -CFLAGS "-O2 -I$C/mock $DEFS" -LDFLAGS "$S/main_host.o" --top-module snn_board_top \
  "$V4/rtl/snn_fifo.sv" "$V4/rtl/snn_${MODEL}.sv" "$V4/board/rtl/snn_board.sv" "$V4/board/rtl/snn_board_top.v" \
  "$C/cosim.cpp" > build.log 2>&1 || { tail -40 build.log; exit 1; }
./obj_dir/Vsnn_board_top spikes.bin labels.bin > cosim_uart.log
grep -E "^(===|ID|FCLK|SUMMARY|>>>|CONT|IDLE)" cosim_uart.log
python3 "$V4/board/tools/compare_results.py" cosim_uart.log "$B/rtl_results.txt"
