"""Locate individual cutouts in the generated transparent catalogue sheets."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path('C:/Users/marti/.codex/generated_images/01a1262e-d807-75b1-98e6-be84f8353e49')
SHEETS = [('exec-274f9f09-fdf2-4911-a4c7-cda17395e468.png', 7), ('exec-4eb29007-a1f8-4b15-a8f0-20de5cc4221b.png', 3)]
output = []
for sheet, (filename, rows) in enumerate(SHEETS):
    source = ROOT / filename
    pixels = np.asarray(Image.open(source))
    height, width = pixels.shape[:2]
    _, labels, stats, centroids = cv2.connectedComponentsWithStats((pixels[:, :, 3] > 180).astype(np.uint8))
    subjects = {}
    for component, ((x, y, w, h, area), (cx, cy)) in enumerate(zip(stats[1:], centroids[1:]), 1):
        if area < 500:
            continue
        index = min(int(cy / (height / rows)), rows - 1) * 7 + min(int(cx / (width / 7)), 6)
        assert index not in subjects, f'Multiple subjects in sheet {sheet}, cell {index}'
        left, top = max(0, int(x) - 2), max(0, int(y) - 2)
        right, bottom = min(width, int(x + w) + 2), min(height, int(y + h) + 2)
        # A crop can contain a thin fragment of a neighbouring fruit. Build a silhouette
        # for this subject only, keeping a two-pixel margin for its original soft edges.
        silhouette = (labels[top:bottom, left:right] == component).astype(np.uint8)
        silhouette = cv2.dilate(silhouette, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(silhouette, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        paths = []
        for contour in contours:
            points = contour[:, 0]
            paths.append('M' + ' L'.join(f'{px},{py}' for px, py in points) + ' Z')
        mask = f'<svg xmlns="http://www.w3.org/2000/svg" width="{right-left}" height="{bottom-top}"><path fill="white" d="{" ".join(paths)}"/></svg>'
        subjects[index] = {'source': str(source), 'sheet': sheet, 'index': index, 'mask': mask, 'rect': {'left': left, 'top': top, 'width': right - left, 'height': bottom - top}}
    assert len(subjects) == rows * 7, f'Expected {rows * 7} subjects, found {len(subjects)}'
    output.extend(subjects[i] for i in range(rows * 7))
print(json.dumps(output))
