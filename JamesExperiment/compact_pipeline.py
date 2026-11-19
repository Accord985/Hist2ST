"""Bounded-memory remote patch sampling and final paired tensor export."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import time


class _PrefetchedFile:
    """Seekable file adapter supplying validated preloaded metadata fragments."""
    def __init__(self, remote):
        self.remote = remote
        self.fragments = {}
        self.starts = []

    def add(self, starts, contents):
        self.fragments.update(zip(starts, contents))
        self.starts = sorted(self.fragments)

    def seek(self, offset, whence=0):
        return self.remote.seek(offset, whence)

    def tell(self):
        return self.remote.tell()

    def read(self, size=-1):
        from bisect import bisect_right
        position = self.tell()
        index = bisect_right(self.starts, position) - 1
        if size >= 0 and index >= 0:
            start = self.starts[index]
            fragment = self.fragments[start]
            offset = position - start
            if offset + size <= len(fragment):
                self.seek(position + size)
                return fragment[offset:offset + size]
        return self.remote.read(size)

    def readinto(self, buffer):
        content = self.read(len(buffer))
        buffer[:len(content)] = content
        return len(content)

    def flush(self):
        pass


def _selected_chunks(dataset, indices):
    """Walk each chunk index once, retaining metadata only for sampled rows."""
    selected = set(indices)
    records = {}
    if hasattr(dataset.id, 'chunk_iter'):
        def visit(chunk):
            if chunk.chunk_offset[0] in selected:
                records[chunk.chunk_offset[0]] = chunk
        dataset.id.chunk_iter(visit)
        return [records[i] for i in indices]
    return [dataset.id.get_chunk_info_by_coord((i,) + (0,) * (dataset.ndim - 1)) for i in indices]


def _prefetch_barcodes(dataset, file_adapter, indices, url, headers, file_size):
    """Prefetch sampled HDF5 vlen references/heaps; HDF5 still decodes strings.

    Only enable for HEST's unfiltered single-string chunks. Validate every
    reference and global-heap signature; otherwise retain the ordinary reader.
    """
    import asyncio
    import struct
    if (dataset.chunks != (1,) * dataset.ndim or dataset.dtype.kind != 'O'
            or dataset.compression or dataset.shuffle or dataset.fletcher32):
        return
    chunks = _selected_chunks(dataset, indices)
    if any(c.byte_offset is None or c.size != 16 for c in chunks):
        return
    references = asyncio.run(_fetch_chunk_ranges(url, headers, [(c.byte_offset, 16) for c in chunks]))
    heaps = set()
    for value in references:
        length, address, object_id = struct.unpack('<IQI', value)
        if not 0 < length < 1024 or not 0 < address < file_size - 16 or not 0 < object_id < 65536:
            return
        heaps.add(address)
    addresses = sorted(heaps)
    contents = asyncio.run(_fetch_chunk_ranges(url, headers,
                          [(address, min(4096, file_size - address)) for address in addresses]))
    if any(content[:4] != b'GCOL' for content in contents):
        return
    file_adapter.add([c.byte_offset for c in chunks], references)
    file_adapter.add(addresses, contents)


async def _fetch_chunk_ranges(url, headers, chunks):
    """Fetch independent, uncompressed HDF5 chunks concurrently, enforcing 206."""
    import asyncio
    import aiohttp
    from yarl import URL
    semaphore = asyncio.Semaphore(12)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
        resolved = None
        async def fetch(chunk, address, auth_headers):
            start, size = chunk
            request_headers = dict(auth_headers, Range=f'bytes={start}-{start + size - 1}')
            for attempt in range(4):
                try:
                    async with semaphore:
                        async with session.get(URL(address, encoded=True), headers=request_headers) as response:
                            if response.status != 206:
                                raise OSError(f'Expected HTTP 206 range response, got {response.status}')
                            content = await response.read()
                            if len(content) != size:
                                raise OSError('Incomplete HTTP range response.')
                            return content, str(response.url)
                except Exception:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 ** attempt)
        first, resolved = await fetch(chunks[0], url, headers)
        # Signed redirected CDN URLs need no bearer token and avoid a redirect
        # round trip for every sampled patch. Never forward tokens cross-host.
        direct_headers = headers if URL(resolved).host == URL(url).host else {}
        rest = await asyncio.gather(*(fetch(chunk, resolved, direct_headers) for chunk in chunks[1:]))
        return [first, *(content for content, _ in rest)]


def _sample_one(job):
    import anndata
    import fsspec
    import h5py
    from huggingface_hub import hf_hub_download, hf_hub_url, get_token
    import numpy as np

    started = time.monotonic()
    slide_id, image_path, expression_path, revision, percentage, seed, output = job
    shard = Path(output) / f'{slide_id}.npz'
    marker = shard.with_suffix('.json')
    expected = dict(slide_id=slide_id, revision=revision, percentage=percentage, seed=seed)
    if shard.is_file() and marker.is_file():
        saved = json.loads(marker.read_text())
        if all(saved.get(k) == v for k, v in expected.items()):
            return saved
        raise ValueError(f'Existing sample settings differ for {slide_id}.')
    token = get_token()
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    url = hf_hub_url('MahmoodLab/hest', image_path, repo_type='dataset', revision=revision)
    # Resolve the signed CDN URL once instead of redirecting every metadata
    # range request through the Hub. Keep credentials on the original host.
    from urllib.parse import urlsplit
    filesystem = fsspec.filesystem('http', headers=headers)
    info = filesystem.info(url)
    direct_url = info.get('url', url)
    direct_headers = headers if urlsplit(direct_url).netloc == urlsplit(url).netloc else {}
    print(f'Sampling {slide_id}', flush=True)
    # Open image headers first; stop if byte range reads are unavailable.
    direct_fs = fsspec.filesystem('http', headers=direct_headers)
    with direct_fs.open(direct_url, mode='rb', block_size=256 * 1024,
                        cache_type='blockcache', cache_options={'maxblocks': 256},
                        size=info['size']) as remote:
        file_adapter = _PrefetchedFile(remote)
        with h5py.File(file_adapter, 'r') as source:
            config = source.id.get_mdc_config()
            config.set_initial_size = True
            config.initial_size = 32 * 1024**2
            config.max_size = 64 * 1024**2
            config.min_size = 16 * 1024**2
            source.id.set_mdc_config(config)
            dataset = source['img']
            if dataset.shape[1:] != (224, 224, 3) or dataset.dtype != np.uint8:
                raise ValueError(f'{slide_id}: invalid image layout {dataset.shape}/{dataset.dtype}')
            total = len(dataset)
            if not total:
                raise ValueError(f'{slide_id}: empty slide.')
            count = max(1, math.floor(total * percentage / 100))
            indices = sorted(random.Random(f'{seed}:{slide_id}').sample(range(total), count))
            def decode(value):
                item = np.asarray(value).reshape(-1)[0]
                return item.decode() if isinstance(item, bytes) else str(item)
            # HEST stores variable-length strings in scattered HDF5 heaps;
            # restrict those reads to selected patches as well.
            barcode_metadata = source['barcode']
            _prefetch_barcodes(barcode_metadata, file_adapter, indices,
                               direct_url, direct_headers, info['size'])
            barcodes = [decode(barcode_metadata[i]) for i in indices]
            if len(set(barcodes)) != count:
                raise ValueError(f'{slide_id}: duplicate sampled barcodes.')
            images = np.empty((count, 224, 224, 3), dtype=np.uint8)
            fast_chunks = (dataset.chunks == (1, 224, 224, 3) and
                           not dataset.compression and not dataset.shuffle and
                           not dataset.fletcher32 and dataset.scaleoffset is None)
            if fast_chunks:
                chunks = _selected_chunks(dataset, indices)
                if any(c.byte_offset is None or c.size != 224 * 224 * 3 for c in chunks):
                    fast_chunks = False
            if not fast_chunks:
                for position, index in enumerate(indices):
                    images[position] = dataset[index]
    if fast_chunks:
        import asyncio
        metadata_seconds = time.monotonic() - started
        contents = asyncio.run(_fetch_chunk_ranges(direct_url, direct_headers, [(c.byte_offset, c.size) for c in chunks]))
        for position, content in enumerate(contents):
            images[position] = np.frombuffer(content, dtype=np.uint8).reshape(224, 224, 3)
        del contents
    else:
        metadata_seconds = None
    image_seconds = time.monotonic() - started
    print(f'{slide_id}: {count} sampled images ready in {image_seconds:.1f}s', flush=True)
    with tempfile.TemporaryDirectory(prefix='james_st_', dir=output) as staging:
        expression = hf_hub_download(
            'MahmoodLab/hest', expression_path, repo_type='dataset', revision=revision,
            local_dir=staging,
        )
        download_seconds = time.monotonic() - started - image_seconds
        data = anndata.read_h5ad(expression, backed='r')
        try:
            if not data.obs_names.is_unique:
                raise ValueError(f'{slide_id}: duplicate expression barcodes.')
            rows = data.obs_names.get_indexer(barcodes)
            if (rows < 0).any():
                raise ValueError(f'{slide_id}: sampled barcodes lack expression rows.')
            names = np.asarray(data.var_names.astype(str).tolist(), dtype=str)
            if any(not name.strip() for name in names):
                raise ValueError(f'{slide_id}: empty gene names.')
            values = np.empty((count, len(names)), dtype=np.float32)
            for position, row in enumerate(rows):
                item = data.X[int(row):int(row) + 1]
                values[position] = (item.toarray() if hasattr(item, 'toarray') else np.asarray(item)).reshape(-1)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f'{slide_id}: invalid count-like expression.')
            # Sum duplicate source features into their named gene instead of
            # discarding shared genes or selecting an arbitrary expression row.
            genes, inverse = np.unique(names, return_inverse=True)
            if len(genes) != len(names):
                merged = np.zeros((count, len(genes)), dtype=np.float32)
                for source_column, gene_column in enumerate(inverse):
                    merged[:, gene_column] += values[:, source_column]
                values = merged
            else:
                values = values[:, np.argsort(names)]
            temporary = shard.with_suffix('.partial')
            with temporary.open('wb') as handle:
                np.savez_compressed(handle, images=images, expression=values,
                                    genes=genes, barcodes=np.asarray(barcodes),
                                    patch_indices=np.asarray(indices),
                                    library_totals=values.sum(axis=1, dtype=np.float64))
            temporary.replace(shard)
            result = dict(**expected, source_patches=total, sampled_patches=count,
                          genes=len(genes), duplicate_features_merged=len(names) - len(genes),
                          metadata_seconds=metadata_seconds,
                          image_seconds=image_seconds, expression_download_seconds=download_seconds,
                          total_seconds=time.monotonic() - started)
            marker.write_text(json.dumps(result, indent=2), encoding='utf-8')
        finally:
            data.file.close()
    print(f'Finished {slide_id}: {count}/{total} patches', flush=True)
    return result


def _sample_retry(job):
    for attempt in range(4):
        try:
            return _sample_one(job)
        except Exception as exc:
            print(f'Retry {job[0]} ({attempt + 1}/4): {type(exc).__name__}', flush=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def prepare_samples(slide_ids, output_dir, percentage=7, seed=42, workers=3, revision='main'):
    from huggingface_hub import HfApi
    from hest_download_pipeline import match_sample_files

    if isinstance(percentage, bool) or not math.isfinite(float(percentage)) or not 0 < float(percentage) <= 100:
        raise ValueError('Percentage must be in (0, 100].')
    ids = list(dict.fromkeys(slide_ids))
    if not ids or any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9-]+', s) for s in ids):
        raise ValueError('Invalid slide IDs.')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    api = HfApi()
    commit = api.repo_info('MahmoodLab/hest', repo_type='dataset', revision=revision).sha
    paths = []
    for folder in ('patches', 'st'):
        paths.extend(x.path for x in api.list_repo_tree('MahmoodLab/hest', path_in_repo=folder,
                     repo_type='dataset', revision=commit, recursive=True) if hasattr(x, 'size'))
    matches = match_sample_files(paths, ids)
    jobs = []
    for slide in ids:
        image = [p for p, owners in matches.items() if slide in owners and p.startswith('patches/') and p.endswith(('.h5', '.hdf5'))]
        expression = [p for p, owners in matches.items() if slide in owners and p.startswith('st/') and p.endswith('.h5ad')]
        if len(image) != 1 or len(expression) != 1:
            raise ValueError(f'{slide}: expected one patch H5 and one expression H5AD.')
        jobs.append((slide, image[0], expression[0], commit, float(percentage), seed, str(output)))
    results, failures = {}, {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(_sample_retry, job): job[0] for job in jobs}
        for future in as_completed(pending):
            slide = pending[future]
            try:
                results[slide] = future.result()
            except Exception as exc:
                failures[slide] = str(exc)
                print(f'FAILED {slide}: {exc}', flush=True)
            print(f'Progress: {len(results)}/{len(ids)} slides; {len(failures)} failed', flush=True)
    (output / 'failures.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')
    if failures:
        raise RuntimeError(f'{len(failures)} slides failed; completed samples are resumable. See {output / "failures.json"}')
    (output / 'sampling_complete.json').write_text(json.dumps(dict(
        complete=True, revision=commit, percentage=float(percentage), seed=seed,
        slides=[results[s] for s in ids],
    ), indent=2), encoding='utf-8')
    return output


def export_samples(settings_path):
    import numpy as np
    import torch
    from .patch_sampling import load_patch_settings
    from .tensor_stream import save_float_tensor, open_batch_tensor

    settings = load_patch_settings(settings_path)
    root = Path(settings['data_dir'])
    completion = json.loads((root / 'sampling_complete.json').read_text())
    ids = settings['slide_ids']
    if (not completion.get('complete') or completion['percentage'] != settings['percentage']
            or completion['seed'] != settings['seed']
            or [s['slide_id'] for s in completion['slides']] != ids):
        raise ValueError('Incomplete or mismatched samples. Rerun section 5.')
    output = Path(settings['output_dir'])
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'experiment.json').exists():
        saved = json.loads((output / 'sampling_settings.json').read_text())
        if saved == settings:
            print('Completed tensors already exist:', output, flush=True)
            return output
        raise ValueError('Output already contains a different experiment.')
    common = None
    total = 0
    has_ensembl = False
    # Early locally generated shards used NumPy object arrays for gene strings.
    # Permit those trusted local shards on resume; new shards use Unicode arrays.
    for slide in ids:
        with np.load(root / f'{slide}.npz', allow_pickle=True) as sample:
            panel = set(sample['genes'].tolist())
            has_ensembl = has_ensembl or any(re.match(r'^ENSG\d+', gene) for gene in panel)
            common = panel if common is None else common & panel
            total += len(sample['patch_indices'])
    mapping = None
    if has_ensembl:
        from .gene_alignment import load_human_gene_map
        mapping = load_human_gene_map(settings.get('gene_annotation_path'))
        common = None
        alignment = []
        for slide in ids:
            with np.load(root / f'{slide}.npz', allow_pickle=True) as sample:
                names = sample['genes'].tolist()
                normalized = mapping.panel(names)
                panel = set(normalized)
                common = panel if common is None else common & panel
                alignment.append(dict(slide_id=slide, source_genes=len(names),
                                      canonical_genes=len(panel), renamed_genes=sum(a != b for a, b in zip(names, normalized))))
        (output / 'gene_alignment.json').write_text(json.dumps(dict(
            source=str(mapping.path), sha256=mapping.sha256, slides=alignment,
        ), indent=2), encoding='utf-8')
    genes = sorted(common)
    if not genes:
        raise ValueError('No shared named genes across the selected cohort.')
    needed = total * (3 * 224 * 224 + len(genes)) * 4
    if needed > shutil.disk_usage(output).free:
        raise OSError(f'Tensors need {needed / 2**30:.2f} GiB free disk space.')
    print(f'Exporting {total} patches, {len(genes)} shared genes; {needed / 2**30:.2f} GiB', flush=True)
    mean = np.array([.697, .575, .728], dtype=np.float32)[None, :, None, None]
    std = np.array([.188, .240, .187], dtype=np.float32)[None, :, None, None]
    def image_batches():
        for slide in ids:
            with np.load(root / f'{slide}.npz', allow_pickle=True) as sample:
                images = sample['images']
                for begin in range(0, len(images), 32):
                    batch = images[begin:begin + 32].transpose(0, 3, 1, 2).astype(np.float32)
                    batch /= 255
                    batch -= mean
                    batch /= std
                    yield batch
            print(f'Image tensor: {slide}', flush=True)
    image_path = output / 'images.pt'
    if not image_path.exists():
        save_float_tensor(image_path, (total, 3, 224, 224), image_batches())
    def target_batches():
        from .gene_alignment import align_columns
        for slide in ids:
            with np.load(root / f'{slide}.npz', allow_pickle=True) as sample:
                values = align_columns(sample['expression'], sample['genes'], genes, mapping)
                if settings['expression_mode'] == 'relative_log_10000':
                    totals = sample['library_totals'][:, None]
                    values = np.log1p(np.divide(values, totals, out=np.zeros_like(values),
                                               where=totals != 0) * 10000)
                yield values
    resume_saved = ((output / 'sampling_settings.json').exists()
                    and (output / 'genes.json').exists()
                    and json.loads((output / 'sampling_settings.json').read_text()) == settings
                    and json.loads((output / 'genes.json').read_text()) == genes)
    if not (resume_saved and (output / 'targets.pt').exists()):
        save_float_tensor(output / 'targets.pt', (total, len(genes)), target_batches())
    with (output / 'patch_manifest.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['order', 'slide_id', 'patch_name', 'patch_index', 'barcode'])
        order = 0
        for slide in ids:
            with np.load(root / f'{slide}.npz', allow_pickle=True) as sample:
                for index, barcode in zip(sample['patch_indices'], sample['barcodes']):
                    writer.writerow([order, slide, f'{slide}_patch_{index:05d}', int(index), str(barcode)])
                    order += 1
    (output / 'genes.json').write_text(json.dumps(genes, indent=2), encoding='utf-8')
    (output / 'sampling_settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
    for name, shape in [('images.pt', (total, 3, 224, 224)), ('targets.pt', (total, len(genes)))]:
        tensor = open_batch_tensor(output / name)
        if tuple(tensor.shape) != shape or not torch.isfinite(tensor[:min(total, 16)]).all():
            raise ValueError(f'Failed saved-tensor verification: {name}')
        del tensor
    (output / 'experiment.json').write_text(json.dumps(dict(
        complete=True, technique='random_patch_sampling', sampling_unit='patch_within_slide',
        patch_percentage=settings['percentage'], seed=settings['seed'], slide_count=len(ids),
        images_shape=[total, 3, 224, 224], targets_shape=[total, len(genes)],
        expression_mode=settings['expression_mode'], duplicate_genes='sum source columns by gene name',
        gene_alignment='HGNC symbols where unambiguous; otherwise source IDs' if mapping else 'source names',
        gene_annotation_sha256=mapping.sha256 if mapping else None,
        dtype='float32', revision=completion['revision'],
    ), indent=2), encoding='utf-8')
    return output
