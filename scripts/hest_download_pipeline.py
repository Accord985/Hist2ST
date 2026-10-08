"""HEST selection and download functions for Google Colab or local Python.

Install huggingface_hub and pandas, then import:
    from hest_download_pipeline import prepare_selection, download_selection

prepare_selection(...) returns an editable list of IDs.
download_selection(data_ids, output_dir=...) downloads the final list.
download_clean_selection(data_ids, output_dir=...) saves slide/patch PNG + CSV.
clean_selection(data_ids, raw_dir=..., output_dir=...) converts existing files.
"""
from pathlib import Path, PurePosixPath
import json
import re
import shutil
import tempfile
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

REPO_ID = "MahmoodLab/hest"


def filter_metadata(metadata, organs=None, species=None, st_technologies=None):
    """OR within each list; AND across filters; None/[] selects all values."""
    result = metadata.copy()
    for column, choices in (("organ", organs), ("species", species),
                            ("st_technology", st_technologies)):
        if column not in result:
            raise ValueError(f"Missing metadata column: {column}")
        if isinstance(choices, str):
            choices = [choices]
        if not choices:
            continue
        available = set(metadata[column].dropna().astype(str).str.strip().str.casefold())
        requested = {str(value).strip().casefold() for value in choices}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Unknown {column} values: {sorted(unknown)}. "
                             f"Available: {sorted(metadata[column].dropna().unique())}")
        result = result[result[column].astype('string').str.strip().str.casefold().isin(requested)]
    if result.empty:
        raise ValueError("No samples match this combination of filters.")
    if result['id'].isna().any() or result['id'].duplicated().any():
        raise ValueError("Metadata contains missing or duplicate sample IDs.")
    return result.reset_index(drop=True)


def match_sample_files(paths, ids):
    """Match complete IDs in path components, including ID-prefixed filenames."""
    ids = set(map(str, ids))
    pattern = re.compile(r"^(" + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
                         + r")(?=$|[_.])") if ids else None
    matches = {}
    for path in paths:
        if pattern is None:
            break
        owners = set()
        for component in PurePosixPath(path).parts:
            match = pattern.match(component)
            if match:
                owners.add(match.group(1))
        if owners:
            matches[path] = sorted(owners)
    return matches


def prepare_selection(organs=None, species=None, st_technologies=None,
                      metadata_filename="HEST_v1_3_0.csv", revision="main",
                      max_samples=None):
    """Return a plain editable list of matching sample IDs."""
    api = HfApi()
    commit = api.repo_info(REPO_ID, repo_type="dataset", revision=revision).sha
    meta_path = hf_hub_download(REPO_ID, metadata_filename, repo_type="dataset",
                                revision=commit)
    metadata = pd.read_csv(meta_path, dtype={'id': str})
    for col in ('organ', 'species', 'st_technology'):
        print(f"Available {col}: {sorted(metadata[col].dropna().unique())}")
    selected = filter_metadata(metadata, organs, species, st_technologies)
    if max_samples is not None:
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 1:
            raise ValueError('max_samples must be a positive integer or None')
        selected = selected.head(max_samples)
    ids = selected['id'].tolist()
    print(f"Selected {len(ids)} samples")
    return ids


def download_selection(data_ids, output_dir, max_workers=2, data_folders=None,
                       metadata_filename="HEST_v1_3_0.csv", revision="main",
                       dry_run=False):
    """Build a fresh download manifest from the user's editable ID list.

    data_folders=None downloads all associated files. dry_run=True saves only
    metadata, IDs, and the download plan. Existing unrelated files are retained.
    """
    if isinstance(data_ids, str):
        raise ValueError('Pass a list of IDs, not a single string.')
    ids = list(dict.fromkeys(data_ids))
    if not ids or any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9-]+', i) for i in ids):
        raise ValueError('Provide a nonempty list of valid sample ID strings.')
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    api = HfApi()
    commit = api.repo_info(REPO_ID, repo_type='dataset', revision=revision).sha
    meta_path = hf_hub_download(REPO_ID, metadata_filename, repo_type='dataset',
                                revision=commit, local_dir=str(output))
    metadata = pd.read_csv(meta_path, dtype={'id': str})
    unknown = set(ids) - set(metadata['id'])
    if unknown:
        raise ValueError(f'IDs absent from {metadata_filename}: {sorted(unknown)}')
    selected = metadata.set_index('id').loc[ids].reset_index()
    # List remote sizes without loading images or expression matrices into RAM.
    entries = [entry for entry in api.list_repo_tree(REPO_ID, repo_type='dataset',
                revision=commit, recursive=True) if hasattr(entry, 'size')]
    paths = [entry.path for entry in entries]
    matches = match_sample_files(paths, ids)
    if data_folders is not None:
        if isinstance(data_folders, str):
            data_folders = [data_folders]
        unknown = set(data_folders) - {p.split('/')[0] for p in paths}
        if unknown:
            raise ValueError(f'Unknown data folders: {sorted(unknown)}')
        matches = {p: owners for p, owners in matches.items() if p.split('/')[0] in data_folders}
    sizes = {entry.path: entry.size for entry in entries}
    rows = [{'path': p, 'sample_ids': '|'.join(matches[p]), 'size_bytes': sizes[p]}
            for p in sorted(matches)]
    manifest = pd.DataFrame(rows, columns=['path', 'sample_ids', 'size_bytes'])
    found = {i for owners in matches.values() for i in owners}
    missing = set(ids) - found
    if missing:
        raise RuntimeError(f'No associated files found for: {sorted(missing)}')
    selected.to_csv(output / 'selected_metadata.csv', index=False)
    (output / 'selected_ids.json').write_text(json.dumps(ids, indent=2), encoding='utf-8')
    (output / 'selected_ids.txt').write_text('\n'.join(ids) + '\n', encoding='utf-8')
    manifest.to_csv(output / 'download_manifest.csv', index=False)
    plan = dict(repo_id=REPO_ID, revision=commit, metadata_filename=metadata_filename,
                output_dir=str(output),
                data_folders=data_folders, ids=ids, files=manifest['path'].tolist(),
                total_bytes=int(manifest['size_bytes'].sum()))
    (output / 'selection_config.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print(f"Selected {len(ids)} samples, {len(manifest)} files, "
          f"{plan['total_bytes'] / 2**30:.2f} GiB total. Destination: {output}")
    print(manifest.groupby(manifest['path'].str.split('/').str[0])['size_bytes'].agg(['count', 'sum']))
    if dry_run:
        return manifest
    (output / 'download_complete.json').unlink(missing_ok=True)
    needed = sum(int(row.size_bytes) for row in manifest.itertuples()
                 if not (output / row.path).is_file()
                 or (output / row.path).stat().st_size != int(row.size_bytes))
    free = shutil.disk_usage(output).free
    if needed > free:
        raise OSError(f'Insufficient disk space: {needed / 2**30:.2f} GiB needed, '
                      f'{free / 2**30:.2f} GiB free. Choose a larger destination or smaller cohort.')
    snapshot_download(repo_id=plan['repo_id'], repo_type='dataset',
                      revision=plan['revision'], local_dir=str(output),
                      allow_patterns=plan['files'], max_workers=max_workers)
    manifest['status'] = ['complete' if (output / row.path).is_file()
                          and (output / row.path).stat().st_size == int(row.size_bytes)
                          else 'missing_or_wrong_size' for row in manifest.itertuples()]
    manifest.to_csv(output / 'download_manifest.csv', index=False)
    if (manifest['status'] != 'complete').any():
        raise RuntimeError('Some files failed verification; inspect download_manifest.csv and rerun.')
    (output / 'download_complete.json').write_text(json.dumps({
        'revision': plan['revision'], 'samples': len(plan['ids']),
        'files': len(plan['files']), 'total_bytes': plan['total_bytes']}, indent=2), encoding='utf-8')
    print(f"Verified {len(manifest)} files in {output}")
    return manifest


def export_slide(patches_path, expression_path, output_dir, slide_id):
    """Export 224x224 RGB PNGs, unchanged .X gene values, barcodes and coordinates.

    Each output patch is named SLIDE_patch_INDEX; expression rows are matched
    strictly by barcode, never by row order. Reads one image/expression row at a
    time. H5AD is opened backed; sparse .X rows are densified individually.
    """
    import anndata
    import h5py
    import numpy as np
    from PIL import Image

    if not re.fullmatch(r'[A-Za-z0-9-]+', slide_id):
        raise ValueError('Invalid slide ID')
    slide_dir = Path(output_dir).expanduser().resolve() / slide_id
    slide_dir.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a previous slide export. Incomplete folders must be
    # reviewed or removed explicitly before retrying.
    if any(slide_dir.iterdir()):
        raise FileExistsError(f'{slide_dir} is not empty; choose a new destination.')
    adata = anndata.read_h5ad(expression_path, backed='r')
    try:
        if not adata.obs_names.is_unique:
            raise ValueError('Expression barcodes must be unique.')
        genes = adata.var_names.astype(str).tolist()
        with h5py.File(patches_path, 'r') as patches:
            if not {'img', 'barcode'}.issubset(patches.keys()):
                raise ValueError('Patch H5 must contain img and barcode datasets.')
            images = patches['img']
            if images.shape[1:] != (224, 224, 3) or images.dtype != np.dtype('uint8'):
                raise ValueError(f'Expected uint8 (N,224,224,3), got {images.shape}, {images.dtype}')
            if len(images) == 0 or len(patches['barcode']) != len(images):
                raise ValueError('Empty patches or barcode/image count mismatch.')
            def decode_barcode(value):
                values = np.asarray(value).reshape(-1)
                if len(values) != 1:
                    raise ValueError('Expected one barcode per patch.')
                value = values[0]
                return value.decode('utf-8') if isinstance(value, bytes) else str(value)
            barcodes = [decode_barcode(b) for b in patches['barcode']]
            if len(set(barcodes)) != len(barcodes):
                raise ValueError('Duplicate patch barcodes: cannot assign unique targets.')
            row_indices = adata.obs_names.get_indexer(barcodes)
            missing = [b for b, i in zip(barcodes, row_indices) if i < 0]
            if missing:
                raise ValueError(f'{len(missing)} patch barcodes have no expression row: {missing[:10]}')
            coords = patches.get('coords')
            if coords is not None and (coords.shape != (len(images), 2)):
                raise ValueError(f'Unexpected patch coordinate shape: {coords.shape}')
            spatial = adata.obsm.get('spatial')
            if spatial is not None and (len(spatial.shape) != 2 or spatial.shape[1] < 2):
                raise ValueError('Unexpected expression spatial coordinate shape.')
            rows = []
            for i, (barcode, row_index) in enumerate(zip(barcodes, row_indices)):
                name = f'{slide_id}_patch_{i:05d}'
                folder = slide_dir / name
                folder.mkdir()
                Image.fromarray(images[i]).save(folder / f'{name}.png')
                expression = adata.X[int(row_index):int(row_index) + 1, :]
                values = (expression.toarray() if hasattr(expression, 'toarray')
                          else np.asarray(expression)).reshape(-1)
                if not np.isfinite(values).all():
                    raise ValueError(f'Nonfinite expression values for {barcode}')
                # Save every gene, including zero values; no normalization/log transform.
                pd.DataFrame({'gene_index': range(len(genes)), 'gene': genes, 'expression': values}).to_csv(
                    folder / f'{name}.csv', index=False)
                location = {'slide_id': slide_id, 'patch_name': name, 'barcode': barcode,
                            'patch_index': i}
                if coords is not None:
                    location.update(patch_x=coords[i, 0].item(), patch_y=coords[i, 1].item())
                if spatial is not None:
                    location.update(spot_x=float(spatial[row_index, 0]),
                                    spot_y=float(spatial[row_index, 1]))
                pd.DataFrame([location]).to_csv(folder / 'barcode.csv', index=False)
                rows.append(location)
            result = pd.DataFrame(rows)
            result.to_csv(slide_dir / 'patch_manifest.csv', index=False)
            (slide_dir / 'export_complete.json').write_text(json.dumps({
                'slide_id': slide_id, 'patches': len(rows), 'genes': len(genes),
                'expression_source': 'AnnData.X; values unchanged',
                'patch_coords': 'H5 coords as supplied; no coordinate conversion',
                'spot_coords': 'AnnData.obsm spatial as supplied; no coordinate conversion',
            }, indent=2), encoding='utf-8')
            print(f'Exported {len(rows)} patches to {slide_dir}')
            return result
    finally:
        adata.file.close()


def clean_selection(data_ids, raw_dir, output_dir):
    """Convert already-downloaded patches/ + st/ without changing original files."""
    if isinstance(data_ids, str) or not data_ids:
        raise ValueError('Provide a nonempty list of slide IDs.')
    root = Path(raw_dir)
    summaries = []
    for slide_id in dict.fromkeys(data_ids):
        patch_files = list(match_sample_files(
            [p.as_posix() for p in (root / 'patches').rglob('*')
             if p.is_file() and p.suffix in ('.h5', '.hdf5')], [slide_id]))
        expression_files = list(match_sample_files(
            [p.as_posix() for p in (root / 'st').rglob('*.h5ad')], [slide_id]))
        if len(patch_files) != 1 or len(expression_files) != 1:
            raise ValueError(f'{slide_id}: expected one patch H5 and one expression H5AD; '
                             f'found {len(patch_files)} and {len(expression_files)}')
        result = export_slide(patch_files[0], expression_files[0], output_dir, slide_id)
        summaries.append({'slide_id': slide_id, 'patches': len(result)})
    return pd.DataFrame(summaries)


def download_clean_selection(data_ids, output_dir, max_workers=2,
                             metadata_filename='HEST_v1_3_0.csv', revision='main',
                             staging_dir=None):
    """Download only patches + expression to temporary storage, then export.

    Only the clean slide/patch folders are kept in output_dir. Temporary raw H5
    files are discarded when each slide finishes (also on errors); existing
    downloaded originals elsewhere are never deleted. staging_dir should be a
    local Colab directory, e.g. /content, not the final destination on Drive.
    """
    if isinstance(data_ids, str) or not data_ids:
        raise ValueError('Provide a nonempty list of slide IDs.')
    ids = list(dict.fromkeys(data_ids))
    output = Path(output_dir).expanduser().resolve()
    for slide_id in ids:
        if not isinstance(slide_id, str) or not re.fullmatch(r'[A-Za-z0-9-]+', slide_id):
            raise ValueError(f'Invalid slide ID: {slide_id}')
        slide_dir = output / slide_id
        if slide_dir.exists() and any(slide_dir.iterdir()):
            raise FileExistsError(f'{slide_dir} is not empty; choose a new destination.')
    commit = HfApi().repo_info(REPO_ID, repo_type='dataset', revision=revision).sha
    results = []
    for slide_id in ids:
        with tempfile.TemporaryDirectory(prefix='hest_stage_', dir=staging_dir) as raw:
            download_selection([slide_id], raw, max_workers=max_workers,
                               data_folders=['patches', 'st'],
                               metadata_filename=metadata_filename, revision=commit)
            summary = clean_selection([slide_id], raw, output)
            results.extend(summary.to_dict('records'))
    result = pd.DataFrame(results)
    output.mkdir(parents=True, exist_ok=True)
    result.to_csv(output / 'slides_manifest.csv', index=False)
    (output / 'clean_config.json').write_text(json.dumps({
        'ids': ids, 'revision': commit, 'metadata_filename': metadata_filename,
        'format': 'slide/patch/{patch.png, patch.csv, barcode.csv}',
    }, indent=2), encoding='utf-8')
    return result
