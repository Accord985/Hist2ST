"""Technique 1: sample whole slides and export paired PathFM inputs/targets."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import random


def sample_slide_ids(slide_ids, percentage, seed=42):
    """Sample metadata IDs before any slide files are listed or downloaded."""
    if isinstance(percentage, bool) or not math.isfinite(float(percentage)) or not 0 < float(percentage) <= 100:
        raise ValueError('percentage must be greater than 0 and at most 100.')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer.')
    ids = sorted(set(slide_ids))
    if any(not isinstance(s, str) or not s or Path(s).name != s or s in ('.', '..') for s in ids):
        raise ValueError('Expected nonempty slide IDs without path components.')
    count = math.floor(len(ids) * float(percentage) / 100)
    if count == 0:
        raise ValueError(f'{len(ids)} eligible slides: percentage selects zero slides. Increase it.')
    return sorted(random.Random(seed).sample(ids, count))


def sample_slides(data_dir, percentage, seed=42, slide_ids=None):
    """Select IDs first, then inspect only selected slides and retain all patches.

    Pass metadata slide_ids to avoid enumerating unrelated data directories.
    Missing selected slides/patch files raise instead of changing the sample.
    """
    root = Path(data_dir).expanduser().resolve()
    eligible = (sorted(set(slide_ids)) if slide_ids is not None else
                sorted(s.name for s in root.iterdir() if s.is_dir()
                       and any(p.is_dir() and p.name.startswith(s.name + '_patch_')
                               for p in s.iterdir())))
    chosen = sample_slide_ids(eligible, percentage, seed)
    records = []
    for slide_id in chosen:
        slide = root / slide_id
        if not slide.is_dir():
            raise ValueError(f'Selected slide directory is missing: {slide_id}')
        patches = sorted(p for p in slide.iterdir()
                         if p.is_dir() and p.name.startswith(slide_id + '_patch_'))
        if not patches:
            raise ValueError(f'Selected slide has no patch folders: {slide_id}')
        for patch in patches:
            row = dict(slide_id=slide_id, patch_name=patch.name,
                       image_path=str(patch / f'{patch.name}.png'),
                       expression_path=str(patch / f'{patch.name}.csv'),
                       barcode_path=str(patch / 'barcode.csv'))
            for key in ('image_path', 'expression_path', 'barcode_path'):
                if not Path(row[key]).is_file():
                    raise FileNotFoundError(row[key])
            records.append(row)
    return records, eligible, chosen


def read_expression(path):
    """Read the existing cleaned HEST CSV format; reject ambiguous gene names."""
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not {'gene', 'expression'}.issubset(reader.fieldnames or []):
            raise ValueError(f'Expected gene/expression columns: {path}')
        pairs = [(row['gene'].strip(), float(row['expression'])) for row in reader]
    if not pairs or any(not gene or not math.isfinite(value) or value < 0 for gene, value in pairs):
        raise ValueError(f'Empty genes or invalid expression values: {path}')
    duplicates = [gene for gene, count in Counter(g for g, _ in pairs).items() if count > 1]
    if duplicates:
        raise ValueError(f'Ambiguous duplicate gene names in {path}: {duplicates[:10]}')
    return dict(pairs)


def export_tensors(data_dir, output_dir, percentage, seed=42, expression_mode='raw', slide_ids=None):
    """Write CPU float32 images [N,3,224,224] and targets [N,G].

    Shared genes are intersected across every retained patch, then sorted.
    relative_log_10000 normalizes using each patch's full source gene panel
    before selecting shared genes. No model weights are needed for export.
    """
    if expression_mode not in ('raw', 'relative_log_10000'):
        raise ValueError('expression_mode must be raw or relative_log_10000.')
    import torch
    from PIL import Image
    from torchvision import transforms

    records, eligible, selected = sample_slides(data_dir, percentage, seed, slide_ids=slide_ids)
    out = Path(output_dir).expanduser().resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f'Choose an empty output directory: {out}')
    shared = None
    for row in records:
        panel = set(read_expression(row['expression_path']))
        shared = panel if shared is None else shared & panel
    genes = sorted(shared)
    if not genes:
        raise ValueError('No shared genes across selected patches. Check species and identifiers.')
    transform = transforms.Compose([
        transforms.Resize((224, 224)), transforms.ToTensor(),
        transforms.Normalize(mean=(0.697, 0.575, 0.728), std=(0.188, 0.240, 0.187)),
    ])
    gib = len(records) * (3 * 224 * 224 + len(genes)) * 4 / 1024**3
    print(f'{len(selected)}/{len(eligible)} slides; {len(records)} patches; {len(genes)} shared genes.', flush=True)
    print(f'Tensor storage in RAM: approximately {gib:.2f} GiB. Reduce percentage if needed.', flush=True)
    images = torch.empty((len(records), 3, 224, 224), dtype=torch.float32)
    targets = torch.empty((len(records), len(genes)), dtype=torch.float32)
    gene_set = set(genes)
    for index, row in enumerate(records):
        values = read_expression(row['expression_path'])
        if not gene_set.issubset(values):
            raise ValueError('Source gene panel changed during export; rerun.')
        aligned = [values[gene] for gene in genes]
        if expression_mode == 'relative_log_10000':
            total = sum(values.values())
            aligned = [math.log1p(value / total * 10000) if total else 0.0 for value in aligned]
        targets[index] = torch.tensor(aligned, dtype=torch.float32)
        with Image.open(row['image_path']) as image:
            images[index] = transform(image.convert('RGB'))
    if not torch.isfinite(targets).all():
        raise ValueError('Expression values exceed float32 range.')
    out.mkdir(parents=True, exist_ok=True)
    torch.save(images, out / 'images.pt')
    torch.save(targets, out / 'targets.pt')
    with (out / 'patch_manifest.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['order', *records[0]])
        writer.writeheader()
        writer.writerows(dict(order=i, **row) for i, row in enumerate(records))
    (out / 'genes.json').write_text(json.dumps(genes, indent=2), encoding='utf-8')
    # Written last: absence of this marker means the export is incomplete.
    metadata = dict(complete=True, technique='random_slide_sampling',
                    data_dir=str(Path(data_dir).resolve()), percentage=float(percentage),
                    seed=seed, rounding='floor', eligible_slides=eligible,
                    selected_slides=selected, expression_mode=expression_mode,
                    images_shape=list(images.shape), targets_shape=list(targets.shape),
                    dtype='float32', shared_gene_scope='all_selected_patches',
                    image_mean=[0.697, 0.575, 0.728], image_std=[0.188, 0.240, 0.187])
    (out / 'experiment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--percentage', type=float, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--expression-mode', choices=['raw', 'relative_log_10000'], default='raw')
    args = parser.parse_args()
    export_tensors(**vars(args))


if __name__ == '__main__':
    main()
