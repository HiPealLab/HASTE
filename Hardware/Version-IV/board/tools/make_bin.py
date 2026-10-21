#!/usr/bin/env python3
"""Convert the test-set spike encoding into the binary files that are loaded
into the Zynq DDR with XSCT (`dow -data`), for board/sw/main.c.

  python3 board/tools/make_bin.py                       # data/spikes.mem + data/labels.mem, all 1000 images
  python3 board/tools/make_bin.py --count 50            # first 50 images only
  python3 board/tools/make_bin.py --npz data/spikes.npz # from the .npz instead (same content)

Output (default board/data/):
  spikes.bin  little-endian, 16-byte header + payload
      u32 magic   = 0x534E4E53  ("SNNS" as bytes 53 4E 4E 53 read LE)
      u32 n_img   number of images
      u32 t_rows  rows (time steps) per image          (100 for data/)
      u32 n_in    bytes per row = number of inputs     (64)
      u8  rows[n_img][t_rows][n_in]
          row = indices of the inputs that spike in that time step, ascending,
          terminated by 0xFF and padded with 0xFF -- byte-for-byte the same as
          one line of data/spikes.mem (what tb/tb_snn.sv replays).
  labels.bin  u32 magic = 0x4C4E4E53 ("SNNL"), u32 n_img, u8 label[n_img]

The PS copies row t of image k, word by word, to the wrapper's spike buffer
at 0x4000 + 4*(t*n_in/4 + w); a 32-bit word holds slots 4w..4w+3 with slot
4w in bits 7:0 (= the byte order of the file read as little-endian words).
"""
import argparse, os, struct, sys

V4 = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MAGIC_S, MAGIC_L = 0x534E4E53, 0x4C4E4E53


def read_mem(fn):
    out = []
    for line in open(fn):
        line = line.split("//")[0].strip()
        if line:
            out.extend(int(x, 16) for x in line.split())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mem", default=os.path.join(V4, "data", "spikes.mem"))
    ap.add_argument("--labels", default=os.path.join(V4, "data", "labels.mem"))
    ap.add_argument("--npz", default=None, help="read spikes/labels from this .npz instead of the .mem files")
    ap.add_argument("--rows", type=int, default=100, help="rows per image in the input (TDATA), default 100")
    ap.add_argument("--n-in", type=int, default=64)
    ap.add_argument("--count", type=int, default=None, help="number of images (default: all)")
    ap.add_argument("--out", default=os.path.join(V4, "board", "data"))
    a = ap.parse_args()

    if a.npz:
        import numpy as np
        d = np.load(a.npz)
        sp = d["spikes"]
        n_img, rows, n_in = sp.shape
        flat = [int(x) for x in sp.reshape(-1)]
        labels = [int(x) for x in d["labels"]]
    else:
        flat = read_mem(a.mem)
        labels = read_mem(a.labels)
        rows, n_in = a.rows, a.n_in
        if len(flat) % (rows * n_in):
            sys.exit("spikes.mem size %d is not a multiple of rows*n_in=%d" % (len(flat), rows * n_in))
        n_img = len(flat) // (rows * n_in)
    if n_in % 4:
        sys.exit("n_in must be a multiple of 4")
    if a.count is not None:
        n_img = min(n_img, a.count)
    flat = flat[: n_img * rows * n_in]
    labels = labels[:n_img]
    if len(labels) < n_img:
        sys.exit("fewer labels (%d) than images (%d)" % (len(labels), n_img))
    if any(x < 0 or x > 255 for x in flat) or any(x != 0xFF and x >= n_in for x in flat):
        sys.exit("spike rows must hold input indices < n_in or 0xFF")

    os.makedirs(a.out, exist_ok=True)
    fs, fl = os.path.join(a.out, "spikes.bin"), os.path.join(a.out, "labels.bin")
    with open(fs, "wb") as f:
        f.write(struct.pack("<4I", MAGIC_S, n_img, rows, n_in))
        f.write(bytes(flat))
    with open(fl, "wb") as f:
        f.write(struct.pack("<2I", MAGIC_L, n_img))
        f.write(bytes(labels))
    print("wrote %s (%d bytes: %d images x %d rows x %d inputs)" % (fs, os.path.getsize(fs), n_img, rows, n_in))
    print("wrote %s (%d bytes)" % (fl, os.path.getsize(fl)))

    # cross-check .mem against .npz when both exist (they encode the same data)
    other = os.path.join(os.path.dirname(a.mem), "spikes.npz")
    if not a.npz and os.path.exists(other):
        try:
            import numpy as np
            sp = np.load(other)["spikes"][:n_img]
            ok = sp.shape[1:] == (rows, n_in) and [int(x) for x in sp.reshape(-1)] == flat
            print("cross-check spikes.mem vs spikes.npz:", "identical" if ok else "DIFFERENT")
        except ImportError:
            pass


if __name__ == "__main__":
    main()
