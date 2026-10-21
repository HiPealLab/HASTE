import matplotlib.pyplot as plt
from collections import Counter

# Path to your file
file_path = r"D:\GitHub\HH\Hardware\Version-I\LIF\Spikes.txt"

# Read and parse digits
digits = []
with open(file_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("din ="):
            try:
                val = int(line.split("=")[1].strip())
                digits.append(val)
            except ValueError:
                pass  # ignore malformed lines

# Count occurrences of each digit
counts = Counter(digits)

# Ensure all digits 0–9 appear, even if missing
all_digits = list(range(10))
frequencies = [counts.get(d, 0) for d in all_digits]

# Plot
plt.bar(all_digits, frequencies)
plt.xlabel("Digit")
plt.ylabel("Frequency")
plt.title("Frequency of Digits in Spikes.txt")
plt.xticks(all_digits)

# Add text labels on top of each bar
for d, freq in zip(all_digits, frequencies):
    plt.text(d, freq + 0.05, str(freq), ha='center', va='bottom', fontsize=10)

plt.show()
