# Post-route Vivado results (paper Tables hw and hw-precision, Section "A Convolutional Network on the Same Core")

Vivado 2022.2, out-of-context synthesis and implementation on xc7z010clg400-1 with a 20 ns (50 MHz) clock constraint.
All 16 configurations come from one batch run: `vivado -mode batch -source vivado/run_all.tcl -tclargs saif`
(log: `logs/vivado_run_all.log`).

Per configuration (`<model>_<topology>[_b<bits>]/`):

- `utilization.rpt`, `timing.rpt`, `power.rpt`: post-route reports (power with SAIF activity of the first 10 test images)
- `netlist_check.txt`, `netlist_sim_results.txt`: gate-level simulation of the routed netlist (`vivado/netlist_sim.tcl`)
  compared with the Verilator RTL output in `build/<cfg>/rtl_results.txt`

`netlist_checks.txt` lists all 16 checks. 13 configurations are compared on whole images (3 images, or 1 for single-layer HH).
`hh_64x10`, `hh_64x64x10` and `lif_cnn` take hours per image at gate level, so they are compared on the first 10 (HH) or 20 (CNN)
timesteps of image 0 (prefix mode, 4th argument of `netlist_sim.tcl`). The raw simulator logs are in `logs/`.

`python3 tools/hw_report.py` prints the table used in the paper from these reports. F_max there is the register-to-register
value, 1/(20 ns - WNS_reg); the overall WNS also includes the I/O ports, whose generic out-of-context output budget (8 ns)
causes the small negative slacks on `hid_valid`/`out_valid`.

The on-board run of `lif_64x10` (Zynq-7010, 50 MHz) is in `../board/`: UART log of all 1000 images, `compare_results.py` output
(1000/1000 identical to the RTL, cycle offset 0), latency analysis and the reports of the board design.
