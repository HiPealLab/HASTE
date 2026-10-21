# RTL results (verilator), T=100, MNIST test images

Agreement columns: class-agreement %% / exact-spike-train %% (accuracy of the reference)

| config | images | acc % | no-spike | cycles/img | ms @50MHz | FIFO ovf | vs fixed model | vs float model | vs Brian2 |
|---|---|---|---|---|---|---|---|---|---|
| lif_10 | 1000 | 86.3 | 0 | 11172 | 0.22 | 0 | - | - | - |
| lif_64x10 | 1000 | 90.4 | 4 | 74666 | 1.49 | 0 | 100.0 / 100.0 (acc 90.4) | - | - |
| lif_64x64x10 | 1000 | 91.7 | 0 | 145789 | 2.92 | 0 | - | - | - |
| izh_10 | 1000 | 85.9 | 0 | 74672 | 1.49 | 0 | - | - | - |
| izh_64x10 | 1000 | 87.3 | 0 | 535017 | 10.70 | 0 | 100.0 / 100.0 (acc 87.3) | - | - |
| izh_64x64x10 | 1000 | 86.9 | 0 | 1000590 | 20.01 | 0 | - | - | - |
| hh_10 | 1000 | 78.1 | 0 | 3174072 | 63.48 | 0 | 100.0 / 100.0 (acc 78.1) | - | - |
