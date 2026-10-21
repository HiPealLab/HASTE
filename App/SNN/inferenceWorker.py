from PySide6.QtWidgets import QDialog, QVBoxLayout, QProgressBar, QPushButton
from PySide6.QtCore import QObject, Signal, Slot

class ProgressDialog(QDialog):
    canceled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Running inference...")
        self.setModal(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.canceled.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_btn)

    def set_progress(self, value):
        self.progress_bar.setValue(value)

class InferenceWorker(QObject):
    progress = Signal(int)
    finished = Signal(list, list, list)
    cancelled_signal = Signal()

    def __init__(self, brianSim, test_dataset, connection_type):
        super().__init__()
        self.brianSim = brianSim
        self.test_dataset = test_dataset
        self.connection_type = connection_type
        self.cancelled = False

    @Slot()
    def run(self):
        predicted_labels = []
        true_labels = []
        spike_counts = []

        total = len(self.test_dataset)
        for i, (image_tensor, true_label) in enumerate(self.test_dataset):
            if self.cancelled:
                self.cancelled_signal.emit()
                return

            from torchvision.transforms.functional import to_pil_image
            pil_image = to_pil_image(image_tensor)

            predicted, spike_count = self.brianSim.run_inference(pil_image, 0, type=self.connection_type)
            predicted_labels.append(predicted)
            true_labels.append(true_label)
            spike_counts.append(spike_count)

            percent_done = int((i + 1) / total * 100)
            self.progress.emit(percent_done)

        self.finished.emit(predicted_labels, true_labels, spike_counts)

    def stop(self):
        self.cancelled = True
