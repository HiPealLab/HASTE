import time
import os
import numpy as np

import torch
import torch.nn as nn
import torchvision
import torch.nn.functional as F
import torch.utils.data as data
from torch.cuda import amp

from spikingjelly.activation_based import neuron, encoding, functional, surrogate, layer

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox,
    QDialog, QDialogButtonBox, QLabel, QSpinBox, QProgressBar
)

class TrainingWorker(QThread):
    """ 
    Worker thread for training a Spiking Neural Network (SNN) on the MNIST dataset.
    This class handles the training process in a separate thread to keep the GUI responsive.
    Signals:
        - progress_changed: Emitted when the training progress changes (0-100).
        - training_finished: Emitted when training is complete, providing the output file path and training accuracy.
        - epoch_progress_changed: Emitted to update the progress of the current epoch.
    """

    progress_changed = Signal(int)
    training_finished = Signal(str, float)
    epoch_progress_changed = Signal(int)

    def __init__(self, parent_dialog, args: dict, model: nn.Module):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.args = args
        self.model = model
        self.output_file = None

    def run(self):
        input_size = int(self.args['input_size'])

        assert (input_size ** 0.5).is_integer(), "Input size must be a perfect square"
        input_sqrt = int(input_size ** 0.5)
        self.model.to(self.args['device'])
        transform = torchvision.transforms.Compose([
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Resize((input_sqrt, input_sqrt)),
        ])
        train_dataset = torchvision.datasets.MNIST(
            root=self.args['data_dir'], train=True, transform=transform, download=True
        )
        train_data_loader = data.DataLoader(
            dataset=train_dataset, batch_size=self.args['b'], shuffle=True,
            drop_last=True, num_workers=self.args['j'], pin_memory=True
        )

        scaler = amp.GradScaler() if self.args['amp'] else None
        optimizer = None
        if self.args['opt'] == 'sgd':
            optimizer = torch.optim.SGD(self.model.parameters(), lr=self.args['lr'], momentum=self.args['momentum'])
        elif self.args['opt'] =='adam8b':
            # optional dependency (CUDA-oriented): imported only when selected,
            # so the GUI starts without it
            try:
                from bitsandbytes import optim as bnb_optim
            except ImportError as e:
                raise RuntimeError("optimizer 'adam8b' needs the bitsandbytes package "
                                   "(pip install bitsandbytes); choose 'adam' or 'sgd' otherwise") from e
            optimizer = bnb_optim.AdamW8bit(self.model.parameters(), lr=self.args['lr'])
        else:
            optimizer = torch.optim.Adam(self.model.parameters(), lr=self.args['lr'])

        start_epoch = 0
        encoder = encoding.PoissonEncoder()

        epochs = self.args["epochs"]
        train_acc = 0
        for epoch in range(start_epoch, epochs):
            train_acc = self.parent_dialog.train_snn_epoch(self.args, self.model, epoch, optimizer, train_data_loader,
                                                encoder, scaler, self.epoch_progress_changed)
            self.progress_changed.emit(int(((epoch + 1) / epochs) * 100))
        
        layer_weights = []
        self.model.eval() 
        for i in range(len(self.model.cpu().layer)):
            if (self.model.cpu().layer[i]._get_name() == 'Linear'):
                layer_weights.append(self.model.cpu().layer[i].weight.detach().numpy())
        self.output_file = os.path.join(self.args['out_dir'], f'weights-final.npz')
        os.makedirs(self.args['out_dir'], exist_ok=True)
        np.savez(self.output_file, *layer_weights)

        self.training_finished.emit(self.output_file, train_acc)

class SNN(nn.Module):
    def __init__(self, input_size, layer_sizes, tau, type="izh"):
        super().__init__()
        layers = [layer.Flatten()]
        prev_size = input_size
        for size in layer_sizes:
            layers.append(layer.Linear(prev_size, size, bias=False))
            if type == "izh":
                layers.append(neuron.IzhikevichNode(tau=tau, surrogate_function=surrogate.ATan()))
            else:
                layers.append(neuron.LIFNode(tau=tau, surrogate_function=surrogate.ATan()))
            prev_size = size
        self.layer = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor):
        return self.layer(x)

class ArgsDialog(QDialog):
    """
    Dialog for configuring SNN training parameters.
    This dialog allows the user to set various training parameters and
    SNN architecture parameters. It emits signals when the training arguments are ready
    and when training is finished.
    Signals:
        - args_ready: Emitted with the training arguments and the SNN model when the user accepts the dialog.
        - training_finished: Emitted with the output file path and training accuracy when training is complete.
    """
    args_ready = Signal(dict, nn.Module)
    training_finished = Signal(str, float)

    def __init__(self, parent=None, input_size: int =64, layer_sizes: list =[128]):
        super().__init__(parent)
        self.setWindowTitle("Configure SNN Training Parameters")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        self.output_file = None

        def add_spin(name, default, minv, maxv, step=1, float_type=False):
            if float_type:
                widget = QDoubleSpinBox()
                widget.setDecimals(6)
            else:
                widget = QSpinBox()
            widget.setMinimum(minv)
            widget.setMaximum(maxv)
            widget.setSingleStep(step)
            widget.setValue(default)
            self.inputs[name] = widget
            form.addRow(QLabel(name), widget)

        def add_text(name, default):
            widget = QLineEdit(default)
            self.inputs[name] = widget
            form.addRow(QLabel(name), widget)

        def add_combo(name, options, default):
            widget = QComboBox()
            widget.addItems(options)
            widget.setCurrentText(default)
            self.inputs[name] = widget
            form.addRow(QLabel(name), widget)

        # args
        add_spin("T", 10, 1, 10000)
        add_combo("device", ["cpu", "cuda"], "cpu")
        add_spin("b", 4, 1, 10000)
        add_spin("epochs", 1, 1, 10000)
        add_spin("j", 4, 0, 64)
        add_text("data_dir", os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Train", "datasets", "mnist")))
        add_text("out_dir", "./logs")
        add_text("resume", "")
        add_combo("amp", ["False", "True"], "False")
        add_combo("opt", ["sgd", "adam", "adam8b"], "adam")
        add_spin("momentum", 0.9, 0.0, 0.999, step=0.01, float_type=True)   # SGD momentum (was 90)
        add_spin("lr", 1e-3, -10000, 10000, float_type=True)
        add_spin("tau", 2, -10000, 10000, float_type=True)
        add_text("input_size", str(input_size))
        add_text("layer_sizes", ",".join(str(i) for i in layer_sizes))
        add_combo("type", ["izh", "lif"], "izh")
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        args = {}
        for name, widget in self.inputs.items():
            if isinstance(widget, QLineEdit):
                val = widget.text()
                args[name] = None if val.strip() == "" else val
            elif isinstance(widget, QSpinBox):
                args[name] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                args[name] = widget.value()
            elif isinstance(widget, QComboBox):
                text = widget.currentText()
                if text in ["True", "False"]:
                    args[name] = text == "True"
                else:
                    args[name] = text

        input_size = int(args["input_size"])
        layer_sizes = [int(x.strip()) for x in args["layer_sizes"].split(",") if x.strip()]
        tau = float(args["tau"])
        args["momentum"] = float(args["momentum"])
        args["lr"] = float(args["lr"])

        snn_model = SNN(input_size, layer_sizes, tau, args["type"])

        # progress bar
        if hasattr(self, 'progress_bar'):
            self.layout().removeWidget(self.progress_bar)
        if hasattr(self, 'epoch_progress_bar'):
            self.layout().removeWidget(self.progress_bar)
                            
        self.progress_bar = QProgressBar(self)
        self.layout().addWidget(self.progress_bar)
        self.progress_bar.setValue(0)

        self.epoch_progress_bar = QProgressBar(self)
        self.layout().addWidget(self.epoch_progress_bar)
        self.epoch_progress_bar.setValue(0)

        # training
        self.worker = TrainingWorker(self, args, snn_model)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.epoch_progress_changed.connect(self.epoch_progress_bar.setValue)
        self.worker.training_finished.connect(self.train_finished)
        self.worker.start()
    
    def train_finished(self, output_file: str, training_acc: float):
        self.progress_bar.setValue(100)
        self.output_file = self.worker.output_file
        self.training_finished.emit(output_file, training_acc)
        self.close()

    def train_snn_epoch(self, args: dict, model: nn.Module, epoch: int, optimizer, 
                        train_data_loader, encoder, scaler, epoch_progress_changed) -> float:
        """ 
        Train a single epoch of the SNN model.
        Args:
            args (dict): Training arguments including device, batch size, etc.
            model (nn.Module): The SNN model to train.
            epoch (int): The current epoch number.
            optimizer: The optimizer to use for training.
            train_data_loader (DataLoader): DataLoader for the training dataset.
            encoder: The spikking encoder to use for input data.
            scaler: GradScaler for mixed precision training (if applicable).
            epoch_progress_changed (Signal): Signal to update the epoch progress bar.
        Returns:
            float: The training accuracy for the epoch.
        """

        net = model.to(dtype=torch.float)
        start_time = time.time()
        net.train()
        train_loss = 0
        train_acc = 0
        train_samples = 0
        print("starting new epoch...")
        total_batches = len(train_data_loader)
        batch_idx = 0
        for img, label in train_data_loader:
            optimizer.zero_grad()
            img = img.to(args['device'])
            label = label.to(args['device'])
            label_onehot = F.one_hot(label, 10).float()

            if scaler is not None:
                with amp.autocast():
                    out_fr = 0.
                    for t in range(args['T']):
                        encoded_img = encoder(img)
                        out_fr += net(encoded_img)
                    out_fr = out_fr / args['T']
                    loss = F.mse_loss(out_fr, label_onehot)

                    # add l2 regularization
                    # l2_reg = 0.0
                    # for param in net.parameters():
                    #     l2_reg += torch.norm(param, 2)
                    # loss += args['lr'] * l2_reg

                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                out_fr = 0.
                for t in range(args['T']):
                    encoded_img = encoder(img).to(torch.float)
                    out_fr += net(encoded_img)
                out_fr = out_fr / args['T']
                loss = F.mse_loss(out_fr, label_onehot)
                loss.backward()
                optimizer.step()

            train_samples += label.numel()
            train_loss += loss.item() * label.numel()
            train_acc += (out_fr.argmax(1) == label).float().sum().item()
            functional.reset_net(net)

            batch_idx += 1
            progress = int((batch_idx / total_batches) * 100)
            epoch_progress_changed.emit(progress)
        epoch_progress_changed.emit(100)


        train_time = time.time()
        train_speed = train_samples / (train_time - start_time)
        train_loss /= train_samples
        train_acc /= train_samples

        print(f'epoch={epoch}, train_loss={train_loss:.4f}, train_acc={train_acc:.4f}, ')
        print(f'train speed={train_speed:.4f} images/s')
        return train_acc
