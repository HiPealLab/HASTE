# HASTE V4: on-board measurement kit (Zynq xc7z010)

This kit runs the unchanged `rtl/snn_lif.sv` core with the `build/lif_64x10` network on a Zynq-7010 board, such as a Digilent Zybo Z7-10. On the board it measures:

- the latency in clock cycles, using the same definition as `tb/tb_snn.sv`,
- the wall-clock time per image,
- the board input power in three states.

The step-by-step procedure for the person with the board is in **`MANUAL_BOARD.md`**.

```
board/
  rtl/snn_board.sv        PL wrapper: AXI4-Lite slave, spike-row BRAM, sequencer, counters, spike log
  rtl/snn_board_top.v     Verilog-2001 top with AXI interface attributes (Vivado module reference)
  tb/tb_board.sv          Verilator testbench: AXI4-Lite BFM doing what sw/main.c does
  tb/run_board_sim.sh     build + run tb_board, compare with build/<cfg>/rtl_results.txt
  tb/cosim/               host co-simulation: sw/main.c compiled for the host (mock BSP headers),
                          register accesses = AXI transactions on the Verilated wrapper
  vivado/build_board.tcl  PS7 + AXI interconnect + proc_sys_reset + wrapper -> bitstream, .xsa, reports
  vivado/board.xdc        (no constraints needed; the clock constraint comes from the PS7 IP)
  sw/main.c               bare-metal app: latency pass, then IDLE / CONTINUOUS power phases
  sw/create_app.tcl       XSCT: platform + app from the .xsa, build the ELF
  sw/run_board.tcl        XSCT: program PL, ps7_init, download ELF + data, run
  tools/make_bin.py       data/spikes.mem (or .npz) -> board/data/spikes.bin + labels.bin
  tools/compare_results.py  strict check of a UART log against the Verilator golden file (+ tools/score.py)
  tools/analyze_board.py  latency/duty summary of a UART log + power arithmetic from meter readings
  data/                   spikes.bin, labels.bin (generated, 1000 images)
  sim/                    local Verilator results (verify_1000.log, verify_50.log, cosim/cosim_uart.log)
```

## How the on-board CYCLES are made identical to the testbench

`tb_snn.sv` counts clock edges from the falling edge where `active` is set until the falling edge after the final STEP's `done`. CLEAR is accepted on the 2nd counted edge. Each later op is accepted on the first edge where the core is back in IDLE, which is the edge after the FIN state. The edge that leaves the last FIN is also counted.

The wrapper works the same way:

1. The edge where START is written counts as cycle 1, and it registers `op_valid` with CLEAR.
2. On every edge with `done = 1`, the wrapper registers the next op, so the core accepts it on the next edge.
3. The edge with `done = 1` of the final STEP is the last counted edge.

The next op (AXON index or STEP) is prefetched from the spike-row BRAM in 2 cycles. Every core op lasts much longer than that, so `done` never has to wait for the prefetch. If a prefetch were ever late, the sequencer would set STATUS.ERR. That cannot happen with this core.

The core is reset only by the AXI reset or by CTRL.CORE_RST, never between images. The FIFO's sticky `ovf` therefore behaves as it does in the testbench.

**Result (Verilator 5.052, `tb/run_board_sim.sh`):** all 1000 test images, and separately the first 50, match `build/lif_64x10/rtl_results.txt` exactly in every field: LABEL, HID, OVF, CYCLES and COUNTS, and the full output spike train. The CYCLES offset is 0, with no constant correction.

Two further checks also match exactly:

- T = 200 and T = 50, using `data_s1_T200/` against `rtl_results_s1_T200_T{200,50}.txt` (8 images each).
- The host co-simulation of `sw/main.c` (`tb/cosim/run_cosim.sh`, 50 images).

## Register map (AXI4-Lite, 32-bit, base `0x43C0_0000`, 64 KiB window)

| Offset | Name | Access | Content |
|---|---|---|---|
| 0x0000 | ID | R | `0x534E4E01` ("SNN", wrapper v1) |
| 0x0004 | CTRL | R/W | bit0 START (write 1; ignored while BUSY or in reset; reads 0). bit1 CORE_RST: 1 holds the core and sequencer in reset (idle mode) with the clock running. Writing START also needs bit1 = 0. |
| 0x0008 | STATUS | R | bit0 BUSY, bit1 DONE (cleared by START), bit2 OVF (core FIFO overflow, sticky since core reset), bit3 CORE_READY (core in IDLE), bit4 ERR (prefetch underrun, never expected), bit5 LOG_OVF (more than 1024 output spikes) |
| 0x000C | T | R/W | time steps per image, 1..T_MAX (default 100) |
| 0x0010 | CYCLES | R | cycles of the last image; same definition as `cyc` in tb_snn.sv |
| 0x0014 | HID | R | hidden-layer spikes (`hid_valid`) of the last image |
| 0x0018 | NSPK | R | output spikes (`out_valid`) of the last image |
| 0x001C | INFO | R | `{N_OUT[31:24], N_IN[23:16], T_MAX[15:0]}` (= `0x0A4000C8`) |
| 0x0020 | WALL_LO | R | free-running 64-bit PL clock counter, low word. Reading it latches the high word. |
| 0x0024 | WALL_HI | R | high word latched by the last WALL_LO read |
| 0x0028 | RUNS | R | images completed since core reset |
| 0x0040 + 4c | COUNT[c] | R | output spikes of class c (c < N_OUT) for the last image |
| 0x1000 + 4e | SPKLOG[e] | R | e-th output spike of the last image: `{t[15:8], class[7:0]}` (e < min(NSPK, 1024)) |
| 0x4000 + 4w | SBUF[w] | W | spike-row buffer, T_MAX × N_IN bytes. Word w = t·(N_IN/4) + s/4. Slot s is in bits [8·(s%4) +: 8]. |

Rules for using the registers:

- Use full 32-bit accesses only; WSTRB is ignored.
- Unmapped registers read `0xDEADBEEF`.
- Write SBUF only while not BUSY.
- Each row is the list of input indices that spike, terminated by `0xFF` (one line of `data/spikes.mem`). The PS only needs to write a row up to and including the word that holds the `0xFF`. If a row has 64 indices, the sequencer stops at slot 64.

Per image, the PS:

1. Writes the rows into SBUF.
2. Writes CTRL = 1.
3. Polls STATUS.DONE.
4. Reads CYCLES, HID, STATUS.OVF, COUNT[0..9], NSPK and SPKLOG.

## Data files (`tools/make_bin.py`)

All words are little-endian.

- `spikes.bin` = header `u32 0x534E4E53, n_img, rows, n_in`, followed by `u8 rows[n_img][rows][n_in]`. The payload is byte-for-byte `data/spikes.mem`, cross-checked against `data/spikes.npz`.
- `labels.bin` = `u32 0x4C4E4E53, n_img`, followed by `u8 label[n_img]`.

These are loaded with XSCT `dow -data` at `0x0800_0000` and `0x0F00_0000`.

## Resources, timing and risks

These estimates come from the RTL; Vivado has not been run on the wrapper.

**Wrapper resources:**

- Spike buffer: 3200 × 32 bit (100 Kb), about 3–4 RAMB36.
- Spike log: 1024 × 16 bit, 1 RAMB18.
- About 16 × 32-bit counters and a small FSM: a few hundred LUTs/FFs.
- The xc7z010 has 60 RAMB36, so BRAM is not a concern.

**Timing:**

- The core's own outputs are registered before the counters, so the wrapper does not extend the core's critical path.
- 50 MHz should close easily.
- 100 MHz will probably **not** close: the out-of-context internal Fmax of `snn_lif` was about 84 MHz.
- Look at the WNS in `summary.txt`. If 100 MHz fails, use `fclk=62.5`, which the PS7 IO PLL produces exactly (1 GHz / 16), to show that latency scales with the clock.

**Module reference:** the top is a plain Verilog file. The submodules are SystemVerilog, which Vivado 2020.2+ accepts under a module reference.

**`$readmemh` paths:** `syn.mem`/`layer.mem` are relative paths. The flow adds them as Memory Files and synthesises the block design globally (`synth_checkpoint_mode None`). A missing file (Synth 8-4445) stops the build with an ERROR.
