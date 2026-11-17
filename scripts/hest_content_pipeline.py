"""Cohort selection, download and grouped targets for the HEST Colab pipeline.

Expression target baseline: within-patch relative expression (counts per 10,000),
followed by log1p, matching the general HEST benchmark target convention.
HVG ranking is fit on training patients only to avoid test-set feature leakage.
"""
from pathlib import Path
import csv
import json
import math
import os
import re
import shutil
import tempfile
import hashlib
from collections import Counter
from datetime import datetime, timezone
import pandas as pd

REPO_ID = 'MahmoodLab/hest'


def get_hest_categories(metadata_filename='HEST_v1_3_0.csv', revision='main'):
    """Return valid filter choices to display before the notebook prompts."""
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(REPO_ID, metadata_filename, repo_type='dataset', revision=revision)
    metadata = pd.read_csv(path)
    return {column: sorted(metadata[column].dropna().astype(str).unique().tolist())
            for column in ('organ','species','st_technology')}


def _as_choices(value):
    if value is None or str(value).strip().lower() in ('', 'all', '*'):
        return None
    return [v.strip() for v in str(value).split(',') if v.strip()]


def query_hest_category(organ=None, species=None, st_technology=None,
                        metadata_filename='HEST_v1_3_0.csv', revision='main'):
    """Fetch current HEST metadata and filter by comma-separated exact values."""
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(REPO_ID, metadata_filename, repo_type='dataset', revision=revision)
    metadata = pd.read_csv(path, dtype={'id': str})
    filters = {'organ': organ, 'species': species, 'st_technology': st_technology}
    for column, raw in filters.items():
        choices = _as_choices(raw)
        print(f'{column} options: {", ".join(sorted(metadata[column].dropna().astype(str).unique()))}')
        if choices:
            canonical = {x.casefold(): x for x in metadata[column].dropna().astype(str).unique()}
            unknown = [x for x in choices if x.casefold() not in canonical]
            if unknown:
                raise ValueError(f'Unknown {column}: {unknown}')
            metadata = metadata[metadata[column].astype('string').str.casefold().isin(
                [x.casefold() for x in choices])]
    if metadata.empty:
        raise ValueError('No HEST slides match these filters.')
    return metadata.reset_index(drop=True)


def download_and_clean_cohort(metadata, output_dir, max_workers=2,
                              metadata_filename='HEST_v1_3_0.csv'):
    """Download and clean selected slides through the established HEST helper."""
    from hest_download_pipeline import download_clean_selection
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    ids = metadata['id'].astype(str).tolist()
    metadata.to_csv(output/'selected_metadata.csv', index=False)
    # `download_clean_selection` stages raw H5/H5AD locally, keeping Drive usage
    # to the cleaned files; cleaned folders remain slide/patch organized.
    return download_clean_selection(ids, output, max_workers=max_workers,
                                    metadata_filename=metadata_filename,
                                    staging_dir='/content' if Path('/content').is_dir() else None)


def read_selected_metadata(selection_csv):
    """Read the desired cohort from disk, independent of notebook variables."""
    frame = pd.read_csv(selection_csv, dtype={'id': str})
    if 'id' not in frame or frame.empty or frame['id'].isna().any():
        raise ValueError(f'{selection_csv}: expected a nonempty id column.')
    frame['id'] = frame['id'].str.strip()
    if not frame['id'].map(lambda x: bool(re.fullmatch(r'[A-Za-z0-9-]+', x))).all():
        raise ValueError(f'{selection_csv}: invalid slide IDs.')
    if frame['id'].duplicated().any():
        raise ValueError(f'{selection_csv}: duplicate slide IDs would give an incorrect slide count.')
    return frame.reset_index(drop=True)


def audit_cohort(selection_csv, data_dir, *, reference_metadata=None,
                 verify_contents=False):
    """Compare selected slide IDs and patch-folder counts with saved manifests.

    Completion markers alone are insufficient: whole missing patch folders are
    detected against patch_manifest.csv, and its count is checked against the
    source export's recorded patch count. The default does not inspect files
    inside each patch folder. Content validation is reserved for new downloads
    using verify_contents=True. HEST tissue-spot counts are not assumed to equal
    exported patches. Existing patch contents are trusted after download validation.
    """
    metadata = read_selected_metadata(selection_csv)
    root = Path(data_dir).expanduser().resolve()
    selected_ids = metadata['id'].tolist()
    unknown = (set(selected_ids) - set(reference_metadata['id'].astype(str))
               if reference_metadata is not None else set())
    slide_rows, patch_rows, records = [], [], []
    for slide_id in selected_ids:
        slide = root / slide_id
        issues, expected_count, expected_genes = [], None, None
        if slide_id in unknown:
            slide_rows.append(dict(slide_id=slide_id, status='unknown_id',
                                   expected_patches=None, found_patches=0,
                                   valid_patches=0, issues='ID absent from HEST metadata'))
            continue
        if not slide.exists() or (slide.is_dir() and not any(slide.iterdir())):
            slide_rows.append(dict(slide_id=slide_id, status='missing',
                                   expected_patches=None, found_patches=0,
                                   valid_patches=0, issues='Slide folder is missing or empty'))
            continue
        if not slide.is_dir() or slide.is_symlink():
            slide_rows.append(dict(slide_id=slide_id, status='damaged',
                                   expected_patches=None, found_patches=0,
                                   valid_patches=0, issues='Slide path must be a regular directory'))
            continue
        try:
            marker = json.loads((slide/'export_complete.json').read_text(encoding='utf-8'))
            if not isinstance(marker, dict):
                raise ValueError('Export marker must be a JSON object')
            expected_count = marker['patches']
            expected_genes = marker['genes']
            if (marker.get('slide_id') != slide_id
                    or type(expected_count) is not int or expected_count < 1
                    or type(expected_genes) is not int or expected_genes < 1):
                raise ValueError('Invalid slide ID, patch count or gene count')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append(f'Missing or invalid export marker: {exc}')
            expected_count, expected_genes = None, None
        manifest = {}
        manifest_valid = True
        try:
            with (slide/'patch_manifest.csv').open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            barcodes = set()
            for row in rows:
                name, barcode = row['patch_name'], row['barcode']
                if (not re.fullmatch(re.escape(slide_id)+r'_patch_\d+', name)
                        or row['slide_id'] != slide_id or not barcode
                        or name in manifest or barcode in barcodes):
                    raise ValueError('Invalid or duplicated patch identity')
                manifest[name] = row
                barcodes.add(barcode)
            if not manifest:
                raise ValueError('Empty patch manifest')
            if expected_count is not None and len(manifest) != expected_count:
                issues.append(f'Manifest has {len(manifest)} patches; export expects {expected_count}')
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
            issues.append(f'Missing or invalid patch manifest: {exc}')
            manifest, manifest_valid = {}, False
        # Directory entries usually carry their type, avoiding a separate Drive
        # metadata request per folder and any requests for its patch files.
        with os.scandir(slide) as entries:
            folders = {entry.name: Path(entry.path) for entry in entries
                       if entry.name.startswith(slide_id+'_patch_')
                       and entry.is_dir(follow_symlinks=False)}
        if expected_count is not None and len(folders) != expected_count:
            issues.append(f'Found {len(folders)} patch folders; expected {expected_count}')
        if manifest_valid:
            absent, extra = set(manifest)-set(folders), set(folders)-set(manifest)
            if absent:
                issues.append(f'{len(absent)} patch folders missing')
                patch_rows.extend(dict(slide_id=slide_id, patch_name=n,
                                       reason='Missing patch folder') for n in sorted(absent))
            if extra:
                issues.append(f'{len(extra)} patch folders not in manifest')
                patch_rows.extend(dict(slide_id=slide_id, patch_name=n,
                                       reason='Patch absent from manifest') for n in sorted(extra))
        valid_count = 0
        names = sorted(set(folders) & set(manifest) if manifest_valid else folders)
        for name in names:
            folder = folders[name]
            record = dict(slide_id=slide_id, patch_name=name, patch_dir=str(folder),
                          image_path=str(folder/f'{name}.png'),
                          expression_path=str(folder/f'{name}.csv'),
                          barcode_path=str(folder/'barcode.csv'))
            try:
                if verify_contents:
                    if folder.is_symlink():
                        raise ValueError('Patch folder is a symbolic link')
                    for key in ('image_path', 'expression_path', 'barcode_path'):
                        path = Path(record[key])
                        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                            raise ValueError(f'Missing, empty or linked {key}')
                    from PIL import Image
                    with Image.open(record['image_path']) as image:
                        if image.format != 'PNG' or image.size != (224, 224) or image.mode != 'RGB':
                            raise ValueError('Expected a 224x224 RGB PNG')
                        image.verify()
                    schema, values = read_expression_csv(record['expression_path'])
                    if any(not isinstance(gene, str) or not gene.strip() for _, gene in schema):
                        raise ValueError('Empty gene name')
                    if expected_genes is not None and len(values) != expected_genes:
                        raise ValueError(f'Found {len(values)} genes; expected {expected_genes}')
                    with open(record['barcode_path'], encoding='utf-8-sig', newline='') as f:
                        locations = list(csv.DictReader(f))
                    if (len(locations) != 1 or locations[0].get('slide_id') != slide_id
                            or locations[0].get('patch_name') != name
                            or not locations[0].get('barcode')):
                        raise ValueError('Invalid patch barcode identity')
                    if manifest_valid and locations[0]['barcode'] != manifest[name]['barcode']:
                        raise ValueError('Barcode does not match slide manifest')
                records.append(record)
                valid_count += 1
            except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
                patch_rows.append(dict(slide_id=slide_id, patch_name=name, reason=str(exc)))
        if valid_count != len(names):
            issues.append(f'{len(names)-valid_count} incomplete or unreadable patches')
        if not valid_count:
            issues.append('No usable patches')
        slide_rows.append(dict(slide_id=slide_id, status='damaged' if issues else 'complete',
                               expected_patches=expected_count, found_patches=len(folders),
                               valid_patches=valid_count, issues='; '.join(issues)))
    extras = sorted(p.name for p in root.iterdir() if p.is_dir()
                    and p.name not in selected_ids
                    and ((p/'patch_manifest.csv').exists() or (p/'export_complete.json').exists()
                         or any(p.glob(p.name+'_patch_*')))) if root.is_dir() else []
    return dict(metadata=metadata, slides=pd.DataFrame(slide_rows), records=records,
                patch_issues=pd.DataFrame(patch_rows, columns=['slide_id','patch_name','reason']),
                extra_slide_ids=extras, selected_count=len(selected_ids),
                present_count=sum((root/x).is_dir() and any((root/x).iterdir())
                                  for x in selected_ids))


def checkpoint_cohort(data_dir, run_dir, *, selection_csv=None,
                      metadata_filename='HEST_v1_3_0.csv', reference_metadata=None,
                      verify_contents=False, max_workers=2, input_fn=None,
                      download_fn=None):
    """Audit files on disk and offer missing-slide download/damaged-slide repair.

    Defaults to slide/patch counts only, trusting prior download validation.
    New or replacement downloads always undergo content validation. Returns
    records and active_metadata for subsequent training. A no
    answer preserves existing data; excluded patches/slides are recorded. Repairs
    download into a new folder and validate before archiving the old slide.
    No successful cell execution or in-memory selection variables are required.
    """
    root, run = Path(data_dir).expanduser().resolve(), Path(run_dir).expanduser().resolve()
    run.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    if selection_csv is None:
        candidates = [run/'selected_metadata.csv', run/'download_selection.csv',
                      root/'selected_metadata.csv']
        selection_csv = next((p for p in candidates if p.is_file()), None)
        if selection_csv is None:
            raise FileNotFoundError('No selection CSV found. Set selection_csv to your saved selected_metadata.csv.')
    metadata = read_selected_metadata(selection_csv)
    print(f'Saved selection: {selection_csv} ({len(metadata)} slides)')
    # Use a saved HEST metadata snapshot, or download/cache the public ID table.
    if reference_metadata is None:
        snapshot = run/'hest_reference_metadata.csv'
        if snapshot.is_file():
            reference_metadata = pd.read_csv(snapshot, dtype={'id': str})
        else:
            try:
                from huggingface_hub import hf_hub_download
                path = hf_hub_download(REPO_ID, metadata_filename, repo_type='dataset')
                reference_metadata = pd.read_csv(path, dtype={'id': str})
                reference_metadata.to_csv(snapshot, index=False)
            except Exception as exc:
                print(f'HEST ID lookup unavailable ({exc}); auditing local files and manifests only.')
    audit_args = dict(reference_metadata=reference_metadata, verify_contents=verify_contents)
    audit = audit_cohort(selection_csv, root, **audit_args)
    print(f'Selected slides on disk: {audit["present_count"]}/{audit["selected_count"]}; '
          f'{len(audit["extra_slide_ids"])} unselected slides ignored.')
    print(audit['slides'].to_string(index=False))
    if audit['extra_slide_ids']:
        print('Unselected slide folders:', ', '.join(audit['extra_slide_ids']))
    ask = input if input_fn is None else input_fn
    downloader = download_and_clean_cohort if download_fn is None else download_fn
    actions = []
    for status, question in [('missing', 'Download missing slides'),
                             ('damaged', 'Redownload damaged/incomplete slides')]:
        ids = audit['slides'].loc[audit['slides']['status'] == status, 'slide_id'].tolist()
        if not ids:
            continue
        answer = ask(f'{question} ({len(ids)}): {", ".join(ids)}? [y/N]: ').strip().lower()
        if answer not in ('y', 'yes'):
            actions.extend(dict(slide_id=x, action='left_as_is', error='') for x in ids)
            continue
        for slide_id in ids:
            try:
                if (root/slide_id).is_symlink() or ((root/slide_id).exists() and not (root/slide_id).is_dir()):
                    raise ValueError('Slide destination must be a regular directory')
                with tempfile.TemporaryDirectory(prefix='.hest_repair_', dir=root.parent) as staging:
                    stage = Path(staging)
                    one = metadata[metadata['id'] == slide_id].copy()
                    one.to_csv(stage/'selection_for_verification.csv', index=False)
                    downloader(one, output_dir=stage, max_workers=max_workers,
                               metadata_filename=metadata_filename)
                    fresh = audit_cohort(stage/'selection_for_verification.csv', stage,
                                         reference_metadata=reference_metadata, verify_contents=True)
                    if fresh['slides'].iloc[0]['status'] != 'complete':
                        raise ValueError('New slide failed verification: '+fresh['slides'].iloc[0]['issues'])
                    original = root/slide_id
                    backup = None
                    if original.exists():
                        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                        backup = root.parent/(root.name+'_repair_backups')/stamp/slide_id
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(original), str(backup))
                    try:
                        shutil.move(str(stage/slide_id), str(original))
                    except OSError:
                        if backup is not None and not original.exists():
                            shutil.move(str(backup), str(original))
                        raise
                    actions.append(dict(slide_id=slide_id, action='downloaded' if status == 'missing' else 'repaired',
                                        error='', backup=str(backup) if backup else ''))
                    # Reuse the validated new-slide result. Do not scan the
                    # existing cohort again or repeat reads of patch content.
                    audit['slides'].loc[audit['slides']['slide_id'] == slide_id,
                                        fresh['slides'].columns] = fresh['slides'].iloc[0].values
                    audit['records'] = [r for r in audit['records'] if r['slide_id'] != slide_id]
                    for record in fresh['records']:
                        record = record.copy()
                        for key in ('patch_dir', 'image_path', 'expression_path', 'barcode_path'):
                            record[key] = str(root/Path(record[key]).relative_to(stage))
                        audit['records'].append(record)
                    audit['patch_issues'] = audit['patch_issues'][audit['patch_issues']['slide_id'] != slide_id]
                    if status == 'missing':
                        audit['present_count'] += 1
            except Exception as exc:
                print(f'{slide_id}: download/repair failed: {exc}; existing data preserved.')
                actions.append(dict(slide_id=slide_id, action='failed', error=str(exc)))
    result = audit
    slide_order = {slide_id: i for i, slide_id in enumerate(metadata['id'])}
    result['records'].sort(key=lambda row: (slide_order[row['slide_id']], row['patch_name']))
    active_ids = {r['slide_id'] for r in result['records']}
    result['active_metadata'] = metadata[metadata['id'].isin(active_ids)].copy()
    result['actions'] = pd.DataFrame(actions, columns=['slide_id','action','error','backup'])
    result['slides'].to_csv(run/'checkpoint_slides.csv', index=False)
    result['patch_issues'].to_csv(run/'checkpoint_patch_issues.csv', index=False)
    result['actions'].to_csv(run/'checkpoint_actions.csv', index=False)
    result['active_metadata'].to_csv(run/'active_metadata.csv', index=False)
    write_split_manifest(result['records'], run/'checkpoint_patches.csv')
    print(f'Usable after checkpoint: {len(active_ids)}/{len(metadata)} slides, '
          f'{len(result["records"])} patches. Selection CSV preserved.')
    return result


def create_patient_map(metadata, output_csv):
    """Create slide-to-patient mapping template; returns it for user completion.

    The HEST public table does not guarantee a patient key for all cohorts, so
    this explicit mapping prevents treating slide IDs as patient IDs silently.
    """
    frame = metadata[['id']].drop_duplicates().rename(columns={'id':'slide_id'})
    frame['patient_id'] = ''
    frame.to_csv(output_csv, index=False)
    return frame


def load_patient_map(mapping_csv, slide_ids):
    """Read and validate a filled slide_id,patient_id CSV."""
    with open(mapping_csv, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    mapping = {}
    for row in rows:
        slide, patient = row.get('slide_id','').strip(), row.get('patient_id','').strip()
        if slide in mapping:
            raise ValueError(f'Duplicate slide in patient map: {slide}')
        if slide in slide_ids:
            if not patient:
                raise ValueError(f'Fill in patient_id for slide {slide} in {mapping_csv}')
            mapping[slide] = patient
    missing = set(slide_ids)-set(mapping)
    if missing:
        raise ValueError(f'Patient map is missing slides: {sorted(missing)}')
    return mapping


def read_expression_csv(path):
    """Return ordered (gene_index, gene) schema and source values from patch CSV."""
    schema, values = [], []
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'gene','expression'}.issubset(reader.fieldnames or []):
            raise ValueError(f'Expected gene/expression fields in {path}')
        for i, row in enumerate(reader):
            idx = int(row['gene_index']) if 'gene_index' in row else i
            value = float(row['expression'])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'Expected finite nonnegative count-like values in {path}')
            schema.append((idx, row['gene']))
            values.append(value)
    if not schema or len({i for i,_ in schema}) != len(schema):
        raise ValueError(f'Empty or duplicated gene indices: {path}')
    return schema, values


def discover_patches(data_dir):
    """Return complete slide/patch records in deterministic lexical order."""
    root = Path(data_dir).expanduser().resolve()
    records, skipped = [], []
    for slide in sorted(root.iterdir()):
        if not slide.is_dir():
            continue
        for folder in sorted(slide.iterdir()):
            if not folder.is_dir() or not folder.name.startswith(slide.name+'_patch_'):
                continue
            row = {'slide_id':slide.name, 'patch_name':folder.name,
                   'patch_dir':str(folder), 'image_path':str(folder/f'{folder.name}.png'),
                   'expression_path':str(folder/f'{folder.name}.csv'),
                   'barcode_path':str(folder/'barcode.csv')}
            missing = [k for k in ('image_path','expression_path','barcode_path')
                       if not Path(row[k]).is_file()]
            if missing:
                skipped.append({'patch_dir':str(folder),'missing_fields':missing})
            else:
                records.append(row)
    print(f'Found {len(records)} complete patches; skipped {len(skipped)} incomplete patches.')
    return records, skipped


def patientwise_ordered_split(records, patient_by_slide, train_fraction=0.8):
    """Deterministic patient holdout: lexical patients, no randomization/shuffling."""
    return groupwise_ordered_split(records, patient_by_slide, train_fraction)


def groupwise_ordered_split(records, group_by_slide, train_fraction=0.8):
    """Hold out whole patient or slide groups in lexical order, without shuffling."""
    fraction = float(train_fraction)
    if not 0 < fraction < 1:
        raise ValueError('train_fraction must be between 0 and 1.')
    if any(not isinstance(group_by_slide.get(r['slide_id']), str)
           or not group_by_slide[r['slide_id']].strip() for r in records):
        raise ValueError('Every active slide needs a nonempty group ID.')
    groups = sorted({group_by_slide[r['slide_id']] for r in records})
    if len(groups) < 2:
        raise ValueError('Train/test splitting needs at least two distinct groups.')
    n = math.floor(len(groups)*fraction)
    n = max(1, min(len(groups)-1, n))
    train_groups, test_groups = set(groups[:n]), set(groups[n:])
    # Preserve deterministic slide then patch order within each split.
    train = [r for r in records if group_by_slide[r['slide_id']] in train_groups]
    test = [r for r in records if group_by_slide[r['slide_id']] in test_groups]
    return train, test, sorted(train_groups), sorted(test_groups)


def save_grouped_split(records, group_by_slide, output_dir, *, grouping_unit,
                       train_fraction=0.8):
    """Persist an explicitly chosen patient or slide split and its grouping."""
    if grouping_unit not in ('patient', 'slide'):
        raise ValueError("grouping_unit must be 'patient' or 'slide'.")
    ids = {r['slide_id'] for r in records}
    if grouping_unit == 'slide' and any(group_by_slide.get(s) != s for s in ids):
        raise ValueError('For a slide split, each slide ID must be its own group.')
    train, test, train_groups, test_groups = groupwise_ordered_split(
        records, group_by_slide, train_fraction)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_split_manifest(train, out/'train.csv')
    write_split_manifest(test, out/'test.csv')
    config = dict(grouping_unit=grouping_unit, train_fraction=float(train_fraction),
                  group_by_slide={s: group_by_slide[s] for s in sorted(ids)},
                  train_groups=train_groups, test_groups=test_groups,
                  train_sha256=hashlib.sha256((out/'train.csv').read_bytes()).hexdigest(),
                  test_sha256=hashlib.sha256((out/'test.csv').read_bytes()).hexdigest())
    # Written last so a runtime interruption cannot silently mix split versions.
    (out/'split_config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    return load_grouped_split(out)


def load_grouped_split(output_dir):
    """Restore training state from split files, preserving patch row order."""
    out = Path(output_dir)
    if not all((out/name).is_file() for name in ('train.csv', 'test.csv', 'split_config.json')):
        raise FileNotFoundError(
            'No completed split exists. Run section 4 and choose slide grouping '
            'if patient IDs are unavailable. Then rerun section 5.')
    config = json.loads((out/'split_config.json').read_text(encoding='utf-8'))
    result = dict(config)
    for name in ('train', 'test'):
        path = out/f'{name}.csv'
        if hashlib.sha256(path.read_bytes()).hexdigest() != config[f'{name}_sha256']:
            raise ValueError('Saved split files have changed or are incomplete. Recreate the split in section 4.')
        frame = pd.read_csv(path, dtype=str).fillna('')
        if frame.empty or not {'slide_id', 'patch_name', 'image_path', 'expression_path'}.issubset(frame.columns):
            raise ValueError(f'Invalid or empty split manifest: {path}')
        result[f'{name}_records'] = frame.drop(columns=['order'], errors='ignore').to_dict('records')
    result['records'] = result['train_records'] + result['test_records']
    train_groups = {config['group_by_slide'][r['slide_id']] for r in result['train_records']}
    test_groups = {config['group_by_slide'][r['slide_id']] for r in result['test_records']}
    if (train_groups & test_groups or train_groups != set(config['train_groups'])
            or test_groups != set(config['test_groups'])):
        raise ValueError('Split grouping is inconsistent or shared between train and test. Recreate section 4.')
    return result


def normalize_relative_log(values, scale=10000.0):
    """Per-patch relative expression: log1p(value / row_sum * scale)."""
    import numpy as np
    values = np.asarray(values, dtype=np.float64)
    total = values.sum()
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Relative normalization needs finite nonnegative values.')
    return np.log1p(values/total*scale) if total > 0 else np.zeros_like(values)


def select_top_variable_genes(train_records, patient_by_slide, top_k=50,
                              all_records=None, output_dir=None, grouping_unit='patient',
                              progress_every=1000, sample_fraction=1/3, sampling_seed=42, checkpoint_every=500, checkpoint_mode='resume'):
    """Rank training-group variance using reproducibly sampled training patches.

    sample_fraction=1/3 samples ceil(group_size/3) patches without replacement
    within each training patient/slide (at least one). sampling_seed fixes the
    sample; input manifests and target row order are never changed.

    Sampling mode aligns panels across sampled training patches and one
    representative per selected slide. It assumes other patches use these panels;
    build_target_array still validates selected names in EVERY target patch.
    Only sampled training patches contribute expression statistics. No held-out
    expression values are normalized or used for ranking. Descriptive all-cohort
    variance is unavailable (NaN) in sampling mode. sample_fraction=1 restores
    the original exhaustive panel checks and all-cohort descriptive statistics.

    With output_dir, running sums/counts and provisional variance CSVs are saved
    every checkpoint_every scanned patches. Resume requires unchanged manifests,
    grouping and settings. Start anew if source CSV contents have changed.

    Normalization uses each patch's entire measured panel. Shared, unambiguous
    names define the candidate axis; missing genes are never zero-filled.
    """
    import numpy as np
    if not isinstance(checkpoint_every, int) or isinstance(checkpoint_every, bool) or checkpoint_every < 1:
        raise ValueError('checkpoint_every must be a positive integer.')
    if checkpoint_mode not in ('new', 'resume'):
        raise ValueError("checkpoint_mode must be 'new' or 'resume'.")
    if grouping_unit not in ('patient', 'slide'):
        raise ValueError("grouping_unit must be 'patient' or 'slide'.")
    if top_k < 1: raise ValueError('top_k must be positive.')
    all_records = all_records if all_records is not None else train_records
    reference_names = None
    common_mask = None
    panel_cache = {}
    panel_summary = {}
    all_names, ambiguous_names = set(), set()
    patient_sums, patient_counts = {}, {}
    train_patient_set = {patient_by_slide[r['slide_id']] for r in train_records}
    if not train_records:
        raise ValueError('No training patches available for gene ranking.')
    if not np.isfinite(sample_fraction) or not 0 < sample_fraction <= 1:
        raise ValueError('sample_fraction must be in (0, 1].')
    sampling = sample_fraction < 1
    key = lambda r: (r['slide_id'], r['patch_name'], str(r['expression_path']))
    if len({key(r) for r in train_records}) != len(train_records):
        raise ValueError('Duplicate training patch records are not allowed.')
    groups = {}
    for record in train_records:
        groups.setdefault(patient_by_slide[record['slide_id']], []).append(record)
    rng = np.random.default_rng(sampling_seed)
    sampled_records, sample_summary = [], []
    for group in sorted(groups):
        rows = sorted(groups[group], key=key)
        count = max(1, math.ceil(len(rows) * sample_fraction))
        indices = sorted(rng.choice(len(rows), size=count, replace=False)) if sampling else range(len(rows))
        sampled_records.extend(rows[i] for i in indices)
        sample_summary.append(dict(group_id=group, total_patches=len(rows), sampled_patches=count))
    sampled_keys = {key(r) for r in sampled_records}
    if not sampled_keys.issubset({key(r) for r in all_records}):
        raise ValueError('all_records must contain every sampled training patch.')
    if sampling:
        # Scan the sample plus ONE panel representative per slide, not every CSV.
        representatives = {}
        for record in all_records:
            slide = record['slide_id']
            if slide not in representatives or key(record) < key(representatives[slide]):
                representatives[slide] = record
        scan = {key(r): r for r in sampled_records}
        for record in representatives.values():
            scan.setdefault(key(record), record)
        scan_records = [scan[k] for k in sorted(scan)]
    else:
        scan_records = all_records
    fingerprint = _checkpoint_fingerprint(dict(version=1, normalization='relative_log_10000',
        train=[key(r) for r in train_records], all_records=[key(r) for r in all_records],
        groups=patient_by_slide, grouping_unit=grouping_unit, top_k=top_k,
        sample_fraction=sample_fraction, sampling_seed=sampling_seed))
    restored = _load_gene_checkpoint(output_dir, 'gene_statistics_checkpoint', fingerprint,
                                     checkpoint_mode) if output_dir else None
    start_position = 0
    if restored is not None:
        state, arrays = restored
        start_position = state['next_position']
        if not 0 <= start_position <= len(scan_records):
            raise ValueError('Invalid statistics checkpoint offset. Choose start anew.')
        reference_names = state['reference_names']
        common_mask = arrays['common_mask'].astype(bool) if reference_names is not None else None
        patient_counts = state['patient_counts']
        patient_sums = {p: arrays['patient_sums'][i] for i, p in enumerate(state['patients'])}
        all_names, ambiguous_names = set(state['all_names']), set(state['ambiguous_names'])
        panel_summary = {(s, signature): row for s, signature, row in state['panel_summary']}
        print(f'Resumed gene statistics: {start_position}/{len(scan_records)} patches.', flush=True)
    if output_dir:
        out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
        # Invalidate stale selected genes immediately when starting a new run.
        _atomic_json(out/'gene_selection_complete.json', dict(complete=False, fingerprint=fingerprint))
        pd.DataFrame(sampled_records).to_csv(out/'gene_statistics_sample.csv', index=False)
        pd.DataFrame(sample_summary).to_csv(out/'gene_statistics_sample_summary.csv', index=False)
        (out/'gene_statistics_config.json').write_text(json.dumps(dict(
            sample_fraction=sample_fraction, sampling_seed=sampling_seed,
            total_training_patches=len(train_records), sampled_training_patches=len(sampled_records),
            panel_scan_patches=len(scan_records),
            panel_validation_scope='sample_plus_slide_representatives' if sampling else 'every_patch',
            all_cohort_variance_available=not sampling), indent=2), encoding='utf-8')
    print(f'Gene ranking: {len(sampled_records)}/{len(train_records)} training patches; '
          f'{len(scan_records)} total CSV reads for statistics/panel checks.', flush=True)
    def save_statistics(next_position):
        if not output_dir:
            return
        patients = sorted(patient_sums)
        state = dict(fingerprint=fingerprint, next_position=next_position, total=len(scan_records),
            reference_names=reference_names, patients=patients, patient_counts=patient_counts,
            all_names=sorted(all_names), ambiguous_names=sorted(ambiguous_names),
            panel_summary=[[s, signature, row] for (s, signature), row in panel_summary.items()])
        arrays = dict(common_mask=common_mask if common_mask is not None else np.array([], dtype=bool),
            patient_sums=np.stack([patient_sums[p] for p in patients]) if patients
                         else np.empty((0, len(reference_names or []))))
        def publish():
            _statistics_progress_csv(output_dir, reference_names, common_mask, patient_sums,
                patient_counts, train_patient_set, grouping_unit, next_position, len(scan_records))
        _commit_gene_checkpoint(output_dir, 'gene_statistics_checkpoint', state, arrays, publish)
        print(f'Saved statistics and variance CSV: {next_position}/{len(scan_records)} patches.', flush=True)

    # Persist an empty checkpoint on new runs; repair the provisional CSV on resume.
    save_statistics(start_position)
    for position in range(start_position, len(scan_records)):
        record = scan_records[position]
        schema, values = read_expression_csv(record['expression_path'])
        names = tuple(gene for _, gene in schema)
        if any(not isinstance(gene, str) or not gene.strip() for gene in names):
            raise ValueError(f"Empty gene name at {record['patch_name']}.")
        if reference_names is None:
            counts = Counter(names)
            reference_names = sorted(gene for gene, count in counts.items() if count == 1)
            common_mask = np.ones(len(reference_names), dtype=bool)
        if names not in panel_cache:
            if len(panel_cache) >= 16:
                panel_cache.pop(next(iter(panel_cache)))
            counts = Counter(names)
            unique_positions = {gene: i for i, gene in enumerate(names) if counts[gene] == 1}
            reference_positions = np.asarray([i for i, gene in enumerate(reference_names)
                                              if gene in unique_positions], dtype=np.int64)
            source_positions = np.asarray([unique_positions[reference_names[i]]
                                           for i in reference_positions], dtype=np.int64)
            available = np.zeros(len(reference_names), dtype=bool)
            available[reference_positions] = True
            duplicated = {gene for gene, count in counts.items() if count > 1}
            signature = hashlib.sha256(json.dumps(names, ensure_ascii=False).encode('utf-8')).hexdigest()
            panel_cache[names] = (reference_positions, source_positions, available,
                                  len(unique_positions), duplicated, signature)
            all_names.update(names)
            ambiguous_names.update(duplicated)
        reference_positions, source_positions, available, unique_count, duplicated, signature = panel_cache[names]
        common_mask &= available
        summary_key = (record['slide_id'], signature)
        if summary_key not in panel_summary:
            panel_summary[summary_key] = dict(
                slide_id=record['slide_id'], source_features=len(names),
                unique_gene_names=unique_count, ambiguous_gene_names=len(duplicated), patches=0)
        panel_summary[summary_key]['patches'] += 1
        if not sampling or key(record) in sampled_keys:
            patient=patient_by_slide[record['slide_id']]
            if patient not in patient_sums:
                patient_sums[patient]=np.zeros(len(reference_names),dtype=np.float64)
                patient_counts[patient]=0
            normalized = normalize_relative_log(values)
            patient_sums[patient][reference_positions] += normalized[source_positions]
            patient_counts[patient] += 1
        if progress_every and ((position+1) % progress_every == 0 or position+1 == len(scan_records)):
            print(f'Expression statistics/panels: {position+1}/{len(scan_records)} patches', flush=True)
        if (position+1) % checkpoint_every == 0 or position+1 == len(scan_records):
            save_statistics(position+1)
    if reference_names is None:
        raise ValueError('No expression rows available for gene ranking.')
    kept = np.flatnonzero(common_mask)
    shared_names = [reference_names[i] for i in kept]
    if output_dir:
        out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
        summaries = [dict(row, shared_gene_names=len(shared_names)) for row in panel_summary.values()]
        pd.DataFrame(summaries).to_csv(out/'gene_panel_summary.csv', index=False)
        shared_set = set(shared_names)
        exclusions = [dict(gene=gene, reason='ambiguous_duplicate_name' if gene in ambiguous_names
                            else 'not_present_in_every_scanned_patch') for gene in sorted(all_names-shared_set)]
        pd.DataFrame(exclusions, columns=['gene', 'reason']).to_csv(
            out/'gene_alignment_exclusions.csv', index=False)
        pd.DataFrame({'gene_index':range(len(shared_names)), 'gene':shared_names}).to_csv(
            out/'shared_gene_axis.csv', index=False)
    if not shared_names:
        raise ValueError('No unambiguous gene names are shared across the selected patches. '
                         'Check species and gene identifiers (symbols versus Ensembl IDs).')
    if not train_patient_set.issubset(patient_sums):
        raise ValueError('Ranking records do not include all training groups.')
    print(f'Aligned {len(shared_names)} shared genes across {len(panel_summary)} slide/panel combinations.', flush=True)
    patient_means={p:patient_sums[p][kept]/patient_counts[p] for p in patient_sums}
    train_matrix=np.stack([patient_means[p] for p in sorted(train_patient_set)])
    cohort_matrix=np.stack([patient_means[p] for p in sorted(patient_means)])
    train_var = train_matrix.var(axis=0,ddof=1) if train_matrix.shape[0]>1 else np.zeros(train_matrix.shape[1])
    cohort_var = cohort_matrix.var(axis=0,ddof=1) if cohort_matrix.shape[0]>1 else np.zeros(cohort_matrix.shape[1])
    if sampling:
        cohort_var = np.full_like(train_var, np.nan)
    order = np.argsort(-train_var, kind='stable')[:min(top_k,len(shared_names))]
    train_column = f'train_{grouping_unit}_variance'
    cohort_column = f'all_{grouping_unit}_variance_descriptive'
    selected = [{'gene_index':int(i), 'gene':shared_names[i],
                 train_column:float(train_var[i]),
                 cohort_column:float(cohort_var[i])} for i in order]
    if output_dir:
        out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
        _atomic_write(out/'top_variable_genes.csv', lambda p: pd.DataFrame(selected).to_csv(p,index=False))
        table=pd.DataFrame({'gene_index':range(len(shared_names)), 'gene':shared_names,
                            train_column:train_var,
                            cohort_column:cohort_var})
        table['provisional'] = False
        table['processed_patches'] = len(scan_records)
        table['total_patches'] = len(scan_records)
        _atomic_write(out/'gene_variance_all.csv', lambda p:
            table.sort_values(train_column,ascending=False,kind='stable').to_csv(p,index=False))
        _atomic_json(out/'gene_selection_complete.json', dict(complete=True,
            fingerprint=fingerprint, genes_sha256=_checkpoint_file_hash(out/'top_variable_genes.csv')))
    return selected


def build_target_array(records, selected_genes, progress_every=1000):
    """Align target columns by gene name, preserving the saved patch row order."""
    import numpy as np
    target=np.empty((len(records),len(selected_genes)),dtype=np.float32)
    selected_names=[gene['gene'] for gene in selected_genes]
    if len(set(selected_names)) != len(selected_names):
        raise ValueError('Selected target gene names must be unambiguous and unique.')
    panel_cache = {}
    for i,record in enumerate(records):
        schema,values=read_expression_csv(record['expression_path'])
        names = tuple(gene for _, gene in schema)
        if names not in panel_cache:
            if len(panel_cache) >= 16:
                panel_cache.pop(next(iter(panel_cache)))
            counts = Counter(names)
            missing = [gene for gene in selected_names if counts[gene] == 0]
            ambiguous = [gene for gene in selected_names if counts[gene] > 1]
            if missing or ambiguous:
                raise ValueError(f"Cannot align targets at {record['patch_name']}: "
                                 f'missing genes={missing[:10]}, repeated genes={ambiguous[:10]}. '
                                 'Rerun gene selection if the underlying data changed.')
            positions = {gene: row for row, gene in enumerate(names)}
            panel_cache[names] = [positions[gene] for gene in selected_names]
        normalized=normalize_relative_log(values)
        target[i]=normalized[panel_cache[names]]
        if progress_every and ((i+1) % progress_every == 0 or i+1 == len(records)):
            print(f'Gene targets: {i+1}/{len(records)} patches', flush=True)
    return target


def write_split_manifest(records, output_csv):
    import pandas as pd
    frame=pd.DataFrame(records)
    frame.insert(0,'order',range(len(frame)))
    frame.to_csv(output_csv,index=False)
    return frame


def _checkpoint_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    default=str).encode('utf-8')).hexdigest()


def _atomic_write(path, writer):
    """Write beside the destination so replace stays on the same filesystem."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        writer(Path(temporary))
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def _atomic_json(path, value):
    _atomic_write(path, lambda p: p.write_text(json.dumps(value, indent=2), encoding='utf-8'))


def _checkpoint_file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _load_gene_checkpoint(directory, stem, fingerprint, mode):
    import numpy as np
    if mode not in ('new', 'resume'):
        raise ValueError("checkpoint_mode must be 'new' or 'resume'.")
    path = Path(directory)/f'{stem}.json'
    if mode == 'new' or not path.exists():
        return None
    try:
        meta = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError('Checkpoint manifest is incomplete. Choose start anew.') from exc
    if meta.get('version') != 1 or meta.get('fingerprint') != fingerprint:
        raise ValueError('Checkpoint belongs to different records, genes, grouping or settings. '
                         'Choose start anew or restore the original settings.')
    snapshot = Path(directory)/meta['snapshot']
    if _checkpoint_file_hash(snapshot) != meta['snapshot_sha256']:
        raise ValueError(f'Checkpoint snapshot is incomplete or changed: {snapshot}. Choose start anew.')
    with np.load(snapshot, allow_pickle=False) as stored:
        state = json.loads(str(stored['state'].item()))
        arrays = {name: stored[name].copy() for name in stored.files if name != 'state'}
    if state['fingerprint'] != fingerprint or state['next_position'] != meta['next_position']:
        raise ValueError('Checkpoint state and manifest disagree. Choose start anew.')
    return state, arrays


def _commit_gene_checkpoint(directory, stem, state, arrays, publish=None):
    """Keep the previous snapshot until the new snapshot/output/manifest commit."""
    import numpy as np
    directory = Path(directory)
    manifest = directory/f'{stem}.json'
    try:
        previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    except json.JSONDecodeError:
        previous = {}
    previous_slot = previous.get('slot')
    slot = 1 - previous_slot if previous_slot in (0, 1) else 0
    snapshot = directory/f'{stem}.{slot}.npz'
    def write_snapshot(path):
        with path.open('wb') as handle:
            np.savez_compressed(handle, state=np.asarray(json.dumps(state)), **arrays)
    _atomic_write(snapshot, write_snapshot)
    published = publish() if publish else {}
    meta = dict(version=1, fingerprint=state['fingerprint'], slot=slot,
                snapshot=snapshot.name, snapshot_sha256=_checkpoint_file_hash(snapshot),
                next_position=state['next_position'], total=state['total'],
                complete=state['next_position'] == state['total'])
    meta.update(published or {})
    _atomic_json(manifest, meta)


def prompt_checkpoint_mode(stage):
    """Notebook prompt; library functions themselves never block for input."""
    while True:
        choice = input(f'{stage}: [1] start anew, [2] resume checkpoints: ').strip().lower()
        if choice in ('1', 'new', 'start anew'):
            return 'new'
        if choice in ('2', 'resume'):
            return 'resume'
        print('Enter 1 or 2.')


def _statistics_progress_csv(out, reference_names, common_mask, sums, counts,
                             train_groups, grouping_unit, processed, total):
    """Provisional variance across the training groups observed so far."""
    import numpy as np
    names = reference_names or []
    kept = np.flatnonzero(common_mask) if common_mask is not None else np.array([], dtype=int)
    observed = sorted(p for p in train_groups if counts.get(p, 0))
    if len(observed) >= 2:
        means = np.stack([sums[p][kept]/counts[p] for p in observed])
        variance = means.var(axis=0, ddof=1)
    else:
        variance = np.full(len(kept), np.nan)
    table = pd.DataFrame(dict(gene_index=range(len(kept)), gene=[names[i] for i in kept],
        **{f'train_{grouping_unit}_variance': variance},
        processed_patches=processed, total_patches=total,
        observed_training_groups=len(observed), required_training_groups=len(train_groups),
        provisional=True))
    table = table.sort_values(f'train_{grouping_unit}_variance', ascending=False, kind='stable')
    _atomic_write(Path(out)/'gene_variance_all.csv', lambda p: table.to_csv(p, index=False))


def load_selected_genes(output_dir):
    """Restore finalized genes without rerunning selection or earlier notebook cells."""
    out = Path(output_dir)
    marker = out/'gene_selection_complete.json'
    if not marker.exists():
        raise RuntimeError('No completed gene selection. Run section 5a first.')
    complete = json.loads(marker.read_text(encoding='utf-8'))
    progress = out/'gene_statistics_checkpoint.json'
    if not complete.get('complete') or not progress.exists():
        raise RuntimeError('Gene selection is incomplete. Resume section 5a.')
    state = json.loads(progress.read_text(encoding='utf-8'))
    if not state.get('complete') or state['fingerprint'] != complete['fingerprint']:
        raise RuntimeError('Gene-selection checkpoint and selected genes disagree. Resume section 5a.')
    path = out/'top_variable_genes.csv'
    if _checkpoint_file_hash(path) != complete['genes_sha256']:
        raise ValueError('Selected gene file changed. Rerun gene selection.')
    return pd.read_csv(path).to_dict('records')


def _publish_target_prefix(path, prefix):
    import torch
    # Save a plain CPU tensor, compatible with existing training code.
    def write(destination):
        with destination.open('wb') as handle:
            torch.save(torch.from_numpy(prefix.copy()), handle)
    _atomic_write(path, write)


def save_target_tensor(records, selected_genes, output_path, *, checkpoint_every=500,
                       checkpoint_mode='resume'):
    """Save/resume ordered normalized targets, overwriting the .pt every 500 rows.

    The .pt is a PREFIX until complete. Sidecar .json/.npz files retain the exact
    manifest/ordered-gene fingerprint and numeric prefix for interruption recovery.
    Resume reads only remaining expression CSVs. No images or GPU are required.
    """
    import numpy as np
    if not isinstance(checkpoint_every, int) or isinstance(checkpoint_every, bool) or checkpoint_every < 1:
        raise ValueError('checkpoint_every must be a positive integer.')
    names = [g['gene'] for g in selected_genes]
    if not names or len(set(names)) != len(names):
        raise ValueError('Selected target gene names must be nonempty and unique.')
    path = Path(output_path)
    stem = f'{path.name}.checkpoint'
    fingerprint = _checkpoint_fingerprint(dict(version=1, normalization='relative_log_10000',
        records=[(r['slide_id'], r['patch_name'], str(r['expression_path'])) for r in records], genes=names))
    restored = _load_gene_checkpoint(path.parent, stem, fingerprint, checkpoint_mode)
    target = np.empty((len(records), len(names)), dtype=np.float32)
    start = 0
    if restored is not None:
        state, arrays = restored
        start = state['next_position']
        prefix = arrays['targets']
        if prefix.shape != (start, len(names)) or not 0 <= start <= len(records):
            raise ValueError('Invalid target checkpoint dimensions. Choose start anew.')
        target[:start] = prefix
        print(f'Resumed {path.name}: {start}/{len(records)} patches.', flush=True)
    else:
        print(f'Starting {path.name}: {len(records)} patches.', flush=True)

    def save(next_position):
        state = dict(fingerprint=fingerprint, next_position=next_position, total=len(records))
        def publish():
            _publish_target_prefix(path, target[:next_position])
            return dict(shape=[next_position, len(names)],
                        tensor_sha256=_checkpoint_file_hash(path))
        _commit_gene_checkpoint(path.parent, stem, state,
                                dict(targets=target[:next_position]), publish)
        print(f'Saved {path.name}: {next_position}/{len(records)} patches.', flush=True)

    # Reconcile a .pt that was ahead of/behind the committed manifest at disconnect.
    save(start)
    for begin in range(start, len(records), checkpoint_every):
        end = min(begin + checkpoint_every, len(records))
        target[begin:end] = build_target_array(records[begin:end], selected_genes, progress_every=0)
        save(end)
    return path


def validate_target_checkpoint(output_path, records=None, selected_genes=None):
    """Reject partial or replaced targets before model training."""
    path = Path(output_path)
    meta_path = path.parent/f'{path.name}.checkpoint.json'
    if not meta_path.exists():
        raise RuntimeError(f'No completion checkpoint for {path.name}. Run/resume section 5b.')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    if not meta.get('complete') or meta['next_position'] != meta['total']:
        raise RuntimeError(f'{path.name} is partial ({meta["next_position"]}/{meta["total"]}). Resume section 5b.')
    if records is not None and selected_genes is not None:
        expected = _checkpoint_fingerprint(dict(version=1, normalization='relative_log_10000',
            records=[(r['slide_id'], r['patch_name'], str(r['expression_path'])) for r in records],
            genes=[g['gene'] for g in selected_genes]))
        if meta['fingerprint'] != expected:
            raise ValueError(f'{path.name} belongs to different patch order or genes. Run section 5b.')
    if not path.exists() or _checkpoint_file_hash(path) != meta['tensor_sha256']:
        raise ValueError(f'{path.name} does not match its checkpoint. Resume section 5b.')
    return meta
