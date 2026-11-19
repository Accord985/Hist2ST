"""Small synthetic checks; no real patient data or model downloads."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .slide_sampling import export_tensors, sample_slides, sample_slide_ids


class SamplingTests(unittest.TestCase):
    def test_metadata_sampling_needs_no_slide_files(self):
        with patch.object(Path, 'iterdir', side_effect=AssertionError('Unexpected disk scan')):
            selected = sample_slide_ids(['D', 'B', 'A', 'C'], 25, 42)
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected, sample_slide_ids(['A', 'B', 'C', 'D'], 25, 42))
        with self.assertRaises(ValueError):
            sample_slide_ids(['A'], 1)

    def test_unsampled_slides_are_never_inspected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ids = ['A', 'B', 'C', 'D']
            chosen = sample_slide_ids(ids, 25, 42)
            name = f'{chosen[0]}_patch_0'
            folder = root / chosen[0] / name
            folder.mkdir(parents=True)
            for filename in (f'{name}.png', f'{name}.csv', 'barcode.csv'):
                (folder / filename).touch()
            # All unsampled slides are absent: selection must still succeed.
            records, eligible, selected = sample_slides(root, 25, 42, slide_ids=ids)
            self.assertEqual(selected, chosen)
            self.assertEqual(eligible, ids)
            self.assertEqual(len(records), 1)

    def test_slide_sampling_keeps_all_patches_and_repeats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for slide in ('A', 'B', 'C', 'D'):
                for number in range(2):
                    name = f'{slide}_patch_{number}'
                    patch = root / slide / name
                    patch.mkdir(parents=True)
                    for filename in (f'{name}.png', f'{name}.csv', 'barcode.csv'):
                        (patch / filename).touch()
            first = sample_slides(root, 50, 42)
            self.assertEqual(first, sample_slides(root, 50, 42))
            self.assertEqual(len(first[2]), 2)
            self.assertEqual(len(first[0]), 4)
            limited = sample_slides(root, 100, 42, slide_ids=['A', 'C'])
            self.assertEqual(limited[1], ['A', 'C'])
            self.assertEqual(limited[2], ['A', 'C'])
            self.assertEqual({r['slide_id'] for r in limited[0]}, {'A', 'C'})
            with self.assertRaises(ValueError):
                sample_slides(root, 100, slide_ids=['missing'])
            with self.assertRaises(ValueError):
                sample_slides(root, 1)
            Path(first[0][0]['image_path']).unlink()
            with self.assertRaises(FileNotFoundError):
                sample_slides(root, 50, 42)

    def test_image_target_alignment_and_shared_gene_axis(self):
        import torch
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'data'
            for slide, expression, color in (
                ('A', 'gene,expression\nz,9\na,1\nonly_a,5\n', 'red'),
                ('B', 'gene,expression\na,2\nz,8\nonly_b,4\n', 'blue'),
            ):
                name = f'{slide}_patch_0'
                patch = root / slide / name
                patch.mkdir(parents=True)
                Image.new('RGB', (12, 12), color).save(patch / f'{name}.png')
                (patch / f'{name}.csv').write_text(expression)
                (patch / 'barcode.csv').write_text('barcode\nspot0\n')
            out = export_tensors(root, Path(temporary) / 'output', 100)
            images = torch.load(out / 'images.pt', weights_only=True)
            targets = torch.load(out / 'targets.pt', weights_only=True)
            self.assertEqual(json.loads((out / 'genes.json').read_text()), ['a', 'z'])
            torch.testing.assert_close(targets, torch.tensor([[1., 9.], [2., 8.]]))
            self.assertEqual(tuple(images.shape), (2, 3, 224, 224))
            self.assertAlmostEqual(images[0, 0, 0, 0].item(), (1 - .697) / .188, places=5)
            normalized = export_tensors(root, Path(temporary) / 'normalized', 100,
                                        expression_mode='relative_log_10000')
            actual = torch.load(normalized / 'targets.pt', weights_only=True)
            expected = torch.log1p(targets / torch.tensor([[15.], [14.]]) * 10000)
            torch.testing.assert_close(actual, expected)


if __name__ == '__main__':
    unittest.main()
