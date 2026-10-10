"""Visual ripeness is isolated, uncertainty-aware and cached by exact image and slot."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from shelfos.counting import CountError, ModelResponseError
from shelfos.ripeness import assess_bananas, normalise
from shelfos.server import create_app

AREA = SimpleNamespace(area_id='6215_1', product_name='BANANA CAT I CNT KG',
                       quad=np.array([[10, 10], [90, 10], [90, 90], [10, 90]], np.float32))
RIPE = dict(state='ripe', quality='clear', evidence=['yellow_peel'],
            stage_counts={'green': 0, 'turning': 0, 'ripe': 8, 'very_ripe': 0})


class RipenessTests(unittest.TestCase):
    def test_uncertainty_and_browning_guard(self):
        self.assertEqual(normalise(RIPE)['state'], 'ripe')
        self.assertEqual(normalise({**RIPE, 'quality': 'poor'})['state'], 'unclear')
        self.assertEqual(normalise({**RIPE, 'quality': 'limited'})['state'], 'ripe')
        overripe = {**RIPE, 'state': 'very_ripe', 'stage_counts': {'green': 0, 'turning': 0, 'ripe': 0, 'very_ripe': 8}}
        self.assertEqual(normalise({**overripe, 'evidence': ['brown_spots']})['state'], 'unclear')
        self.assertTrue(normalise({**overripe, 'evidence': ['extensive_browning']})['review'])

    def test_majority_overrides_single_different_banana(self):
        counts = {'green': 7, 'turning': 0, 'ripe': 1, 'very_ripe': 0}
        result = normalise({**RIPE, 'stage_counts': counts, 'evidence': ['green_peel', 'yellow_peel']})
        self.assertEqual(result['state'], 'green')
        self.assertEqual(result['label'], 'Mostly green')
        self.assertEqual(normalise({**RIPE, 'stage_counts': {**counts, 'green': 4, 'ripe': 4}})['state'], 'mixed')
        self.assertEqual(normalise({**RIPE, 'stage_counts': {s: 0 for s in counts}})['state'], 'unclear')
        self.assertEqual(normalise({**RIPE, 'state': 'no_bananas', 'quality': 'poor', 'evidence': []})['state'], 'no_bananas')
        for bad in ['unsafe', [], None]:
            with self.assertRaises(CountError):
                normalise({**RIPE, 'state': bad})

    def test_cache_and_changed_image(self):
        with tempfile.TemporaryDirectory() as d:
            image = Path(d) / 'frame.jpg'
            cache = Path(d) / 'ripeness.json'
            cv2.imwrite(str(image), np.full((100, 100, 3), 200, np.uint8))
            with patch('shelfos.ripeness.ask_model', return_value=RIPE) as model:
                first = assess_bananas(image, AREA, 'secret', 'test-model', cache)
                second = assess_bananas(image, AREA, 'secret', 'test-model', cache)
                self.assertFalse(first['cached'])
                self.assertTrue(second['cached'])
                self.assertEqual(model.call_count, 1)
                self.assertNotIn('secret', cache.read_text())
                cv2.imwrite(str(image), np.full((100, 100, 3), 120, np.uint8))
                assess_bananas(image, AREA, 'secret', 'test-model', cache)
                self.assertEqual(model.call_count, 2)
                self.assertEqual(model.call_args.kwargs['max_tokens'], 1600)

    def test_incomplete_model_response_retries_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.jpg'
            cv2.imwrite(str(path), np.full((100, 100, 3), 200, np.uint8))
            with patch('shelfos.ripeness.ask_model', side_effect=[ModelResponseError('empty'), RIPE]) as model:
                self.assertEqual(assess_bananas(path, AREA, 'key', 'm', None)['state'], 'ripe')
                self.assertEqual(model.call_count, 2)
            with patch('shelfos.ripeness.ask_model', side_effect=ModelResponseError('empty')) as model:
                with self.assertRaises(ModelResponseError):
                    assess_bananas(path, AREA, 'key', 'm', None)
                self.assertEqual(model.call_count, 2)

    def test_api_does_not_modify_stock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'frame.jpg'
            path.touch()
            prediction = {'stock_level': 'full', 'p_compliant': 1, 'stock_probs': [0, 0, 1]}
            service = SimpleNamespace(areas={'6215': [AREA]}, lock=threading.Lock(), run={},
                reference={'6215': {'frame.jpg': {'6215_1': prediction}}}, empty_compliant=True,
                frame_path=lambda camera, file: path if camera == '6215' and file == 'frame.jpg' else None)
            client = TestClient(create_app(service, Path(d) / 'no-ui'))
            body = dict(camera='6215', file='frame.jpg', area='6215_1')
            with patch('shelfos.server.config', return_value='key'), patch('shelfos.ripeness.assess_bananas', return_value=normalise(RIPE)):
                self.assertEqual(client.post('/api/ripeness', json=body).status_code, 200)
                self.assertEqual(prediction, {'stock_level': 'full', 'p_compliant': 1, 'stock_probs': [0, 0, 1]})
                self.assertEqual(client.post('/api/ripeness', json={}).status_code, 400)
                self.assertEqual(client.post('/api/ripeness', json={**body, 'file': 'bad.jpg'}).status_code, 404)
                AREA.product_name = 'MELAO'
                try:
                    self.assertEqual(client.post('/api/ripeness', json=body).status_code, 422)
                finally:
                    AREA.product_name = 'BANANA CAT I CNT KG'
                prediction['p_compliant'] = 0
                self.assertEqual(client.post('/api/ripeness', json=body).status_code, 409)


if __name__ == '__main__':
    unittest.main()
