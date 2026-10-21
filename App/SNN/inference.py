import os
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, accuracy_score
import numpy as np
import torchvision.transforms as transforms

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout, QMessageBox,
    QFileDialog, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)

from brian2Sim import BrianSimulator, ConnectionType
from inferenceWorker import *


class InferenceWidget(QWidget):
    """
    Widget for performing inference using a trained SNN model.
    This widget allows users to load an image or dataset, set parameters for inference,
    and visualize the results of the inference process.
    Attributes:
        connection_type (ConnectionType): Type of connection to use for inference.
        graphics_view (QGraphicsView): View for displaying images.
        graphics_scene (QGraphicsScene): Scene for managing graphical items.
        pil_image (Image): Loaded image in PIL format.
        dataset (str): Path to the loaded dataset directory.
        weights (dict): Weights for the SNN model.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inference Widget")
        self.setMinimumSize(400, 600)
        self.connection_type = ConnectionType.HODGKIN_HUXLEY
        layout = QVBoxLayout(self)

        self.graphics_row = QHBoxLayout()
        self.graphics_view = QGraphicsView()
        self.graphics_scene = QGraphicsScene()
        self.graphics_view.setScene(self.graphics_scene)
        self.graphics_view.setFixedSize(400, 200)
        self.graphics_row.addWidget(self.graphics_view)

        self.graphics_explanation = QLabel("")
        self.graphics_explanation.setText("Nothing is loaded yet!")
        self.graphics_explanation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.graphics_explanation.setWordWrap(True)
        self.graphics_row.addWidget(self.graphics_explanation)
        layout.addLayout(self.graphics_row)

        button_row = QHBoxLayout()

        self.load_button = QPushButton("Load Image")
        self.load_button.clicked.connect(self.load_image)
        button_row.addWidget(self.load_button)

        self.load_dataset_button = QPushButton("Load Dataset")
        self.load_dataset_button.clicked.connect(self.load_dataset)
        button_row.addWidget(self.load_dataset_button)

        layout.addLayout(button_row)

        self.infer = QPushButton("infer")
        self.infer.clicked.connect(self.get_inference)
        self.infer.setEnabled(False)

        layout.addWidget(self.infer)

        self.args_row = QHBoxLayout()
        self.T_arg = QLabel("T:")
        self.T_input = QTextEdit("50")
        self.refractory_arg = QLabel("Refractory (ms):")
        self.refractory_input = QTextEdit("2")
        self.threshold_arg = QLabel("Threshold (mV):")
        self.threshold_input = QTextEdit("-50")
        self.I_inj_arg = QLabel("I Inj (nA):")
        self.I_inj_input = QTextEdit("0.0")
        self.scale_arg = QLabel("Scale Weights:")
        self.scale_input = QTextEdit("1")
        self.T_arg.setFixedHeight(200)
        self.T_input.setFixedHeight(20)
        self.refractory_arg.setFixedHeight(20)
        self.refractory_input.setFixedHeight(20)
        self.threshold_arg.setFixedHeight(20)
        self.threshold_input.setFixedHeight(20)
        self.I_inj_arg.setFixedHeight(20)
        self.I_inj_input.setFixedHeight(20)
        self.scale_arg.setFixedHeight(20)
        self.scale_input.setFixedHeight(20)
        self.args_row.addWidget(self.T_arg)
        self.args_row.addWidget(self.T_input)
        self.args_row.addWidget(self.refractory_arg)
        self.args_row.addWidget(self.refractory_input)
        self.args_row.addWidget(self.threshold_arg)
        self.args_row.addWidget(self.threshold_input)
        self.args_row.addWidget(self.I_inj_arg)
        self.args_row.addWidget(self.I_inj_input)
        self.args_row.addWidget(self.scale_arg)
        self.args_row.addWidget(self.scale_input)
        layout.addLayout(self.args_row)

    def set_weights(self, weights: dict):
        self.weights = weights

    def set_type(self, type_str: str):
        try:
            self.connection_type = ConnectionType.from_string(type_str)
        except ValueError as e:
            QMessageBox.critical(self, "Invalid Connection Type", str(e))
            return

    def load_image(self):
        self.file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Image Files (*.png *.jpg *.bmp)")
        if self.file_path:
            self.dataset=None
            self.pil_image = Image.open(self.file_path).convert("RGB")
            pixmap = QPixmap(self.file_path)
            self.graphics_scene.clear()
            item = QGraphicsPixmapItem(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.graphics_scene.addItem(item)
            self.infer.setEnabled(True)
            self.graphics_explanation.setText(f"Image loaded from: {self.file_path}")

    def load_dataset(self):
        self.dataset = QFileDialog.getExistingDirectory(
            None,
            "Select Folder",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if self.dataset:
            try:
                example = [f for f in os.listdir(self.dataset) if os.path.isfile(os.path.join(self.dataset, f))][0]
                example = os.path.join(self.dataset, example)
                pixmap = QPixmap(example)
                self.graphics_scene.clear()
                item = QGraphicsPixmapItem(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.graphics_scene.addItem(item)
                self.file_path = None
                self.pil_image=None
                self.infer.setEnabled(True)
                self.graphics_explanation.setText(f"Dataset loaded from: {self.dataset}")
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", f"Failed to import dataset:\n{str(e)}")

    def tie_aware_accuracy(self, spike_counts: list, true_labels: list):
        """ 
        Calculate tie-aware accuracy based on spike counts and true labels.
        This method checks if the maximum spike count corresponds to the true label,
        and handles ties by dividing the accuracy score across tied neurons:
        credit 1/|T| if the true label is among the |T| tied maxima, and 0 if no
        output neuron spiked (as in the paper and Hardware/Version-IV/tools/score.py).
        Args:
            spike_counts (list): List of List of spike counts for each neuron for each image.
            true_labels (list): List of true labels corresponding to the input data.
        """
        correct = 0
        for sc, y_true in zip(spike_counts, true_labels):
            sc = np.asarray(sc)
            max_count = np.max(sc)
            if max_count == 0:      # no output spike: wrong, not a 10-way tie
                continue
            max_indices = np.where(sc == max_count)[0]
            if y_true in max_indices:
                correct += 1 / len(max_indices)
        return correct / len(true_labels)
    
    def get_args(self):
        try:
            T = int(self.T_input.toPlainText())
            refractory = int(self.refractory_input.toPlainText())
            threshold = float(self.threshold_input.toPlainText())
            I_inj = float(self.I_inj_input.toPlainText())
            scale = float(self.scale_input.toPlainText())
            return {
                'T': T,
                'refractory': refractory,
                'threshold': threshold,
                'I_inj': I_inj,
                'scale': scale
            }
        except ValueError as e:
            QMessageBox.critical(self, "Invalid Input", f"Please enter valid numeric values:\n{str(e)}")
            return None
    
    def get_inference(self):
        if self.pil_image!=None:
            self.brianSim = BrianSimulator(self.weights, self.get_args())
            predicted, spike_counts = self.brianSim.run_inference(self.pil_image, 0, type=self.connection_type)
            label = int(self.file_path.split("_")[-1].split(".")[0])
            self.show_output([predicted], [label], spike_counts, False)
        else:
            self.get_inference_all()

    def show_output(self, predicted: list, true: list, spikes: list, display_confusion_matrix: bool = True):
        """      
        Display the output of the inference process in a new window.
        Args:
            predicted (list): List of predicted labels.
            true (list): List of true labels.
            spikes (list): List of spike counts for each neuron.
            display_confusion_matrix (bool): Whether to display the confusion matrix.
        """
        self.infer_output_window= QWidget()
        self.infer_output_window.setWindowTitle("Inference Output")
        layout = QVBoxLayout(self.infer_output_window)

        if display_confusion_matrix:
            # predicted == -1 means no output spike; it counts as wrong and gets
            # its own "none" column in the confusion matrix
            acc = accuracy_score(true, predicted)
            tieAcc = self.tie_aware_accuracy(spikes, true)
            labels = sorted(set(true) | set(predicted))
            cm = confusion_matrix(true, predicted, labels=labels)
            disp = ConfusionMatrixDisplay(confusion_matrix=cm,
                                          display_labels=["none" if l == -1 else str(l) for l in labels])
            disp.plot(cmap='Blues')

            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            plt.close()
            buf.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(buf.read())
            scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            label = QLabel()
            label.setPixmap(scaled_pixmap)
            layout.addWidget(label)

            acc_label = QLabel(f"<b>Accuracy:</b> {acc:.2%}")
            tie_acc_label = QLabel(f"<b>Tie-Aware Accuracy:</b> {tieAcc:.2%}")
            layout.addWidget(acc_label)
            layout.addWidget(tie_acc_label)

        else:
            spike_str = "\n".join([f"\tNeuron{i}: {count}" for i, count in enumerate(spikes)])
            spike_label = QLabel(spike_str)
            spike_label.setWordWrap(True)
            layout.addWidget(QLabel("<b>Spike Counts:</b>"))
            layout.addWidget(spike_label)

            pred_vs_true_str = "\n".join(
                [f"Predicted: {'none (no output spike)' if p == -1 else p}, True: {t}" for p, t in zip(predicted, true)]
            )
            pred_label = QLabel(f"<b>Result:</b>\n{pred_vs_true_str}")
            layout.addWidget(pred_label)

        self.infer_output_window.show()

    def load_test_dataset(self, image_dir: str = "saved_dataset"):
        # TODO: load from csv
        images = []
        labels = []
        transform = transforms.ToTensor()

        for fname in os.listdir(image_dir):
            if fname.endswith(".png"):
                label = int(fname.split("_")[-1].split(".")[0])
                img_path = os.path.join(image_dir, fname)
                image = Image.open(img_path).convert("L")
                image_tensor = transform(image)

                images.append(image_tensor)
                labels.append(label)

        return list(zip(images, labels))

    def get_inference_all(self):
        """ 
        Perform inference on all images in the loaded dataset.
        This method initializes the inference process using a separate thread to avoid blocking the UI.
        """
        if not self.dataset:
            QMessageBox.critical(self, "No Dataset Loaded", "Please load a dataset before running inference.")
            return
        self.brianSim = BrianSimulator(self.weights, self.get_args())

        test_dataset = self.load_test_dataset(self.dataset)

        self.infer_thread = QThread()
        self.worker = InferenceWorker(self.brianSim, test_dataset, self.connection_type)
        self.worker.moveToThread(self.infer_thread)

        self.infer_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.cancelled_signal.connect(self.on_cancelled)

        self.progress_dialog = ProgressDialog()
        self.progress_dialog.canceled.connect(self.worker.stop)
        self.progress_dialog.show()

        self.worker.finished.connect(self.infer_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.infer_thread.finished.connect(self.infer_thread.deleteLater)

        self.infer_thread.start()

    def on_progress(self, value):
        self.progress_dialog.set_progress(value)

    def on_finished(self, predicted_labels, true_labels, spike_counts):
        self.progress_dialog.close()
        print("Inference finished")
        self.show_output(predicted_labels, true_labels, spike_counts)

    def on_cancelled(self):
        self.progress_dialog.close()
        print("Inference cancelled")

