# RTL results (verilator), T=100, MNIST test images

Agreement columns: class-agreement %% / exact-spike-train %% (accuracy of the reference)

| config | images | acc % | no-spike | cycles/img | ms @50MHz | FIFO ovf | vs fixed model | vs float model | vs Brian2 |
|---|---|---|---|---|---|---|---|---|---|
| lif_10 | 1000 | 87.3 | 0 | 22324 | 0.45 | 0 | - | - | - |
| lif_64x10 | 1000 | 92.5 | 3 | 149519 | 2.99 | 0 | 100.0 / 100.0 (acc 92.5) | - | - |
| lif_64x64x10 | 1000 | 94.1 | 0 | 293682 | 5.87 | 0 | - | - | - |
| izh_10 | 1000 | 87.0 | 0 | 149324 | 2.99 | 0 | - | - | - |
| izh_64x10 | 1000 | 90.3 | 0 | 1068930 | 21.38 | 0 | 100.0 / 100.0 (acc 90.3) | - | - |
| izh_64x64x10 | 1000 | 88.7 | 0 | 1993141 | 39.86 | 0 | - | - | - |
| hh_10 | 1000 | 84.8 | 0 | 6348124 | 126.96 | 0 | 100.0 / 100.0 (acc 84.8) | - | - |
