import os
import shutil
from pathlib import Path
import subprocess

def run_questasim(show_questasim=False):
    hdl_files = [
        "Hardware/Version-I/ModuleGenerator/Generator/Test/snnTb.sv", "Hardware/Version-I/ModuleGenerator/Generator/Test/spikes.svh",
        "Hardware/Version-I/ModuleGenerator/Generator/Modules/Single/layerMem.sv", "Hardware/Version-I/ModuleGenerator/Generator/Modules/Single/synMem.sv",
        "Hardware/Version-I/Src/frFifo.sv", "Hardware/Version-I/Src/neumMgNa_memory.sv", "Hardware/Version-I/Src/neumHgL_memory.sv", "Hardware/Version-I/Src/neumNgK_memory.sv",
        "Hardware/Version-I/Src/neumVolt_memory.sv", "Hardware/Version-I/Src/ngvController.sv", "Hardware/Version-I/Src/ngvLut.sv", "Hardware/Version-I/Src/ngvmodules.sv",
        "Hardware/Version-I/Src/ngvMult.sv", "Hardware/Version-I/Src/ngvtb.sv", "Hardware/Version-I/Src/ngvUnit.sv", "Hardware/Version-I/Src/SNN.sv", "Hardware/Version-I/Src/snnController.sv",
        "Hardware/Version-I/Src/synUnit.sv", "Hardware/Version-I/Src/vdfMult.sv", "Hardware/Version-I/Src/vdfUnit.sv"
    ]

    target_root = Path("QuestasimRoot")
    src_dir = target_root / "src"
    prj_dir = target_root / "prj"

    src_dir.mkdir(parents=True, exist_ok=True)
    prj_dir.mkdir(parents=True, exist_ok=True)

    (prj_dir / "gui_start.do").write_text("""
vlog +incdir+../src -sv ../src/*.sv
vsim work.snnTb
do wave.do
run -all
quit -force
""")

    for file_path in hdl_files:
        source = Path(file_path)
        if source.exists():
            shutil.copy(source, src_dir / source.name)
        else:
            print(f"Warning: {source} does not exist")

    source = Path("Hardware/Version-I/questasim/wave.do")
    if source.exists():
        shutil.copy(source, prj_dir / source.name)
    else:
        print(f"Warning: {source} does not exist")

    print("Files copied successfully.")

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
        # result_dir = Path("results")
        # result_dir.mkdir(exist_ok=True)
        # shutil.copy(output_file, result_dir / "output.txt")
        return None
    else:
        print("Warning: output.txt not found after simulation.")
        return None

run_questasim()