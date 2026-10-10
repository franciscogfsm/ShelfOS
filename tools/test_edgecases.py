"""Contract tests for the evaluator: scoring, exclusion, review and leakage guards."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.edgecases import metrics, validate


class EdgecaseTests(unittest.TestCase):
    def test_asymmetric_stock_penalties_and_partial_labels(self):
        rows = [dict(expected=dict(stock_level='empty'), prediction=dict(stock_level='full')),
                dict(expected=dict(stock_level='full'), prediction=dict(stock_level='half')),
                dict(expected=dict(planogram_compliant=False), prediction=dict(planogram_compliant=True)),
                dict(expected={}, prediction=dict(stock_level='full', planogram_compliant=True))]
        m = metrics(rows)
        self.assertEqual((m['points'], m['maximum'], m['over'], m['under']), (-7, 3, 1, 1))
        json.dumps(m)  # numpy counts must be converted to native JSON numbers

    def validate_case(self, mutate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one.jpg').write_bytes(b'first')
            (root / 'two.jpg').write_bytes(b'first')
            case = dict(id='one', split='test', image='one.jpg', camera='1', reviewed=True,
                        labels={'a': dict(stock_level='empty', planogram_compliant=True)})
            manifest = dict(cases=[case])
            mutate(manifest)
            with patch('tools.edgecases.ROOT', root):
                validate(manifest, {'1': [SimpleNamespace(area_id='a')]})

    def test_valid_reviewed_case(self):
        self.validate_case(lambda m: None)

    def test_reject_unreviewed_labels(self):
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            self.validate_case(lambda m: m['cases'][0].update(reviewed=False))

    def test_reject_empty_noncompliant(self):
        with self.assertRaisesRegex(ValueError, 'Empty is compliant'):
            self.validate_case(lambda m: m['cases'][0]['labels']['a'].update(planogram_compliant=False))

    def test_identical_files_cannot_cross_splits(self):
        def mutate(m):
            m['cases'].append(dict(m['cases'][0], id='two', split='train', image='two.jpg'))
        with self.assertRaisesRegex(ValueError, 'identical image'):
            self.validate_case(mutate)

    def test_source_family_cannot_cross_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one.jpg').write_bytes(b'first')
            (root / 'two.jpg').write_bytes(b'different edit')
            cases = [dict(id='one', split='test', image='one.jpg', camera='1', source_group='source'),
                     dict(id='two', split='train', image='two.jpg', camera='1', source_group='source')]
            with patch('tools.edgecases.ROOT', root), self.assertRaisesRegex(ValueError, 'source family'):
                validate(dict(cases=cases), {'1': [SimpleNamespace(area_id='a')]})


if __name__ == '__main__':
    unittest.main()
