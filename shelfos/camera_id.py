"""Recognise which ceiling camera took an image.

The cameras never move, so the floor, the gondola frames and the walls give every camera a
fixed signature. A small grey thumbnail plus its edge map, compared with the reference
day's frames, is enough to tell them apart (also at night, with the blinds down), which
lets ShelfOS take loose image files that come without a camera folder.
"""
from __future__ import annotations

import cv2
import numpy as np

W, H = 160, 90


def _unit(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


def signature(image: np.ndarray) -> np.ndarray:
    """Zero-mean, unit-norm grey thumbnail ++ edge-strength thumbnail."""
    g = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    big = cv2.resize(g, (W * 4, H * 4), interpolation=cv2.INTER_AREA).astype(np.float32)
    gx, gy = cv2.Sobel(big, cv2.CV_32F, 1, 0), cv2.Sobel(big, cv2.CV_32F, 0, 1)
    edge = cv2.resize(np.sqrt(gx * gx + gy * gy), (W, H), interpolation=cv2.INTER_AREA)
    grey = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
    return np.concatenate([_unit(grey), _unit(edge)]) / np.sqrt(2)


class CameraIdentifier:
    def __init__(self):
        self.sigs = np.zeros((0, 2 * W * H), np.float32)
        self.cams = np.zeros(0, dtype="<U16")

    def add(self, camera: str, image: np.ndarray) -> None:
        self.sigs = np.vstack([self.sigs, signature(image)[None]])
        self.cams = np.append(self.cams, camera)

    def identify(self, image: np.ndarray) -> tuple[str | None, float, float]:
        """-> (camera, similarity of the best match, margin over the best other camera)."""
        if not len(self.sigs):
            return None, 0.0, 0.0
        s = self.sigs @ signature(image)
        best = int(np.argmax(s))
        cam = str(self.cams[best])
        other = s[self.cams != cam]
        return cam, float(s[best]), float(s[best] - (other.max() if len(other) else -1.0))
