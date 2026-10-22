# HASTE: A Hardware-Aware End-to-End ANN-to-SNN Toolchain With HDL Co-Simulation

HASTE trains an artificial neural network (ANN), converts it into a spiking neural
network (SNN) with Leaky Integrate-and-Fire (LIF), Izhikevich (IZH) or
Hodgkin-Huxley (HH) neurons, and runs the same network on three paths that are
compared spike for spike:

- a **bit-exact software model** and a **floating-point model** (`tools/ref_model.py`),
- a **Brian2** simulation of the same network (`tools/brian2_ref.py`),
- a **parameterised SystemVerilog core** per neuron model, simulated with Verilator
  (or Questa/xsim) and implemented with Vivado for a Zynq-7010 (`xc7z010clg400-1`).

This repository contains the code, the trained weights, the generated memory
images, the encoded spike trains and the result files behind the IEEE Access paper.

## Repository layout

| Path | Contents |
|---|---|
| `App/` | PySide6 GUI: SNN training (SpikingJelly), inference, Brian2 simulation, hardware export |
| `Train/` | Notebooks, trained weights (`Train/outputs/`), the 1000 test images (`Train/test_images_1k/`) |
| `Hardware/Version-IV/` | **The evaluated hardware flow** (see below) |
| `Hardware/Version-I` … `Version-III/` | Earlier hardware versions, kept for reference; the GUI's legacy Questa path still uses Version-II |

`Hardware/Version-IV/`:

| Path | Contents |
|---|---|
| `rtl/` | `snn_lif.sv`, `snn_izh.sv`, `snn_hh.sv` (one time-multiplexed datapath per model) and `snn_fifo.sv` |
| `tools/gen_mem.py` | Quantises the trained weights and writes `build/<cfg>/`: `syn.mem`, `layer.mem`, `params.svh` |
| `build/<cfg>/` | The 16 evaluated configurations (memory images, parameters, RTL and reference results) |
| `build_seeds/` | The same networks retrained with training seeds 1–4 |
| `data/`, `data_s1` … `data_s5/` | The six Poisson encodings of the 1000 MNIST test images (8×8, T = 100) |
| `data_s*_T200/` | T = 200 encodings used for the time-window sweep |
| `data_val/` | 300 MNIST *training* images used to tune operating points |
| `tb/tb_snn.sv` | Testbench shared by all models and simulators |
| `scripts/` | Campaign scripts (Verilator, Questa, Vivado) |
| `vivado/` | Out-of-context implementation, SAIF power, post-route gate-level check |
| `board/` | On-board measurement kit (Zynq PS + PL wrapper, bare-metal app, host co-simulation) |
| `results/` | Summary tables and logs of the runs reported in the paper |

## Requirements

- Python ≥ 3.10 with `numpy`; `torch` and `torchvision` for training; `brian2` for the
  Brian2 baseline. The GUI needs everything in `App/requirements.txt`.
- [Verilator](https://verilator.org) ≥ 5.0 for RTL simulation (tested with 5.052).
- Optional: Questa/ModelSim, or AMD Vivado 2022.2 (synthesis, power, xsim) and
  Vitis 2022.2 (board).

MNIST is downloaded automatically by `torchvision` into `Train/datasets/` when needed.

## Quick start

```bash
cd Hardware/Version-IV
scripts/run_rtl.sh lif 64x10 0 100 4          # 100 images, 4 processes -> build/lif_64x10/rtl_results.txt
python3 tools/ref_model.py build/lif_64x10 --mode fixed --count 100
python3 tools/score.py build/lif_64x10/rtl_results.txt build/lif_64x10/ref_fixed.txt
```

The RTL and the bit-exact model must agree on every output spike (100 %).

GUI: `pip install -r App/requirements.txt`, then `python App/SNN/main.py`.

## Reproducing the paper

All commands run from `Hardware/Version-IV`. The shipped `build/` folders are the
ones that were simulated and implemented, so do not regenerate them
(`gen_mem.py prepare`) if you want to reproduce the published numbers exactly.

| Result | Command |
|---|---|
| Accuracy and agreement for all configurations (RTL, bit-exact, float) | `scripts/run_all.sh` → `results/summary.txt` |
| Brian2 agreement | `python3 scripts/campaign.py ref --mode brian2` |
| Six input encodings | `HASTE_DATA=data_sN python3 scripts/campaign.py sim` (N = 1…5; `data/` is the sixth), then `python3 tools/aggregate.py seeds` |
| T sweep over five encodings, deep-HH re-encodings | `scripts/revision_runs.sh`, then `python3 tools/agg_T.py` |
| Training-seed study | `scripts/seed_study.sh`, then `tools/agg_seeds.py` |
| Weight precision B = 4 / 8 / 16 | part of `scripts/run_all.sh` (`build/*_b4`, `*_b16`) |
| Convolutional network | `tools/train_cnn.py`; RTL with `scripts/run_rtl.sh lif cnn` |
| Deep-HH limitation (ablation, operating-point sweeps) | `tools/ablate_binary.py`, `tools/sweep.py` |
| Resources, F<sub>max</sub>, SAIF power (Vivado) | `vivado -mode batch -source vivado/run_all.tcl -tclargs saif`; published reports in `results/vivado/`, table with `python3 tools/hw_report.py` |
| Post-route netlist vs RTL (gate level) | `vivado -mode batch -source vivado/netlist_sim.tcl -tclargs <model> <topo> [<n_img> <t_prefix>]` → `results/vivado/netlist_checks.txt` |
| On-board latency | `board/README.md` and `board/MANUAL_BOARD.md`; the published run is in `results/board/` |
| Source ANNs | `tools/train_ann.py` (weights in `Train/outputs/`) |

Questa instead of Verilator: `python scripts/campaign.py all --sim questa`.

## Citation

If you use HASTE, please cite the paper (details will be added on publication) and
this software archive; see `CITATION.cff`.

## License

MIT, see `LICENSE`.
