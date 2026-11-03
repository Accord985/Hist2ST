"""Train/test splits and aligned tensor exports for HEST; Colab compatible.

Expected layout: data_folder/slide_id/patch_name/{patch_name.png,
patch_name.csv, barcode.csv}. This module uses only the Python standard library.
It writes split manifests, leaving the images and expression files in place.
Tensor export additionally requires torch, torchvision, transformers, numpy and
pillow. By default it loads genbio-ai/genbio-pathfm using the supplied reference
notebook's preprocessing. You can also pass an already loaded model/transform.
"""
from pathlib import Path
import csv
import json
import math
import random
import uuid


def random_split_data(data_folder, train_percentage, seed=None, output_dir=None):
    """Shuffle patches, assign a percentage to training, and the rest to testing.

    Args:
        data_folder: Root containing cleaned slide/patch folders.
        train_percentage: Percentage from 0 to 100; e.g. 80 means 80% training.
        seed: Optional integer for a repeatable split. None produces a new split.
        output_dir: Empty folder for train.csv, test.csv and split_config.json.
            Default: a new uniquely named folder under data_folder/splits/.

    Returns:
        (train_paths, test_paths): Two lists of absolute patch-folder paths,
        in randomized order. CSV rows have the same order as these lists.

    The training count is floor(total_patches * train_percentage / 100).
    This splits individual patches, so a slide can appear in both partitions.
    Files within each patch remain paired; no files are moved or copied.
    Patches missing an image, expression CSV or barcode CSV are skipped and
    recorded in skipped_patches.json; percentages use only complete patches.
    """
    if isinstance(train_percentage, bool):
        raise ValueError('train_percentage must be a number from 0 to 100.')
    try:
        percentage = float(train_percentage)
    except (TypeError, ValueError) as exc:
        raise ValueError('train_percentage must be a number from 0 to 100.') from exc
    if not math.isfinite(percentage) or not 0 <= percentage <= 100:
        raise ValueError('train_percentage must be between 0 and 100.')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError('seed must be an integer or None.')
    root = Path(data_folder).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f'Data folder does not exist: {root}')

    records = []
    skipped = []
    # Sort before shuffling so a fixed seed is reproducible on the same dataset.
    for slide in sorted(root.iterdir()):
        if not slide.is_dir():
            continue
        for folder in sorted(slide.iterdir()):
            if not folder.is_dir():
                continue
            image = folder / f'{folder.name}.png'
            expression = folder / f'{folder.name}.csv'
            barcode = folder / 'barcode.csv'
            # Skip auxiliary folders and incomplete patch folders.
            if not (folder.name.startswith(f'{slide.name}_patch_')
                    or image.is_file() or barcode.is_file()):
                continue
            missing = [p.name for p in (image, expression, barcode) if not p.is_file()]
            if missing:
                skipped.append({'patch_dir': str(folder), 'missing_files': missing})
                continue
            records.append(dict(slide_id=slide.name, patch_name=folder.name,
                                patch_dir=str(folder), image_path=str(image),
                                expression_path=str(expression), barcode_path=str(barcode)))
    if not records:
        raise ValueError(f'No complete patch folders found under {root}; skipped {len(skipped)}.')

    random.Random(seed).shuffle(records)
    n_train = math.floor(len(records) * percentage / 100)
    if 0 < percentage < 100 and (n_train == 0 or n_train == len(records)):
        raise ValueError('Too few patches for nonempty training and testing sets '
                         'at this percentage. Choose a different percentage or more data.')
    train, test = records[:n_train], records[n_train:]
    destination = (Path(output_dir).expanduser().resolve() if output_dir is not None
                   else root / 'splits' / f'split_{uuid.uuid4().hex[:12]}')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError(f'Split output must be an empty folder: {destination}')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'skipped_patches.json').write_text(json.dumps(skipped, indent=2), encoding='utf-8')
    columns = ['order', 'slide_id', 'patch_name', 'patch_dir', 'image_path',
               'expression_path', 'barcode_path']
    for filename, rows in (('train.csv', train), ('test.csv', test)):
        with (destination / filename).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for order, row in enumerate(rows):
                writer.writerow(dict(order=order, **row))
    (destination / 'split_config.json').write_text(json.dumps({
        'data_folder': str(root), 'train_percentage': percentage, 'seed': seed,
        'split_unit': 'patch', 'rounding': 'floor', 'total_patches': len(records),
        'train_count': len(train), 'test_count': len(test),
        'skipped_count': len(skipped),
        'actual_train_percentage': 100 * len(train) / len(records),
        'output_dir': str(destination),
    }, indent=2), encoding='utf-8')
    print(f'Training: {len(train)} patches; testing: {len(test)} patches.')
    print(f'Skipped {len(skipped)} incomplete patches.')
    print(f'Shuffled lists saved in: {destination}')
    return [row['patch_dir'] for row in train], [row['patch_dir'] for row in test]


def _ordered_records(input_path, split='train', verify_files=True):
    """Load a split CSV, a folder containing that CSV, or an ordered path list."""
    if isinstance(input_path, (list, tuple)):
        records = []
        for p in input_path:
            folder = Path(p).expanduser().resolve()
            records.append(dict(slide_id=folder.parent.name, patch_name=folder.name,
                                patch_dir=str(folder), image_path=str(folder/f'{folder.name}.png'),
                                expression_path=str(folder/f'{folder.name}.csv'),
                                barcode_path=str(folder/'barcode.csv')))
    else:
        path = Path(input_path).expanduser().resolve()
        if path.is_dir():
            if split not in ('train', 'test'):
                raise ValueError('split must be train or test.')
            path = path / f'{split}.csv'
        with path.open(encoding='utf-8-sig', newline='') as f:
            records = list(csv.DictReader(f))
        for i, row in enumerate(records):
            if int(row.get('order', -1)) != i:
                raise ValueError('CSV order must be consecutive from zero; preserve the saved split order.')
            for key in ('patch_dir', 'image_path', 'expression_path', 'barcode_path'):
                value = Path(row[key]).expanduser()
                row[key] = str((value if value.is_absolute() else path.parent/value).resolve())
    if not records:
        raise ValueError('The requested split is empty.')
    identities = [(row['slide_id'], row['patch_name']) for row in records]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate patch identities in the split.')
    if not verify_files:
        return records
    complete = []
    for row in records:
        missing = [row[key] for key in ('image_path', 'expression_path', 'barcode_path')
                   if not Path(row[key]).is_file()]
        if missing:
            print(f"Skipping incomplete patch {row['patch_name']}: {missing}")
        else:
            complete.append(row)
    if not complete:
        raise ValueError('No complete patches remain in this split.')
    return complete


def _save_tensor(tensor, output_path, metadata):
    """Write a single CPU tensor plus a JSON sidecar describing its axes/order."""
    import torch
    import os
    output = Path(output_path).expanduser().resolve()
    if output.suffix != '.pt':
        raise ValueError('output_path must end with .pt')
    sidecar = output.with_suffix('.json')
    if output.exists() or sidecar.exists():
        raise FileExistsError(f'Choose a new output filename: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f'.{output.name}.{uuid.uuid4().hex}.tmp')
    try:
        torch.save(tensor.cpu(), temporary)
        sidecar.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Saved {list(tensor.shape)} tensor: {output}')
    return str(output)


def load_pathfm(device=None):
    """Load GenBio PathFM and the transform from Foundationmodel_test.ipynb.

    Reference notebook uses transformers==4.57.1 and trust_remote_code=True.
    This downloads weights/custom model code from genbio-ai/genbio-pathfm.
    Authentication, if required, should be done via the Hugging Face login prompt.
    """
    import torch
    from transformers import AutoModel
    from torchvision import transforms
    target = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))
    model = AutoModel.from_pretrained('genbio-ai/genbio-pathfm', trust_remote_code=True)
    model = model.to(target)
    model.eval()
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.697, 0.575, 0.728), std=(0.188, 0.240, 0.187)),
    ])
    return model, transform


def _embedding_callable_id(value):
    if value is None:
        return None
    return f'{getattr(value, "__module__", type(value).__module__)}.{getattr(value, "__qualname__", type(value).__qualname__)}'


def _embedding_record_fingerprint(records):
    from hest_content_pipeline import _checkpoint_fingerprint
    return _checkpoint_fingerprint([
        (r['slide_id'], r['patch_name'], str(r['image_path']), str(r['expression_path']))
        for r in records])


def _publish_embedding_prefix(path, prefix):
    import torch
    from hest_content_pipeline import _atomic_write
    def write(destination):
        with destination.open('wb') as handle:
            torch.save(torch.from_numpy(prefix.copy()), handle)
    _atomic_write(path, write)


def _load_embedding_image(row, transform):
    import torch
    from PIL import Image
    with Image.open(row['image_path']) as image:
        item = transform(image.convert('RGB'))
    if not isinstance(item, torch.Tensor) or item.ndim != 3:
        raise ValueError('transform must return a CHW torch tensor.')
    return item


def _embedding_batches(records, begin, end, batch_size, transform, num_workers):
    """Bounded, ordered CPU prefetch: at most one future model batch."""
    from concurrent.futures import ThreadPoolExecutor
    if num_workers == 0:
        for start in range(begin, end, batch_size):
            rows = records[start:min(start + batch_size, end)]
            yield start, [_load_embedding_image(row, transform) for row in rows]
        return
    with ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix='patch-loader') as pool:
        def submit(start):
            return [pool.submit(_load_embedding_image, row, transform)
                    for row in records[start:min(start + batch_size, end)]]
        pending = submit(begin)
        for start in range(begin, end, batch_size):
            # Consume futures in manifest order, regardless of completion order.
            images = [future.result() for future in pending]
            next_start = start + batch_size
            pending = submit(next_start) if next_start < end else []
            yield start, images


def export_embeddings(input_path, model=None, transform=None, output_path=None, batch_size=32,
                      split='train', device=None, output_selector=None, *, checkpoint_every=500,
                      checkpoint_mode='resume', checkpoint_unit='batches', model_id=None,
                      transform_id=None, selector_id=None, num_workers=4):
    """Encode ordered patches with resumable CPU tensor checkpoints.

    checkpoint_unit='batches' saves every 500 model forward passes by default;
    use 'patches' to save every 500 patch rows instead. The last short interval
    is always saved. batch_size independently controls GPU memory consumption.

    Each .pt is an ordered PREFIX until complete. Its .json records row identities
    and completion; .checkpoint.json and alternating .npz snapshots permit resume
    without re-encoding saved rows. A complete checkpoint returns without loading
    the model. Keep every sidecar on Drive. Existing outputs without checkpoint
    sidecars require a fresh run. Image contents/weights are not rehashed; start
    anew if they change. Use explicit versioned model_id/transform_id/selector_id
    for custom models or processing. The notebook supplies fixed PathFM IDs.

    This function requires the current companion hest_content_pipeline.py.
    It never shuffles/skips saved manifest rows, preserving alignment with targets.
    Missing/unreadable images stop processing while preserving the last checkpoint.
    Model evaluation mode is restored on exit; GPU holds only a model batch.
    num_workers parallelizes deterministic image decoding/transforms and prefetches
    the next batch during inference. Set 0 for sequential loading; this setting
    may change on resume without invalidating completed embeddings.
    """
    import numpy as np
    import torch
    from contextlib import closing
    from hest_content_pipeline import (_checkpoint_fingerprint, _load_gene_checkpoint,
        _commit_gene_checkpoint, _atomic_json, _checkpoint_file_hash)
    if output_path is None:
        raise ValueError('Specify output_path for the embedding .pt tensor.')
    for name, value in [('batch_size', batch_size), ('checkpoint_every', checkpoint_every)]:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f'{name} must be a positive integer.')
    if isinstance(num_workers, bool) or not isinstance(num_workers, int) or num_workers < 0:
        raise ValueError('num_workers must be a nonnegative integer.')
    if checkpoint_unit not in ('patches', 'batches'):
        raise ValueError("checkpoint_unit must be 'patches' or 'batches'.")
    path = Path(output_path).expanduser().resolve()
    if path.suffix != '.pt':
        raise ValueError('output_path must end with .pt')
    records = _ordered_records(input_path, split, verify_files=False)
    order_id = _embedding_record_fingerprint(records)
    model_tag = model_id or ('genbio-ai/genbio-pathfm' if model is None else _embedding_callable_id(model))
    transform_tag = transform_id or ('pathfm_rgb224_norm_v1' if transform is None else _embedding_callable_id(transform))
    selector_tag = selector_id or _embedding_callable_id(output_selector)
    fingerprint = _checkpoint_fingerprint(dict(version=1, order=order_id, model=model_tag,
        transform=transform_tag, selector=selector_tag, batch_size=batch_size,
        checkpoint_every=checkpoint_every, checkpoint_unit=checkpoint_unit))
    stem = f'{path.name}.checkpoint'
    restored = _load_gene_checkpoint(path.parent, stem, fingerprint, checkpoint_mode)
    result = np.empty((len(records), 0), dtype=np.float32)
    start = 0
    if restored is not None:
        state, arrays = restored
        start = state['next_position']
        prefix = arrays['embeddings']
        if (prefix.ndim != 2 or prefix.shape[0] != start or not 0 <= start <= len(records)
                or (start and prefix.shape[1] == 0) or not np.isfinite(prefix).all()):
            raise ValueError('Invalid embedding checkpoint dimensions/values. Choose start anew.')
        result = np.empty((len(records), prefix.shape[1]), dtype=np.float32)
        result[:start] = prefix
        print(f'Resumed {path.name}: {start}/{len(records)} patches.', flush=True)
    else:
        print(f'Starting {path.name}: {len(records)} patches.', flush=True)

    def save(next_position):
        state = dict(fingerprint=fingerprint, next_position=next_position, total=len(records))
        def publish():
            _publish_embedding_prefix(path, result[:next_position])
            metadata = dict(kind='embeddings', shape=[next_position, result.shape[1]],
                complete=next_position == len(records), total_patches=len(records),
                processed_patches=next_position, model_id=model_tag, transform_id=transform_tag,
                selector_id=selector_tag, checkpoint_unit=checkpoint_unit,
                checkpoint_every=checkpoint_every, batch_size=batch_size,
                num_workers=num_workers,
                patches=records[:next_position])
            _atomic_json(path.with_suffix('.json'), metadata)
            return dict(shape=metadata['shape'], order_fingerprint=order_id,
                tensor_sha256=_checkpoint_file_hash(path),
                metadata_sha256=_checkpoint_file_hash(path.with_suffix('.json')))
        _commit_gene_checkpoint(path.parent, stem, state,
                                dict(embeddings=result[:next_position]), publish)
        print(f'Saved {path.name}: {next_position}/{len(records)} patches.', flush=True)

    # Repair a .pt/sidecar interrupted between publication and manifest commit.
    save(start)
    if start == len(records):
        return torch.from_numpy(result)

    target = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))
    if target.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA was requested but is unavailable.')
    if model is None:
        model, reference_transform = load_pathfm(device=str(target))
        if transform is None:
            transform = reference_transform
    elif transform is None:
        from torchvision import transforms
        transform = transforms.Compose([
            transforms.Resize((224, 224)), transforms.ToTensor(),
            transforms.Normalize(mean=(0.697, 0.575, 0.728), std=(0.188, 0.240, 0.187)),
        ])
    model.to(target)
    previous_training = model.training
    model.eval()
    interval = checkpoint_every * batch_size if checkpoint_unit == 'batches' else checkpoint_every
    try:
        with torch.inference_mode():
            for window_start in range(start, len(records), interval):
                window_end = min(window_start + interval, len(records))
                with closing(_embedding_batches(records, window_start, window_end,
                                                batch_size, transform, num_workers)) as batches:
                    for batch_start, images in batches:
                        features = model(torch.stack(images).to(target))
                        if output_selector is not None:
                            features = output_selector(features)
                        if (not isinstance(features, torch.Tensor) or features.ndim != 2
                                or features.shape[0] != len(images)):
                            raise ValueError('Model must return [batch, embedding_dim]; supply output_selector for other outputs.')
                        features = features.detach().to(device='cpu', dtype=torch.float32).numpy()
                        if features.shape[1] == 0 or not np.isfinite(features).all():
                            raise ValueError('Embedding vectors must be nonempty and finite.')
                        if result.shape[1] == 0:
                            result = np.empty((len(records), features.shape[1]), dtype=np.float32)
                        if features.shape[1] != result.shape[1]:
                            raise ValueError('Model embedding dimension changed between batches.')
                        result[batch_start:batch_start + len(images)] = features
                save(window_end)
    finally:
        model.train(previous_training)
    return torch.from_numpy(result)


def validate_embedding_checkpoint(output_path, input_path=None, split='train'):
    """Reject partial, changed or reordered raw embeddings before PCA/training."""
    from hest_content_pipeline import _checkpoint_file_hash
    path = Path(output_path).expanduser().resolve()
    checkpoint = path.parent/f'{path.name}.checkpoint.json'
    if not checkpoint.exists():
        raise RuntimeError(f'No completed checkpoint for {path.name}. Run/resume section 6.')
    meta = json.loads(checkpoint.read_text(encoding='utf-8'))
    if not meta.get('complete') or meta['next_position'] != meta['total']:
        raise RuntimeError(f'{path.name} is partial ({meta["next_position"]}/{meta["total"]}). Resume section 6.')
    if not path.is_file() or _checkpoint_file_hash(path) != meta['tensor_sha256']:
        raise ValueError(f'{path.name} does not match its checkpoint. Resume section 6.')
    sidecar = path.with_suffix('.json')
    if not sidecar.is_file() or _checkpoint_file_hash(sidecar) != meta['metadata_sha256']:
        raise ValueError(f'{path.name} metadata does not match its checkpoint. Resume section 6.')
    if input_path is not None:
        records = _ordered_records(input_path, split, verify_files=False)
        if _embedding_record_fingerprint(records) != meta['order_fingerprint']:
            raise ValueError('Embedding patch order/identity differs from the current split.')
    return meta


def _read_genes(expression_path):
    with Path(expression_path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'gene', 'expression'}.issubset(reader.fieldnames or []):
            raise ValueError(f'Expected gene/expression CSV: {expression_path}')
        schema, values = [], []
        for i, row in enumerate(reader):
            index = int(row['gene_index']) if 'gene_index' in row else i
            value = float(row['expression'])
            if index < 0 or not math.isfinite(value):
                raise ValueError(f'Invalid gene index or expression in {expression_path}')
            schema.append({'gene_index': index, 'gene': row['gene']})
            values.append(value)
    if not schema or len({s['gene_index'] for s in schema}) != len(schema):
        raise ValueError(f'Missing or duplicate gene indices in {expression_path}')
    return schema, values


def export_gene_tensor(input_path, output_path, embedding_path, split='train',
                       gene_schema_path=None):
    """Save float32 [N, G, 2]: pair = (gene_index, expression).

    embedding_path: the matching .pt embedding file. Its JSON sidecar is required
        and checked against every patch's identity and order before exporting.
    gene_schema_path: optional train gene tensor's .json sidecar; use for testing
        to enforce the same gene axis in train and test.

    Repeated gene names are kept by gene_index. Every patch must have the exact
    same ordered gene schema; different panels are rejected, never silently
    padded or summed. No expression normalization is performed. Gene names and
    exact patch order are saved in the output's .json sidecar.
    """
    import torch
    records = _ordered_records(input_path, split)
    embedding = Path(embedding_path).expanduser().resolve()
    if not embedding.is_file():
        raise FileNotFoundError(embedding)
    reference = json.loads(embedding.with_suffix('.json').read_text(encoding='utf-8'))
    def identities(rows):
        return [(r['slide_id'], r['patch_name'], r['image_path'], r['expression_path']) for r in rows]
    if reference.get('kind') != 'embeddings' or identities(records) != identities(reference['patches']):
        raise ValueError('Patch order or identity differs from the embedding tensor. Use the same split/list.')
    if reference['shape'][0] != len(records):
        raise ValueError('Embedding patch count does not match.')
    schema = None
    if gene_schema_path is not None:
        schema = json.loads(Path(gene_schema_path).read_text(encoding='utf-8'))['genes']
    result = None
    for i, record in enumerate(records):
        current, values = _read_genes(record['expression_path'])
        if schema is None:
            schema = current
        if current != schema:
            raise ValueError(f"Gene panel/order differs for {record['patch_name']}. "
                             'Use a consistent gene panel across all slides before tensor export.')
        if result is None:
            result = torch.empty((len(records), len(schema), 2), dtype=torch.float32)
        if any(s['gene_index'] > 2**24 for s in schema):
            raise ValueError('Gene indices exceed exact float32 integer range.')
        result[i, :, 0] = torch.tensor([s['gene_index'] for s in schema], dtype=torch.float32)
        result[i, :, 1] = torch.tensor(values, dtype=torch.float32)
        if not torch.isfinite(result[i]).all():
            raise ValueError('Expression values exceed float32 range.')
    _save_tensor(result, output_path, dict(kind='gene_expression', shape=list(result.shape),
                 channels=['gene_index', 'expression'], genes=schema,
                 embedding_path=str(embedding), patches=records))
    return result
