# RTL results (verilator), T=100, MNIST test images

Agreement columns: class-agreement %% / exact-spike-train %% (accuracy of the reference)

| config | images | acc % | no-spike | cycles/img | ms @50MHz | FIFO ovf | vs fixed model | vs float model | vs Brian2 |
|---|---|---|---|---|---|---|---|---|---|
| lif_10 | 1000 | 87.4 | 0 | 44641 | 0.89 | 0 | - | - | - |
| lif_64x10 | 1000 | 93.4 | 3 | 299297 | 5.99 | 0 | 100.0 / 100.0 (acc 93.4) | - | - |
| lif_64x64x10 | 1000 | 95.3 | 0 | 589449 | 11.79 | 0 | - | - | - |
| izh_10 | 1000 | 87.5 | 0 | 298641 | 5.97 | 0 | - | - | - |
| izh_64x10 | 1000 | 91.4 | 0 | 2136372 | 42.73 | 0 | 100.0 / 100.0 (acc 91.4) | - | - |
| izh_64x64x10 | 1000 | 89.5 | 0 | 3974664 | 79.49 | 0 | - | - | - |
| hh_10 | 1000 | 86.0 | 0 | 12696241 | 253.92 | 0 | 100.0 / 100.0 (acc 86.0) | - | - |
