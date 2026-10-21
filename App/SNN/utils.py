from email.mime import image
from PIL import Image
import sys
import os

def gen_verilog(n: int, default_const: str = "8'd255") -> str:
    if n < 1:
        raise ValueError("Number of layers must be >= 1")

    out_ass = []

    # ------- lay wires + range checks -------
    out_ass.append("//dynass")
    lay_names = ", ".join(f"lay{i}" for i in range(1, n + 1))
    out_ass.append(f"  wire {lay_names};")
    for i in range(1, n + 1):
        out_ass.append(f"  assign lay{i} = ((spikeN >= SL{i}) && (spikeN <= FL{i}));")
    out_ass.append("//dynass")
    out_ass.append("")
    out_lay = []
    # helper for pretty, multi-line ternary chains
    def ternary_chain(pairs, default_value):
        """
        pairs: list of (cond, expr) tuples; printed as:
            (cond0) ? (expr0) :
            (cond1) ? (expr1) :
            default;
        """
        if not pairs:
            return f"{default_value};"
        lines = []
        for idx, (cond, expr) in enumerate(pairs):
            head = "(" + cond + ") ? (" + expr + ") :"
            if idx == 0:
                lines.append(head)
            else:
                lines.append("           " + head)
        lines.append("           " + default_value + ";")
        return "\n".join(lines)

    # ------- J_ADDR -------
    # For layers 1..N-1: layi => spikeN - SLi ; last layer falls to default
    j_pairs = [(f"lay{i}", f"spikeN - SL{i}") for i in range(1, max(1, n))]
    out_lay.append("//dynlay")
    if n >= 2:
        out_lay.append("        J_ADDR  <= " + ternary_chain(j_pairs, default_const))
    else:
        out_lay.append(f"        J_ADDR  <= {default_const};")

    # ------- I_ADDR -------
    # For layers 1..N-1: layi => SL(i+1)
    i_pairs = [(f"lay{i}", f"SL{i+1}") for i in range(1, n)]
    if n >= 2:
        out_lay.append("        I_ADDR  <= " + ternary_chain(i_pairs, default_const))
    else:
        out_lay.append(f"        I_ADDR  <= {default_const};")

    # ------- FINISHN -------
    # For layers 1..N-1: layi => FL(i+1)
    f_pairs = [(f"lay{i}", f"FL{i+1}") for i in range(1, n)]
    if n >= 2:
        out_lay.append("        FINISHN <= " + ternary_chain(f_pairs, default_const))
    else:
        out_lay.append(f"        FINISHN <= {default_const};")
    out_lay.append("//dynlay")

    return "\n".join(out_lay), "\n".join(out_ass)

def generate_layer_mem_text(neuron_counts):
    verilog_lines = []
    verilog_lines.append("module layerMem (")
    verilog_lines.append("    input       clk,")
    verilog_lines.append("    input       rd_en,")
    verilog_lines.append("    input [7:0] addr,")
    verilog_lines.append("")
    verilog_lines.append("    output reg [7:0] offset,")
    verilog_lines.append("    output reg [7:0] count,")
    verilog_lines.append("    output reg [7:0] nextstart,")
    verilog_lines.append("    output reg [7:0] nextlayer")
    verilog_lines.append(");")

    num_layers = len(neuron_counts)
    verilog_lines.append(f"  reg [31:0] layers[{num_layers}] = {{")

    # Generate offset/count entries
    offset = 0
    layer_lines = []
    layer_lines.append("    //offset count   nstart  nend")
    for i, count in enumerate(neuron_counts):
        try:
            layer_lines.append(f"    {{ {{8'd{offset}}}, {{8'd{count-1}}}, {{8'd{sum(neuron_counts[:i+1])}}}, {{8'd{sum(neuron_counts[:i+2])-1}}}}}")
        except:
            layer_lines.append(f"    {{{{8'd{offset}}}, {{8'd{count-1}}}, {{8'd0}}, {{8'd0}}}}")
        offset += count

    # Join with commas and close the list
    verilog_lines.append(",\n".join(layer_lines))
    verilog_lines.append("  };")
    verilog_lines.append("")
    verilog_lines.append("  always @(posedge clk) begin")
    verilog_lines.append("    if (rd_en) begin")
    verilog_lines.append("      offset <= layers[addr][31:24];")
    verilog_lines.append("      count  <= layers[addr][23:16];")
    verilog_lines.append("      nextstart <= layers[addr][15:8];")
    verilog_lines.append("      nextlayer <= layers[addr][7:0];")
    verilog_lines.append("    end")
    verilog_lines.append("  end")
    verilog_lines.append("")
    verilog_lines.append("endmodule")

    return "\n".join(verilog_lines)

def generate_syn_mem_text(synapse_map, neuron_counts, neuron_type):
    WIDTH = 8
    INTER_LAYER_FRAC = 4
    verilog_lines = []    
    NEURON_COUNT = 256
    weight_data = []
    for layer in synapse_map:
        for row in layer:
            row_weights = [conn.weight for conn in row]
            weight_data.append(row_weights)

    num_neurons = len(weight_data)
    # verilog_lines.append((f"  reg [{WIDTH-1}:0] syanpse_array[256][256] = ") + ("'{"))

    import copy
    num_layer=0

    def int_to_binary(num, n):
        if num < 0:
            num = (1 << n) + num
        bin_repr = bin(num)[2:].zfill(n)
        if len(bin_repr) > n:
            raise ValueError(f"Number {num} cannot be represented in {n} bits.")
        return bin_repr

    # start from last layer and go backwards
    curr=0
    for num_layer in range(1, len(neuron_counts), 1):
        num_neurons = neuron_counts[num_layer]
        if num_neurons == 0:
            continue

        prev_layer_neuron_count = neuron_counts[num_layer-1]
        if prev_layer_neuron_count == 0:
            continue
        
        for den in range(neuron_counts[num_layer]):
            verilog_lines.append(f"reg [{WIDTH-1}:0] Den{curr}[{prev_layer_neuron_count}] = '{{")
            curr += 1

            this_neuron = ""
            neurons_until_now = sum(neuron_counts[:num_layer]) - neuron_counts[num_layer-1]
            for i in range(neurons_until_now, neurons_until_now+neuron_counts[num_layer-1]):
                bin_a_m = int_to_binary((int(weight_data[i][den] * (2 ** INTER_LAYER_FRAC))), (WIDTH))
                this_neuron += f"8'b{bin_a_m}, "
            this_neuron = this_neuron[:-2] + "\n};"
            verilog_lines.append(copy.deepcopy(this_neuron))

    if neuron_type == "lif":
        verilog_lines +=["""
    localparam signed THRESHOLD = {{16'd50}, {16'd0}};
    localparam signed RESTVOLT = 32'd0;
    localparam RERRACTORY = 8'd0;

    typedef struct {
    reg signed [31:0] volt;
    reg [7:0]         refractory;
    reg signed [31:0] threshold;
    reg [7:0]         dendrite[64];
    } neuron_t;
    """]
        verilog_lines.append(f"neuron_t neuron_reg[{sum(neuron_counts)-neuron_counts[0]}]='{{")
        for i in range(sum(neuron_counts)-neuron_counts[0]):
            verilog_lines.append(f"    '{{RESTVOLT, 8'd0, {{{{16'd30}}, {{16'd0}}}}, Den{i}}},")
        verilog_lines[-1]=verilog_lines[-1][:-1] + "\n};\n"


    elif neuron_type=='izh':
        verilog_lines+=["""
    // localparam signed TESTVOLT = {{16'd41}, {16'd0}};
    localparam signed THRESHOLD = {{16'd50}, {16'd0}};
    localparam signed RESTVOLT = 32'd0;
    localparam RERRACTORY = 8'd0;

    typedef struct {
    reg signed [31:0] volt;
    reg signed [31:0] reco;
    // a in [0.01,0.2]
    reg unsigned [7:0] tau;
    // b in [0.1,0.3]
    reg unsigned [7:0] gain;
    // c in [-70,-50]
    reg [31:0] vreset;
    // d in [0,15]
    reg unsigned [7:0] urest;
    reg unsigned [7:0] refractory;

    reg [7:0] dendrite[64];
    } neuron_t;
    """]
        
        verilog_lines.append(f"neuron_t neuron_reg[{sum(neuron_counts)-neuron_counts[0]}]='{{")
        for i in range(sum(neuron_counts)-neuron_counts[0]):
            verilog_lines.append(f"    '{{RESTVOLT, 32'd0, 8'd5, 8'd50, {{{{16'hFFBF}}, {{16'd0}}}}, {{{{4'd8}}, {{8'd0}}}}, 8'd0, Den{i}}},")
                # '{RESTVOLT, 32'd0, 8'd5, 8'd50, {{16'hFFBF}, {16'd0}}, {{4'd8}, {8'd0}}, 8'd0, Den0},
        verilog_lines[-1]=verilog_lines[-1][:-1] + "\n};\n"


    elif neuron_type=="hh":
        verilog_lines+=["""
    localparam signed UPPER = {{9'd80}, {7'd0}};
    localparam signed LOWER = {{9'd0}, {7'd0}};
    localparam signed RESTVOLT = {{9'd0}, {7'd0}};
    localparam signed TESTVOLT = {{9'd50}, {7'd0}};

    typedef struct {
    reg signed [15:0] volt;
    reg signed [15:0] n;
    reg signed [15:0] m;
    reg signed [15:0] h;

    reg unsigned [15:0] gK;
    reg unsigned [15:0] gNa;
    reg unsigned [15:0] gL;

    reg signed [15:0] upper;
    reg signed [15:0] lower;

    reg unsigned spk;

    reg [7:0] dendrite[64];
    } neuron_t;
"""]
        
        verilog_lines.append(f"neuron_t neuron_reg[{sum(neuron_counts)-neuron_counts[0]}]='{{")
        for i in range(sum(neuron_counts)-neuron_counts[0]):
            verilog_lines.append(f"    '{{RESTVOLT, {{{{2'd0}}, {{14'd0}}}},{{{{2'd0}}, {{14'd0}}}},{{{{2'd1}}, {{14'd0}}}},{{{{8'd36}}, {{8'd0}}}},{{{{8'd120}}, {{8'd0}}}},{{{{8'd0}}, {{8'd76}}}},UPPER,LOWER,1'd0, Den{i}}},")
                                    # '{RESTVOLT,{{2'd0}, {14'd0}},{{2'd0}, {14'd0}},{{2'd1}, {14'd0}},{{8'd36}, {8'd0}},{{8'd120}, {8'd0}},{{8'd0}, {8'd76}},UPPER,LOWER,1'd0,Den0},
        verilog_lines[-1]=verilog_lines[-1][:-1] + "\n};\n"


    else:
        print("WARNING: neuron type is not supported!!")


    i = 1
    neurons_until_now = 0
    for count in neuron_counts[1:]:
        verilog_lines.append(f"localparam unsigned SL{i} = 8'd{neurons_until_now};")
        verilog_lines.append(f"localparam unsigned FL{i} = 8'd{neurons_until_now + count - 1};")
        neurons_until_now += count
        i += 1
    verilog_lines.append(f"localparam unsigned SLAST = SL{len(neuron_counts)-1};")
    verilog_lines.append(f"localparam unsigned FLAST = FL{len(neuron_counts)-1};")

    return "\n".join(verilog_lines)

from torchvision import transforms

def encode_image_spikes(image_path, inp_size=64, T=100, seed=0):
    """Poisson-encode an image (grayscale, resized to sqrt(inp_size)^2) into T
    lists of spiking input indices.  Seeded, so software and hardware runs
    (and reruns) see exactly the same spike trains."""
    import torch
    from spikingjelly.activation_based import encoding
    torch.manual_seed(seed)
    input_sqrt = int(inp_size**0.5)
    assert (input_sqrt**2 == inp_size), "Input size must be a perfect square"
    transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=1),
            transforms.ToTensor(),
            transforms.Resize((input_sqrt, input_sqrt))
        ])
    img = transform(Image.open(image_path).convert("RGB")).unsqueeze(0).to('cpu')
    encoder = encoding.PoissonEncoder()
    rows = []
    for t in range(T):
        s = encoder(img).view(-1).numpy()
        rows.append([i for i, j in enumerate(s) if j != 0])
    return rows


def generate_spike_image_text(image_path="Train/saved_dataset/img_1_2.png", inp_size=64, image_name="spikes"):
    pil_image = Image.open(image_path).convert("RGB")

    input_sqrt = int(inp_size**0.5)
    assert (input_sqrt**2 == inp_size), "Input size must be a perfect square"
    transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=1),
            transforms.ToTensor(),
            transforms.Resize((input_sqrt, input_sqrt))
        ])

    img = transform(pil_image)
    img = img.unsqueeze(0)
    img = img.to('cpu')

    
    from spikingjelly.activation_based import encoding
    encoder = encoding.PoissonEncoder()
    T = 100
    spike_trains = []
    for t in range(T):
        encoded_img = encoder(img)
        spike_trains.append(encoded_img.view(-1).squeeze().numpy())
    
    spike_reg = []
    for spike_list in spike_trains:
        spike_reg_row = []
        for i, j in enumerate(spike_list):
            if (j!=0):
                spike_reg_row.append(i)

        row_len = len(spike_reg_row)
        for i in range(inp_size-row_len):
            spike_reg_row.append(255)
        spike_reg.append(spike_reg_row.copy())

    
    verilog_lines = []

    # indices are 8-bit (255 = padding), independent of the input size
    verilog_lines.append(f"reg [7:0] {image_name} [100][{inp_size}] = '{{")
    for line in spike_reg:
        verilog_lines.append("'{" + ", ".join(f"8'd{num}" for num in line) + "},")

    verilog_lines[-1]=verilog_lines[-1][:-1] + "\n};"
    return "\n".join(verilog_lines)


def generate_multi_spike_image(ds_path, inp_size=64):
    verilog_lines = []
    labels=[]

    for filename in os.listdir(ds_path):
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
            verilog_lines.append(generate_spike_image_text(os.path.join(ds_path, filename), inp_size, filename.split(".")[-2]))
            labels.append(int(filename.split(".")[-2][-1]))
    return "\n".join(verilog_lines), labels

def generate_tb(image_names):
    verilog_lines = []
    verilog_lines.append("""
`include "spikes.svh"

module neuron_tb;

  import file_pkg::*;

  logic clk;
  logic rst;

  initial clk = 0;
  always #5 clk = ~clk;

  reg [ 7:0] ADDR_I = 0;
  reg [ 7:0] ADDR_J = 0;
  reg [15:0] input_current = 16'd30;
  reg [15:0] input_volt = 16'd0;
  wire spike, done, ack;

  reg tr = 0;
  reg de = 0;
  reg ae = 0;
  reg ve = 0;
  reg vn = 0;

  wire [7:0] I_ADDR;
  wire [7:0] J_ADDR;

  wire [7:0] addr_f;

  LIF lif (
      .clk(clk),
      .rst(rst),
      .tr(tr),
      .ve(ve),
      .vn(vn),
      .de(de),
      .ae(ae),
      .IADDR(ADDR_I),
      .JADDR(ADDR_J),
      .input_current(input_current),
      .input_volt(input_volt),
      .ack(ack),
      .done(done)
  );

  integer Irow = 0;
  integer Icol = 0;
  reg [7:0] Nneuron = 0;

  initial begin
    spike_file = $fopen("output.txt", "w");
    if (spike_file == 0) begin
      $display("ERROR: Could not open file!");
      $finish;
    end
  end

  initial begin
    #10;
    rst = 1;
    #10;
    rst = 0;
    #10;
    SIM();
    $fclose(spike_file);
    $finish;
  end

  task automatic TREF(input [7:0] trN, integer t);
    begin
      repeat (t) begin
        ADDR_I = trN;
        tr = 1;
        @(posedge ack);
        tr = 0;
        @(posedge done);
      end
    end
  endtask

  task automatic AXON(input [7:0] trN);
    begin
      ADDR_J = trN;
      @(posedge clk);
      ae = 1;
      @(posedge ack);
      ae = 0;
      @(posedge done);
    end
  endtask

  task automatic VIRN(input [7:0] trN, input [15:0] VOLT);
    begin
      ADDR_I = trN;
      input_volt = VOLT;
      @(posedge clk);
      vn = 1;
      @(posedge ack);
      vn = 0;
      @(posedge done);
    end
  endtask

  task automatic VIRN_range(input int start_trN, input int end_trN, input [15:0] VOLT);
    int k;
    begin
      for (k = start_trN; k <= end_trN; k++) begin
        ADDR_I = k[7:0];
        input_volt = VOLT;
        @(posedge clk);
        vn = 1;
        @(posedge ack);
        vn = 0;
        @(posedge done);
      end
    end
  endtask

  task automatic SIM();
    begin
""")
    
    for name in image_names:
        verilog_lines.append(
f"""
      for (Irow = 0; Irow < 100; Irow = Irow + 1) begin
        for (Icol = 0; Icol < 64; Icol = Icol + 1) begin
          Nneuron = {name.split(".")[-2]}[Irow][Icol];
          if (Nneuron == 8'd255) begin
            break;
          end else begin
            AXON(Nneuron);
          end
        end
        TREF(8'd0, 2);
        TREF(8'd1, 2);
        TREF(8'd2, 2);
        TREF(8'd3, 2);
        TREF(8'd4, 2);
        TREF(8'd5, 2);
        TREF(8'd6, 2);
        TREF(8'd7, 2);
        TREF(8'd8, 2);
        TREF(8'd9, 2);
      end
      VIRN_range(0, 74, 16'd0);
      $fdisplay(spike_file, "------");
""")

    verilog_lines.append(
"""

    end
  endtask
endmodule

""")
    return "\n".join(verilog_lines)
# print(gen_verilog(2))

# images = []
# for filename in os.listdir("Train/test_images_1k"):
#     images.append(filename)

# tb = generate_tb(images)
# with open("tb.sv", "w") as f3:
#     f3.write(tb)


# spikes, labels = generate_multi_spike_image(ds_path="Train/test_images_1k")

# with open("spikes.sv", "w") as f1:
#     f1.write(spikes)

# with open("labels.txt", "w") as f2:
#     f2.write("\n".join(map(str, labels)))


