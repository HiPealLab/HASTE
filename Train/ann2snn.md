# ANN to SNN conversion
Python module to initiate Hodgkin-Huxley network weights. The objective is to classify MNIST dataset using accurate HH modules and find optimal weights.

## MLP
a 3 layer MLP to classify MNIST. very accurate results but conversion is hard.

## HH
an HH network to imitiate MLP. simulated using brain2, weights are converted using SpikingJelly.

## Theft
single layer LIF snn from lif_fc_mnist file in spikingjelly

## HH from LIF
trying to use LIF weights in HH.

Observations: 
1. changing scale parameter affects results
2. increasing simulation time improves results at the cost of longer run duration 
