# revision2: experiments added for the second version of the HASTE paper

Everything here builds on `Hardware/Version-IV/` without modifying it: the cores in `rtl/`, the
testbenches in `tb/`, the reference models in `tools/` and the builds in `build/` are used as they are.
Paths below are relative to this folder unless they start with `Version-IV/`.

## Quantized 8-bit ANN core (same-device baseline)

- `rtl/ann_q8.sv`: integer ANN core with the serial datapath of the SNN cores. It reads the same
  `syn.mem` weight image (int8, address = neuron*FANIN + slot) as the SNN builds.
- `tb/tb_ann.sv`, `scripts/run_ann.sh <10|64x10|64x64x10>`: Verilator run on the 1000 test images
  (analog 8-bit pixels), compared with the bit-exact Python model (prediction and all 10 scores).
- `tools/gen_ann.py`: generates `build_ann/ann_<topo>/` (memories, parameters, bit-exact reference).
- `vivado/impl_ann.tcl`: out-of-context implementation on xc7z010clg400-1 at 50 MHz.

## Power from the routed netlist

- `vivado/netlist_saif.tcl`: simulates the routed netlist (`netlist_funcsim.v`), records SAIF
  activity on the implemented nets, runs `report_power` with it and checks the netlist output against
  the Verilator output. `vivado/run_rev2_all.tcl` runs it for all configurations and the ANN cores.
- `results/hw_netsaif_2026-11-15/`: raw outputs of that run (Vivado 2022.2).
  `vivado/out/<cfg>/` holds the SNN reports, `revision2/vivado/out/ann_<topo>/` the ANN reports;
  `power_netlist_saif.rpt` is the power report, `summary_netsaif.txt` the per-configuration summary.

## Statistics, latency model and sweeps (software)

| script | output in `results/` |
|---|---|
| `tools/stats.py`: McNemar tests, TOST equivalence, Wilson intervals, tie rules, ANN baselines | `stats_mcnemar.txt`, `stats_ties.txt`, `ann_baselines.txt` |
| `tools/check_cycles.py`, `tools/fit_cycles.py`: closed-form cycle model vs RTL cycle counts | `cycle_model_check.txt`, `cycle_model.txt`, `cycle_model.json` |
| `tools/sweep_dt.py` + `tools/summarize_sweeps.py`: Euler step and model-time-per-timestep sweeps (LIF, IZH, HH) | `sweep_*.jsonl`, `sweeps_summary.txt` |
| `tools/hh_failure.py`, `tools/hh_failure_ext.py` + `tools/summarize_hh_failure.py`: causes of the multi-layer HH failure (normalisation, synapse model, class-I Wang-Buzsaki neuron) | `hh_failure*.jsonl`, `hh_failure_summary.txt`, `hh_fI.txt` |
| `tools/hh_tune.py`: per-layer gain tuning of deep HH networks | `hh_tune_*.jsonl` |

`tools/runner.py` extends the reference model of `Version-IV/tools/ref_model.py` with event counters.
Gains are chosen on the 300-image tuning set (`Version-IV/data_val`), never on the test images.

Cycle model (exact on every checked image, all three neuron models and depths, CNN, B=4):
`cycles = 2*n_ops + 2*visits + sweeps + S*T + K*N*S*T + N + 1`, with K = 2 (LIF), 4 (IZH), 21 (HH).
