# Notes

## Package Management

Currently we are using `requirements.txt`  which is lightweight but only manages python packages. 

When done with environments: Run `pip list --format=freeze > requirements.txt` to overwrite the existing `requirements.txt` file in the current directory.

`environment.yml` is used by conda only for conda environment. Beyond what pip can do, it allows management for python version and non-python dependencies (like CUDA, C++ libraries)
```
conda env create -f environment.yml
```
