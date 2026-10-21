# RTL results (verilator), T=100, MNIST test images

Agreement columns: class-agreement %% / exact-spike-train %% (accuracy of the reference)

| config | images | acc % | no-spike | cycles/img | ms @50MHz | FIFO ovf | vs fixed model | vs float model | vs Brian2 |
|---|---|---|---|---|---|---|---|---|---|
| lif_10 | 1000 | 83.0 | 0 | 4473 | 0.09 | 0 | - | - | - |
| lif_64x10 | 1000 | 85.4 | 24 | 29695 | 0.59 | 0 | 100.0 / 100.0 (acc 85.4) | - | - |
| lif_64x64x10 | 1000 | 85.5 | 2 | 56868 | 1.14 | 0 | - | - | - |
| izh_10 | 1000 | 83.0 | 0 | 29873 | 0.60 | 0 | - | - | - |
| izh_64x10 | 1000 | 83.0 | 13 | 214169 | 4.28 | 0 | 100.0 / 100.0 (acc 83.0) | - | - |
| izh_64x64x10 | 1000 | 79.9 | 2 | 401383 | 8.03 | 0 | - | - | - |
| hh_10 | 1000 | 66.6 | 0 | 1269633 | 25.39 | 0 | 100.0 / 100.0 (acc 66.6) | - | - |
