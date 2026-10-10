"""Draw planogram areas over camera images for visual inspection.

usage: python tools/overlay.py <planogram.json> <images_root> <out_dir> [camera ...]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import list_images, load_planogram, read_image, write_image  # noqa: E402


def draw(image: np.ndarray, areas, labels: bool = True) -> np.ndarray:
    out = image.copy()
    for i, a in enumerate(areas):
        color = tuple(int(c) for c in cv2.cvtColor(np.uint8([[[(i * 37) % 180, 220, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
        q = np.round(a.quad).astype(np.int32)
        cv2.polylines(out, [q], True, color, 2, cv2.LINE_AA)
        if labels:
            c = np.clip(a.quad.mean(axis=0), [10, 12], [out.shape[1] - 60, out.shape[0] - 6]).astype(int)
            txt = a.area_id.split("_")[1]
            cv2.putText(out, txt, tuple(c), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(out, txt, tuple(c), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return out


def main():
    plano, root, out_dir = sys.argv[1:4]
    cams = sys.argv[4:]
    areas = load_planogram(plano)
    images = list_images(root)
    for cam, files in images.items():
        if cams and cam not in cams:
            continue
        for f in files:
            write_image(Path(out_dir) / cam / f.name, draw(read_image(f), areas.get(cam, [])), 85)
        print(cam, len(files), "areas:", ", ".join(f"{a.area_id.split('_')[1]}={a.product_name[:22]}{'[P]' if a.packaged else ''}" for a in areas.get(cam, [])))


if __name__ == "__main__":
    main()
