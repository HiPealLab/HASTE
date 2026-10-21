#!/usr/bin/env python3
"""HASTE Version-IV campaign runner (Windows / Linux / macOS).

  python scripts/campaign.py prepare                      # data/ + all build dirs
  python scripts/campaign.py sim   --sim questa  [--cfg lif_64x10 ...] [--count 1000] [--jobs 8]
  python scripts/campaign.py ref   --mode fixed|float|brian2 [--cfg ...] [--count 1000]
  python scripts/campaign.py summary [--sim questa]       # results/summary.md
  python scripts/campaign.py all   --sim questa           # everything above
  python scripts/campaign.py crosscheck --sim questa      # Questa vs shipped Verilator results, line by line
  add --T 50 to sim/ref/summary for a shorter time window (T sweep; files get suffix _T50)

Simulators: verilator (default on Linux/macOS), questa (vlog/vsim in PATH),
xsim (Vivado xvlog/xelab/xsim in PATH).  RTL results go to
build/<cfg>/rtl_<sim>.txt (verilator: rtl_results.txt, kept for compatibility).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

V4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
WIN = os.name == "nt"
sys.path.insert(0, os.path.join(V4, "tools"))
import gen_mem  # noqa: E402

CFGS = ["%s_%s" % (m, t) + ("" if b == 8 else "_b%d" % b) for (m, t, b) in gen_mem.ALL_CONFIGS]


def sh(cmd, cwd, log=None):
    out = open(log, "w") if log else None
    r = subprocess.run(cmd, cwd=cwd, shell=WIN, stdout=out or None, stderr=subprocess.STDOUT if out else None)
    if out:
        out.close()
    if r.returncode != 0:
        raise SystemExit("command failed (%s): %s%s" % (r.returncode, " ".join(cmd), ("  -> see " + log) if log else ""))


def rtl_name(sim):
    """result file name; with HASTE_DATA=data_sN the suffix _sN is added, with --T N the suffix _TN."""
    tag = "" if os.environ.get("HASTE_DATA", "data") == "data" else "_" + os.path.basename(os.environ["HASTE_DATA"]).replace("data_", "")
    if os.environ.get("HASTE_T"):
        tag += "_T%s" % os.environ["HASTE_T"]
    return ("rtl_results%s.txt" if sim == "verilator" else "rtl_%s%%s.txt" % sim) % tag


def prepare(_a=None):
    if not os.path.exists(os.path.join(V4, "data", "spikes.mem")):
        gen_mem.write_spikes(os.path.join(V4, "data"))
    for (m, t, b) in gen_mem.ALL_CONFIGS:
        name = "%s_%s" % (m, t) + ("" if b == 8 else "_b%d" % b)
        gen_mem.write_net(m, t, os.path.join(V4, "build", name), {"WEIGHT_BITS": b})


def sim_cfg(cfg, sim, count, jobs):
    model = cfg.split("_")[0]
    B = os.path.join(V4, "build", cfg)
    if not os.path.exists(os.path.join(B, "params.svh")):
        prepare()
    define = "MODEL_" + model.upper()
    srcs = [os.path.join(V4, "rtl", "snn_fifo.sv"), os.path.join(V4, "rtl", "snn_%s.sv" % model),
            os.path.join(V4, "tb", "tb_snn.sv")]
    spikes = os.path.join(gen_mem.data_dir(), "spikes.mem")
    labels = os.path.join(gen_mem.data_dir(), "labels.mem")
    t0 = time.time()
    # ---- compile once
    if sim == "verilator":
        sh(["verilator", "--binary", "--timing", "-O3", "--Mdir", "obj_dir", "-Wno-fatal", "-Wno-WIDTHEXPAND",
            "-Wno-WIDTHTRUNC", "+define+" + define, "-I" + B, "--top-module", "tb_snn"] + srcs, B,
           os.path.join(B, "build_verilator.log"))
        run = lambda plus: [os.path.join(B, "obj_dir", "Vtb_snn")] + plus
    elif sim == "questa":
        lib = "questa_work"
        shutil.rmtree(os.path.join(B, lib), ignore_errors=True)
        sh(["vlib", lib], B)
        sh(["vlog", "-work", lib, "-sv", "+define+" + define, "+incdir+" + B] + srcs, B, os.path.join(B, "build_questa.log"))
        run = lambda plus: ["vsim", "-c", "-lib", lib, "tb_snn", "-do", "run -all; quit -f"] + plus
    elif sim == "xsim":
        sh(["xvlog", "-sv", "-d", define, "-i", B] + srcs, B, os.path.join(B, "build_xsim.log"))
        sh(["xelab", "tb_snn", "-s", "tb_snn_snap"], B, os.path.join(B, "elab_xsim.log"))
        run = lambda plus: ["xsim", "tb_snn_snap", "-R"] + sum([["-testplusarg", p[1:]] for p in plus], [])
    else:
        raise SystemExit("unknown simulator " + sim)
    import numpy as np
    tdata = np.load(os.path.join(gen_mem.data_dir(), "spikes.npz"))["spikes"].shape[1]
    # ---- run image ranges in parallel
    per = (count + jobs - 1) // jobs
    procs, parts = [], []
    for p in range(jobs):
        s = p * per
        n = min(per, count - s)
        if n <= 0:
            break
        part = os.path.join(B, "part_%d.txt" % p)
        plus = ["+SPIKES=" + spikes, "+LABELS=" + labels, "+START=%d" % s, "+COUNT=%d" % n, "+OUT=" + part,
                "+TDATA=%d" % tdata, "+T=%d" % int(os.environ.get("HASTE_T", tdata))]
        cmd = run(plus)
        if sim == "questa":
            cmd += ["-l", "sim_%d.log" % p]
        elif sim == "xsim":
            cmd += ["-log", "sim_%d.log" % p]
        log = open(os.path.join(B, "run_%d.log" % p), "w")
        procs.append((subprocess.Popen(cmd, cwd=B, shell=WIN, stdout=log, stderr=subprocess.STDOUT), log))
        parts.append(part)
    for pr, log in procs:
        pr.wait()
        log.close()
    with open(os.path.join(B, rtl_name(sim)), "w") as f:
        for part in parts:
            f.write(open(part).read())
            os.remove(part)
    print("[%s] %s: %d images in %.0f s -> %s" % (sim, cfg, count, time.time() - t0, rtl_name(sim)), flush=True)


def ref_cfg(cfg, mode, count, jobs):
    B = os.path.join(V4, "build", cfg)
    tag = rtl_name("verilator")[len("rtl_results"):-4]
    out = os.path.join(B, "ref_%s%s.txt" % (mode, tag))
    if mode == "brian2":
        sh([PY, os.path.join(V4, "tools", "brian2_ref.py"), B, "--count", str(count), "--out", out], V4)
    else:
        sh([PY, os.path.join(V4, "tools", "ref_model.py"), B, "--mode", mode, "--count", str(count),
            "--jobs", str(jobs), "--out", out], V4)
    print("[ref %s] %s done" % (mode, cfg), flush=True)


def summary(sim):
    import numpy as np
    import score
    rows = []
    for cfg in CFGS:
        B = os.path.join(V4, "build", cfg)
        f = os.path.join(B, rtl_name(sim))
        if not os.path.exists(f):
            continue
        A = score.load(f)
        ks = sorted(A)
        lab = np.array([A[k]["label"] for k in ks])
        C = np.array([A[k]["counts"] for k in ks])
        nos = C.sum(1) == 0
        acc = ((C.argmax(1) == lab) & ~nos).mean() * 100
        cyc = np.mean([A[k]["cyc"] for k in ks])
        ovf = sum(A[k]["ovf"] for k in ks)
        ag = {}
        for ref in ("fixed", "float", "brian2"):
            tag = rtl_name(sim)[len("rtl_results") if sim == "verilator" else len("rtl_" + sim):-4]
            rf = os.path.join(B, "ref_%s%s.txt" % (ref, tag))
            if os.path.exists(rf):
                R = score.load(rf)
                common = [k for k in ks if k in R]
                if common:
                    pa = np.array([A[k]["counts"].argmax() if A[k]["counts"].sum() else -1 for k in common])
                    pb = np.array([R[k]["counts"].argmax() if R[k]["counts"].sum() else -1 for k in common])
                    ex = np.mean([A[k]["spk"] == R[k]["spk"] for k in common]) * 100
                    racc = np.mean([(R[k]["counts"].argmax() == R[k]["label"]) and R[k]["counts"].sum() > 0
                                    for k in common]) * 100
                    ag[ref] = "%.1f / %.1f (acc %.1f)" % ((pa == pb).mean() * 100, ex, racc)
        rows.append("| %s | %d | %.1f | %d | %.0f | %.2f | %d | %s | %s | %s |" % (
            cfg, len(ks), acc, nos.sum(), cyc, cyc / 50e3, ovf, ag.get("fixed", "-"), ag.get("float", "-"),
            ag.get("brian2", "-")))
    os.makedirs(os.path.join(V4, "results"), exist_ok=True)
    out = os.path.join(V4, "results", "summary_%s%s.md" % (sim, rtl_name(sim)[len("rtl_results") if sim == "verilator" else len("rtl_" + sim):-4]))
    with open(out, "w") as f:
        f.write("# RTL results (%s), T=100, MNIST test images\n\n" % sim)
        f.write("Agreement columns: class-agreement %% / exact-spike-train %% (accuracy of the reference)\n\n")
        f.write("| config | images | acc % | no-spike | cycles/img | ms @50MHz | FIFO ovf | vs fixed model | vs float model | vs Brian2 |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        f.write("\n".join(rows) + "\n")
    print(open(out).read())


def crosscheck(sim, cfgs):
    """compare build/<cfg>/rtl_<sim>.txt with the shipped Verilator results, line by line
    (every IMG line incl. CYCLES/HID/OVF/COUNTS and every SPK line must be identical)."""
    ok = True
    for cfg in cfgs:
        B = os.path.join(V4, "build", cfg)
        a, b = os.path.join(B, rtl_name("verilator")), os.path.join(B, rtl_name(sim))
        if not (os.path.exists(a) and os.path.exists(b)):
            print("%-16s missing %s" % (cfg, a if not os.path.exists(a) else b))
            ok = False
            continue
        la, lb = open(a).read().split("\n"), open(b).read().split("\n")
        diff = sum(x != y for x, y in zip(la, lb)) + abs(len(la) - len(lb))
        n = sum(l.startswith("IMG") for l in lb)
        print("%-16s %4d images  %s" % (cfg, n, "IDENTICAL" if diff == 0 else "%d DIFFERENT LINES" % diff))
        ok &= diff == 0
    print("cross-check:", "PASS" if ok else "FAIL")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prepare", "sim", "ref", "summary", "crosscheck", "all"])
    ap.add_argument("--sim", default="questa" if WIN else "verilator", choices=["verilator", "questa", "xsim"])
    ap.add_argument("--mode", default="fixed", choices=["fixed", "float", "brian2"])
    ap.add_argument("--cfg", nargs="*", default=CFGS)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--T", type=int, default=None, help="simulate only the first T steps of each encoding (T sweep)")
    a = ap.parse_args()
    if a.T:
        os.environ["HASTE_T"] = str(a.T)
    if a.cmd == "prepare":
        prepare()
    elif a.cmd == "sim":
        for c in a.cfg:
            sim_cfg(c, a.sim, a.count, a.jobs)
    elif a.cmd == "ref":
        for c in a.cfg:
            ref_cfg(c, a.mode, a.count, a.jobs)
    elif a.cmd == "summary":
        summary(a.sim)
    elif a.cmd == "crosscheck":
        crosscheck(a.sim, a.cfg)
    else:
        prepare()
        for c in a.cfg:
            sim_cfg(c, a.sim, a.count, a.jobs)
        for mode in ("fixed", "float", "brian2"):
            for c in a.cfg:
                if mode == "float" and "_b" in c:
                    continue  # float model does not depend on B
                if mode == "brian2" and "_b" in c:
                    continue
                ref_cfg(c, mode, a.count, a.jobs)
        summary(a.sim)


if __name__ == "__main__":
    main()
