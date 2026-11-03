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

Windows Users with Navida GPU: Go to [pytorch official site](https://pytorch.org/) for the command to download pytorch with hardware acceleration (CUDA).


## Document Structure

Names in brackets are *hidden*. They should never be commited, and their names have been tracked in `.gitignore`. 

```text
├── requirements.txt       # dependencies for the scripts in `scripts/`
├── (data/)                # downloaded dataset.
├── (outputs/)             # outputs from our model.
├── (checkpoints/)         # checkpoints during training. 
├── (.env)                 # the huggingface access key.
├── .env.example           # a sample of what an .env would look like.
├── configs/               # experiment settings (e.g., YAML)
├── src/                   # reusable code: data loading, models, metrics
|   ├── scripts/           # short helpers (ex. train/evaluate/make_figures)
├── notebooks/             # explorations demos (call functions from `src/`)
├── splits/                # saved train/validation/test ID lists
├── jobs/                  # cluster batch scripts
├── docs/                  # notes, meeting notes, design choices
├── Presentation/          # presentation slides
```