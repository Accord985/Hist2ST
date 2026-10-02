# Hist2ST
JHU EN.580.697 26 fall, Project F. A model that is trained to predict spatial gene expression (Spatial Transcriptomics) from H&amp;E stains (Histogram). Data comes from HEST-1k. 

## How to run

**Using `venv`**

```
uv venv --python 3.11
pip install -r requirements.txt
```

**Using `conda`** (conda needs to be installed first)

In a conda terminal
```powershell
conda create -n my_env_name python=3.11
conda activate my_env
pip install -r requirements.txt
```


## Document Structure

- `.env` the huggingface access key. NEVER COMMITTED
- `.env.example` a sample of what an `.env` would look like.
- `README.md` (this file) what the project is, how to install, how to run
- `requirements.txt` dependencies
- `.gitignore` includes the data folder `data/`, output folder `outputs/`, checkpoints `checkpoints/`, large files
- `configs/` experiment settings (e.g., YAML)
- `src/` reusable code: data loading, models, metrics
- `scripts/` short helpers like `train.py`, `evaluate.py`,  `make_figures.py`
- `notebooks/` EDA and demos (call functions from `src/`)
- `splits/` saved train/validation/test ID lists
- `jobs/` cluster batch scripts
- `docs/` notes, meeting notes, design choices
- `Presentation/` presentation slides

In `.gitignore`: Large data, checkpoints (`checkpoints`), and generated outputs (`outputs`) are not tracked in Git