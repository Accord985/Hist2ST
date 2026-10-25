# Notes

## General Rules to Follow

- main should always run
- one task per branch; merge only after a teammate reviews
- commit small changes often
- never commit large data files or model weights unless agreed
- never commit passwords, API keys, restricted data, or patient data (PHI)
- notebooks for exploration; final code as functions and scripts
- document how to reproduce key results

## Package Management

Currently we are using `requirements.txt` which is lightweight but only manages python packages. 

When done with environments: Run `pip list --format=freeze > requirements.txt` to overwrite the existing `requirements.txt` file in the current directory. DO NOT run this as it exports all system packages and dependencies. Modify manually as it is still manageable. pytorch is a bit special due to gpu usage. Plan to include default pytorch in requirements and offer option to upgrade

`environment.yml` is used by conda only for conda environment. Beyond what pip can do, it allows management for python version and non-python dependencies (like CUDA, C++ libraries)

When creating a conda environment with `environment.yml`:
```bash
conda env create -f environment.yml
```


## GPU Management

### Windows or Linux with an NVIDIA GPU

First, open Command Prompt or a terminal and run:

```powershell
nvidia-smi
```

This should show your NVIDIA GPU and driver. The `CUDA Version` shown by `nvidia-smi` is the highest CUDA version supported by that driver; it does not necessarily mean the CUDA Toolkit is installed separately. If the command is missing or no GPU is listed, check the NVIDIA driver (ask your system administrator if needed), or use the CPU option.

Install the CUDA 13.0 PyTorch build used by this project:
```bash
%pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu130
```

### Apple Silicon (M-series Mac) or no GPU

CUDA does not work on mac GPU, and  on a mac the attempt to download pytorch with `cu130` will be rejected. Thus, for mac, download the default pytorch, and Mac's GPU can be used just fine. It is also compatible with no GPU (falling back on CPU for computation).

*Note*: if you are on CPU, use just one patch as this notebook does; running the model will be slower.
```bash
%pip install -q torch torchvision torchaudio
```

Then you can pick which gpu acceleration to use. 
```python
# Picking the best device to run on
import torch

cuda_available = torch.cuda.is_available()
mps_available = (
    hasattr(torch.backends, "mps")  # check if mps attribute even exists for safety
    and torch.backends.mps.is_available()
)

if cuda_available:
    device = torch.device("cuda")
elif mps_available:
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print("CUDA available:", cuda_available)
print("Apple Silicon GPU (MPS) available:", mps_available)
print("Using:", device)
```
```
CUDA available: True
Apple Silicon GPU (MPS) available: False
Using: cuda
```

## import scripts from `scripts`

in `notebooks/` or `src/`, when we want to use any python file from `scripts/`: add this cell at the beginning of the notebook. 

```python
%load_ext autoreload
%autoreload 2

import sys
from pathlib import Path
sys.path.append(str(Path.cwd().parent))
```

then you can use code from elsewhere with live reload

```python
from scripts.download_pipeline import some_method
```