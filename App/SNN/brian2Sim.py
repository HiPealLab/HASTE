from brian2 import *
import numpy as np
import torchvision.transforms as transforms
import random
import enum
import PIL
from PySide6.QtCore import QObject

class ConnectionType(enum.Enum):
    HODGKIN_HUXLEY = "Hodgkin-Huxley"
    LEAKY_INTEGRATE_AND_FIRE = "Leaky Integrate-and-Fire"
    IZHIKEVICH = "Izhikevich"

    @classmethod
    def from_string(cls, type_str):
        for member in cls:
            if member.value == type_str:
                return member
        raise ValueError(f"Unknown connection type: {type_str}")
    
    def to_string(self):
        return self.value
    
class BrianSimulator(QObject):
    """
    A class to run inference using Brian2 simulator for SNNs.
    It supports Hodgkin-Huxley, Leaky Integrate-and-Fire and Izhikevich models.
    The predicted class is the output neuron with the most spikes, or -1 if no
    output neuron spiked (such an image counts as wrong).
    """

    # Izhikevich fast-spiking preset, identical to the hardware/reference models
    # (Hardware/Version-IV/tools/gen_mem.py DEFAULTS["izh"]: A_Q8=26, B_Q8=50,
    # C_MV=-65, D_MV=2, VPEAK_MV=30, VMIN_MV=-150).
    IZH_A = 26 / 256
    IZH_B = 50 / 256
    IZH_C = -65
    IZH_D = 2
    IZH_VPEAK = 30
    IZH_VMIN = -150

    @staticmethod
    def _predict(spike_counts):
        """argmax of the output spike counts; -1 if no output neuron spiked."""
        return int(np.argmax(spike_counts)) if np.sum(spike_counts) > 0 else -1

    def __init__(self, weights, args=None):
        self.layer_weights = [np.array(w).T for w in weights]
        if args is not None:
            self.args = args
        else:
            self.args = {'T' : 50,
                     'refractory': 2,
                     'threshold': -50,
                     'I_inj': 0.5,
                     'scale': 1}

    def set_args(self, args: dict):
        self.args = args
        
    def run_inference(self, img: PIL.Image, label: int, type: ConnectionType = ConnectionType.HODGKIN_HUXLEY):
        if type == ConnectionType.HODGKIN_HUXLEY:
            return self._run_hh_inference(img, label)
        elif type == ConnectionType.LEAKY_INTEGRATE_AND_FIRE:
            return self._run_lif_inference(img, label)
        elif type == ConnectionType.IZHIKEVICH:
            return self._run_izh_inference(img, label)
        else:
            raise NotImplementedError()

    def _run_hh_inference(self, img: PIL.Image, label: int)-> tuple:
        """
        Runs inference using Hodgkin-Huxley model with Brian2.
        Args:
            img: Input image from Pillow.
            label: Input image label, not used for now.
        Return:
            predicted: Predicted class index.
            spike_counts: Spike counts for each output neuron.
        """
        # init params

        @check_units(v=volt, result=Hz)
        def alpha_m(v):
            dv = (25*mV - v)
            return clip(dv/(exp(dv/(10*mV)) - 1), -1e6, 1e6) * (0.1/mV) / ms

        C = 1*uF/cm**2
        gNa = 120*msiemens/cm**2
        gK = 36*msiemens/cm**2
        gL = 0.3*msiemens/cm**2
        ENa = 120*mV
        EK = -12*mV
        EL = -10.5*mV

        self.hh_eqs = '''
        dv/dt = (I_inj - INa - IK - IL) / C : volt
        INa = gNa * m**3 * h * (v - ENa) : amp/meter**2
        IK = gK * n**4 * (v - EK) : amp/meter**2
        IL = gL * (v - EL) : amp/meter**2

        dm/dt = alpham*(1-m) - betam*m : 1
        dn/dt = alphan*(1-n) - betan*n : 1
        dh/dt = alphah*(1-h) - betah*h : 1

        alpham = 0.1/mV*(25*mV - v)/(exp((25*mV - v)/(10*mV)) - 1)/ms : Hz (constant over dt)
        betam = 4*exp(-v/(18*mV))/ms : Hz (constant over dt)
        alphah = 0.07*exp(-v/(20*mV))/ms : Hz (constant over dt)
        betah = 1/(exp((30*mV - v)/(10*mV)) + 1)/ms : Hz (constant over dt)
        alphan = 0.01/mV*(10*mV - v)/(exp((10*mV - v)/(10*mV)) - 1)/ms : Hz (constant over dt)
        betan = 0.125*exp(-v/(80*mV))/ms : Hz (constant over dt)
        I_inj : amp/meter**2
        '''


        device.reinit()
        device.activate()
        defaultclock.dt = 0.1*ms

        # start simulation

        input_sqrt = int(self.layer_weights[0].shape[1]**0.5)
        assert (input_sqrt**2 == self.layer_weights[0].shape[1]), "Input size must be a perfect square"
        transform = transforms.Compose([
                transforms.Grayscale(num_output_channels=1),
                transforms.ToTensor(),
                transforms.Resize((input_sqrt, input_sqrt))
            ])
        img = transform(img)
        img = img.unsqueeze(0)
        img = img.to('cpu')

        from spikingjelly.activation_based import encoding
        encoder = encoding.PoissonEncoder()
        T = self.args['T']
        spike_trains = []
        for t in range(T):
            encoded_img = encoder(img)
            spike_trains.append(encoded_img.view(-1).squeeze().numpy())

        spike_indices = []
        spike_times = []
        for t in range(T):
            dt = defaultclock.dt
            time_in_ms = t * dt
            for neuron_idx, spike in enumerate(spike_trains[t]):
                if spike == 1:
                    spike_indices.append(neuron_idx)
                    spike_times.append(time_in_ms)
        spike_indices = np.array(spike_indices)
        spike_times = np.array(spike_times) * second
        input_size = self.layer_weights[0].shape[1]
        input_layer = SpikeGeneratorGroup(input_size, spike_indices, spike_times)

        threshold = f'v > {self.args["threshold"]}*mV'
        reset = ''
        refractory = self.args['refractory']*ms
        scale = self.args['scale'] * amp / cm**2

        layers = [input_layer]
        neuron_groups = []
        synapses = []

        for i, w in enumerate(self.layer_weights):
            out_size, in_size = w.shape

            group = NeuronGroup(out_size, self.hh_eqs,
                                threshold=threshold,
                                reset=reset,
                                refractory=refractory,
                                method='exponential_euler')

            group.v = -65*mV
            group.m = 0.05
            group.h = 0.6
            group.n = 0.32
            group.I_inj = self.args['I_inj']*amp/cm**2

            if i == 0:
                neuron_idx = random.randint(0, out_size - 1)
                mon_voltage = StateMonitor(group, 'v', record=[neuron_idx])

            neuron_groups.append(group)
            layers.append(group)

            syn = Synapses(layers[i], group, model='w : amp/meter**2', on_pre='I_inj_post += w')
            syn.connect(True)
            syn.w = w.T.flatten() * scale
            synapses.append(syn)

        mon_output = SpikeMonitor(layers[-1])

        all_components = [input_layer] + neuron_groups + synapses + [mon_output]
        net = Network(*all_components)
        net.run(T * defaultclock.dt)

        final_layer_size = self.layer_weights[-1].shape[0]
        spike_counts = np.array([mon_output.count[i] for i in range(final_layer_size)])
        predicted = self._predict(spike_counts)

        return predicted, spike_counts
    
    def _run_izh_inference(self, img: PIL.Image, label: int) -> tuple:
        """
        Runs inference using Izhikevich neurons with Brian2.
        Uses the fast-spiking preset of the hardware (class constants IZH_*):
        a spike is emitted when v reaches the model's peak IZH_VPEAK (30 mV),
        so the GUI "Threshold" field does not apply to this model, and v is
        floored at IZH_VMIN (-150 mV) after every integration step, as in the
        hardware.
        Args:
            img: Input image from Pillow.
            label: Input image label, not used for now.
        Return:
            predicted: Predicted class index.
            spike_counts: Spike counts for each output neuron.
        """

        # init args
        self.izh_eqs = '''
        dv/dt = (0.04*v**2 + 5*v + 140 - u + I_inj)/ms : 1
        du/dt = a*(b*v - u)/ms : 1
        I_inj : 1
        a : 1
        b : 1
        c : 1
        d : 1
        C : 1
        '''


        device.reinit()
        device.activate()
        defaultclock.dt = 0.1*ms

        # start simulation

        input_sqrt = int(self.layer_weights[0].shape[1]**0.5)
        assert (input_sqrt**2 == self.layer_weights[0].shape[1]), "Input size must be a perfect square"
        transform = transforms.Compose([
                transforms.Grayscale(num_output_channels=1),
                transforms.ToTensor(),
                transforms.Resize((input_sqrt, input_sqrt))
            ])
        img = transform(img)
        img = img.unsqueeze(0)
        img = img.to('cpu')

        from spikingjelly.activation_based import encoding
        encoder = encoding.PoissonEncoder()
        T = self.args['T']
        spike_trains = []
        for t in range(T):
            encoded_img = encoder(img)
            spike_trains.append(encoded_img.view(-1).squeeze().numpy())

        spike_indices = []
        spike_times = []
        for t in range(T):
            dt = defaultclock.dt
            time_in_ms = t * dt
            for neuron_idx, spike in enumerate(spike_trains[t]):
                if spike == 1:
                    spike_indices.append(neuron_idx)
                    spike_times.append(time_in_ms)
        spike_indices = np.array(spike_indices)
        spike_times = np.array(spike_times) * second
        input_size = self.layer_weights[0].shape[1]
        input_layer = SpikeGeneratorGroup(input_size, spike_indices, spike_times)

        threshold = f'v >= {self.IZH_VPEAK}'
        reset = '''
        v = c
        u += d
        '''
        refractory = 0*ms
        scale = self.args['scale']

        layers = [input_layer]
        neuron_groups = []
        synapses = []

        for i, w in enumerate(self.layer_weights):
            out_size, in_size = w.shape

            group = NeuronGroup(out_size, self.izh_eqs,
                                threshold=threshold,
                                reset=reset,
                                refractory=refractory,
                                method='euler')

            group.a = self.IZH_A
            group.b = self.IZH_B
            group.c = self.IZH_C
            group.d = self.IZH_D
            group.C = 100

            group.v = group.c
            group.u = group.b * group.v
            group.I_inj = self.args['I_inj']
            # inhibitory floor on v after every integration step (as in the hardware)
            group.run_regularly(f'v = clip(v, {self.IZH_VMIN}, inf)', when='before_thresholds')

            if i == 0:
                neuron_idx = random.randint(0, out_size - 1)
                mon_voltage = StateMonitor(group, 'v', record=[neuron_idx])

            neuron_groups.append(group)
            layers.append(group)

            syn = Synapses(layers[i], group, model='w : 1', on_pre='I_inj_post += w')
            syn.connect(True)
            syn.w = w.T.flatten() * scale
            synapses.append(syn)

        mon_output = SpikeMonitor(layers[-1])

        all_components = [input_layer] + neuron_groups + synapses + [mon_output]
        net = Network(*all_components)
        net.run(T * defaultclock.dt)

        final_layer_size = self.layer_weights[-1].shape[0]
        spike_counts = np.array([mon_output.count[i] for i in range(final_layer_size)])
        predicted = self._predict(spike_counts)

        return predicted, spike_counts


    def _run_lif_inference(self, img: PIL.Image, label: int)-> tuple:
        """
        Runs inference using Leaky Integrate-and-Fire model with Brian2.
        Args:
            img: Input image tensor.
            label: Input image label, not used for now.
        Return:
            predicted: Predicted class index.
            spike_counts: Spike counts for each output neuron.
        """
        # init params

        tau = 10*ms
        v_rest = -65*mV
        v_reset = -65*mV
        v_thresh = self.args['threshold']*mV

        self.lif_eqs = '''
        dv/dt = (-(v - v_rest) + R_m * I_inj) / tau : volt (unless refractory)
        I_inj : amp
        R_m : ohm
        '''

        device.reinit()
        device.activate()
        defaultclock.dt = 0.1*ms

        # start simulation

        input_sqrt = int(self.layer_weights[0].shape[1]**0.5)
        assert (input_sqrt**2 == self.layer_weights[0].shape[1]), "Input size must be a perfect square"
        transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=1),
            transforms.ToTensor(),
            transforms.Resize((input_sqrt, input_sqrt))
        ])
        img = transform(img)
        img = img.unsqueeze(0).to('cpu')

        from spikingjelly.activation_based import encoding
        encoder = encoding.PoissonEncoder()
        T = self.args['T']
        spike_trains = []
        for t in range(T):
            encoded_img = encoder(img)
            spike_trains.append(encoded_img.view(-1).squeeze().numpy())

        spike_indices = []
        spike_times = []
        for t in range(T):
            dt = defaultclock.dt
            time_in_ms = t * dt
            for neuron_idx, spike in enumerate(spike_trains[t]):
                if spike == 1:
                    spike_indices.append(neuron_idx)
                    spike_times.append(time_in_ms)
        spike_indices = np.array(spike_indices)
        spike_times = np.array(spike_times) * second

        input_size = self.layer_weights[0].shape[1]
        input_layer = SpikeGeneratorGroup(input_size, spike_indices, spike_times)

        threshold = 'v > v_thresh'
        reset = 'v = v_reset'
        refractory = self.args['refractory']*ms

        layers = [input_layer]
        neuron_groups = []
        synapses = []
        scale = self.args['scale'] * 1e-9 * amp # * 1e-9

        for i, w in enumerate(self.layer_weights):
            out_size, in_size = w.shape

            group = NeuronGroup(
                out_size, self.lif_eqs,
                threshold=threshold,
                reset=reset,
                refractory=refractory,
                method='euler'
            )

            group.v = v_rest
            group.R_m = 100e6*ohm
            group.I_inj = self.args['I_inj']*nA

            if i == 0:
                neuron_idx = random.randint(0, out_size - 1)
                mon_voltage = StateMonitor(group, 'v', record=[neuron_idx])

            neuron_groups.append(group)
            layers.append(group)

            syn = Synapses(layers[i], group, model='w : amp', on_pre='I_inj_post += w')
            syn.connect(True)
            syn.w = w.T.flatten() * scale
            synapses.append(syn)

        mon_output = SpikeMonitor(layers[-1])

        all_components = [input_layer] + neuron_groups + synapses + [mon_output]
        net = Network(*all_components)
        net.run(T * defaultclock.dt)

        final_layer_size = self.layer_weights[-1].shape[0]
        spike_counts = np.array([mon_output.count[i] for i in range(final_layer_size)])
        predicted = self._predict(spike_counts)

        return predicted, spike_counts
