from collections import Counter
import re
import matplotlib.pyplot as plt
import numpy as np

def analyze_lif_results(file_path):
    with open(file_path, "r") as f:
        lines = [line.strip() for line in f]

    # Initialize 10x10 confusion matrix for numbers 0-9
    confusion_matrix = np.zeros((10, 10), dtype=int)

    mismatched_details = []

    for i, line in enumerate(lines):
        dash_match = re.match(r"^---(\d+)---$", line)
        if dash_match:
            dash_val = int(dash_match.group(1))
            if dash_val < 0 or dash_val > 9:
                continue  # skip numbers outside 0-9

            # Collect all consecutive 'din =' lines above
            j = i - 1
            din_block = []
            while j >= 0 and lines[j].startswith("din ="):
                try:
                    din_val = int(lines[j].split("=")[1].strip())
                    din_block.append(din_val)
                except ValueError:
                    pass
                j -= 1

            if din_block:
                most_common_din, freq = Counter(din_block).most_common(1)[0]
                if most_common_din < 0 or most_common_din > 9:
                    continue  # skip numbers outside 0-9

                confusion_matrix[dash_val, most_common_din] += 1

                if most_common_din != dash_val:
                    mismatched_details.append(
                        f"Line {i+1}: dashed value = {dash_val}, most repeated din = {most_common_din}"
                    )
            else:
                # No din lines above counts as mismatch
                mismatched_details.append(
                    f"Line {i+1}: dashed value = {dash_val}, no din = lines above"
                )

    # Print totals
    total_matches = np.trace(confusion_matrix)
    total_mismatches = np.sum(confusion_matrix) - total_matches
    print(f"Total dashed lines: {np.sum(confusion_matrix)}")
    print(f"Matches: {total_matches}")
    print(f"Mismatches: {total_mismatches}\n")

    if mismatched_details:
        print("Mismatched lines:")
        for detail in mismatched_details:
            print(detail)

    # Plot confusion matrix
    plt.figure(figsize=(8, 6))
    plt.imshow(confusion_matrix, cmap='Blues', origin='lower')

    plt.colorbar(label='Count')
    plt.xticks(range(10))
    plt.yticks(range(10))
    plt.xlabel('Predicted (most repeated din =)')
    plt.ylabel('Actual (dashed value)')
    plt.title('Prediction vs Actual Confusion Matrix')

    # Annotate counts in each cell
    for y in range(10):
        for x in range(10):
            count = confusion_matrix[y, x]
            if count > 0:
                plt.text(x, y, str(count), ha='center', va='center', color='black')

    plt.show()


if __name__ == "__main__":
    file_path = r"D:/GitHub/HH/Hardware/Version-II/IZHIKEVICH/res/IZH_Results.txt"
    analyze_lif_results(file_path)
