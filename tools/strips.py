"""Per-camera sheet: one row per planogram area, one column per frame (rectified crops).

usage: python tools/strips.py <planogram.json> <images_root> <out_dir> [cell_w] [pad]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import list_images, load_planogram, read_image, write_image  # noqa: E402


def main():
    plano, root, out_dir = sys.argv[1:4]
    cell_w = int(sys.argv[4]) if len(sys.argv) > 4 else 150
    pad = float(sys.argv[5]) if len(sys.argv) > 5 else 0.12
    cell_h = int(cell_w * 0.72)
    areas = load_planogram(plano)
    for cam, files in list_images(root).items():
        frames = [read_image(f) for f in files]
        label_w = 190
        rows = []
        header = np.full((22, label_w + cell_w * len(files), 3), 30, np.uint8)
        for j, f in enumerate(files):
            cv2.putText(header, f"t{j} {f.stem[-5:]}", (label_w + j * cell_w + 4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        rows.append(header)
        for a in areas.get(cam, []):
            row = np.full((cell_h, label_w + cell_w * len(files), 3), 30, np.uint8)
            cv2.putText(row, a.area_id, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 255, 160), 1, cv2.LINE_AA)
            for k, part in enumerate([a.product_name[:20], a.product_name[20:40]]):
                cv2.putText(row, part, (4, 42 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1, cv2.LINE_AA)
            for j, img in enumerate(frames):
                crop, valid = a.warp(img, (cell_w - 4, cell_h - 4), pad=pad)
                crop[~valid] = (60, 0, 60)
                row[2:-2, label_w + j * cell_w + 2 : label_w + (j + 1) * cell_w - 2] = crop
            rows.append(row)
        write_image(Path(out_dir) / f"{cam}.jpg", np.vstack(rows), 88)
        print(cam, np.vstack(rows).shape)


if __name__ == "__main__":
    main()
