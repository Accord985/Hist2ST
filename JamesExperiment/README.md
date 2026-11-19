# JamesExperiment

Technique 1 samples **patches within every selected slide**.
Techniques 2 and 3 await definition.

The separate [gene_expression_heatmap(JAMES).ipynb](gene_expression_heatmap%28JAMES%29.ipynb)
uses the saved target tensor and HEST metadata to generate an interactive
patch-level heatmap, a patient-mean overview, 24 detailed PNG pages, and exact
patient boundary tables under outputs/JamesExperiment/gene_expression_heatmap_7pct.
It marks patient starts/ends, organ, exact tissue, disease state, and slide-level
cancer annotation. Patient labels are scoped to their dataset. The 302 slides
without patient IDs remain separately labeled slide groups; no patient identity
is invented. Cancer, Healthy, Tumor with unspecified malignancy, and uncertain
Diseased/Treated annotations remain distinct. Display colors use gene-wise
z-scores of log1p(raw expression); interactive hover retains original values.

Open [patch_sampling_pipeline(JAMES).ipynb](patch_sampling_pipeline%28JAMES%29.ipynb).
The previous slide_sampling_pipeline filename also runs the corrected patch workflow.
Defaults for the requested run: all tissues, Homo sapiens, Visium, 7%, seed 42.

1. Filter HEST metadata by organ, species and technology.
2. Choose slide IDs, a count/range, or all filtered slides.
3. Set PATCH_PERCENTAGE and SEED.
4. For every selected slide, choose max(1, floor(N * percentage / 100))
   patch indices before reading images.
5. Extract only those images and their barcode-matched expression rows.
6. Export paired PathFM inputs and all shared-gene targets.

Install the project requirements plus Pillow, numpy, anndata, h5py, fsspec and
aiohttp. Optional PathFM inference uses transformers==4.57.1.
Alternatively, install all notebook dependencies with
`python -m pip install -r JamesExperiment/requirements.txt` from the project root.

Image HDF5 files use seekable HTTP range reads; no full-image-download fallback
is provided. HDF5 metadata, chunks and cache blocks can fetch neighboring bytes.
Expression H5AD containers are downloaded in full per active slide for the
AnnData backed reader, then removed from temporary storage. Only sampled rows
are retained. Whole-slide TIFFs are never requested. Independent image chunks
are fetched concurrently when the source layout permits; HTTP 206 is required.

Completed sampled slides are reused when percentage, seed and source revision
match. Compact per-slide NPZ samples replace the intermediate PNG/CSV folders.
Incomplete NPZ files are retried without repeating completed slides.
Sampling settings are saved on disk before extraction.
Existing full-cohort data is untouched.

Outputs:
- images.pt: CPU float32 [N, 3, 224, 224], using the
  [official PathFM normalization](https://huggingface.co/genbio-ai/genbio-pathfm).
- targets.pt: CPU float32 [N, G], paired with the same image row.
- genes.json: alphabetically sorted names for every gene shared across sampled patches.
- patch_manifest.csv: row order and source image/expression/barcode paths.
- experiment.json: completion marker and tensor dimensions.
- sampling_settings.json: patch percentage, seed, every selected slide and data paths.

Expression is raw by default. relative_log_10000 optionally applies
log1p(10000 * count / full_source_panel_total) before selecting shared genes.
Gene identifiers must be consistent across species/panels. Duplicate source
features with the same gene name are summed before aligning targets.
When Ensembl identifiers occur, the exporter uses a saved
[official HGNC snapshot](https://www.genenames.org/download/) to align Ensembl
IDs, approved symbols and unambiguous previous symbols/aliases. Explicit human
reference prefixes (such as GRCh38__) and Ensembl version suffixes are removed;
mouse reference prefixes are preserved. Unresolved identifiers remain unchanged.
Features resolving to the same gene are summed. gene_alignment.json records the
annotation SHA256 and per-slide counts; the HGNC snapshot stays in
data/JamesExperiment/annotations. All shared canonical genes are retained,
even when some source slides' small gene panels make the intersection small.

Export streams standard float32 PyTorch tensors directly to disk, using small
batches and no full-size RAM allocation or duplicate disk buffer. The notebook
uses memory mapping to inspect results without loading all tensors again.
On Windows, use `open_batch_tensor` for the large image tensor rather than
`torch.load(..., mmap=True)`, whose private mapping can reserve commit memory
for the entire file:

```python
from JamesExperiment.tensor_stream import open_batch_tensor
images = open_batch_tensor('outputs/JamesExperiment/compact_patches_7_seed_42/images.pt')
batch = images[:8]  # Ordinary float32 torch tensor; only this batch is copied.
```

No training split or model training
is performed; establish patient-disjoint evaluation splits before training.

The older slide_sampling.py CLI remains an already-local tensor-export utility.
The notebook uses compact_pipeline instead, preserving every chosen slide
and avoiding a second reduction. tensor_stream implements the PyTorch ZIP
serialization layout and is tested with normal and memory-mapped torch.load.

To execute and save both notebooks' outputs programmatically, install nbformat
and nbclient, then run `python -m JamesExperiment.run_notebook` from the project
root. Progress is also recorded in outputs/JamesExperiment/notebook_run_status.txt.
After completion, `python -m JamesExperiment.verify_run` checks slide coverage,
the exact reproducible patch indices, tensor shapes, and representative paired
image/expression rows, then writes verification.json beside the tensors.

Synthetic checks:
python -m unittest JamesExperiment.test_slide_sampling JamesExperiment.test_patch_sampling JamesExperiment.test_compact_pipeline
