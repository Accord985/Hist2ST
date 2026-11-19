"""Annotated patient-grouped heatmaps of the saved shared-gene target tensor."""
from collections import defaultdict
import base64
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

CANCER_COLORS = {
    'Cancer': '#bf3549', 'Healthy / no cancer annotation': '#238a83',
    'Tumor / malignancy unspecified': '#d49a26',
    'Unknown / not specified': '#8d96a8', 'Mixed': '#835bb1',
}
DISEASE_COLORS = {'Cancer': '#bf3549', 'Healthy': '#238a83', 'Tumor': '#d49a26',
                  'Diseased': '#7787ab', 'Treated': '#9267a8', 'Unknown': '#c3c8d1', 'Mixed': '#343c50'}


def cancer_annotation(state):
    """Use explicit slide metadata; do not infer malignancy from 'Diseased'."""
    return {'cancer': 'Cancer', 'healthy': 'Healthy / no cancer annotation',
            'tumor': 'Tumor / malignancy unspecified'}.get(
                str(state).strip().casefold(), 'Unknown / not specified')


def build_annotations(manifest, metadata, patient_map_path=None):
    """Scope known patient IDs to their dataset; keep unknown slides separate."""
    metadata = metadata.copy().fillna('')
    for column in metadata:
        metadata[column] = metadata[column].astype(str).str.strip()
    if metadata['id'].duplicated().any():
        raise ValueError('Duplicate slide IDs in metadata.')
    if manifest['order'].tolist() != list(range(len(manifest))):
        raise ValueError('Manifest must preserve consecutive original tensor row order.')
    missing = set(manifest['slide_id']) - set(metadata['id'])
    if missing:
        raise ValueError(f'Metadata missing for slides: {sorted(missing)}')
    overrides = {}
    if patient_map_path:
        mapping = pd.read_csv(patient_map_path, dtype=str).fillna('')
        if not {'slide_id', 'patient_id'}.issubset(mapping):
            raise ValueError('Patient map needs slide_id and patient_id columns.')
        if mapping.slide_id.duplicated().any():
            raise ValueError('Duplicate slides in patient map.')
        overrides = dict(zip(mapping.slide_id.str.strip(), mapping.patient_id.str.strip()))
    slides = metadata[metadata['id'].isin(manifest['slide_id'])].copy()
    group_keys, known, patients = [], [], []
    placeholders = {'', 'unknown', 'nan', 'none', 'n/a', 'na', 'not available', 'not reported'}
    for row in slides.to_dict('records'):
        patient = overrides.get(row['id'], '')
        if patient.casefold() not in placeholders:
            key = 'manual::' + patient
            is_known = True
        else:
            patient = row.get('patient', '')
            is_known = patient.casefold() not in placeholders
            # Labels such as 'Patient 1' from unrelated studies must not merge.
            study = row.get('dataset_title', '') or row.get('study_link', '') or row['id']
            key = ('metadata::' + study + '::' + patient.casefold()
                   if is_known else 'unknown_slide::' + row['id'])
        group_keys.append(key)
        known.append(is_known)
        patients.append(patient if is_known else '')
    slides['patient_group_key'] = group_keys
    slides['patient_id_known'] = known
    slides['patient_id'] = patients
    slides['cancer_annotation'] = slides['disease_state'].map(cancer_annotation)
    slides['disease_state'] = slides.disease_state.replace('', 'Unknown')
    slides['organ'] = slides.organ.replace('', 'Unknown')
    slides['tissue'] = slides.tissue.replace('', 'Unknown')
    ordering = slides.groupby('patient_group_key', sort=False).agg(
        first_organ=('organ', 'min'), study=('dataset_title', 'min'),
        patient=('patient_id', 'min'), slide=('id', 'min'), known=('patient_id_known', 'first'),
    ).sort_values(['first_organ', 'study', 'patient', 'slide'], kind='stable')
    labels, ranks = {}, {}
    pcount = scount = 0
    for rank, (key, row) in enumerate(ordering.iterrows()):
        if row['known']:
            pcount += 1
            code = f'P{pcount:03d}'
            label = f'{code} | {row["patient"]}'
        else:
            scount += 1
            code = f'S{scount:03d}'
            label = f'{code} | {row["slide"]} (ID unknown)'
        labels[key] = (code, label)
        ranks[key] = rank
    slides['group_code'] = slides.patient_group_key.map(lambda key: labels[key][0])
    slides['patient_label'] = slides.patient_group_key.map(lambda key: labels[key][1])
    slides['group_rank'] = slides.patient_group_key.map(ranks)
    columns = ['id', 'patient_group_key', 'patient_id_known', 'patient_id', 'patient_label',
               'group_code', 'group_rank', 'organ', 'tissue', 'disease_state',
               'cancer_annotation', 'dataset_title', 'oncotree_code']
    annotations = manifest.rename(columns={'order': 'tensor_row'}).merge(
        slides[columns], left_on='slide_id', right_on='id', how='left', validate='many_to_one', sort=False)
    annotations = annotations.sort_values(['group_rank', 'slide_id', 'tensor_row'], kind='stable').reset_index(drop=True)
    annotations.insert(0, 'heatmap_column', np.arange(1, len(annotations) + 1))
    groups = []
    join = lambda values: ' | '.join(dict.fromkeys(str(value) for value in values))
    for key, frame in annotations.groupby('patient_group_key', sort=False):
        groups.append(dict(
            group_code=frame.group_code.iloc[0], patient_label=frame.patient_label.iloc[0],
            patient_id=frame.patient_id.iloc[0], patient_id_known=bool(frame.patient_id_known.iloc[0]),
            start_index_0based=int(frame.index[0]), end_index_0based_exclusive=int(frame.index[-1] + 1),
            start_column_1based=int(frame.heatmap_column.iloc[0]),
            end_column_1based_inclusive=int(frame.heatmap_column.iloc[-1]), patch_count=len(frame),
            slide_ids=join(frame.slide_id), organs=join(frame.organ), tissues=join(frame.tissue),
            disease_states=join(frame.disease_state), cancer_annotations=join(frame.cancer_annotation),
            dataset_title=join(frame.dataset_title),
        ))
    boundaries = pd.DataFrame(groups)
    if boundaries.patch_count.sum() != len(manifest) or annotations.tensor_row.duplicated().any():
        raise ValueError('Reordering lost or duplicated expression rows.')
    return slides, annotations.drop(columns=['id']), boundaries


def expression_colors(expression):
    logged = np.log1p(expression.astype(np.float64))
    means, stds = logged.mean(axis=0), logged.std(axis=0)
    z = np.divide(logged - means, stds, out=np.zeros_like(logged), where=stds > 0)
    if not np.isfinite(z).all():
        raise ValueError('Nonfinite display values.')
    return z.astype(np.float32), means, stds


def _colors(names, cmap_name='tab20'):
    from matplotlib import colormaps
    names = sorted(set(names))
    cmap = colormaps[cmap_name]
    from matplotlib.colors import to_hex
    return {name: to_hex(cmap(index / max(1, len(names) - 1))) for index, name in enumerate(names)}


def _track_image(ax, values, colors, label):
    from matplotlib.colors import to_rgb
    rgb = np.array([to_rgb(colors.get(value, '#adb4c1')) for value in values])[None, :, :]
    ax.imshow(rgb, aspect='auto', interpolation='nearest')
    ax.set_yticks([0], [label], fontsize=8)
    ax.set_xticks([])
    ax.tick_params(axis='y', length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _draw_plot(z, genes, tracks, patient_positions, labels, title, destination, organ_colors,
               note, width_pixels=4200, patient_key=None, tissue_colors=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    fig = plt.figure(figsize=(width_pixels / 160, 10.8), dpi=160, facecolor='white')
    axes = [fig.add_axes([.06, .905 - i * .023, .88, .016]) for i in range(4)]
    _track_image(axes[0], tracks['organ'], organ_colors, 'Organ')
    _track_image(axes[1], tracks['tissue'], tissue_colors, 'Tissue')
    _track_image(axes[2], tracks['disease'], DISEASE_COLORS, 'Disease')
    _track_image(axes[3], tracks['cancer'], CANCER_COLORS, 'Cancer status')
    bottom = .36 if patient_key else .25
    ax = fig.add_axes([.06, bottom, .88, .818 - bottom])
    image = ax.imshow(z.T, cmap='RdBu_r', vmin=-2.5, vmax=2.5, aspect='auto', interpolation='nearest')
    ax.set_yticks(np.arange(len(genes)), genes, fontsize=8)
    overview = len(labels) > 50
    ax.set_xticks([item[2] for item in patient_positions], labels,
                  rotation=90 if overview else 60, ha='center' if overview else 'right',
                  fontsize=5.5 if overview else 7)
    ax.tick_params(axis='both', length=2)
    if overview:
        ax.set_xlabel('Contiguous patient groups; S codes indicate missing patient ID', fontsize=9)
    for start, end, _ in patient_positions:
        for boundary in (start - .5, end - .5):
            ax.axvline(boundary, color='white', linewidth=1.1, alpha=.9)
            for track in axes:
                track.axvline(boundary, color='white', linewidth=.65)
    cax = fig.add_axes([.954, bottom, .008, .818 - bottom])
    fig.colorbar(image, cax=cax, label='Per-gene z-score of log1p(raw expression)', ticks=[-2.5, 0, 2.5])
    footer = fig.add_axes([.06, .025, .88, .105])
    footer.axis('off')
    handles = [Patch(color=color, label='Mixed organs' if label == 'Mixed' else label)
               for label, color in organ_colors.items()]
    handles += [Patch(color=color, label='Mixed cancer annotations' if label == 'Mixed' else label)
                for label, color in CANCER_COLORS.items() if label != 'Mixed' or 'Mixed' in set(tracks['cancer'])]
    handles += [Patch(color=DISEASE_COLORS.get(label, '#adb4c1'), label=f'Disease: {label}')
                for label in dict.fromkeys(tracks['disease'])]
    footer.legend(handles=handles, ncol=7, loc='upper left', frameon=False, fontsize=7)
    if patient_key:
        lines_per_column = math.ceil(len(patient_key) / 2)
        for index, line in enumerate(patient_key):
            fig.text(.06 + .45 * (index // lines_per_column),
                     .226 - .011 * (index % lines_per_column), line, fontsize=7, color='#35465f')
    fig.text(.06, .012, note, fontsize=8, va='bottom')
    fig.suptitle(title, x=.06, y=.972, ha='left', fontsize=16, fontweight='bold', color='#17263d')
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def create_heatmaps(tensor_dir, metadata_csv, output_dir, patients_per_page=16, patient_map_path=None):
    import torch
    from matplotlib import colormaps
    from .heatmap_viewer import write_viewer
    tensor_dir, output = Path(tensor_dir), Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    complete = json.loads((tensor_dir / 'experiment.json').read_text())
    if not complete.get('complete'):
        raise ValueError('Tensor export is not complete.')
    target_path = tensor_dir / 'targets.pt'
    target = torch.load(target_path, map_location='cpu', weights_only=True).numpy()
    genes = json.loads((tensor_dir / 'genes.json').read_text())
    manifest = pd.read_csv(tensor_dir / 'patch_manifest.csv')
    metadata = pd.read_csv(metadata_csv, dtype=str).fillna('')
    if target.shape != (len(manifest), len(genes)) or not np.isfinite(target).all() or (target < 0).any():
        raise ValueError('Invalid or misaligned gene tensor.')
    slides, ordered, boundaries = build_annotations(manifest, metadata, patient_map_path)
    raw = np.ascontiguousarray(target[ordered.tensor_row.to_numpy()])
    z, log_mean, log_std = expression_colors(raw)
    slides.to_csv(output / 'slide_annotations.csv', index=False)
    ordered.to_csv(output / 'patch_annotations.csv', index=False)
    boundaries.to_csv(output / 'patient_boundaries.csv', index=False)
    pd.DataFrame(dict(gene=genes, log1p_mean=log_mean, log1p_std=log_std,
                      raw_mean=raw.mean(axis=0), raw_min=raw.min(axis=0), raw_max=raw.max(axis=0))).to_csv(
                          output / 'gene_display_statistics.csv', index=False)
    organ_colors = _colors([*ordered.organ.unique(), 'Mixed'])
    import colorsys
    from matplotlib.colors import to_hex
    tissue_colors = {}
    for tissue in [*ordered.tissue.unique(), 'Mixed']:
        hue = 0
        for letter in tissue:
            hue = (hue * 31 + ord(letter)) & 0xffffffff
        tissue_colors[tissue] = to_hex(colorsys.hls_to_rgb((hue % 360) / 360, .61, .48))
    summarize = lambda values: values.iloc[0] if values.nunique() == 1 else 'Mixed'
    track_rows = ordered.groupby('group_rank', sort=False).agg(
        organ=('organ', summarize), tissue=('tissue', summarize),
        disease=('disease_state', summarize), cancer=('cancer_annotation', summarize))
    means = np.stack([z[row.start_index_0based:row.end_index_0based_exclusive].mean(axis=0)
                      for row in boundaries.itertuples()])
    overview = output / 'patient_mean_overview.png'
    _draw_plot(means, genes, track_rows, [(i, i + 1, i) for i in range(len(boundaries))],
               boundaries.group_code.tolist(), 'Shared gene expression | patient-group overview', overview,
               organ_colors, 'Each column is the mean of sampled patches in one group. '
               'Cancer status is slide metadata, not a patch-level tumor prediction.',
               width_pixels=6400, tissue_colors=tissue_colors)
    pages = output / 'patient_pages'
    pages.mkdir(exist_ok=True)
    page_files = []
    for page, start_group in enumerate(range(0, len(boundaries), patients_per_page), 1):
        groups = boundaries.iloc[start_group:start_group + patients_per_page]
        start, end = int(groups.start_index_0based.iloc[0]), int(groups.end_index_0based_exclusive.iloc[-1])
        frame = ordered.iloc[start:end]
        tracks = dict(organ=frame.organ.tolist(), tissue=frame.tissue.tolist(),
                      disease=frame.disease_state.tolist(), cancer=frame.cancer_annotation.tolist())
        positions = [(int(row.start_index_0based - start), int(row.end_index_0based_exclusive - start),
                      (row.start_index_0based + row.end_index_0based_exclusive - 1) / 2 - start)
                     for row in groups.itertuples()]
        destination = pages / f'patient_page_{page:02d}.png'
        _draw_plot(z[start:end], genes, tracks, positions, groups.patient_label.tolist(),
                   f'Shared gene expression | page {page} | patch columns {start + 1:,}–{end:,}',
                   destination, organ_colors,
                   'White lines mark group starts/ends. P = dataset-scoped patient; S = unknown patient, separate slide. '
                   'Exact tissue and disease labels: patient_boundaries.csv / interactive heatmap.',
                   width_pixels=max(4400, end - start + 700), tissue_colors=tissue_colors,
                   patient_key=[f'{row.group_code}: {row.organs} / {row.tissues[:140]} / {row.disease_states}'
                                for row in groups.itertuples()])
        page_files.append(str(destination))
        print(f'Rendered patient page {page}: {len(groups)} groups, {end - start:,} patches', flush=True)
    slide_ranges = []
    for slide_id, frame in ordered.groupby('slide_id', sort=False):
        first = frame.iloc[0]
        if frame.index[-1] - frame.index[0] + 1 != len(frame):
            raise ValueError('Slide columns are not contiguous.')
        slide_ranges.append(dict(start=int(frame.index[0]), end=int(frame.index[-1] + 1),
                                 slide_id=slide_id, organ=first.organ, tissue=first.tissue,
                                 disease=first.disease_state, cancer=first.cancer_annotation,
                                 patient=first.patient_label, patient_known=bool(first.patient_id_known),
                                 study=first.dataset_title))
    payload = dict(genes=genes, patches=len(raw), log_mean=log_mean.tolist(), log_std=log_std.tolist(),
                   expression_b64=base64.b64encode(np.ascontiguousarray(raw.T, dtype='<f4').tobytes()).decode(),
                   patients=boundaries.to_dict('records'), slides=slide_ranges,
                   organ_colors=organ_colors, disease_colors=DISEASE_COLORS, cancer_colors=CANCER_COLORS,
                   palette=(colormaps['RdBu_r'](np.linspace(0, 1, 256))[:, :3] * 255).astype(int).tolist())
    write_viewer(output / 'gene_expression_heatmap.html', payload)
    summary = dict(
        complete=True, patches=len(raw), genes=len(genes), slides=len(slides),
        known_patient_groups=int(boundaries.patient_id_known.sum()),
        unknown_patient_slide_groups=int((~boundaries.patient_id_known).sum()),
        slides_with_known_patient=int(slides.patient_id_known.sum()),
        page_count=len(page_files), patients_per_page=patients_per_page,
        color_scale='per-gene z-score of log1p(raw expression), clipped at +/-2.5',
        patient_scope='dataset title + patient ID; missing patient ID remains a separate slide',
        cancer_policy='Cancer=yes; Healthy=no cancer annotation; Tumor=malignancy unspecified; Diseased/Treated=unknown',
        target_sha256=hashlib.sha256(target_path.read_bytes()).hexdigest(),
        source_tensor_dir=str(tensor_dir.resolve()),
    )
    (output / 'heatmap_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
    return summary
