import ast
import numpy as np
import os

def read_arrays_from_file(filename):
    with open(filename, 'r') as f:
        content = f.read()

    content = "[" + content.strip().rstrip(',') + "]"

    arrays = ast.literal_eval(content)
    return arrays

def flatten_arrays(arrays):
    flattened = []
    for arr in arrays:
        arr_np = np.array(arr).squeeze()
        arr_flat = arr_np.flatten()
        flattened.append(arr_flat)
    return np.array(flattened) 

def get_verilog_code(array, num):
    IMG_SIZE = 64

    verilog_lines = []
    verilog_lines.append("`define TWOS_COMP(val) (((~(val)) + 1'b1) & ((1 << (16)) - 1))")
    verilog_lines.append("")
    verilog_lines.append("module volt_memory (")
    verilog_lines.append("    input             clk,")
    verilog_lines.append("    input             wr_en,")
    verilog_lines.append("    input             rd_en,")
    verilog_lines.append("    input      [ 7:0] addr,")
    verilog_lines.append("    input      [15:0] data_in,")
    verilog_lines.append("    input             EN,")
    verilog_lines.append("    output reg [15:0] data_out,")
    verilog_lines.append("    output reg [ 7:0] spk_neu,")
    verilog_lines.append("    output reg        spk,")
    verilog_lines.append("")
    verilog_lines.append("    input done")
    verilog_lines.append("")
    verilog_lines.append("")
    verilog_lines.append(");")
    verilog_lines.append("")
    verilog_lines.append("")



    verilog_lines.append("  reg [15:0] V_array[0:255] = {")

    for i in range(IMG_SIZE):
        if array[i] == 1:
            verilog_lines.append("    {{9'h1B0}, {7'd0}},")
        else:
            verilog_lines.append("    {{9'h0}, {7'd0}},")
    for _ in range(256-IMG_SIZE): 
        verilog_lines.append("    {{9'h0}, {7'd0}},")
    verilog_lines[-1] = verilog_lines[-1][:-1]

    verilog_lines.append("  };")

    
    verilog_lines.append("")
    verilog_lines.append("")
    verilog_lines.append("  integer file;")
    verilog_lines.append("  integer i;")
    verilog_lines.append("  real j;")
    verilog_lines.append("")
    verilog_lines.append("  initial begin")
    verilog_lines.append(f'    file = $fopen("output{num}.txt", "w");')
    verilog_lines.append("    if (!file) begin")
    verilog_lines.append('      $display("Failed to open file.");')
    verilog_lines.append("      $finish;")
    verilog_lines.append("    end")
    verilog_lines.append("  end")
    verilog_lines.append("")
    verilog_lines.append("  always @(posedge clk) begin")
    verilog_lines.append("    if (done == 1'b1) begin")
    verilog_lines.append("      for (i = 64; i < 74; i = i + 1) begin")
    verilog_lines.append("        j = $itor($signed(V_array[i]));")
    verilog_lines.append("        j = j / (1 << 7);")
    verilog_lines.append('        $fdisplay(file, "Neuron %%0d = %%f", (i - 64), j);')
    verilog_lines.append('        $fdisplay(file, "Time = %0t", $time);')
    verilog_lines.append("      end")
    verilog_lines.append("    end")
    verilog_lines.append("  end")
    verilog_lines.append("")
    verilog_lines.append("  reg spk_r[0:255] = {")

    for i in range(255):  
        verilog_lines.append("    {1'b0},")

    verilog_lines.append("    {1'b0}")
    verilog_lines.append("  };")
    verilog_lines.append("")
    verilog_lines.append("  reg spike;")
    verilog_lines.append("  always @(posedge clk) begin")
    verilog_lines.append("    spk   <= 1'b0;")
    verilog_lines.append("    spike <= spk_r[addr];")
    verilog_lines.append("    if (wr_en) begin")
    verilog_lines.append("      V_array[addr] <= data_in;")
    verilog_lines.append("      if (spike == 1'b0) begin")
    verilog_lines.append("        if (((data_in[15] == 1'b0) || (`TWOS_COMP(data_in) < 16'b0001101110000000))) begin")
    verilog_lines.append("          if (EN == 1'b1) begin")
    verilog_lines.append("            spk_r[addr] <= 1'b1;")
    verilog_lines.append("            spk <= 1'b1;")
    verilog_lines.append("            spk_neu <= addr;")
    verilog_lines.append("          end")
    verilog_lines.append("        end")
    verilog_lines.append("      end else if (spike == 1'b1) begin")
    verilog_lines.append("        if (((data_in[15] == 1'b1) && (`TWOS_COMP(data_in) > 16'b0010000010000000))) begin")
    verilog_lines.append("          spk_r[addr] <= 1'b0;")
    verilog_lines.append("        end")
    verilog_lines.append("      end")
    verilog_lines.append("    end")
    verilog_lines.append("")
    verilog_lines.append("    if (rd_en) begin")
    verilog_lines.append("      data_out <= V_array[addr];")
    verilog_lines.append("    end")
    verilog_lines.append("  end")
    verilog_lines.append("")
    verilog_lines.append("endmodule")
    verilog_lines.append("")
    return "\n".join(verilog_lines)

filename = 'C:/Users/arian/Downloads/Telegram Desktop/0-img.txt'
arrays_8x8 = read_arrays_from_file(filename)
arrays = flatten_arrays(arrays_8x8)


output_dir = "volt_mem_auto_gen"
os.makedirs(output_dir, exist_ok=True)

for idx, arr in enumerate(arrays):
    verilog_code = get_verilog_code(arr, idx)
    file_path = os.path.join(output_dir, f"neumVolt_memory{idx}.sv")
    with open(file_path, 'w') as f:
        f.write(verilog_code)