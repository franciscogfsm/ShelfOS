"""Sheets of crops whose silver stock label needs a second look.

usage: python tools/review_sheet.py <planogram.json> <images_root> <labels.txt> <out_dir> [which=half|all-late]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.labels import load_labels  # noqa: E402
from shelfos.planogram import list_images, load_planogram, read_image, write_image  # noqa: E402

S, PER_ROW, ROWS = 168, 9, 6


def main():
    plano, root, labels_path, out_dir = sys.argv[1:5]
    which = sys.argv[5] if len(sys.argv) > 5 else "half"
    areas, labels = load_planogram(plano), load_labels(labels_path)
    cells = []
    for cam, files in list_images(root).items():
        frames = {}
        for a in areas.get(cam, []):
            for t, f in enumerate(files):
                lab = labels[a.area_id][t]
                if which == "half":
                    pick = lab.stock is None or lab.stock == 1 or not lab.stock_sure
                else:
                    pick = t >= len(files) - 3
                if not pick:
                    continue
                if t not in frames:
                    frames[t] = read_image(f)
                crop, valid = a.warp(frames[t], (S, S), pad=0.08)
                crop[~valid] = (60, 0, 60)
                im = cv2.copyMakeBorder(crop, 0, 18, 1, 1, cv2.BORDER_CONSTANT, value=(25, 25, 25))
                s = "?" if lab.stock is None else ("EHF"[lab.stock] if lab.stock_sure else "ehf"[lab.stock])
                cv2.putText(im, f"{a.area_id} t{t} {s}", (3, S + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 255, 160), 1, cv2.LINE_AA)
                cells.append(im)
    per = PER_ROW * ROWS
    for k in range(0, len(cells), per):
        chunk = cells[k : k + per]
        while len(chunk) % PER_ROW:
            chunk.append(np.zeros_like(chunk[0]))
        write_image(Path(out_dir) / f"review_{k // per:02d}.jpg", np.vstack([np.hstack(chunk[i : i + PER_ROW]) for i in range(0, len(chunk), PER_ROW)]), 88)
    print(len(cells), "cells")


if __name__ == "__main__":
    main()
