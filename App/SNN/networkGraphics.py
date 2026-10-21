import numpy as np
import json

from PySide6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QSpinBox, QComboBox, 
    QHBoxLayout, QGraphicsEllipseItem, QGraphicsLineItem, QLabel, QFileDialog, 
    QMessageBox, QDialog, QVBoxLayout, QLineEdit, QPushButton
)

from brian2Sim import ConnectionType
from snnTrainer import *

class WeightedLineItem(QGraphicsLineItem):
    """
    A custom QGraphicsLineItem that represents a synapse with a weight.
    It allows for editing the weight through a dialog when clicked.
    """

    def __init__(self, x1, y1, x2, y2, weight=0.0):
        super().__init__(x1, y1, x2, y2)
        self.setPen(QPen(Qt.black))
        self.setFlag(QGraphicsLineItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.weight = weight

    def shape(self):
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(1)
        return stroker.createStroke(path)

    def mousePressEvent(self, event):
        dialog = QDialog()
        dialog.setWindowTitle("Edit Weight")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Synapse Weight:"))
        weight_input = QLineEdit(str(self.weight))
        layout.addWidget(weight_input)
        save_btn = QPushButton("Save")
        layout.addWidget(save_btn)

        def save_weight():
            try:
                self.weight = float(weight_input.text())
            except ValueError:
                pass
            dialog.accept()

        save_btn.clicked.connect(save_weight)
        dialog.exec()

    def hoverEnterEvent(self, event):
        self.setToolTip(f"Weight: {self.weight:.3f}")
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setToolTip("")
        super().hoverLeaveEvent(event)

class ZoomableGraphicsView(QGraphicsView):
    """ 
    A custom QGraphicsView that supports zooming with the mouse wheel.
    It allows for smooth zooming in and out using the Control key. 
    This class is used to display the neural network graphically.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.zoom_factor = 1.15

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.scale(self.zoom_factor, self.zoom_factor)
            else:
                self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
        else:
            super().wheelEvent(event)

class NeuralNetworkVisualizer(QWidget):
    """ 
    A widget for visualizing a neural network.
    It allows users to specify the number of layers, the number of neurons in each layer, and the type of connections.
    It also provides options to export and import weights, and to train the network.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Neural Network Visualizer")
        self.layout = QVBoxLayout(self)

        self.loading_label = QLabel("Loading, please wait...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 18px; color: gray;")
        self.layout.addWidget(self.loading_label)
        self.loading_label.hide()

        control_panel = QWidget()
        control_layout = QVBoxLayout()
        control_panel.setLayout(control_layout)
        self.layout.addWidget(control_panel)

        top_controls_layout = QHBoxLayout()
        top_controls_layout.addWidget(QLabel("Number of Layers"))
        self.layer_count_spin = QSpinBox()
        self.layer_count_spin.setRange(1, 10)
        self.layer_count_spin.setValue(3)
        self.layer_count_spin.valueChanged.connect(self.sync_layer_controls)
        top_controls_layout.addWidget(self.layer_count_spin)

        top_controls_layout.addSpacing(200)

        top_controls_layout.addWidget(QLabel("Neuron Type"))
        self.conn_type = QComboBox()
        self.conn_type.addItems([i.value for i in ConnectionType])
        top_controls_layout.addWidget(self.conn_type)

        control_layout.addLayout(top_controls_layout)

        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView(self.scene)
        self.layout.addWidget(self.view)

        self.spinboxRow = QWidget()
        self.spinboxRow.setLayout(QHBoxLayout())
        self.layer_spinboxes = []
        self.layout.addWidget(self.spinboxRow)

        self.export_button = QPushButton("Export Weights")
        self.export_button.clicked.connect(self.export_weights)
        self.layout.addWidget(self.export_button)

        self.import_button = QPushButton("Import Weights")
        self.import_button.clicked.connect(self.open_import_dialog)
        self.layout.addWidget(self.import_button)

        self.train_button = QPushButton("Train")
        self.train_button.clicked.connect(self.open_train_dialog)
        self.layout.addWidget(self.train_button)

        self.neurons_per_layer = []
        self.synapse_map = []

        self.sync_layer_controls()

    def show_loading(self, message="Building..."):
        self.loading_label.setText(message)
        self.loading_label.show()
        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget != self.loading_label:
                widget.hide()
        self.repaint()

    def hide_loading(self):
        self.loading_label.hide()
        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget != self.loading_label:
                widget.show()
        self.repaint()

    def open_import_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Weights", "", "Weight Files (*.txt *.npz)")
        if file_path:
            self.import_weights(file_path)

    def update_layers(self, neuron_counts: list):
        """ 
        Update the neural network visualization with the specified number of neurons in each layer.
        This method clears the current scene and redraws the network based on the provided neuron counts.
        """
        self.scene.clear()
        self.synapse_map = []
        self.neurons_per_layer = neuron_counts

        num_layers = len(neuron_counts)
        view_width = self.view.viewport().width()
        view_height = self.view.viewport().height()

        margin = 20
        spacing_x = max((view_width - 2 * margin) / max(1, num_layers - 1), 40)
        max_neurons = max(neuron_counts) if neuron_counts else 1
        spacing_y = max((view_height - 2 * margin) / max(1, max_neurons - 1), 30)

        radius = min(spacing_x, spacing_y) * 0.3
        radius = min(radius, 20)

        layer_positions = []
        self.synapse_map = [[] for _ in range(len(neuron_counts) - 1)]

        for i, neuron_count in enumerate(neuron_counts):
            x = margin + i * spacing_x
            layer_neurons = []
            for j in range(neuron_count):
                y = margin + j * spacing_y
                neuron = QGraphicsEllipseItem(x - radius / 2, y - radius / 2, radius, radius)
                neuron.setBrush(Qt.white)
                neuron.setPen(QPen(QColor(Qt.black)))
                self.scene.addItem(neuron)
                layer_neurons.append((x, y))
            layer_positions.append(layer_neurons)

        for layer_index in range(len(layer_positions) - 1):
            src_layer = layer_positions[layer_index]
            dst_layer = layer_positions[layer_index + 1]
            layer_weights = []
            for src in src_layer:
                weights_row = []
                for dst in dst_layer:
                    line = WeightedLineItem(src[0], src[1], dst[0], dst[1])
                    self.scene.addItem(line)
                    weights_row.append(line)
                layer_weights.append(weights_row)
            self.synapse_map[layer_index] = layer_weights

        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def export_weights(self):
        """ 
        Export the weights of the neural network to a file.
        This method collects the weights from the synapse map and saves them in a JSON format.
        The user is prompted to choose a file location to save the weights.
        """
        weight_data = []
        for layer in self.synapse_map:
            layer_weights = []
            for row in layer:
                row_weights = [conn.weight for conn in row]
                layer_weights.append(row_weights)
            weight_data.append(layer_weights)

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Weights", "weights.npz", "Weight Files (*.txt *.npz)")
        if not file_path:
            return
        if not file_path.endswith(('.txt', '.npz')):
            file_path += '.txt'

        if file_path.endswith('.npz'):
            np.savez(file_path, *weight_data)
        else:
            with open(file_path, 'w') as f:
                json.dump(weight_data, f, indent=2)

    def import_weights(self, filepath: str):
        try:
            if filepath.endswith('.txt'):
                with open(filepath, 'r') as f:
                    weight_data = json.load(f)
            elif filepath.endswith('.npz'):
                loaded = np.load(filepath)
                weight_data = [loaded[key].T.tolist() for key in loaded.files]
            else:
                raise ValueError("Unsupported file format. Use .txt or .npz files.")

            if not isinstance(weight_data, list) or not all(isinstance(layer, list) for layer in weight_data):
                raise ValueError("Invalid format")

            self.weights = weight_data

            neuron_counts = []
            for i, layer in enumerate(weight_data):
                if not layer or not all(isinstance(row, list) for row in layer):
                    raise ValueError("Invalid format in layer")
                src_neurons = len(layer)
                dst_neurons = len(layer[0])
                if not all(len(row) == dst_neurons for row in layer):
                    raise ValueError("Inconsistent row lengths in layer")
                neuron_counts.append(src_neurons)
                if i == len(weight_data) - 1:
                    neuron_counts.append(dst_neurons)

            self.update_layers(neuron_counts)

            for layer_idx, layer in enumerate(weight_data):
                for src_idx, row in enumerate(layer):
                    for dst_idx, weight in enumerate(row):
                        try:
                            line_item = self.synapse_map[layer_idx][src_idx][dst_idx]
                            line_item.weight = weight
                        except IndexError:
                            raise ValueError("Mismatch between weight file and visualized network")

            # self.layer_count_spin.setValue(len(neuron_counts))
            # for i, spin in enumerate(self.layer_spinboxes):
            #     if i < len(neuron_counts):
            #         spin.setValue(neuron_counts[i])
            # for i in range(len(self.layer_spinboxes), len(neuron_counts)):
            #     spin = QSpinBox()
            #     spin.setRange(1, 100)
            #     spin.setValue(neuron_counts[i])
            #     spin.valueChanged.connect(self.redraw_network)
            #     self.spinboxRow.layout().addWidget(spin)
            #     self.layer_spinboxes.append(spin)
            # while len(self.layer_spinboxes) > len(neuron_counts):
            #     spin = self.layer_spinboxes.pop()
            #     spin.deleteLater()

            # self.synapse_map = []
            # print(weight_data)
            # for layer in weight_data:
            #     layer_weights = []
            #     for row in layer:
            #         row_weights = [WeightedLineItem(0, 0, 0, 0, weight) for weight in row]
            #         layer_weights.append(row_weights)
            #     self.synapse_map.append(layer_weights)
            # self.redraw_network()
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Failed to import weights:\n{str(e)}")

    def sync_layer_controls(self):
        """ 
        Synchronize the number of layer spinboxes with the layer count spinbox.
        This method updates the number of spinboxes based on the value of the layer count spinbox.
        It clears the existing spinboxes and creates new ones according to the specified layer count.
        """
        layout = self.spinboxRow.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.layer_spinboxes = []

        for _ in range(self.layer_count_spin.value()):
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(3)
            spin.valueChanged.connect(self.redraw_network)
            layout.addWidget(spin)
            self.layer_spinboxes.append(spin)

        self.redraw_network()

    def redraw_network(self):
        neuron_counts = [spin.value() for spin in self.layer_spinboxes]
        self.update_layers(neuron_counts)

    def open_train_dialog(self):
        """ 
        Open a dialog to set training parameters and start training the SNN.
        This method collects the number of neurons in each layer and opens a dialog for training parameters.
        It connects the dialog's signals to the appropriate slots for handling training arguments and completion.
        """

        layers = [len(layer) for layer in self.synapse_map]
        layers.append(len(self.synapse_map[-1][0]))
        dialog = ArgsDialog(self, layers[0], layers[1:])

        def on_args_ready(args, snn_model):
            print("Training args:", args)
            print("Model architecture:", snn_model)
            dialog.train_snn(args, snn_model)

        def on_train_finished(output_file, training_acc):
            self.import_weights(output_file)
            QMessageBox.information(self, "Training Finished", f"Training accuracy: {training_acc:.2f}\nWeights saved to: {output_file}")

        dialog.args_ready.connect(on_args_ready)
        dialog.training_finished.connect(on_train_finished)
        dialog.exec()

