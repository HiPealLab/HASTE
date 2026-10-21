import os
import ast
import numpy as np

input_folder = "Weights/output_images/"
output_folder = "Weights/spike_images_T100_bad_format/"
os.makedirs(output_folder, exist_ok=True)

for filename in os.listdir(input_folder):
    if not filename.endswith(".txt"):
        continue

    input_path = os.path.join(input_folder, filename)
    output_path = os.path.join(output_folder, filename)

    with open(input_path, "r") as f:
        content = f.read()

    try:
        data = ast.literal_eval(content)
    except Exception as e:
        print(f"Failed to parse {filename}: {e}")
        continue

    if len(data) != 100:
        print(f"Skipping {filename}: does not contain 100 rows.")
        continue

    output_blocks = []
    for i, row in enumerate(data):
        if len(row) != 64:
            print(f"Skipping row {i} in {filename}: does not contain 64 elements.")
            continue
        array = np.array(row, dtype=float).reshape(8, 8)
        output_blocks.append([array.tolist()])

    with open(output_path, "w") as f:
        lines = ""
        for block in output_blocks:
            for line in block:
                lines += (f'[[')
                for i in line:
                    lines += (f"{i},\n")
                lines = lines[:-2]
                lines += (f']],\n\n')
        lines = lines[:-3]
        f.write(lines)