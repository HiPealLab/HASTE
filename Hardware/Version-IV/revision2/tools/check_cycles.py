#!/usr/bin/env python3
"""Check the integer cycle formula against RTL cycle counts:
cycles = 2*n_ops + 2*visits + sweeps + S*T + K*N*S*T + N + 1,  K = 2 (LIF), 4 (IZH), 21 (HH)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner  # noqa: E402
import fit_cycles as fc  # noqa: E402

K = {'lif': 2, 'izh': 4, 'hh': 21}


def cycles(r, model):
    return 2 * r['n_ops'] + 2 * r['visits'] + r['sweeps'] + r['subs'] + K[model] * r['upd'] + r['n_neu'] + 1


if __name__ == "__main__":
    for c, n in [('lif_64x64x10', 1000), ('izh_64x10', 300), ('hh_10', 24), ('hh_64x64x10', 24),
                 ('lif_cnn', 24), ('lif_64x10_b4', 300)]:
        res = runner.run(os.path.join(runner.V4, 'build', c), 'data', n)
        cyc = fc.rtl_cycles(os.path.join(runner.V4, 'build', c, 'rtl_results.txt'))
        bad = sum(cycles(r, c.split('_')[0]) != cyc[r['k']] for r in res)
        print(c, len(res), 'mismatches', bad, flush=True)
