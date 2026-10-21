# SNN Simulation Project

This project provides a graphical and programmatic environment for building, training, simulating, and performing inference with Spiking Neural Networks (SNNs). It supports both software-based simulation (using PyTorch and Brian2) and hardware simulation (using Questasim).

## Main Components

### 1. Network Builder & Visualizer (`networkGraphics.py`)
- Interactive GUI for designing SNN architectures.
- Allows users to set the number of layers and neurons per layer.
- Supports editing synaptic weights visually.
- Import/export weights in `.txt` or `.npz` formats.

### 2. SNN Trainer (`snnTrainer.py`)
- Trains SNN models on the MNIST dataset using PyTorch and SpikingJelly.
- Supports configurable architecture and training parameters.
- Saves trained weights for later inference or hardware export.

### 3. Inference (`inference.py`, `inferenceWorker.py`)
- Performs inference using trained weights on images or datasets.
- Supports Hodgkin-Huxley, Leaky Integrate-and-Fire and Izhikevich neuron models via Brian2 (Izhikevich uses the hardware's fast-spiking preset, its own 30 mV spike peak and a -150 mV floor; the Threshold field applies to HH and LIF only).
- Provides top-1 accuracy, tie-aware accuracy and confusion matrix visualization. Images with no output spike are predicted as "none" and count as wrong in both metrics.

### 4. Hardware Simulation (`hardwareController.py`)
- File > Export Memory Images (synMem/layerMem): writes the Version-IV memory images (syn.mem, layer.mem, params.svh, quant.json) for the chosen neuron model (LIF/IZH/HH) and weight precision (4/8/16 bits).
- File > Run Hardware Simulation: encodes one image (seeded), generates the images and runs the Version-IV RTL in Verilator or Questa; shows per-class spike counts and cycles.

### 5. Utilities (`utils.py`)
- Functions for generating SystemVerilog memory modules from network configuration.

### 6. UI Controller (`uiCtrl.py`, `main.py`)
- Integrates all components into a PySide6-based GUI.
- Handles user interactions, file dialogs, and menu actions.

## Usage

1. **Build Network**: Use the visualizer to design your SNN architecture and select the neuron type (LIF, IZH or HH).
2. **Train**: Configure training parameters and train the network on MNIST.
3. **Export/Import Weights**: Save trained weights or load existing weights.
4. **Inference**: Run inference on images or datasets and view results.
5. **Hardware Simulation**: Export memory images and run the RTL in Verilator or Questa for hardware verification.

## Supported Features

- Visual network editing and weight management.
- Training with configurable parameters (epochs, batch size, learning rate, etc.).
- Inference using biologically realistic neuron models.
- Export to hardware simulation formats.
- Progress bars and responsive UI for long-running tasks.

## Requirements

- Python 3.11
- PySide6
- PyTorch
- SpikingJelly
- Brian2
- Questasim (for hardware simulation)
- MNIST dataset (downloaded automatically)

## Getting Started

1. Install dependencies.
2. Run `main.py` to launch the GUI.
3. Design, train, and simulate your SNN.

## File Structure

- `main.py`: Entry point for the GUI application.
- `networkGraphics.py`: Network visualizer and builder.
- `snnTrainer.py`: SNN training logic.
- `inference.py`, `inferenceWorker.py`: Inference logic and worker thread.
- `brian2Sim.py`: Brian2-based neuron simulation.
- `hardwareController.py`: Hardware export and simulation.
- `uiCtrl.py`: UI integration and event handling.
- `utils.py`: Utility functions for hardware export.
- `SNN.md`: Project documentation.

## License

This project is intended for educational and research purposes.
