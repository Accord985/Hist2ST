"""Sparse remote patch extraction: every selected slide, only sampled images."""
import json
from pathlib import Path
import tempfile


def load_patch_settings(settings_path):
    """Reject old slide-sampling settings before downloads or tensor export."""
    settings = json.loads(Path(settings_path).read_text(encoding='utf-8'))
    required = {'slide_ids', 'data_dir', 'output_dir', 'percentage', 'seed', 'expression_mode'}
    if settings.get('sampling_unit') != 'patch_within_slide' or not required.issubset(settings):
        raise ValueError('Old slide-sampling settings detected. Run notebook section 4 '
                         'to save PATCH_PERCENTAGE settings, then section 5 to extract patches.')
    return settings


def export_sampled_tensors(settings_path):
    """Export all pre-sampled patches, preserving every selected slide."""
    settings = load_patch_settings(settings_path)
    root = Path(settings['data_dir'])
    for slide_id in settings['slide_ids']:
        marker = root / slide_id / 'export_complete.json'
        if not marker.is_file():
            raise ValueError(f'Sampled patches are not ready for {slide_id} in {root}. '
                             'Run section 5 (patch extraction) before section 6 (tensor export).')
        saved = json.loads(marker.read_text(encoding='utf-8'))
        if (saved.get('patch_percentage') != settings['percentage']
                or saved.get('sampling_seed') != settings['seed']):
            raise ValueError(f'{slide_id}: sampled patches do not match the saved percentage/seed. '
                             'Rerun sections 4 and 5 with a matching data directory.')
    from JamesExperiment.slide_sampling import export_tensors
    out = export_tensors(
        root, settings['output_dir'], percentage=100, seed=settings['seed'],
        expression_mode=settings['expression_mode'], slide_ids=settings['slide_ids'],
    )
    (out / 'sampling_settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
    path = out / 'experiment.json'
    metadata = json.loads(path.read_text(encoding='utf-8'))
    metadata.update(technique='random_patch_sampling', sampling_unit='patch_within_slide',
                    patch_percentage=settings['percentage'], patch_sampling_seed=settings['seed'])
    path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return out


def download_sampled_patches(slide_ids, output_dir, percentage, seed=42, revision='main'):
    """Range-read image HDF5 files; download only expression H5AD files in full.

    Requires fsspec and aiohttp. The HTTP server must support byte ranges:
    failures stop processing rather than downloading full image containers.
    HDF5 chunking and a 1 MiB read cache can fetch neighboring bytes. Only
    selected image/expression rows are decoded and exported. Completed slides
    with identical settings are reused; interrupted slide folders are retained.
    """
    import fsspec
    from huggingface_hub import HfApi, get_token, hf_hub_download, hf_hub_url
    from hest_download_pipeline import REPO_ID, export_slide, match_sample_files

    if isinstance(percentage, bool) or not 0 < float(percentage) <= 100:
        raise ValueError('percentage must be greater than zero and at most 100.')
    if isinstance(slide_ids, str) or not slide_ids:
        raise ValueError('Provide a nonempty list of slide IDs.')
    ids = list(dict.fromkeys(slide_ids))
    import re
    if any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9-]+', s) for s in ids):
        raise ValueError('Invalid slide IDs.')
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    api = HfApi()
    commit = api.repo_info(REPO_ID, repo_type='dataset', revision=revision).sha
    # List only the two required remote folders once for the whole cohort.
    paths = []
    for folder in ('patches', 'st'):
        paths.extend(entry.path for entry in api.list_repo_tree(
            REPO_ID, path_in_repo=folder, repo_type='dataset', revision=commit,
            recursive=True) if hasattr(entry, 'size'))
    matches = match_sample_files(paths, ids)
    token = get_token()
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    for position, slide_id in enumerate(ids, 1):
        marker = output / slide_id / 'export_complete.json'
        if marker.is_file():
            saved = json.loads(marker.read_text(encoding='utf-8'))
            if (saved.get('patch_percentage') != float(percentage)
                    or saved.get('sampling_seed') != seed
                    or saved.get('source_revision') != commit):
                raise ValueError(f'{slide_id}: existing sample has different settings; use a new output directory.')
            print(f'[{position}/{len(ids)}] Reusing {slide_id}', flush=True)
            continue
        image_paths = [p for p, owners in matches.items() if slide_id in owners
                       and p.startswith('patches/') and p.endswith(('.h5', '.hdf5'))]
        expression_paths = [p for p, owners in matches.items() if slide_id in owners
                            and p.startswith('st/') and p.endswith('.h5ad')]
        if len(image_paths) != 1 or len(expression_paths) != 1:
            raise ValueError(f'{slide_id}: expected exactly one patch H5 and one expression H5AD.')
        print(f'[{position}/{len(ids)}] Sampling patches from {slide_id}', flush=True)
        with tempfile.TemporaryDirectory(prefix='james_expression_') as staging:
            expression = hf_hub_download(
                REPO_ID, expression_paths[0], repo_type='dataset', revision=commit,
                local_dir=staging,
            )
            url = hf_hub_url(REPO_ID, image_paths[0], repo_type='dataset', revision=commit)
            # h5py reads only selected datasets/chunks through this seekable file.
            with fsspec.open(url, mode='rb', block_size=1024**2,
                             cache_type='blockcache', headers=headers) as remote:
                export_slide(remote, expression, output, slide_id,
                             patch_percentage=percentage, sampling_seed=seed)
            saved = json.loads(marker.read_text(encoding='utf-8'))
            saved['source_revision'] = commit
            marker.write_text(json.dumps(saved, indent=2), encoding='utf-8')
    (output / 'patch_sampling.json').write_text(json.dumps(dict(
        slide_ids=ids, percentage=float(percentage), seed=seed,
        revision=commit, sampling_unit='patch_within_slide',
        rounding='max(1, floor(N * percentage / 100))',
    ), indent=2), encoding='utf-8')
    return output
