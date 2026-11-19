"""Check patient identity, missing IDs, annotations, and expression ordering."""
import unittest
import numpy as np
import pandas as pd
from .gene_heatmap import build_annotations, cancer_annotation, expression_colors


class HeatmapTests(unittest.TestCase):
    def test_patient_scope_unknowns_and_tensor_row_order(self):
        metadata = pd.DataFrame([
            dict(id='A', patient='Patient 1', dataset_title='Study A', organ='Lung', tissue='Lung', disease_state='Cancer', oncotree_code=''),
            dict(id='B', patient='Patient 1', dataset_title='Study A', organ='Lung', tissue='Lung', disease_state='Healthy', oncotree_code=''),
            dict(id='C', patient='Patient 1', dataset_title='Study B', organ='Brain', tissue='Brain', disease_state='Tumor', oncotree_code=''),
            dict(id='D', patient='', dataset_title='Study A', organ='Lung', tissue='Lung', disease_state='Diseased', oncotree_code=''),
            dict(id='E', patient=' ', dataset_title='Study A', organ='Lung', tissue='Lung', disease_state='Treated', oncotree_code=''),
        ])
        manifest = pd.DataFrame(dict(order=range(6), slide_id=['A', 'D', 'B', 'E', 'C', 'A']))
        slides, ordered, groups = build_annotations(manifest, metadata)
        self.assertEqual(len(groups), 4)
        self.assertEqual(groups.patient_id_known.sum(), 2)
        self.assertEqual(sorted(ordered.tensor_row), list(range(6)))
        group_by_slide = dict(zip(slides.id, slides.patient_group_key))
        self.assertEqual(group_by_slide['A'], group_by_slide['B'])
        self.assertNotEqual(group_by_slide['A'], group_by_slide['C'])
        self.assertNotEqual(group_by_slide['D'], group_by_slide['E'])
        self.assertEqual(groups.start_index_0based.iloc[0], 0)
        self.assertEqual(groups.end_index_0based_exclusive.iloc[-1], 6)
        self.assertEqual(groups.patch_count.sum(), 6)
        np.testing.assert_array_equal(groups.start_index_0based.iloc[1:].values,
                                      groups.end_index_0based_exclusive.iloc[:-1].values)

    def test_cancer_annotation_preserves_uncertainty(self):
        self.assertEqual(cancer_annotation('Cancer'), 'Cancer')
        self.assertEqual(cancer_annotation('Healthy'), 'Healthy / no cancer annotation')
        self.assertEqual(cancer_annotation('Tumor'), 'Tumor / malignancy unspecified')
        self.assertEqual(cancer_annotation('Diseased'), 'Unknown / not specified')
        self.assertEqual(cancer_annotation('Treated'), 'Unknown / not specified')

    def test_color_transform_constant_gene(self):
        values = np.array([[0, 0], [2, 0], [8, 0]], dtype=np.float32)
        original = values.copy()
        z, means, stds = expression_colors(values)
        self.assertTrue(np.isfinite(z).all())
        np.testing.assert_array_equal(z[:, 1], 0)
        self.assertAlmostEqual(z[:, 0].mean(), 0, places=6)
        np.testing.assert_array_equal(values, original)


if __name__ == '__main__':
    unittest.main()
