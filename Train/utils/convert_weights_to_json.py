import numpy as np
import json

data = np.loadtxt('Weights/weights_scaled.txt')
data = data.T

wrapped = [ data.tolist() ]
with open('output.txt', 'w') as f:
    json.dump(wrapped, f, indent=2)