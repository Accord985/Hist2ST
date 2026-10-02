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

When done with environments: Run `pip list --format=freeze > requirements.txt` to overwrite the existing `requirements.txt` file in the current directory.

`environment.yml` is used by conda only for conda environment. Beyond what pip can do, it allows management for python version and non-python dependencies (like CUDA, C++ libraries)

When creating a conda environment with `environment.yml`:
```
conda env create -f environment.yml
```

## PyTorch

Though Pytorch can work perfectly on CPU, the library also has an optional CUDA addon to allow GPU usage for faster computation. Whether to have CUDA addon can be specified in `requirements.txt` (or its equivalents). **We are using addon for CUDA 13.0**

More info: https://pytorch.org/get-started/locally/

For Pytorch to work on CUDA, the computer must have CUDA >13.0 installed separately. You may check your CUDA installation in a `cmd` terminal:
```
nvidia-smi
```