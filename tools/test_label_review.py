"""Data integrity checks: python -m unittest discover -s tools -p test_label_review.py."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
from label_review import Review, session_lock


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.labels = self.root / 'labels.txt'
        self.labels.write_text('# labels\n1_1 | eHF | NTT\n', encoding='utf-8')
        self.planogram = self.root / 'planogram.json'
        self.planogram.write_text(json.dumps({'section': {'cameras': {'1': {'products': [dict(
            area_id='1_1', product_id='p', product_name='Fruit',
            image_coordinates=dict(top_left=[2,2], top_right=[25,2], bottom_right=[25,25], bottom_left=[2,25]))]}}}}))
        self.images = self.root / 'images'
        (self.images / '1').mkdir(parents=True)
        for t in range(3):
            cv2.imencode('.jpg', np.zeros((32,32,3), np.uint8))[1].tofile(str(self.images / '1' / f'{t}.jpg'))
        self.state = self.root / 'review/session.json'
        self.review = self.open()

    def tearDown(self):
        self.tmp.cleanup()

    def open(self):
        return Review(self.labels, self.planogram, self.images, self.state)

    def test_unknown_resume_apply_and_revise(self):
        initial = self.labels.read_bytes()
        result = self.review.answer('1_1:0', '?', 'N')
        self.assertEqual(self.labels.read_bytes(), initial)
        resumed = self.open()
        self.assertEqual(resumed.session['answers']['1_1:0'], result['answer'])
        backup = resumed.apply()
        self.assertEqual(backup.read_bytes(), initial)
        self.assertIn('?HF', self.labels.read_text())
        resumed.answer('1_1:0', 'E', 'N', result['answer'])
        resumed.apply()
        self.assertIn('EHF', self.labels.read_text())

    def test_conflict_never_overwrites_source(self):
        self.review.answer('1_1:0', 'H')
        self.labels.write_text('# labels\n1_1 | FHF | NTT\n')
        before = self.labels.read_bytes()
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.review.apply()
        self.assertEqual(before, self.labels.read_bytes())

    def test_preserve_unrelated_stock_and_compliance(self):
        self.review.answer('1_1:0', 'E', 'F')
        self.labels.write_text('# external edit\n1_1 | eFF | NTF\n')
        self.review.apply()
        self.assertEqual(self.labels.read_text(), '# external edit\n1_1 | EFF | FTF\n')

    def test_stale_browser_cannot_overwrite_answer(self):
        saved = self.review.answer('1_1:0', 'E')['answer']
        with self.assertRaisesRegex(ValueError, 'Another browser'):
            self.review.answer('1_1:0', 'F', expected=None)
        self.assertEqual(self.review.session['answers']['1_1:0'], saved)

    def test_frame_order_change_is_rejected(self):
        self.review.save()
        (self.images/'1/0.jpg').rename(self.images/'1/9.jpg')
        with self.assertRaisesRegex(ValueError, 'Image names/order changed'):
            self.open()

    def test_images_and_session_lock(self):
        for kind in ['crop','near','context']:
            decoded=cv2.imdecode(np.frombuffer(self.review.image('1_1:0',kind),np.uint8),cv2.IMREAD_COLOR)
            self.assertIsNotNone(decoded)
        with session_lock(self.state):
            with self.assertRaisesRegex(ValueError, 'already open'):
                with session_lock(self.state):
                    pass


if __name__ == '__main__':
    unittest.main()
