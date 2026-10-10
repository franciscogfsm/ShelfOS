"""Planogram parsing and area geometry."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")
_PACK_RE = re.compile(r"\d+([.,]\d+)?\s*(KG|G|GR)\b|EMB", re.IGNORECASE)


@dataclass(frozen=True)
class Area:
    camera: str
    area_id: str
    product_id: str
    product_name: str
    quad: np.ndarray  # (4, 2) float32, order = CORNERS, may fall outside the image

    @property
    def packaged(self) -> bool:
        """Names with a weight or EMB are sold packaged; plain '... KG' is loose."""
        name = self.product_name.strip()
        if re.search(r"(?<![\d.,])\s*KG(\s+IMP)?$", name) and not re.search(
            r"\d+([.,]\d+)?\s*KG(\s+IMP)?$", name
        ):
            return False
        return bool(_PACK_RE.search(name))

    def mask(self, shape: tuple[int, int]) -> np.ndarray:
        m = np.zeros(shape[:2], np.uint8)
        cv2.fillPoly(m, [np.round(self.quad).astype(np.int32)], 255)
        return m

    def visible_fraction(self, shape: tuple[int, int]) -> float:
        full = cv2.contourArea(self.quad.astype(np.float32))
        return float(self.mask(shape).astype(bool).sum() / max(full, 1.0))

    def warp(self, image: np.ndarray, size: tuple[int, int] = (224, 224), pad: float = 0.0):
        """Perspective-rectify the quad to size (w, h). Returns (crop, valid_mask).

        Pixels that come from outside the image (negative coordinates) are
        flagged invalid in the mask instead of being treated as black shelf.
        """
        w, h = size
        q = self.quad.astype(np.float32)
        if pad:
            c = q.mean(axis=0, keepdims=True)
            q = c + (q - c) * (1 + pad)
        dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
        M = cv2.getPerspectiveTransform(q, dst)
        crop = cv2.warpPerspective(image, M, (w, h), flags=cv2.INTER_LINEAR)
        ones = np.full(image.shape[:2], 255, np.uint8)
        valid = cv2.warpPerspective(ones, M, (w, h), flags=cv2.INTER_NEAREST)
        return crop, valid > 0

    def rect_size(self, max_side: int = 224) -> tuple[int, int]:
        """Output size that keeps the quad's approximate aspect ratio."""
        q = self.quad
        w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
        h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
        s = max_side / max(w, h, 1.0)
        return max(int(round(w * s)), 16), max(int(round(h * s)), 16)


def load_planogram(path: str | Path) -> dict[str, list[Area]]:
    """Return {camera_id: [Area, ...]} for every section in the file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[Area]] = {}
    for section in data.values():
        for cam, body in section["cameras"].items():
            areas = out.setdefault(str(cam), [])
            for p in body["products"]:
                ic = p["image_coordinates"]
                quad = np.array([ic[k] for k in CORNERS], np.float32)
                areas.append(
                    Area(str(cam), str(p["area_id"]), str(p["product_id"]), p["product_name"], quad)
                )
    return out


def list_images(root: str | Path) -> dict[str, list[Path]]:
    """Return {camera_id: [image paths sorted by timestamp]}, skipping macOS '._' files."""
    out: dict[str, list[Path]] = {}
    for cam_dir in sorted(Path(root).iterdir()):
        if not cam_dir.is_dir():
            continue
        files = sorted(
            (f for f in cam_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png") and not f.name.startswith("._")),
            key=lambda f: f.stem,
        )
        if files:
            out[cam_dir.name] = files
    return out


def read_image(path: str | Path) -> np.ndarray:
    """cv2.imread that tolerates non-ASCII Windows paths."""
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


def write_image(path: str | Path, image: np.ndarray, quality: int = 90) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ext = Path(path).suffix
    ok, buf = cv2.imencode(ext, image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        buf.tofile(str(path))
