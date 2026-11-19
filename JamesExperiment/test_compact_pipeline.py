"""Verify bounded-memory paired export against synthetic per-slide samples."""
import json
from pathlib import Path
import tempfile
import unittest


class CompactPipelineTests(unittest.TestCase):
    def test_export_mixed_ensembl_and_symbol_panels(self):
        import numpy as np
        import torch
        from .compact_pipeline import export_samples
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = root / 'samples'
            samples.mkdir()
            annotation = root / 'hgnc.tsv'
            annotation.write_text('symbol\tstatus\tensembl_gene_id\talias_symbol\tprev_symbol\n'
                                  'GENEA\tApproved\tENSG00000000001\t\t\n')
            for slide, names, values in [('A', ['ENSG00000000001.5', 'otherA'], [3., 7.]),
                                         ('B', ['GENEA', 'otherB'], [2., 8.])]:
                np.savez_compressed(samples / f'{slide}.npz', images=np.zeros((1, 224, 224, 3), dtype=np.uint8),
                                    genes=np.array(names), expression=np.array([values], dtype=np.float32),
                                    patch_indices=np.array([0]), barcodes=np.array([slide]), library_totals=np.array([10.]))
            (samples / 'sampling_complete.json').write_text(json.dumps(dict(
                complete=True, percentage=7, seed=42, revision='test',
                slides=[{'slide_id': 'A'}, {'slide_id': 'B'}])))
            settings = dict(sampling_unit='patch_within_slide', slide_ids=['A', 'B'], percentage=7,
                            seed=42, expression_mode='raw', data_dir=str(samples),
                            output_dir=str(root / 'output'), gene_annotation_path=str(annotation))
            path = root / 'settings.json'
            path.write_text(json.dumps(settings))
            out = export_samples(path)
            self.assertEqual(json.loads((out / 'genes.json').read_text()), ['GENEA'])
            torch.testing.assert_close(torch.load(out / 'targets.pt', weights_only=True), torch.tensor([[3.], [2.]]))

    def test_ensembl_symbol_alias_alignment_and_duplicate_sums(self):
        import numpy as np
        from .gene_alignment import HumanGeneMap, align_columns
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'genes.tsv'
            path.write_text('symbol\tstatus\tensembl_gene_id\talias_symbol\tprev_symbol\n'
                            'GENEA\tApproved\tENSG00000000001\tALIASA\tOLDA\n'
                            'GENEB\tApproved\tENSG00000000002\tSHARED\t\n'
                            'GENEC\tApproved\tENSG00000000003\tSHARED\t\n')
            mapping = HumanGeneMap(path)
            self.assertEqual(mapping.panel(['ENSG00000000001.3', 'OLDA', 'ALIASA']), ['GENEA'] * 3)
            self.assertEqual(mapping.canonical('SHARED'), 'SHARED')
            self.assertEqual(mapping.canonical('GRCh38__ENSG00000000001.3'), 'GENEA')
            self.assertEqual(mapping.canonical('GRCh38__GENEA'), 'GENEA')
            self.assertEqual(mapping.canonical('____GENEA'), 'GENEA')
            self.assertEqual(mapping.canonical('mm10__GENEA'), 'mm10__GENEA')
            actual = align_columns(np.array([[2., 3., 9.]]),
                                   ['ENSG00000000001', 'OLDA', 'GENEB'], ['GENEA', 'GENEB'], mapping)
            np.testing.assert_array_equal(actual, [[5., 9.]])

    def test_shared_genes_row_alignment_and_torch_load(self):
        import numpy as np
        import torch
        from .compact_pipeline import export_samples

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shards = root / 'samples'
            shards.mkdir()
            for slide, genes, values, color in [
                ('A', ['shared', 'uniqueA'], [[3, 7]], [255, 0, 0]),
                ('B', ['uniqueB', 'shared'], [[8, 2]], [0, 0, 255]),
            ]:
                np.savez_compressed(
                    shards / f'{slide}.npz',
                    images=np.broadcast_to(np.array(color, dtype=np.uint8), (1, 224, 224, 3)),
                    expression=np.array(values, dtype=np.float32), genes=np.array(genes),
                    patch_indices=np.array([5]), barcodes=np.array([slide + 'spot']),
                    library_totals=np.array([10.]),
                )
            (shards / 'sampling_complete.json').write_text(json.dumps(dict(
                complete=True, percentage=7, seed=42, revision='test',
                slides=[{'slide_id': 'A'}, {'slide_id': 'B'}],
            )))
            settings = dict(
                sampling_unit='patch_within_slide', slide_ids=['A', 'B'],
                percentage=7, seed=42, expression_mode='raw',
                data_dir=str(shards), output_dir=str(root / 'export'),
            )
            path = root / 'settings.json'
            path.write_text(json.dumps(settings))
            out = export_samples(path)
            x = torch.load(out / 'images.pt', weights_only=True, mmap=True)
            y = torch.load(out / 'targets.pt', weights_only=True, mmap=True)
            self.assertEqual(tuple(x.shape), (2, 3, 224, 224))
            torch.testing.assert_close(y, torch.tensor([[3.], [2.]]))
            from .tensor_stream import open_batch_tensor
            reader = open_batch_tensor(out / 'images.pt')
            batch = reader[:1]
            torch.testing.assert_close(batch, x[:1])
            batch.zero_()
            torch.testing.assert_close(reader[0], x[0])
            self.assertAlmostEqual(x[0, 0, 0, 0].item(), (1 - .697) / .188, places=5)
            self.assertEqual(json.loads((out / 'genes.json').read_text()), ['shared'])
            self.assertTrue(json.loads((out / 'experiment.json').read_text())['complete'])
            del x, y, reader, batch
            settings['output_dir'] = str(root / 'normalized')
            settings['expression_mode'] = 'relative_log_10000'
            path.write_text(json.dumps(settings))
            out = export_samples(path)
            actual = torch.load(out / 'targets.pt', weights_only=True)
            torch.testing.assert_close(actual, torch.log1p(torch.tensor([[3000.], [2000.]])))


if __name__ == '__main__':
    unittest.main()
