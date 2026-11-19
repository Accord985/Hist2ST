"""Verify gene-panel progress or the completed 7% human Visium tensor run."""
import argparse
import json
import math
from pathlib import Path
import random


def main():
    import numpy as np
    import pandas as pd
    import torch

    parser = argparse.ArgumentParser()
    parser.add_argument('--samples-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / 'outputs/JamesExperiment/selection/sampling_settings.json').read_text())
    selected_metadata = pd.read_csv(root / 'outputs/JamesExperiment/selection/candidate_metadata.csv')
    assert selected_metadata['id'].tolist() == settings['slide_ids']
    assert set(selected_metadata['species']) == {'Homo sapiens'}
    assert set(selected_metadata['st_technology']) == {'Visium'}
    samples = Path(settings['data_dir'])
    from .gene_alignment import load_human_gene_map, align_columns
    mapping = load_human_gene_map()
    common = None
    completed = 0
    for slide in settings['slide_ids']:
        path = samples / f'{slide}.npz'
        if not path.with_suffix('.json').exists():
            continue
        with np.load(path, allow_pickle=True) as sample:
            panel = set(mapping.panel(sample['genes'].tolist()))
            previous = len(common) if common is not None else None
            common = panel if common is None else common & panel
            if previous and not common:
                print(f'Gene identifiers diverge at {slide}: {sorted(panel)[:12]}', flush=True)
        completed += 1
    print(f'{completed} slides checked; shared genes: {len(common or [])}', flush=True)
    if args.samples_only:
        return
    assert completed == len(settings['slide_ids'])
    output = Path(settings['output_dir'])
    metadata = json.loads((output / 'experiment.json').read_text())
    manifest = pd.read_csv(output / 'patch_manifest.csv')
    genes = json.loads((output / 'genes.json').read_text())
    assert metadata['complete'] and genes == sorted(common)
    assert set(manifest.slide_id) == set(settings['slide_ids'])
    from .tensor_stream import open_batch_tensor
    images = open_batch_tensor(output / 'images.pt')
    targets = torch.load(output / 'targets.pt', weights_only=True)
    assert list(images.shape) == metadata['images_shape']
    assert list(targets.shape) == metadata['targets_shape']
    assert len(images) == len(targets) == len(manifest)
    assert manifest.order.tolist() == list(range(len(manifest)))
    for slide, frame in manifest.groupby('slide_id', sort=False):
        source = json.loads((samples / f'{slide}.json').read_text())
        count = max(1, math.floor(source['source_patches'] * settings['percentage'] / 100))
        expected = sorted(random.Random(f'{settings["seed"]}:{slide}').sample(range(source['source_patches']), count))
        assert frame.patch_index.tolist() == expected
    selected = settings['slide_ids']
    for slide in [selected[0], selected[len(selected) // 3], selected[2 * len(selected) // 3], selected[-1]]:
        frame = manifest[manifest.slide_id == slide]
        with np.load(samples / f'{slide}.npz', allow_pickle=True) as sample:
            for position in (0, len(frame) - 1):
                order = frame.order.iloc[position]
                raw = torch.from_numpy(sample['images'][position].copy()).permute(2, 0, 1).float() / 255
                mean = torch.tensor([.697, .575, .728])[:, None, None]
                std = torch.tensor([.188, .240, .187])[:, None, None]
                torch.testing.assert_close(images[order], (raw - mean) / std)
                expected = align_columns(sample['expression'][position:position + 1], sample['genes'], genes, mapping)[0]
                torch.testing.assert_close(targets[order], torch.from_numpy(expected))
    report = dict(verified=True, slides=len(selected), patches=len(manifest), genes=len(genes),
                  images_shape=list(images.shape), targets_shape=list(targets.shape),
                  percentage=settings['percentage'], seed=settings['seed'],
                  filters=dict(organ='all', species='Homo sapiens', st_technology='Visium'))
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
