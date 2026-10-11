"""Unit counting contracts: product groups, slot geometry, box cleaning, cache and errors (no network)."""
import io
import json
import tempfile
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from shelfos.counting import CountError, ModelResponseError, ask_model, clean_boxes, count_area, countable, crop_for, group_of

QUAD = np.array([[100, 100], [300, 100], [300, 200], [100, 200]], np.float32)
AREA = SimpleNamespace(area_id='c_1', product_id='1', product_name='TOMATE REDONDO CNT KG', quad=QUAD)


def reply(payload):
    return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(payload)}}]}).encode())


class CountingTests(unittest.TestCase):
    def test_wrapped_json_and_empty_response(self):
        for content in ['Here is the result:\n```json\n{"state":"ripe"}\n```',
                        [{'type': 'text', 'text': '{"state":"ripe"}'}]]:
            response = io.BytesIO(json.dumps({'choices': [{'message': {'content': content}}]}).encode())
            with patch('urllib.request.urlopen', return_value=response):
                self.assertEqual(ask_model(b'image', 'prompt', 'k', 'm')['state'], 'ripe')
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': None}}]}).encode())
        with patch('urllib.request.urlopen', return_value=response), self.assertRaises(ModelResponseError):
            ask_model(b'image', 'prompt', 'k', 'm')

    def test_parallel_requests_share_one_call_and_changed_image_recounts(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.jpg'
            cv2.imwrite(str(path), np.full((720, 1280, 3), 200, np.uint8))
            cache = Path(d) / 'counts.json'
            barrier = threading.Barrier(6)
            def ask(*args):
                time.sleep(.1)
                return {'items': [], 'countable': True}
            def run(_):
                barrier.wait()
                return count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=cache)
            with patch('shelfos.counting.ask_model', side_effect=ask) as model:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    results = list(pool.map(run, range(6)))
                self.assertEqual(model.call_count, 1)
                self.assertTrue(all(r['count'] == 0 for r in results))
                with patch('pathlib.Path.read_text', side_effect=AssertionError('warm cache should not read disk')):
                    self.assertTrue(count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=cache)['cached'])
                cv2.imwrite(str(path), np.full((720, 1280, 3), 120, np.uint8))
                self.assertFalse(count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=cache)['cached'])
                self.assertEqual(model.call_count, 2)

    def test_failed_request_can_be_retried(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.jpg'
            cv2.imwrite(str(path), np.full((720, 1280, 3), 200, np.uint8))
            with patch('shelfos.counting.ask_model', side_effect=[CountError('offline'), {'items': []}]):
                with self.assertRaises(CountError):
                    count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=None)
                self.assertEqual(count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=None)['count'], 0)

    def test_all_products_opt_in(self):
        with patch('shelfos.counting.enabled_groups', return_value=frozenset({'all'})):
            self.assertEqual(countable('BANANA CAT I CNT KG'), 'bunch')
            self.assertEqual(countable('FEIJÃO VERDE CNT KG'), 'medium')
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'f.jpg'
                cv2.imwrite(str(path), np.full((720, 1280, 3), 200, np.uint8))
                bulk = SimpleNamespace(**{**AREA.__dict__, 'product_name': 'FEIJÃO VERDE CNT KG'})
                with patch('shelfos.counting.ask_model', return_value={'items': [], 'countable': True}):
                    result = count_area(path, 'c', 'f.jpg', bulk, 'k', 'm', cache_path=None)
                self.assertEqual(result['unit'], 'item')

    def test_groups(self):
        self.assertEqual(group_of('MACA FUJI CNT CAL. 73/85 KG IMP'), 'medium')  # a calibre, not a pack
        self.assertEqual(group_of('TOMATE CHERRY VERMELHO CNT 250GR'), 'pack')
        self.assertEqual(group_of('BATATA VERMELHA EMB:. 5 KG'), 'pack')
        self.assertEqual(group_of('ABÓBORA HOKAIDO R0 KG'), 'large')  # R0 is a grade
        self.assertEqual(group_of('BANANA CAT I CNT KG'), 'bunch')
        self.assertIsNone(group_of('FEIJÃO VERDE CNT KG'))

    def test_crop_greys_outside_and_maps_back(self):
        img = np.full((720, 1280, 3), 255, np.uint8)
        crop, x0, y0, s = crop_for(img, QUAD)
        self.assertEqual(max(crop.shape[:2]), 1024)
        self.assertEqual((x0, y0), (80.0, 90.0))  # 10% margin
        self.assertTrue((crop[2, 2] == 128).all())  # margin is greyed
        self.assertTrue((crop[crop.shape[0] // 2, crop.shape[1] // 2] == 255).all())  # slot is kept

    def test_crop_outside_frame(self):
        with self.assertRaises(CountError):
            crop_for(np.zeros((720, 1280, 3), np.uint8), QUAD + 5000)

    def test_clean_boxes_drops_neighbours_duplicates_and_outliers(self):
        img = np.zeros((720, 1280, 3), np.uint8)
        crop, x0, y0, s = crop_for(img, QUAD)
        # crop covers x 80..320, y 90..210; 1000 units = the crop side
        def box(fx0, fy0, fx1, fy1, partial=False):  # frame pixels -> model 0-1000
            ch, cw = crop.shape[:2]
            to = lambda v, o, n: round((v - o) * s / n * 1000)
            return {'box_2d': [to(fy0, y0, ch), to(fx0, x0, cw), to(fy1, y0, ch), to(fx1, x0, cw)], 'partial': partial}
        items = [box(120, 120, 140, 140), box(121, 121, 141, 141),  # duplicate
                 box(200, 150, 220, 170, partial=True), box(250, 120, 270, 140),
                 box(82, 92, 98, 108),  # centred in the grey margin: a neighbour's
                 box(101, 101, 299, 199),  # absurdly large
                 {'box_2d': 'nonsense'}]
        out = clean_boxes(items, crop.shape, x0, y0, s, QUAD)
        self.assertEqual(len(out), 3)
        self.assertEqual(sum(b['partial'] for b in out), 1)
        self.assertAlmostEqual(out[0]['x'], 120, delta=1)

    def test_count_area_caches_and_refuses_bulk(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.jpg'
            cv2.imwrite(str(path), np.full((720, 1280, 3), 200, np.uint8))
            cache = Path(d) / 'counts.json'
            with patch('urllib.request.urlopen', return_value=reply({'items': [{'box_2d': [300, 300, 600, 500]}], 'countable': True})) as req:
                first = count_area(path, 'c', 'f.jpg', AREA, 'private-key', 'm', cache_path=cache)
                second = count_area(path, 'c', 'f.jpg', AREA, 'private-key', 'm', cache_path=cache)
            self.assertEqual(req.call_count, 1)
            self.assertEqual((first['count'], first['cached'], second['cached']), (1, False, True))
            self.assertNotIn('private-key', req.call_args.args[0].data.decode())
            bulk = SimpleNamespace(**{**AREA.__dict__, 'product_name': 'FEIJÃO VERDE CNT KG'})
            with patch('shelfos.counting.enabled_groups', return_value=frozenset()), self.assertRaises(CountError):
                count_area(path, 'c', 'f.jpg', bulk, 'k', 'm', cache_path=None)

    def test_unreadable_answer_and_not_countable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.jpg'
            cv2.imwrite(str(path), np.full((720, 1280, 3), 200, np.uint8))
            bad = io.BytesIO(json.dumps({'choices': [{'message': {'content': 'sorry'}}]}).encode())
            with patch('urllib.request.urlopen', return_value=bad), self.assertRaises(CountError):
                count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=None)
            with patch('urllib.request.urlopen', return_value=reply({'items': [], 'countable': False, 'reason': 'a solid mass'})):
                with self.assertRaisesRegex(CountError, 'solid mass'):
                    count_area(path, 'c', 'f.jpg', AREA, 'k', 'm', cache_path=None)


if __name__ == '__main__':
    unittest.main()
