#!/usr/bin/env python3
"""Strict comparison of a board (or board-testbench) result file with the
shipped Verilator golden file build/<cfg>/rtl_results.txt.

  python3 board/tools/compare_results.py BOARD.txt [GOLDEN.txt]

BOARD.txt may be a raw UART log: only lines starting with "IMG " / "SPK "
are used (anything before them on the line, e.g. a terminal prefix, and
CR characters are stripped).  Extra fields after the COUNTS (e.g. "US 2401.3")
are ignored.  For every image present in BOARD, LABEL, HID, OVF, CYCLES, the
10 COUNTS and (if BOARD has SPK lines) the output spike train must equal the
golden file.  Exit code 0 = all identical.  Afterwards tools/score.py is run
on the two files (accuracy + agreement), using cleaned copies.
"""
import os, re, subprocess, sys, tempfile

V4 = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def clean_lines(fn, n_out=10):
    out = []
    for raw in open(fn, errors="replace"):
        line = raw.replace("\r", "").strip()
        m = re.search(r"(IMG \d+ .*|SPK \d+ \d+ \d+)", line)
        if not m:
            continue
        s = m.group(1)
        if s.startswith("IMG"):
            p = s.split()
            i = p.index("COUNTS")
            s = " ".join(p[: i + 1 + n_out])  # drop trailing extra fields
        out.append(s)
    return out


def parse(lines):
    img, spk = {}, {}
    for s in lines:
        p = s.split()
        if p[0] == "IMG":
            k = int(p[1])
            i = p.index("COUNTS")
            d = dict(zip(p[2:i:2], p[3:i:2]))
            img[k] = dict(LABEL=int(d["LABEL"]), HID=int(d["HID"]), OVF=int(d["OVF"]),
                          CYCLES=int(d["CYCLES"]), COUNTS=[int(x) for x in p[i + 1:]])
        else:
            spk.setdefault(int(p[1]), []).append((int(p[2]), int(p[3])))
    return img, spk


def main():
    board = sys.argv[1]
    gold = sys.argv[2] if len(sys.argv) > 2 else os.path.join(V4, "build", "lif_64x10", "rtl_results.txt")
    bl, gl = clean_lines(board), clean_lines(gold)
    B, BS = parse(bl)
    G, GS = parse(gl)
    if not B:
        print("no IMG lines in", board); return 2
    has_spk = len(BS) > 0
    bad = 0
    for k in sorted(B):
        if k not in G:
            print("IMG %d not in golden file" % k); bad += 1; continue
        diffs = [f for f in ("LABEL", "HID", "OVF", "CYCLES", "COUNTS") if B[k][f] != G[k][f]]
        if has_spk and BS.get(k, []) != GS.get(k, []):
            diffs.append("SPK")
        if diffs:
            bad += 1
            if bad <= 20:
                print("IMG %d differs in %s:" % (k, ",".join(diffs)))
                for f in diffs:
                    if f == "SPK":
                        print("   SPK board=%s\n       gold =%s" % (BS.get(k, [])[:12], GS.get(k, [])[:12]))
                    else:
                        print("   %s board=%s gold=%s" % (f, B[k][f], G[k][f]))
    n = len(B)
    cyc_off = sorted({B[k]["CYCLES"] - G[k]["CYCLES"] for k in B if k in G})
    print("compared %d images (%d..%d): %d identical, %d different; CYCLES offsets board-gold: %s; spike trains %s"
          % (n, min(B), max(B), n - bad, bad, cyc_off[:5], "compared" if has_spk else "not in board file"))
    sys.stdout.flush()
    # accuracy / agreement with the project's scorer (cleaned copies)
    with tempfile.TemporaryDirectory() as td:
        fb, fg = os.path.join(td, "board.txt"), os.path.join(td, "golden.txt")
        open(fb, "w").write("\n".join(bl) + "\n")
        open(fg, "w").write("\n".join(s for s in gl if int(s.split()[1]) in B) + "\n")
        subprocess.call([sys.executable, os.path.join(V4, "tools", "score.py"), fb, fg])
    print("RESULT:", "PASS (identical counts, HID, OVF, CYCLES%s)" % (", spike trains" if has_spk else "") if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
