# Hist2ST

JHU EN.580.697 26 fall, Project F. The goal is to train a model to predict spatial gene expression (Spatial Transcriptomics) from H&amp;E stains (Histogram). Data comes from HEST-1k ([Huggingface](https://huggingface.co/datasets/MahmoodLab/hest) [Github](https://github.com/mahmoodlab/hest) [Paper](https://arxiv.org/abs/2406.16192)). 


See the [notebook guide](notebooks/table_of_contents.md) for the onboarding sequence and experiments, and [study materials](docs/study_materials.md) for supporting tutorials. 

## Environment and setup

Python 3.11 is recommended. 

For an onboarding notebook, the first setup cell installs all its dependencies. If a notebook imports reusable project code from `src/`, it uses the repository dependency list. A virtual environment keeps the project packages separate. 

**Using `venv`**

```powershell
uv venv --python 3.11
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Using `conda`**

Download anaconda or miniconda first. In a conda terminal:
```powershell
conda create -n hist2st python=3.11
conda activate hist2st
pip install -r requirements.txt
```

This would allow you to run all the notebooks as well as the scripts in `scripts/`. 

*Attention:* `requirements.txt` installs the default PyTorch build. Though it is fine with Apple Silicon, NVIDIA GPU require the NVIDIA CUDA build. See the section below for device checks and installation options. 


### Check CPU and GPU availability

The notebooks can run on CPU. A GPU can speed up image embedding, especially in Notebook 02. First identify which accelerator your machine supports, then check whether the active Python environment can use it.

*Notes:* If you are using Google Colab, feel free to skip this section. Colab has dealt with this for you. 

#### NVIDIA GPU (Windows or Linux)

In PowerShell or a terminal, run:

```powershell
nvidia-smi
```

The output shows whether an NVIDIA GPU and driver are visible. Its `CUDA Version` is the **highest** CUDA level supported by that driver; a machine displaying CUDA 13.1 can support pytorch built with CUDA 13.0 but may not support the one built with 13.4. 

The project `requirements.txt` installs its default PyTorch build. For NVIDIA CUDA acceleration, open the [official PyTorch installation selector](https://pytorch.org/get-started/locally/), select your operating system, Pip, Python, and a CUDA version supported by your driver, then run the generated command in the active environment.

#### Apple Silicon (M-series Mac) or CPU-only systems

Installing the default PyTorch packages suffice; no need to take further steps. On a supported Apple Silicon system, PyTorch can use the Metal Performance Shaders (MPS) backend and enjoy GPU acceleration. 

If you are only using CPU, only process small number of patches because it is slower.

#### Verify PyTorch and select a device

Run this in the notebook kernel (local or Colab). `nvidia-smi` checks the system driver; `torch.cuda.is_available()` and `torch.backends.mps.is_available()` check what PyTorch can actually use in this Python environment.

```python
import torch

cuda_available = torch.cuda.is_available()
mps_available = (
    hasattr(torch.backends, "mps")
    and torch.backends.mps.is_available()
)

if cuda_available:
    device = torch.device("cuda")
elif mps_available:
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print("PyTorch:", torch.__version__)
print("CUDA available:", cuda_available)
print("Apple Silicon GPU (MPS) available:", mps_available)
print("Using:", device)
```

### Colab

Google Colab is a good resource for GPU and for conveniently loading google drive. (gpu and storage via google drive), so we are going to use it. The current notebooks in `notebooks/` are designed to be compatible to run both locally and on Colab.

```python
%pip install -q torch  # No need to specify a CUDA version
import torch
torch.cuda.is_available()  # True
```

## Data storage

It could be helpful to store the data online so that it does not take GBs of space from your local disk. The team's current shared location is Google Drive under `BDD_BJMJ/HEST_breast_ST`. Shared Drive storage lets teammates reuse the same downloads and model output. After mounting Google Drive in Colab:

```python
from pathlib import Path
DATA_DIR = Path("/content/drive/MyDrive/path-to-data")
```

You may instead use a local directory or use Google Drive Desktop to load the drive contents locally. For local runs, ensure the directory has enough free space; raw patch archives can be large. Do not commit downloaded data, model weights, credentials, or patient-sensitive information.


## Repository layout

Names in brackets are *hidden*. They should never be commited, and their names have been tracked in `.gitignore`. 

```text
├── requirements.txt       # dependencies for project code in `src/` and `scripts/`
├── (data/)                # downloaded dataset.
├── (outputs/)             # outputs from our model.
├── (checkpoints/)         # checkpoints during training. 
├── (.env)                 # the huggingface access key.
├── .env.example           # a sample of what an .env would look like.
├── configs/               # experiment settings (e.g., YAML)
├── src/                   # reusable helpers like tensor loading and plotting
├── scripts/               # final code for delivery
├── notebooks/             # tutorials and exploratory experiments
├── splits/                # saved train/validation/test ID lists
├── jobs/                  # cluster batch scripts
├── docs/                  # notes, study materials, and tutorials
├── Presentations/         # presentation slides (pdf)
```
