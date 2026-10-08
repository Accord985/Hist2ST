# PCA on foundation-model embeddings (USELESS)

Notebook: `notebooks/pca_on_embeddings.ipynb`

Part of the baseline: pretrained image embeddings → PCA → ridge regression (ridge is the next step).

## How to run

1. Download a sample with `presentation2_pull_hest_sample_light.ipynb`. You need `data/patches/<id>.h5` and `data/st/<id>.h5ad`.
2. Open `pca_on_embeddings.ipynb`, set `sample_id` and `MAX_SPOTS` in the settings cell, and run all cells.
   - `MAX_SPOTS = 250` is a quick test on a laptop. `None` uses every spot (~11,800 for TENX95) and needs a GPU (or Colab).
3. The embeddings are saved to `outputs/embeddings/` and reused on later runs, so the foundation model only runs once.
   If you change `MAX_SPOTS`, delete that file first.

### Mac (Apple Silicon) notes

- Install PyTorch with conda, not pip: `conda install -c conda-forge pytorch torchvision`.
  The pinned `torch==...+cu130` in `requirements.txt` is the NVIDIA build and doesn't install on a Mac.
  Mixing pip PyTorch with conda numpy/scikit-learn loads two copies of OpenMP and crashes the kernel.
- The notebook uses the Mac GPU (`mps`) automatically. `batch_size = 4` worked on a 16 GB MacBook Air.

### Windows / Linux with an NVIDIA GPU

The notebook was written on a Mac, so change these before running:

| Where | Mac setting | Change to |
|---|---|---|
| Install | `conda install -c conda-forge pytorch torchvision` | `pip install -r requirements.txt` (has the CUDA build), plus `pip install scikit-learn` |
| Embedding cell | `batch_size = 4` | `batch_size = 64` (lower it if you get a CUDA out-of-memory error) |
| First cell | `OMP_NUM_THREADS = "1"` and `KMP_DUPLICATE_LIB_OK = "TRUE"` | Can be deleted (Mac-only fix). Leaving them is harmless but makes CPU steps slower |
| Device | (automatic) | No change needed. The notebook picks `cuda` → `mps` → `cpu`, whichever exists |

Check the GPU is visible first: `import torch; print(torch.cuda.is_available())` should print `True`.
If it prints `False`, the notebook still runs on the CPU, but use a small `MAX_SPOTS`.

### No GPU at all (CPU only)

No code changes needed. Keep `MAX_SPOTS` small (250 or less) because the model is large (~4.3 GB of weights), or run the embedding step on Colab and share the saved file in `outputs/embeddings/`.

## Notebook 1: `pca_on_embeddings.ipynb`

### Setup

- Each spot is a sample. (Test run: 250 spots from TENX95.)
- Each spot gets 4,608 numbers.

**Where do those 4,608 numbers come from?**
From the foundation model GenBio-PathFM. It looks at a spot's 224×224 H&E picture and writes a description of it as 4,608 numbers: the embedding, i.e. 4,608 things measured about the picture. One number might react to lots of purple nuclei, another to pink stroma, another to fat cells. Unlike genes, these measurements don't have names; the model invented them during training.

So we have 250 spots × 4,608 measurements. We can't draw a 4,608-dimensional graph, but PCA still works.

### The gene expression is the answer key, not part of PCA

The notebook also loads each spot's real gene expression, matching spot to spot with the barcode. It takes log(1 + count) so a few huge values don't dominate, and keeps the 50 genes that vary most.

These genes are **not** put into PCA. They're the answers we'll eventually try to predict from the picture. For now they're set aside and used to color the plots.

### Split into train and test

200 spots go into the training group and 50 into the test group. Only training spots get to help find the PCs.

This is a **random spot split within one slide**, which is the "leaky" setting (neighboring spots look alike and have similar expression). It is not a fixed method. The final comparison will add a slide-level split, where whole slides are held out, as in HEST's benchmark.

### Center and scale = move the data to the origin

`StandardScaler` centers each measurement (mean 0), plus one more step: it also scales each measurement so its spread (SD) is 1.

**Why scale?**
Some of the 4,608 numbers naturally vary a lot and others barely move. Without scaling, the big ones would dominate PC1 just because of their size.

### Find PC1: rotate the line

PCA rotates a line through the origin until the projected points have the largest sum of squared distances from the origin. That line is PC1. It's the same idea in 4,608 dimensions: PC1 is the direction where the 200 training spots spread out the most. PC2 is the next-best direction, perpendicular to PC1, and so on.

Our PC1 is a recipe with 4,608 ingredients, one loading score per embedding number.

### How many PCs?

The smaller of the number of variables or the number of samples:

- Variables: 4,608
- Training samples: 200
- So the maximum is 200 PCs.

That's why the test run gave 200 PCs instead of HEST's 256. With all ~11,800 spots, we get the full 256.

### The plots

- **Scree plot:** the percent of variation each PC accounts for.
- **PC1 vs PC2 plot:** each dot is a spot placed by its PC1 and PC2 scores (2D). The color is a gene's expression (ADIPOQ, a fat-cell gene, in the test run). If colors cluster on one side, the picture-based PCs are already "seeing" something about that gene.
- **PC1 on the tissue:** each spot drawn at its real slide position, colored by its PC1 score. This shows where PC1 is high on the tissue.

**Summary:** notebook 1 turns pictures into 4,608 numbers and finds the directions they spread the most (PCs).

### Same as HEST's benchmark?

The PCA step is the same as HEST's code: `StandardScaler` + `PCA(256)`, fit on train only, transform on test, with log1p expression.
Still different in the test run: 250 spots instead of all, random spot split instead of slide-level split, our own top-50 gene list instead of HEST's `var_50genes.json`, and no ridge step yet.

## Next step

Ridge regression from the saved PCA features (`outputs/pca/<id>_pca<k>.npz`) to the 50 genes, scored by Pearson correlation per gene.
