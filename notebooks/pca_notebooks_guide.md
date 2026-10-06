# PCA notebooks: how to use them

Part of the project baseline: **pretrained image embeddings → PCA → ridge regression.**
These notebooks cover the first two parts (embedding + PCA) and measure how much information PCA keeps.
Ridge regression is the next step and is not here yet.

| # | Notebook | What it does | Needs the foundation model? |
|---|---|---|---|
| 1 | `pca_on_embeddings.ipynb` | Embeds H&E patches (first N spots), runs StandardScaler + PCA, saves PCA features | Yes |
| 2 | `pca_reconstruction.ipynb` | Rebuilds embeddings from PCs and measures how much is lost (+ learning curve) | No, reads saved files |
| 3 | `pca_for_reconstruction.ipynb` | Same as notebook 1, but picks spots **at random** across the whole slide | Yes |

**Run order:** notebook 1 or 3 first → then notebook 2 on its results.
For new runs, use **notebook 3** (random spots). Notebook 1 is kept as the first test run.

---

## Before you start

### 1. Get the data

Run `presentation2_pull_hest_sample_light.ipynb` for your sample (e.g. `TENX95`). You need:

```
data/patches/TENX95.h5     ← H&E patches (model input)
data/st/TENX95.h5ad        ← gene expression (answer key)
```

The notebooks read from `data/`. If your data is somewhere else, change the two path lines in the settings cell:

```python
patches_path = f"data/patches/{sample_id}.h5"
st_path = f"data/st/{sample_id}.h5ad"
```

### 2. Install

**Windows / Linux with an NVIDIA GPU**

```
pip install -r requirements.txt
pip install scikit-learn
```

Then check: `import torch; print(torch.cuda.is_available())` should print `True`.

**Mac (Apple Silicon)**

Install PyTorch with **conda, not pip**. `requirements.txt` pins the NVIDIA build (`torch==...+cu130`), which doesn't install on a Mac.

```
conda install -c conda-forge pytorch torchvision
pip install transformers anndata h5py scikit-learn matplotlib pandas pillow
```

Mixing pip PyTorch with conda numpy/scikit-learn loads two copies of the OpenMP library and **crashes the kernel**.
The first cell of notebooks 1 and 3 also sets `OMP_NUM_THREADS = "1"` and `KMP_DUPLICATE_LIB_OK = "TRUE"` as a safety net.
Those two lines are Mac-only; on Windows/Linux they're harmless and can be deleted.

### 3. Settings to change for your computer

| Setting (cell) | Mac, 16 GB | NVIDIA GPU | CPU only |
|---|---|---|---|
| `MAX_SPOTS` (settings cell) | `250` (~a few minutes) | `None` = all spots | `250` or less |
| `batch_size` (embedding cell) | `4` | `64` (lower if out of memory) | `4` |
| Device | automatic (`mps`) | automatic (`cuda`) | automatic (`cpu`) |

The model (genbio-pathfm, ~4.3 GB) downloads from Hugging Face on the first run.

---

## Notebook 1: `pca_on_embeddings.ipynb`

### What it does, step by step

1. **Load patches.** Reads the first `MAX_SPOTS` patches (224×224 H&E images), their barcodes and slide positions.
2. **Embed.** GenBio-PathFM turns each patch into **4,608 numbers** (the embedding), which describe the picture: nuclei, stroma, fat, and so on. These numbers don't have names; the model learned them.
3. **Load gene expression.** Matches each spot to its expression row by **barcode**, takes `log(1 + count)`, and keeps the **50 most variable genes**. The genes are **not** put into PCA. They are the targets (y) for ridge regression later.
4. **Train/test split.** 80% train, 20% test, random spots within one slide.
5. **StandardScaler + PCA, fit on train only.** Centers each of the 4,608 numbers (mean 0) and scales it (SD 1), then finds the PCs: the directions where the training spots spread out most. Test spots are only projected onto those PCs and never help choose them.
6. **Plots.** Scree plot, PC1 vs PC2 colored by a gene, and PC1 drawn on the tissue.
7. **Save** the PCA features for ridge regression.

**Same as the HEST benchmark?** The PCA step is the same as HEST's code: `StandardScaler` + `PCA(256)`, fit on train, transform test, log1p expression.
Still different: HEST uses all spots, a **slide-level** split (whole slides held out), its own 50-gene list (`var_50genes.json`), and ridge on top.

### How many PCs?

PCA can't make more PCs than samples: **number of PCs = min(4,608 variables, number of training spots, 256).**
With `MAX_SPOTS = 250` there are 200 training spots → **200 PCs**. With all spots you get the full 256.

### Outputs

| File | What |
|---|---|
| `outputs/embeddings/TENX95_genbio-pathfm.npz` | Saved embeddings (reused on later runs, so the model only runs once) |
| `outputs/pca/TENX95_pca200.npz` | PCA features + expression + train/test barcodes |
| `outputs/pca/TENX95_scree.png`, `..._pc1_pc2_<gene>.png`, `..._pc1_on_tissue.png` | Plots |

Warning If you change `MAX_SPOTS`, **delete the saved embeddings file**, or the notebook stops with a "doesn't match" error.

---

## Notebook 3: `pca_for_reconstruction.ipynb` (random spots)

Same steps as notebook 1, with one change in step 1:

```python
rng = np.random.default_rng(SEED)
picked = rng.choice(n_total, size=MAX_SPOTS, replace=False)
picked = np.sort(picked)
imgs = f["img"][picked]
```

**Why:** the patches file stores spots in grid order, so notebook 1's "first 250" were one strip along the slide edge, with lots of blank background.
Random spots cover every tissue type, so the results represent the whole slide.

- `SEED = 0` → the same random spots every run. Change the seed to get a different random set.
- A check plot shows the first 250 spots next to your random spots on the slide.
- Files are saved under a **run name** so runs don't overwrite each other:

| `MAX_SPOTS` | Run name | Example files |
|---|---|---|
| `250` | `TENX95_random250` | `outputs/embeddings/TENX95_random250_genbio-pathfm.npz`, `outputs/pca/TENX95_random250_pca200.npz` |
| `500` | `TENX95_random500` | `..._random500_...` |
| `None` | `TENX95_all` | `..._all_...` |

If you change `SEED` without changing `MAX_SPOTS`, delete the saved embeddings file first.

---

## Notebook 2: `pca_reconstruction.ipynb`

### What it does

Goes **backwards**: takes each spot's PC scores and rebuilds its 4,608-number embedding, then measures how close the rebuild is to the real embedding.

```python
rebuilt = scores[:, :k] @ pca.components_[:k] + pca.mean_
```

= score1 × PC1 + score2 × PC2 + … + scorek × PCk, then add the mean back.

With only k PCs, the rebuild can only land in the space those k PCs span. The part of the spot that points in other directions is lost.
This is the "distance from the point to the PC line" in the StatQuest PCA video.

- **R² = 1 − (squared error) / (total squared spread).** 1.0 = perfect, 0 = no better than the average spot.
- Measured on **test spots** (never seen by PCA). This is the honest number.
- Train R² always reaches 1.0 when all PCs are used (n spots → n PCs rebuild them exactly), so it isn't a real result.
- Also reports cosine similarity, which always looks higher than R². Report R².

### How to point it at a run

The notebook reads the files from notebook 1 or 3. Change **one line** in the settings cell to the run name:

```python
sample_id = "TENX95"             # notebook 1 run (first 250 spots)
sample_id = "TENX95_random250"   # notebook 3 run (random 250 spots)
```

It uses the **same train/test split** as the PCA run (it reads the saved barcodes), so results line up.

### Sections

1–7. Reconstruction R² for different numbers of PCs, train vs test curve, one spot real vs rebuilt, per-spot error histogram.
8. **Learning curve:** fits PCA on 25, 50, 100, 150, 200 training spots (10 random repeats each) and rebuilds the same test spots.
   If test R² is still rising at 200, more spots would help.

### Outputs

`outputs/reconstruction/<run name>_reconstruction_curve.png`, `..._one_spot.png`, `..._per_spot_r2.png`, `..._learning_curve.png`

Runs in seconds; no GPU needed.

---

## Results so far (TENX95, 250 spots, 200 train / 50 test)

| | First 250 (notebook 1) | Random 250 (notebook 3) |
|---|---|---|
| Test R², 10 PCs | 0.44 | 0.39 |
| Test R², 50 PCs | 0.61 | 0.58 |
| Test R², 200 PCs | **0.72** | **0.69** |
| PC1 alone (train R²) | 0.22 | 0.14 |
| Learning curve gain, 150 → 200 spots | +0.041 | +0.043 |

- **Random spots score slightly lower, but this is the more honest number.** The first 250 came from one edge strip, so the test spots looked like the training spots. Random spots are more varied (PC1 explains less), so they are harder to compress.
- **The learning curve is still rising in both runs.** The main limit is the number of training spots, not PCA itself.
- **Conclusion so far:** with 200 random training spots, PCA rebuilds about **69%** of an unseen spot's GenBio-PathFM embedding.

These numbers come from only 250 spots. Re-run with more spots before reporting final numbers.

---

## Common problems

| Problem | Fix |
|---|---|
| `FileNotFoundError: data/patches/...` | Data isn't downloaded, or is in a different folder. Fix the two path lines in the settings cell |
| "Saved embeddings don't match these patches" | You changed `MAX_SPOTS` or `SEED`. Delete the file in `outputs/embeddings/` and re-run |
| Kernel crashes on Mac | PyTorch installed with pip. Reinstall with conda (see Install), restart the kernel |
| Kernel crashes on `import torch` (Mac) | Same cause. Check that the first cell has the `OMP_NUM_THREADS` / `KMP_DUPLICATE_LIB_OK` lines and restart the kernel |
| CUDA out of memory | Lower `batch_size` |
| Got fewer than 256 PCs | Expected with few spots: PCs ≤ number of training spots |

---

## Next steps

1. Run notebook 3 with `MAX_SPOTS = 500` / `1000` (or `None` on a GPU or Colab) and re-check test R².
2. Ridge regression from the saved PCA features to the 50 genes, scored by Pearson correlation per gene.
3. Download more breast slides (e.g. TENX99, NCBI783, from HEST's IDC task) for a **slide-level split**, and compare it with the random spot split to measure spatial leakage.
