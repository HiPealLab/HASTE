# On-board latency and power measurement: manual

**Purpose.** The reviewer asked us to run the LIF 64x10 network on the physical xc7z010 board and to measure two things: wall-clock latency and board-level power. Both are then compared with our simulation and synthesis numbers.

**What you need:**
- The Zybo Z7-10 (or another xc7z010 board, see §8).
- Vivado 2022.2 and Vitis/XSCT 2022.2 on Linux.
- A USB power meter or a bench supply that shows current.
- About 2 hours.

**Working directory.** Run all commands from `code/HH-main/Hardware/Version-IV`. Do **not** modify `rtl/`, `build/` or `data/`.

The design has already been verified with Verilator on this side. All 1000 test images give identical spike counts, hidden-spike counts and spike trains, and the CYCLES offset is 0. The board must reproduce the CYCLES exactly.

---

## 0. One-time setup

1. **Digilent board files** (needed for the Zybo DDR settings):
   ```bash
   git clone https://github.com/Digilent/vivado-boards.git ~/vivado-boards
   ```
   We pass `board_repo=$HOME/vivado-boards/new/board_files` to the build in §1. Alternatively, copy that folder's contents into `<Vivado>/2022.2/data/boards/board_files/`.
2. **JTAG cable drivers.** If you have not installed them yet, run this once as root:
   ```bash
   sudo <Vivado>/2022.2/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers
   ```
3. **Serial port access.** `sudo usermod -aG dialout $USER`, then log out and back in. Install a terminal with `sudo apt install picocom`.
4. **Board jumpers:**
   - Boot-mode jumper (JP5 on the Zybo Z7): set to **JTAG**.
   - Power-select jumper (JP6 on the Zybo Z7, labelled USB/WALL): see §4.
   - Check the silkscreen, because older Zybo boards number the jumpers differently.

## 1. Build the bitstream (about 10–15 min)

```bash
source <Vivado>/2022.2/settings64.sh
vivado -mode batch -source board/vivado/build_board.tcl \
       -tclargs board_repo=$HOME/vivado-boards/new/board_files saif=auto | tee board_build_50MHz.log
```

The output goes to `board/vivado/out/lif_64x10_50MHz/`. Open `summary.txt` and check these lines:
- `FCLK_CLK0 requested=50MHz actual=50.000000MHz`
- `timing: ... MET`. If it says **NOT MET**, stop and send me `timing_summary.rpt`.
- The power lines.
- `saif=auto` uses `vivado/out/lif_64x10/activity.saif` from your earlier `vivado/saif.tcl` run, if it is still there. Otherwise the build prints a warning and reports vectorless power only, which is fine.
- `grep 8-4445 board_build_50MHz.log` must print nothing. The flow stops with an error if a weight file is missing.

The script already handles the defaults:
- Board part `digilentinc.com:zybo-z7-10:part0:1.2`. If you only have version 1.0 or 1.1 installed, the newest installed version is used automatically.
- FCLK = 50 MHz.
- AXI base address `0x43C00000`.

## 2. Data files and application (about 3 min)

```bash
python3 board/tools/make_bin.py            # -> board/data/spikes.bin (6.4 MB), labels.bin; prints "cross-check ... identical"
source <Vitis>/2022.2/settings64.sh
xsct board/sw/create_app.tcl               # -> prints "ELF: .../vitis_ws/snn_app/Release/snn_app.elf"
```

## 3. What the application does

These are the phases as they appear on the UART at 115200 8N1.

1. **Start-up.** It prints `ID 534e4e01 ...` and `FCLK measured 50000000 Hz`. The FCLK value is the PL clock measured against the ARM global timer and should be within ±0.01 %.
2. **LATENCY phase.** It runs all 1000 images once, which takes about 40 s with the UART printing. For each image it prints:
   - `SPK k t class` lines,
   - `IMG k LABEL l HID h OVF o CYCLES c COUNTS ...`, the same format as the testbench,
   - `TIME k XTIME_NS n HW_NS m`. Here n is the wall-clock time from writing START to seeing DONE, measured with XTime. m is CYCLES divided by the measured FCLK.

   The phase ends with a `SUMMARY` line.
3. **IDLE phase, 120 s.** The core is held in reset while the clock keeps running. The ARM performs the same bus traffic as in the continuous phase: it copies the images into the PL and polls the status register. Only the core is not computing.
4. **CONT phase, 120 s.** Continuous inference over the 1000 images. Every 10 s it prints a progress line with the duty cycle, which is the fraction of time the core is busy (expected above 90 %), and the cycle-count mismatches against the latency phase (must be 0).
5. **Repeat.** IDLE and CONT then alternate forever, as round 1, 2, 3, ... Stop the program by power-cycling the board.

## 4. Power measurement setup

**What can and cannot be measured.** The Zybo has **no on-board current sensor** and no power-monitor chip. The XADC in the Zynq measures only on-chip supply **voltages** and temperature, not current, so it cannot give power. We therefore measure the **board input power** and use differences between states.

Use one of these two setups, and keep the same setup for all readings:

- **Bench supply (preferred).** Feed 5.0 V into the barrel jack (centre positive, 2.1 mm), with the power jumper set to **WALL**. Read V and I from the supply. A resolution of 1 mA or better is needed.
- **USB power meter.** Put the meter between the PC and the Zybo's PROG/UART micro-USB port, with the power jumper set to **USB**. The meter must pass the data lines, because JTAG and UART run over the same cable. Read V and I, or W.

General rules:
- Do not touch the board or cables during readings.
- Keep the room temperature stable. Static power depends on temperature, so let the board warm up for 2 min first.

**The three states.** In each state, wait 30 s, then take **3 readings**, about 30 s apart (at roughly 30, 60 and 90 s). Write them into `power_50MHz.csv` like this:

```
state,volts,amps
a,5.012,0.312
...
```

| State | How to get there | Readings |
|---|---|---|
| **(a)** board powered, PL not configured | Power the board in JTAG boot mode and run nothing. The DONE LED is off. | 3 |
| **(b)** bitstream loaded, core idle in reset | §5: during `>>> PHASE IDLE round 1 START`, read at 30, 60 and 90 s after that line | 3 |
| **(c)** continuous inference | During `>>> PHASE CONT round 1 START`, read at 30, 60 and 90 s | 3 |

If you have time, also take round 2 (b and c again) as rows `b2`/`c2`. That shows whether the readings drift.

- **(c) − (b)** is the measured dynamic power of the inference. This is the number we compare with Vivado's estimate.
- **(b) − (a)** contains the PS software, DDR and PL configuration and clock tree. It is reported but not compared.

## 5. Run (latency + power)

1. **Terminal 1, start the UART logger first.** The Zybo usually shows up as two ports, `/dev/ttyUSB0` and `/dev/ttyUSB1`; the UART is normally `ttyUSB1`. Check with `ls /dev/ttyUSB*` after plugging in.
   ```bash
   picocom -b 115200 --logfile uart_50MHz.log /dev/ttyUSB1      # quit: Ctrl-A Ctrl-X
   ```
   Alternatives:
   - `screen -L -Logfile uart_50MHz.log /dev/ttyUSB1 115200`
   - the Vitis serial terminal, with "log to file" enabled.
2. **Before starting:** take the 3 readings of state **(a)**. The board has been powered for at least 2 min and nothing is programmed.
3. **Terminal 2:**
   ```bash
   xsct board/sw/run_board.tcl
   ```
   This takes about 20 s: it configures the PL, runs ps7_init, and downloads the ELF and the 6.4 MB of data over JTAG. Then the app starts.
4. Watch terminal 1 and take the **(b)** and **(c)** readings in round 1, and optionally round 2. Then quit picocom and power off.
5. **Check and summarise:**
   ```bash
   python3 board/tools/compare_results.py uart_50MHz.log build/lif_64x10/rtl_results.txt
   python3 board/tools/analyze_board.py uart_50MHz.log --readings power_50MHz.csv \
           --vivado board/vivado/out/lif_64x10_50MHz/summary.txt | tee analysis_50MHz.txt
   ```
   - `compared 1000 images ...: 1000 identical, 0 different; CYCLES offsets board-gold: [0]` and `RESULT: PASS` is the latency result. The hardware cycle count at 50 MHz equals the Verilator CYCLES for every image.
   - `analyze_board.py` prints the following, which together is the power result:
     - the mean and min/max XTime wall-clock per image,
     - the AXI/software overhead (XTime − CYCLES/f, expected below 1 µs),
     - the duty cycle,
     - the means and standard deviations of (a), (b) and (c),
     - (c)−(b), the energy per image, and Vivado's numbers.

## 6. Optional: 100 MHz (latency scales with the clock)

```bash
vivado -mode batch -source board/vivado/build_board.tcl -tclargs fclk=100 board_repo=$HOME/vivado-boards/new/board_files | tee board_build_100MHz.log
```

Check `board/vivado/out/lif_64x10_100MHz/summary.txt`:
- **Only if it says `timing: ... MET`**, continue:
  ```bash
  xsct board/sw/create_app.tcl xsa=board/vivado/out/lif_64x10_100MHz/snn_board.xsa
  xsct board/sw/run_board.tcl out=board/vivado/out/lif_64x10_100MHz
  ```
  Log to `uart_100MHz.log`. At 100 MHz the CYCLES must be identical to 50 MHz, and XTIME must be about half. Power readings at 100 MHz are welcome but optional.
- If timing is **NOT MET** (likely: the core's internal Fmax was about 84 MHz), use `fclk=62.5` instead in the commands above. It is exact from the 1 GHz IO PLL, and the output folder becomes `lif_64x10_62.5MHz`. Tell me which one you used.
- Do **not** use `saif=` for builds other than 50 MHz. The SAIF was recorded at 50 MHz.

## 7. What to send back

One zip with:
1. `uart_50MHz.log`, plus `uart_100MHz.log` or `uart_62.5MHz.log` if run. Send the complete raw logs.
2. `power_50MHz.csv` (and any other CSV files), with a note of the meter or supply model and its resolution, and which setup you used (barrel jack or USB).
3. **Photos:** the board setup with the meter, and one photo of the meter display per state (a, b, c), with the terminal visible if possible.
4. `analysis_50MHz.txt` and the output of `compare_results.py`.
5. From `board/vivado/out/lif_64x10_50MHz/` (and the 100/62.5 MHz folder): `summary.txt`, `utilization.rpt`, `utilization_hier.rpt`, `timing_summary.rpt`, `power_vectorless.rpt`, `power_saif.rpt` (if made), and `board_build_*.log`. Do not send the `.bit`, `.xsa` or `proj/`.
6. The room temperature (roughly), the board name and revision, and the Vivado/Vitis version.

## 8. Other xc7z010 boards / troubleshooting

**Other boards.** Pass `board_part=<vendor:board:part0:version>` to `build_board.tcl`. Examples:
- original Zybo: `digilentinc.com:zybo:part0:2.0`
- Cora Z7-10: `digilentinc.com:cora-z7-10:part0:1.1`
- Arty Z7-10: `digilentinc.com:arty-z7-10:part0:1.1`

The board preset applied to the PS7 sets that board's **DDR configuration**, MIO (UART) and clocks. Without a correct preset, DDR does not work. For a board without board files (e.g. EBAZ4205), use `board_part=none ps7_preset=<file.tcl>` with a Tcl file of `set_property -dict {CONFIG.PCW_...} [get_bd_cells processing_system7_0]` from the vendor. If the UART is not UART1, the standalone BSP picks the enabled UART automatically.

**Troubleshooting:**

| Symptom | Likely cause and fix |
|---|---|
| `FATAL: spikes.bin not found` | The `dow -data` addresses differ from main.c, or `make_bin.py` was not run. |
| `FATAL: wrapper ID mismatch` | Wrong bitstream, or the base address changed. |
| No UART output at all | Wrong ttyUSB port, or the logger was not started before `run_board.tcl`. Rerun `run_board.tcl`; it resets the system. |
| `run_board.tcl`: no targets | Cable drivers are missing, or the board is not in JTAG boot mode. Run `xsct`, then `connect; targets` to list the targets. |
