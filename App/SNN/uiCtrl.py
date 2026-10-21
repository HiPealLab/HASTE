from email.mime import image
from PySide6.QtWidgets import QFileDialog, QDialog, QTextEdit
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QMessageBox, QDialogButtonBox, QRadioButton, 
    QButtonGroup, QLabel, QProgressDialog, QHBoxLayout, QComboBox
)

from PySide6.QtCore import Signal, QObject, QThread, QTimer

from utils import *
from inference import InferenceWidget
from hardwareController import run_questasim, run_hardware_v4, weights_from_synapse_map, V4_ROOT
from networkGraphics import NeuralNetworkVisualizer
import json
  
class UIHandler(QObject):
    """
    Handles the UI interactions for the SNN application.
    This class sets up the UI components, connects signals to slots,
    and manages the interactions between the network visualizer and inference widget.
    It also handles menu actions for exporting memory and running hardware simulations.
    """

    show_file_dialog_sig = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window

    def setup_ui(self):
        self.buildButton = self.window.findChild(QPushButton, "buildButton")
        if self.buildButton:
            self.buildButton.clicked.connect(self.toggle_build_infer)

        container = self.window.findChild(QWidget, "visualizerContainer")
        if container.layout() is None:
            container.setLayout(QVBoxLayout())

        self.visualizer = NeuralNetworkVisualizer()
        self.inference = InferenceWidget()
        container.layout().addWidget(self.visualizer)
        container.layout().addWidget(self.inference)
        self.inference.hide()

        menubar = self.window.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Export Memory Images (synMem/layerMem)")
        file_menu.addAction("Run Hardware Simulation")
        file_menu.triggered.connect(self.handle_menu)

    def toggle_build_infer(self):
        if self.visualizer.isVisible():
            try:
                self.inference.set_weights(self.visualizer.weights)
                self.inference.set_type(self.visualizer.conn_type.currentText())
                self.visualizer.show_loading()
                self.inference.show()
                self.visualizer.hide()
                self.buildButton.setText("Return to Network Builder")
            except Exception as e:
                QMessageBox.critical(self.visualizer, "Build Failed", f"Failed process weights:\n{str(e)}")
        else:
            self.visualizer.hide_loading()
            self.inference.hide()
            self.visualizer.show()
            self.buildButton.setText("Build")

    def handle_menu(self, action):
        """
        Handles menu actions for exporting memory and running hardware simulations.
        :param action: The triggered action from the menu.
        """

        if action.text() == "Export Memory Images (synMem/layerMem)":
            # Version-IV generator: syn.mem (synMem), layer.mem (layerMem),
            # params.svh and quant.json are always written together, for the
            # neuron model and weight precision chosen in the dialog
            dialog = ExportOptions(self.visualizer.conn_type.currentText())
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            neuron_type, weight_bits = dialog.selected_items()
            folder = QFileDialog.getExistingDirectory(self.visualizer, "Output folder for memory images")
            if not folder:
                return
            try:
                rec = self.export_mem_images(folder, neuron_type, weight_bits)
            except Exception as e:
                QMessageBox.critical(self.visualizer, "Export Failed", f"Failed to export memory images:\n{str(e)}")
                return
            QMessageBox.information(
                self.visualizer, "Export Complete",
                f"Wrote syn.mem, layer.mem, params.svh and quant.json to:\n{folder}\n\n"
                f"Neuron model: {rec['model'].upper()}, weight bits: {rec['weight_bits']}, "
                f"layers: {rec['n_in']} -> {' -> '.join(str(n) for n in rec['sizes'])}")

        elif action.text() == "Run Hardware Simulation":
            self.show_file_dialog_sig.connect(self.show_file_dialog)
            self.run_simulation()

    def export_mem_images(self, folder, neuron_type, weight_bits):
        """Write the Version-IV memory images for the current network.
        neuron_type: "lif" | "izh" | "hh";  weight_bits: 4 | 8 | 16."""
        import sys
        sys.path.insert(0, str(V4_ROOT / "tools"))
        import gen_mem
        Ws = weights_from_synapse_map(self.visualizer.synapse_map)
        return gen_mem.write_net_from_weights(neuron_type, Ws, folder, {"WEIGHT_BITS": weight_bits}, "gui")

    def export_synMem(self, path, neuron_type="izh"):
        """Legacy Version-II export (kept for reproducing old results).
        NOTE: works on a copy; the previous version rescaled the GUI weights
        in place, so repeated exports compounded the scaling."""
        min_weight = float('inf')
        max_weight = float('-inf')
        for layer in self.visualizer.synapse_map:
            for row in layer:
                for conn in row:
                    if conn.weight < min_weight:
                        min_weight = conn.weight
                    if conn.weight > max_weight:
                        max_weight = conn.weight
        if max_weight < -1*min_weight:
            max_weight = -1*min_weight
        import copy
        scaled = [[[copy.copy(conn) for conn in row] for row in layer] for layer in self.visualizer.synapse_map]
        for layer in scaled:
            for row in layer:
                for conn in row:
                    conn.weight = conn.weight / max_weight * 7 # since the max range 7 to -8, i scale it to -7 to 7
            
        content = generate_syn_mem_text(scaled, self.visualizer.neurons_per_layer, neuron_type)
        if path:
            with open(path, "w") as f:
                f.write(content)
        return path

    def export_spike_image(self, path, image_path):
        if not path:
            QMessageBox.warning(self.visualizer, "No File Selected", "No file was selected for export.")
            return None
        
        content = generate_spike_image_text(image_path)
        if not content:
            QMessageBox.warning(self.visualizer, "No Image Selected", "No image was selected for export.")
            return None
        if path:
            with open(path, "w") as f:
                f.write(content)

        return path

    def run_simulation(self):
        dialog = HardwareOptions()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            model_type, weight_bits, simulator, seed, image_path, folder = dialog.selected_items()
            if not image_path:
                QMessageBox.warning(self.visualizer, "No Image Selected", "Select an image to encode.")
                return
            weights = weights_from_synapse_map(self.visualizer.synapse_map)
            n_in = weights[0].shape[1]
            spike_rows = encode_image_spikes(image_path, inp_size=n_in, T=100, seed=seed)
            out_dir = folder or "QuestasimRoot/v4"
            
            self.progress = QProgressDialog("Running simulation...", "Cancel", 0, 0, parent=self.visualizer)
            self.progress.setWindowTitle("Please Wait")
            self.progress.setMinimumDuration(0)
            self.progress.setValue(-1)
            self.progress.setCancelButton(None)
            self.progress.show()

            self.hardware_thread = QThread()
            self.worker = HardwareWorker(model_type, weights, spike_rows, out_dir, weight_bits, simulator)
            self.worker.moveToThread(self.hardware_thread)

            self.hardware_thread.started.connect(self.worker.run)
            # self.worker.hardware_simulation_finished.connect(self.progress.destroy)
            self.worker.hardware_simulation_finished.connect(self.on_finished)

            self.hardware_thread.start()

    def on_finished(self, result):
        result = json.loads(result)
        out_str = ""
        for key in result.keys():
            if str(key).isdigit():
                out_str += f"Neuron{key}: {result[key]},\n"
            elif key == "cycles":
                out_str += f"cycles: {result[key]} ({result[key] / 50e3:.2f} ms @ 50 MHz)\n"
            else:
                out_str += f"{key}: {result[key]}\n"

        self.progress.hide()
        self.progress.deleteLater()
        self.hardware_thread.quit()
        self.worker.deleteLater()
        self.hardware_thread.deleteLater()
        self.show_file_dialog_sig.emit(out_str)
    
    def show_file_dialog(self, out_str):
        fwd = FileViewerDialog(out_str, self.visualizer)
        fwd.exec()

class FileViewerDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware output")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        text_area = QTextEdit(self)
        text_area.setReadOnly(True)

        text_area.setPlainText(text)

        layout.addWidget(text_area)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class HardwareWorker(QObject):
    hardware_simulation_finished = Signal(object)

    def __init__(self, model_type, weights, spike_rows, out_dir, weight_bits, simulator):
        super().__init__()
        self.model_type = model_type
        self.weights = weights
        self.spike_rows = spike_rows
        self.out_dir = out_dir
        self.weight_bits = weight_bits
        self.simulator = simulator

    def run(self):
        try:
            output = run_hardware_v4(self.model_type, self.weights, self.spike_rows, self.out_dir,
                                     self.weight_bits, self.simulator)
        except Exception as e:  # report instead of silently killing the thread
            output = {"error": str(e)}
        self.hardware_simulation_finished.emit(json.dumps(output))

class ExportOptions(QDialog):
    """Neuron model and weight precision for "Export Memory Images"."""

    # network-builder neuron types (brian2Sim.ConnectionType values) -> generator model names
    MODEL_OF_CONN_TYPE = {"Leaky Integrate-and-Fire": "lif", "Izhikevich": "izh", "Hodgkin-Huxley": "hh"}

    def __init__(self, conn_type_text=None):
        super().__init__()
        self.setWindowTitle("Export Memory Images")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Neuron model of the hardware core:"))

        self.button_group = QButtonGroup(self)
        self.buttons = {"lif": QRadioButton("LIF (Leaky Integrate-and-Fire)"),
                        "izh": QRadioButton("Izh (Izhikevich)"),
                        "hh": QRadioButton("HH (Hodgkin-Huxley)")}
        for model, button in self.buttons.items():
            self.button_group.addButton(button)
            layout.addWidget(button)
        # default: the neuron type selected in the network builder
        self.buttons[self.MODEL_OF_CONN_TYPE.get(conn_type_text, "lif")].setChecked(True)

        bits_row = QHBoxLayout()
        bits_row.addWidget(QLabel("Weight bits:"))
        self.bits_combo = QComboBox()
        self.bits_combo.addItems(["8", "4", "16"])
        bits_row.addWidget(self.bits_combo)
        layout.addLayout(bits_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def selected_items(self):
        model = next(m for m, b in self.buttons.items() if b.isChecked())
        return model, int(self.bits_combo.currentText())


class HardwareOptions(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Model Type")

        layout = QVBoxLayout()

        label = QLabel("Select the model type for the hardware simulation:")
        layout.addWidget(label)

        self.button_group = QButtonGroup(self)

        self.lif_button = QRadioButton("LIF (Leaky Integrate-and-Fire)")
        self.lif_button.setChecked(True)
        self.hh_button = QRadioButton("HH (Hodgkin-Huxley)")
        self.izh_button = QRadioButton("Izh (Izhikevich)")

        self.button_group.addButton(self.lif_button, 1)
        self.button_group.addButton(self.izh_button, 2)
        self.button_group.addButton(self.hh_button, 3)

        layout.addWidget(self.lif_button)
        layout.addWidget(self.izh_button)
        layout.addWidget(self.hh_button)

        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Weight bits:"))
        self.bits_combo = QComboBox()
        self.bits_combo.addItems(["8", "4", "16"])
        opts_row.addWidget(self.bits_combo)
        opts_row.addWidget(QLabel("Simulator:"))
        self.sim_combo = QComboBox()
        self.sim_combo.addItems(["verilator", "questa"])
        opts_row.addWidget(self.sim_combo)
        opts_row.addWidget(QLabel("Encoder seed:"))
        self.seed_combo = QComboBox()
        self.seed_combo.setEditable(True)
        self.seed_combo.addItems(["0"])
        opts_row.addWidget(self.seed_combo)
        layout.addLayout(opts_row)

        synmem_row = QWidget()
        synmem_layout = QVBoxLayout()
        synmem_layout.setContentsMargins(0, 0, 0, 0)
        synmem_layout.setSpacing(5)
        synmem_row.setLayout(synmem_layout)
        self.synmem_export_button = QPushButton("Select SynMem")
        self.synmem_export_button.clicked.connect(lambda: self.show_file_dialog("Select SynMem"))
        self.synmem_address_textbox = QLabel("No file selected")
        row_layout = QHBoxLayout()
        row_layout.addWidget(self.synmem_export_button)
        row_layout.addWidget(self.synmem_address_textbox)
        synmem_layout.addLayout(row_layout)
        # layout.addWidget(synmem_row)   # Version-II only (memory images are generated now)

        spike_image_row = QWidget()
        spike_image_layout = QVBoxLayout()
        spike_image_layout.setContentsMargins(0, 0, 0, 0)
        spike_image_layout.setSpacing(5)
        spike_image_row.setLayout(spike_image_layout)
        self.spike_image_export_button = QPushButton("Select Spike Image")
        self.spike_image_export_button.clicked.connect(lambda: self.show_file_dialog("Select Spike Image"))
        self.spike_image_address_textbox = QLabel("No file selected")
        spike_row_layout = QHBoxLayout()
        spike_row_layout.addWidget(self.spike_image_export_button)
        spike_row_layout.addWidget(self.spike_image_address_textbox)
        spike_image_layout.addLayout(spike_row_layout)
        # layout.addWidget(spike_image_row)

        image_row = QWidget()
        image_layout = QVBoxLayout()
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(5)
        image_row.setLayout(image_layout)
        self.image_button = QPushButton("Select Image")
        self.image_button.clicked.connect(lambda: self.show_file_dialog("Select Image"))
        self.image_path = None
        self.image_textbox = QLabel("No image selected")
        image_row_layout = QHBoxLayout()
        image_row_layout.addWidget(self.image_button)
        image_row_layout.addWidget(self.image_textbox)
        image_layout.addLayout(image_row_layout)
        layout.addWidget(image_row)

        folder_row = QWidget()
        folder_layout = QVBoxLayout()
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(5)
        folder_row.setLayout(folder_layout)
        self.folder_button = QPushButton("Select Folder")
        self.folder_button.clicked.connect(self.select_folder)
        self.folder = None
        self.folder_textbox = QLabel("No folder selected")
        folder_row_layout = QHBoxLayout()
        folder_row_layout.addWidget(self.folder_button)
        folder_row_layout.addWidget(self.folder_textbox)
        folder_layout.addLayout(folder_row_layout)
        layout.addWidget(folder_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self.setLayout(layout)

        self.synMem_address = None
        self.spike_image_address = None
    
    @staticmethod
    def id_to_string(id):
        if id == 1:
            return "lif"
        elif id == 2:
            return "izh"
        elif id == 3:
            return "hh"
        else:
            return "Unknown"

    def selected_items(self):
        return (HardwareOptions.id_to_string(self.button_group.checkedId()), int(self.bits_combo.currentText()),
                self.sim_combo.currentText(), int(self.seed_combo.currentText() or 0), self.image_path, self.folder)
    
    def show_file_dialog(self, title):
        if title == "Select Image":
            self.image_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "../../Train/saved_dataset", "Image Files (*.png *.jpg *.jpeg *.bmp)")
            if self.image_path:
                self.image_textbox.setText(self.image_path)
            else:
                QMessageBox.warning(self, "No Image Selected", "No image was selected.")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, title, f"{title.split(' ')[-1]}", "SystemVerilog Files (*.svh)")
        if path:
            if title == "Select SynMem":
                self.synmem_address_textbox.setText(path)
                self.synMem_address = path
            elif title == "Select Spike Image":
                self.spike_image_address_textbox.setText(path)
                self.spike_image_address = path
        else:
            QMessageBox.warning(self, "No File Selected", "No file was selected for export.")
    
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            "../../Hardware/Version-IV/build",
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.folder = folder
            self.folder_textbox.setText(folder)
        else:
            QMessageBox.warning(self, "No Folder Selected", "No folder was selected for export.")
  
