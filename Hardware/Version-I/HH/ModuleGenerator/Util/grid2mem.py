import ast
import os

def int_to_binary(num, n):
    if num < 0:
        num = (1 << n) + num
    bin_repr = bin(num)[2:].zfill(n)
    if len(bin_repr) > n:
        raise ValueError(f"Number {num} cannot be represented in {n} bits.")
    return bin_repr

input_folder = 'D:/GitHub/HH/Hardware/Version-I/HH/ModuleGenerator/Util/imgsBIN'
output_file = 'D:/GitHub/HH/Hardware/Version-I/HH/ModuleGenerator/Util/imgsconcated.svh'

filler = ", 8'd255"

# Gather all txt files in the folder
txt_files = [f for f in os.listdir(input_folder) if f.endswith('.txt')]
txt_files.sort()  # sort for consistency

with open(output_file, 'w') as out_f:
    for file_idx, txt_file in enumerate(txt_files):
        input_file = os.path.join(input_folder, txt_file)

        # Create a clean name for the array
        base_name = os.path.splitext(txt_file)[0]
        array_name = base_name.replace('-', '_')

        # Read the entire file content
        with open(input_file, 'r') as f:
            content = f.read()

        # Split using delimiter
        chunks = content.split(']]],')
        clean_chunks = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk.endswith(']]]'):
                chunk += ']]]'
            clean_chunks.append(chunk)

        print(f"Processing {txt_file} with {len(clean_chunks)} grids...")

        all_outputs = []

        for idx, chunk in enumerate(clean_chunks):
            try:
                grid = ast.literal_eval(chunk)
            except Exception as e:
                print(f"Error parsing grid {idx} in {txt_file}: {e}. Skipping.")
                continue

            grid = grid[0]  # Because each grid is [[[ ... ]]]

            flattened_positions = []
            for row in range(8):
                for col in range(8):
                    if grid[row][col] == 1.0:
                        flattened_positions.append(row * 8 + col)

            formatted_positions = [f"{pos}" for pos in flattened_positions]

            out_spikes  = "'{8'd" + ", 8'd".join(formatted_positions) if len(formatted_positions) else "'{"
            output_string = out_spikes + ((64 - len(flattened_positions)) * filler) + "},"

            # Remove comma for the 100th line (index 99)
            if idx == 99:
                output_string = output_string.rstrip(',')

            all_outputs.append(f"    {output_string}\n")
            print(f"Grid {idx} processed ({len(flattened_positions)} spikes)")

        # Write the output for this file
        out_f.write(f"reg [7:0] {array_name} [100][64] = '{{\n")
        out_f.writelines(all_outputs)
        out_f.write("    };\n")
        out_f.write(f"// {txt_file}\n\n")

print(f"\nAll files processed and results written to '{output_file}'")
