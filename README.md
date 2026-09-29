# Hist2ST
JHU EN.580.697 26 fall, Project F. A model that is trained to predict spatial gene expression (Spatial Transcriptomics) from H&amp;E stains (Histogram). Data comes from HEST-1k. 

# Important PLEASE READ
- main should always run
- one task per branch; merge only after a teammate reviews
- commit small changes often
- never commit large data files or model weights unless agreed
- never commit passwords, API keys, restricted data, or patient data (PHI)
- notebooks for exploration; final code as functions and scripts
- document how to reproduce key results

## How to run

**Using `venv`**

```
uv venv --python 3.11
pip pip install -r requirements.txt
```

**Using `conda`** (conda needs to be installed first)

In a conda terminal
```powershell
conda create -n my_env_name python=3.11
conda activate my_env
pip install -r requirements.txt
```


## Document Structure

`.env` the huggingface access key. DO NOT UPLOAD TO GITHUB
`requirements.txt` dependencies
`README.md` what it is, how to install, how to run
`environment.yml` or `requirements.txt`
`.gitignore` `data/`, `outputs/`, checkpoints, large files
`configs/` *(not yet added)* experiment settings (e.g., YAML)
`src/` reusable code: data loading, models, metrics
`scripts/` `train.py`, `evaluate.py`, `make_figures.py`
`notebooks/` EDA and demos (call functions from `src/`)
`splits/` saved train/validation/test ID lists
`jobs/` cluster batch scripts
`docs/` notes, meeting notes

In `.gitignore`: Large data, checkpoints (`checkpoints`), and generated outputs (`outputs`) are not tracked in Git