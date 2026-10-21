import struct

def read_nmnist_bin(file_path):
    events = []
    with open(file_path, 'rb') as f:
        while True:
            bytes_read = f.read(7)
            if len(bytes_read) < 7:
                break  # Reached EOF
            x, y, polarity, timestamp = struct.unpack('>BBBI', bytes_read)
            events.append((timestamp, x, y, polarity))
    return events

# Example usage
events = read_nmnist_bin('C:/Users/arian/Downloads/Test/Test/0/09135.bin')
print("First 10 events:")
for event in events[:10]:
    print(f"Time: {event[0]}, X: {event[1]}, Y: {event[2]}, Polarity: {event[3]}")
print(len(events), "events read from the file.")