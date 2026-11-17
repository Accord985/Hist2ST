
# Notebook Guide

## Onboarding

The ultimate goal of onboarding notebooks is to reproduce our baseline, which is the full-cohort patient-level ridge regression. They are designed to be reproducible for anyone with basic Python and CSE background.

The location for data storage is defined by `DATA_DIR` in each onboarding notebook. Use the same directory for Notebooks 01-03.

**Before Notebook 01:** [00 - Python data basics](../docs/onbd_00_python_data_basics.ipynb) introduces the libraries and file formats used in the onboarding path.

1. [01 - Data preparation](onbd_01_data_preparation.ipynb): inspect HEST metadata and paired image/expression data, then create aligned breast-cohort files.
2. [02 - GenBio embeddings](onbd_02_genbio_embeddings.ipynb): turn each spot patch into a 4,608-value GenBio-PathFM embedding.
3. [03 - PCA, ridge, and evaluation](onbd_03_pca_ridge_evaluation.ipynb): compare spot-, slide-, and patient-level evaluation and reproduce the full-cohort ridge result.


To run these notebooks: 

1. Confirm HEST access and choose a writable data directory.
2. Run Notebook 01 with `N_PATIENTS = 3`. Check barcode alignment and the spatial expression map. Then set `N_PATIENTS = None` to prepare the full study.
3. Run Notebook 02 and confirm one 4,608-feature row per spot in matching barcode order.
4. Run Notebook 03 with the full cohort and four patient folds. The result directory contains fold assignments, score tables, settings, and figures.
5. Treat patient-level scores as the main generalization estimate. Spot and slide splits are comparisons that can share nearby tissue or patients across train and test.


## Experiments

Each notebook records an experiment. Results are recorded where available. Experiment 00 introduces the standard helper-based workflow for downloading, cleaning, and splitting data. Script-based notebooks install project dependencies from `requirements.txt`.


- [00 - Standard project workflow](00_standard_workflow.ipynb): use workflow modules in `scripts/` with reusable helpers from `src/` for cohort selection, clean export, and optional patch-level splitting.
- [Cohort filtering and split](exp_cohort_filtering_and_split.ipynb): alternate HEST filtering and sample-level splitting.
- [PCA versus no PCA](exp_pca_vs_no_pca.ipynb): random-spot comparison and spatial-block follow-up.
- [Neighborhood MLP](exp_neighborhood_mlp.ipynb): patient-fold spatial context experiment.
- [Transformer preparation and training](exp_transformer_preparation_and_training.ipynb): optional full pipeline from cohort preparation to transformer training. 

## How to add new experiments

- Name them with a number and an informative name, so we know which experiment comes first, and what each experiment is about. 
- Make sure the relevant directories are specified at the start of the notebook. 
- Make sure drives are loaded at the start of the notebook.
- Clearly record the method to produce the results
- Add a short description of the experiment in this file in the **Experiments** section above

## How the current notebooks relate to the archived originals

The current onboarding material absorbs [data_summary.ipynb](archived/data_summary.ipynb) and [preview_one_hest_sample.ipynb](archived/preview_one_hest_sample.ipynb) into data preparation, [foundationmodel_test.ipynb](archived/foundationmodel_test.ipynb) into embeddings, and [pca_for_reconstruction.ipynb](archived/pca_for_reconstruction.ipynb) plus [pca_reconstruction.ipynb](archived/pca_reconstruction.ipynb) into PCA/ridge. The filtered clean-export and patch-split workflow from [hest_filtered_download_colab.ipynb](archived/hest_filtered_download_colab.ipynb) is covered in Experiment 00. The cohort split, PCA comparisons, neighborhood MLP, and transformer source notebooks are represented in Experiments. [ridge_on_pt_files_colab.ipynb](ridge_on_pt_files_colab.ipynb) is deferred for now. Original notebooks are retained in [archived/](archived/).

The archived baseline sequence is [01_data_colab.ipynb](archived/01_data_colab.ipynb), [02_embedding_colab.ipynb](archived/02_embedding_colab.ipynb), and [03_pca_ridge_colab.ipynb](archived/03_pca_ridge_colab.ipynb). Other experiment sources are [HEST_Patient_Level_Split_EN.ipynb](archived/HEST_Patient_Level_Split_EN.ipynb), [pca_vs_nopca_colab.ipynb](archived/pca_vs_nopca_colab.ipynb), [pca_vs_nopca_spatial_blocks.ipynb](archived/pca_vs_nopca_spatial_blocks.ipynb), [MLP_JK_Best.ipynb](archived/MLP_JK_Best.ipynb), [hest_content_transformer_pipeline(JAMES).ipynb](archived/hest_content_transformer_pipeline(JAMES).ipynb), and [HEST_train_from_tensors(JAMES).ipynb](archived/HEST_train_from_tensors(JAMES).ipynb).
