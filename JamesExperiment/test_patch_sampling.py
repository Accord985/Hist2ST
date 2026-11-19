"""Synthetic HDF5 checks: all slides contribute only sampled patch rows."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


class PatchSamplingTests(unittest.TestCase):
    def test_old_settings_and_missing_extraction_fail_before_tensor_loading(self):
        from JamesExperiment.patch_sampling import load_patch_settings, export_sampled_tensors

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'settings.json'
            path.write_text(json.dumps({'sampled_ids': ['NCBI638']}))
            with self.assertRaisesRegex(ValueError, 'Old slide-sampling settings'):
                load_patch_settings(path)
            path.write_text(json.dumps(dict(
                sampling_unit='patch_within_slide', slide_ids=['NCBI638'],
                data_dir=str(root / 'patches'), output_dir=str(root / 'tensors'),
                percentage=7, seed=42, expression_mode='raw',
            )))
            with self.assertRaisesRegex(ValueError, 'Run section 5'):
                export_sampled_tensors(path)

    def test_per_slide_counts_reproducibility_and_barcode_alignment(self):
        import anndata
        import h5py
        import numpy as np
        import pandas as pd
        from hest_download_pipeline import export_slide

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            h5 = root / 'images.h5'
            expression = root / 'expression.h5ad'
            with h5py.File(h5, 'w') as handle:
                handle['img'] = np.zeros((10, 224, 224, 3), dtype=np.uint8)
                handle['barcode'] = np.array([f'b{i}'.encode() for i in range(10)])
            # Reverse expression order to ensure matching uses barcodes.
            data = anndata.AnnData(
                X=np.arange(10, dtype=np.float32)[::-1, None],
                obs=pd.DataFrame(index=[f'b{i}' for i in reversed(range(10))]),
                var=pd.DataFrame(index=['geneA']),
            )
            data.write_h5ad(expression)
            for slide in ('A', 'B'):
                first = export_slide(h5, expression, root / 'first', slide,
                                     patch_percentage=25, sampling_seed=42)
                second = export_slide(h5, expression, root / 'second', slide,
                                      patch_percentage=25, sampling_seed=42)
                self.assertEqual(len(first), 2)
                self.assertEqual(first['patch_index'].tolist(), second['patch_index'].tolist())
                for row in first.to_dict('records'):
                    name = row['patch_name']
                    target = pd.read_csv(root / 'first' / slide / name / f'{name}.csv')
                    self.assertEqual(target['expression'].iloc[0], int(row['barcode'][1:]))
            small = export_slide(h5, expression, root / 'small', 'A', patch_percentage=.01)
            self.assertEqual(len(small), 1)
            marker = json.loads((root / 'small' / 'A' / 'export_complete.json').read_text())
            self.assertEqual(marker['source_patches'], 10)
            self.assertEqual(marker['sampling_unit'], 'patch_within_slide')


if __name__ == '__main__':
    unittest.main()
