"""Render the stock mistakes of one out-of-fold method.

usage: python tools/error_sheet.py <bank.npz> <oof.npz> <method> <out.jpg>
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import write_image  # noqa: E402
from shelfos.scoring import decide_stock  # noqa: E402

S, PER_ROW = 150, 10


def main():
    b = np.load(sys.argv[1])
    o = np.load(sys.argv[2])
    p = np.nan_to_num(o[sys.argv[3]], nan=1 / 3)
    y, done = o["y"], o["done"]
    pred = decide_stock(p)
    bad = np.where(done & (pred != y))[0]
    cells = []
    for i in bad:
        im = cv2.resize(b["thumbs"][i], (S, S))
        im = cv2.copyMakeBorder(im, 0, 34, 1, 1, cv2.BORDER_CONSTANT, value=(25, 25, 25))
        cv2.putText(im, f"{b['area'][i]} t{b['t'][i]}", (3, S + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(im, f"me {'EHF'[y[i]]}{'' if o['ys'][i] else '?'} > {'EHF'[pred[i]]} {p[i, 0]:.1f}/{p[i, 1]:.1f}/{p[i, 2]:.1f}", (3, S + 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 255, 160), 1, cv2.LINE_AA)
        cells.append(im)
    print(len(cells), "errors")
    while len(cells) % PER_ROW:
        cells.append(np.zeros_like(cells[0]))
    write_image(sys.argv[4], np.vstack([np.hstack(cells[i : i + PER_ROW]) for i in range(0, len(cells), PER_ROW)]))


if __name__ == "__main__":
    main()
