"""Train the patch occupancy model on early frames, render maps for chosen areas.

usage: python tools/occ_probe.py <bank.npz> <labels.txt> <out.jpg> area_id [area_id ...]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.occupancy import PatchOccupancy, occupancy_features, patch_tokens  # noqa: E402
from shelfos.planogram import write_image  # noqa: E402
from tools.experiment import load  # noqa: E402


def main():
    bank, labels, out = sys.argv[1:4]
    want = sys.argv[4:]
    b, y, ys, c, cs = load(bank, labels)
    cam, t = b["camera"], b["t"]
    last = {k: t[cam == k].max() for k in np.unique(cam)}
    te = np.array([ti >= last[ci] - 1 for ci, ti in zip(cam, t)])
    from shelfos.occupancy import load_background_rects

    tok = patch_tokens(b["patches"], b["thumbs"])
    extra = load_background_rects("labels/background_rects.txt", b["area"], t, tok, exclude=te)
    print("extra background patches:", len(extra))
    occ = PatchOccupancy().fit(tok[~te], y[~te], ys[~te], extra_bg=extra)
    rows = []
    for a in want:
        idx = np.where(b["area"] == a)[0]
        idx = idx[np.argsort(t[idx])]
        maps = occ.maps(tok[idx])
        f = occupancy_features(maps)
        top, bot = [], []
        for j, i in enumerate(idx):
            th = cv2.resize(b["thumbs"][i], (112, 112))
            heat = cv2.applyColorMap((cv2.resize(maps[j].astype(np.float32), (112, 112), interpolation=cv2.INTER_NEAREST) * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
            cv2.putText(heat, f"{f[j, 0]:.2f} {'EHF?'[y[i]]}{'*' if te[i] else ''}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            top.append(th)
            bot.append(heat)
        rows += [np.hstack(top), np.hstack(bot)]
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0))) for r in rows]
    write_image(out, np.vstack(rows))


if __name__ == "__main__":
    main()

