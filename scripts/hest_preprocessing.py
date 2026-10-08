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


def _ordered_records(input_path, split='train'):
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


def export_embeddings(input_path, model=None, transform=None, output_path=None, batch_size=32,
                      split='train', device=None, output_selector=None):
    """Encode the ordered patches and save one float32 tensor [N, embedding_dim].

    input_path: train.csv/test.csv, their containing folder (use split), or the
        ordered train_paths/test_paths returned by random_split_data.
    model: optional loaded feature extractor; default loads GenBio PathFM.
    transform: optional PIL RGB -> CHW callable; default uses the reference
        PathFM resize/normalization. For other models, pass both arguments.
    output_path: required .pt destination, e.g. train_embeddings.pt.
    output_selector: optional callable selecting/pooling an embedding from model
        outputs. Required for dictionaries, tuples, or token matrices; we never
        guess which output represents a feature vector.
    device: None chooses CUDA when available, otherwise CPU.

    Uses eval/inference mode, never shuffles, and restores the model's prior
    training mode. The model stays on the selected device. CPU RAM must hold the
    final tensor; GPU holds only a batch. A .json sidecar preserves exact order.
    """
    import torch
    from PIL import Image
    if output_path is None:
        raise ValueError('Specify output_path for the embedding .pt tensor.')
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError('batch_size must be a positive integer.')
    records = _ordered_records(input_path, split)
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
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.697, 0.575, 0.728), std=(0.188, 0.240, 0.187)),
        ])
    model.to(target)
    previous_training = model.training
    model.eval()
    result = None
    try:
        with torch.inference_mode():
            for start in range(0, len(records), batch_size):
                rows = records[start:start + batch_size]
                images = []
                for row in rows:
                    with Image.open(row['image_path']) as image:
                        item = transform(image.convert('RGB'))
                    if not isinstance(item, torch.Tensor) or item.ndim != 3:
                        raise ValueError('transform must return a CHW torch tensor.')
                    images.append(item)
                batch = torch.stack(images).to(target)
                features = model(batch)
                if output_selector is not None:
                    features = output_selector(features)
                if not isinstance(features, torch.Tensor) or features.ndim != 2 or features.shape[0] != len(rows):
                    raise ValueError('Model must return [batch, embedding_dim]; supply output_selector for other outputs.')
                features = features.detach().to(device='cpu', dtype=torch.float32)
                if features.shape[1] == 0 or not torch.isfinite(features).all():
                    raise ValueError('Embedding vectors must be nonempty and finite.')
                if result is None:
                    result = torch.empty((len(records), features.shape[1]), dtype=torch.float32)
                if features.shape[1] != result.shape[1]:
                    raise ValueError('Model embedding dimension changed between batches.')
                result[start:start + len(rows)] = features
    finally:
        model.train(previous_training)
    _save_tensor(result, output_path, dict(kind='embeddings', shape=list(result.shape),
                 device_used=str(target), patches=records))
    return result


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
