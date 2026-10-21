import os
import shutil
from pathlib import Path
import subprocess
import glob
from utils import gen_verilog
import sys

# ---------------------------------------------------------------------------
# Version-IV flow (parameterised RTL + generated memory images).
# The GUI hands over the float weights and one encoded spike train; the
# generator (Hardware/Version-IV/tools/gen_mem.py) quantises them to B-bit
# weights (synMem) and layer descriptors (layerMem); the unchanged RTL is then
# simulated with Verilator (default) or Questa/ModelSim.
# ---------------------------------------------------------------------------
V4_ROOT = Path(__file__).resolve().parents[2] / "Hardware" / "Version-IV"
# legacy Version-II Questa projects (used by run_questasim / run_verilog_project)
V2_ROOT = str(Path(__file__).resolve().parents[2] / "Hardware" / "Version-II")


def weights_from_synapse_map(synapse_map):
    """GUI synapse_map[l][src][dst].weight  ->  list of arrays W_l[dst, src].
    Does not modify the GUI objects (the old export normalised them in place)."""
    import numpy as np
    Ws = []
    for layer in synapse_map:
        n_src, n_dst = len(layer), len(layer[0])
        W = np.zeros((n_dst, n_src))
        for s_i, row in enumerate(layer):
            for d_i, conn in enumerate(row):
                W[d_i, s_i] = conn.weight
        Ws.append(W)
    return Ws


def run_hardware_v4(neuron_type, weights, spike_rows, out_dir="QuestasimRoot/v4",
                    weight_bits=8, simulator="verilator", overrides=None) -> dict:
    """Simulate one encoded image on the Version-IV RTL.

    neuron_type : "lif" | "izh" | "hh"
    weights     : list of float arrays, W_l shape (n_out_l, n_in_l)
    spike_rows  : T=100 lists of input indices that spike at each step
    returns     : {class: output spike count}, plus key "cycles"
    """
    sys.path.insert(0, str(V4_ROOT / "tools"))
    import gen_mem
    out = Path(out_dir).resolve()
    ov = dict(overrides or {})
    ov["WEIGHT_BITS"] = int(weight_bits)
    rec = gen_mem.write_net_from_weights(neuron_type, weights, str(out), ov, "gui")
    n_in = rec["n_in"]
    assert len(spike_rows) == 100, "the testbench replays T = 100 steps"
    with open(out / "spikes.mem", "w") as f:
        for row in spike_rows:
            row = [int(j) for j in row][:n_in]
            f.write(" ".join("%02x" % j for j in row + [255] * (n_in - len(row))) + "\n")
    (out / "labels.mem").write_text("0\n")
    rtl = [V4_ROOT / "rtl" / "snn_fifo.sv", V4_ROOT / "rtl" / f"snn_{neuron_type}.sv", V4_ROOT / "tb" / "tb_snn.sv"]
    define = "MODEL_" + neuron_type.upper()
    plus = [f"+SPIKES={out / 'spikes.mem'}", f"+LABELS={out / 'labels.mem'}", "+START=0", "+COUNT=1",
            f"+OUT={out / 'rtl_results.txt'}"]
    if simulator == "verilator":
        subprocess.run(["verilator", "--binary", "--timing", "-O3", "--Mdir", str(out / "obj_dir"), "-Wno-fatal",
                        "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", f"+define+{define}", f"-I{out}",
                        "--top-module", "tb_snn"] + [str(r) for r in rtl], check=True, cwd=out)
        subprocess.run([str(out / "obj_dir" / "Vtb_snn")] + plus, check=True, cwd=out)
    else:  # questa / modelsim
        subprocess.run(["vlib", "work"], check=True, cwd=out)
        subprocess.run(["vlog", "-sv", f"+define+{define}", f"+incdir+{out}"] + [str(r) for r in rtl], check=True, cwd=out)
        subprocess.run(["vsim", "-c", "work.tb_snn", "-do", "run -all; quit -f"] + plus, check=True, cwd=out)
    digits = {i: 0 for i in range(rec["sizes"][-1])}
    for line in (out / "rtl_results.txt").read_text().splitlines():
        p = line.split()
        if p and p[0] == "IMG":
            cnt = p[p.index("COUNTS") + 1:]
            digits = {i: int(c) for i, c in enumerate(cnt)}
            digits["cycles"] = int(p[p.index("CYCLES") + 1])
    return digits


def run_questasim(neuron_type, 
                  show_questasim=False, 
                  synMem_address=None, 
                  spike_image_address=None, 
                  root=V2_ROOT,
                  layer_count=3) -> dict:
    output = None
    if synMem_address == None or spike_image_address == None:
        if neuron_type=="hh":
            output = run_verilog_project("HH", show_questasim, root=root, layer_count=layer_count)
        elif neuron_type=="lif":
            output = run_verilog_project("LIF", show_questasim, root=root, layer_count=layer_count)
        elif neuron_type=="izh":
            output = run_verilog_project("IZHIKEVICH", show_questasim, root=root, layer_count=layer_count)
        else:
            raise NotImplementedError("We only support LIF, IZH and HH!")
    else:
        if neuron_type=="hh":
            output = run_verilog_project("HH", show_questasim, synMem_address, spike_image_address, root, layer_count=layer_count)
        elif neuron_type=="lif":
            output = run_verilog_project("LIF", show_questasim, synMem_address, spike_image_address, root, layer_count=layer_count)
        elif neuron_type=="izh":
            output = run_verilog_project("IZHIKEVICH", show_questasim, synMem_address, spike_image_address, root, layer_count=layer_count)
        else:
            raise NotImplementedError("We only support LIF, IZH and HH!")
        
    digits = {}
    for i in range(10):
        digits[i] = 0

    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("din ="):
            try:
                val = int(line.split("=")[1].strip())
                digits[val] += 1
            except ValueError:
                pass
    return digits

def run_verilog_project(neuron_type="LIF",
                      show_questasim=False, 
                      synMem_address=V2_ROOT + "/LIF/src/dendrites.svh", 
                      spike_image_address="Hardware/Version-II/LIF/src/spikes.svh", 
                      root=V2_ROOT,
                      layer_count=4) -> str:

    hdl_files = glob.glob(root + f"/{neuron_type}/**/*.sv", recursive=True)
    hdl_files.append(synMem_address)
    hdl_files.append(spike_image_address)

    target_root = Path("QuestasimRoot")
    src_dir = target_root / "src"
    prj_dir = target_root / "prj"
    
    shutil.rmtree(src_dir, ignore_errors=True)
    shutil.rmtree(prj_dir, ignore_errors=True)

    src_dir.mkdir(parents=True, exist_ok=True)
    prj_dir.mkdir(parents=True, exist_ok=True)



    (prj_dir / "gui_start.do").write_text("""
vlog +incdir+../src -sv ../src/*.sv
vsim work.neuron_tb
do wave.do
run -all
quit -force
""")

    for file_path in hdl_files:
        source = Path(root + "/" + file_path)
        source2 = Path(file_path)
        if source.exists():
            shutil.copy(source, src_dir / source.name)
        elif source2.exists():
            shutil.copy(source2, src_dir / source.name)
        else:
            print(f"Warning: {source} does not exist")
    
    syn_mem_path = src_dir / synMem_address.split(os.sep)[-1]
    if syn_mem_path.exists():
        syn_mem_new_path = src_dir / "dendrites.svh"
        syn_mem_path.rename(syn_mem_new_path)

    syn_mem_path = src_dir / spike_image_address.split(os.sep)[-1]
    if syn_mem_path.exists():
        syn_mem_new_path = src_dir / "spikes.svh"
        syn_mem_path.rename(syn_mem_new_path)

    source = Path(root + f"/{neuron_type}/project/wave.do")
    if source.exists():
        shutil.copy(source, prj_dir / source.name)
    else:
        print(f"Warning: {source} does not exist")

    print("Files copied successfully.")

    neuron_lay, neuron_ass = gen_verilog(layer_count)
    neuron_file = src_dir / "neuron.sv"

    with open(neuron_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Replace between //dynass markers
    start_idx = end_idx = None
    for i, line in enumerate(lines):
        if "//dynass" in line:
            if start_idx is None:
                start_idx = i
            else:
                end_idx = i
                break

    if start_idx is not None and end_idx is not None and end_idx > start_idx:
        lines = lines[:start_idx+1] + [neuron_ass + "\n"] + lines[end_idx:]
    else:
        print("Warning: Could not find two //dynass lines in neuron.sv")

    # Replace between //dynlay markers
    start_idx_dl = end_idx_dl = None
    for i, line in enumerate(lines):
        if "//dynlay" in line:
            if start_idx_dl is None:
                start_idx_dl = i
            else:
                end_idx_dl = i
                break

    if start_idx_dl is not None and end_idx_dl is not None and end_idx_dl > start_idx_dl:
        lines = lines[:start_idx_dl+1] + [neuron_lay + "\n"] + lines[end_idx_dl:]
    else:
        print("Warning: Could not find two //dynlay lines in neuron.sv")

    # Final write
    with open(neuron_file, "w", encoding="utf-8") as f:
        f.writelines(lines)



    project_dir = Path("QuestasimRoot/prj")
    os.chdir(project_dir)
    subprocess.run(["vlib", "work"], check=True)

    if (show_questasim):
        if os.name == "nt":
            subprocess.run(["vsim", "-do", "gui_start.do"], shell=True)
        else:
            subprocess.run(["vsim" ,"-do", "gui_start.do"])
    else:
        if os.name == "nt":
            subprocess.run(["vsim", "-c", "-do", "gui_start.do"], shell=True)
        else:
            subprocess.run(["vsim", "-c" ,"-do", "gui_start.do"])

    os.chdir("../..")

    output_file = Path("QuestasimRoot/prj/output.txt")
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            return f.read()
    else:
        print("Warning: output.txt not found after simulation.")
        return None
    





# output = run_verilog_project()
# digits = {}
# for i in range(10):
#     digits[i] = 0

# for line in output.split("\n"):
#     line = line.strip()
#     if line.startswith("din ="):
#         try:
#             val = int(line.split("=")[1].strip())
#             digits[val] += 1
#         except ValueError:
#             pass
# print(digits)