"""Render crops with the 14x14 patch grid so background rectangles can be annotated.

usage: python tools/grid_sheet.py <bank.npz> <out.jpg> area:t [area:t ...]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import write_image  # noqa: E402

S, PER_ROW = 308, 5


def main():
    b = np.load(sys.argv[1])
    cells = []
    for spec in sys.argv[3:]:
        a, t = spec.split(":")
        i = np.where((b["area"] == a) & (b["t"] == int(t)))[0][0]
        im = cv2.resize(b["thumbs"][i], (S, S), interpolation=cv2.INTER_CUBIC)
        for k in range(15):
            p = k * S // 14
            cv2.line(im, (p, 0), (p, S), (255, 255, 255), 1)
            cv2.line(im, (0, p), (S, p), (255, 255, 255), 1)
            if k < 14:
                cv2.putText(im, str(k), (p + 3, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 255), 1)
                cv2.putText(im, str(k), (1, p + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 255), 1)
        im = cv2.copyMakeBorder(im, 20, 2, 2, 2, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        cv2.putText(im, spec, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 255, 160), 1, cv2.LINE_AA)
        cells.append(im)
    while len(cells) % PER_ROW:
        cells.append(np.zeros_like(cells[0]))
    write_image(sys.argv[2], np.vstack([np.hstack(cells[i : i + PER_ROW]) for i in range(0, len(cells), PER_ROW)]))


if __name__ == "__main__":
    main()
