"""Feature bank of the reference day: one row per (planogram area, frame)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .features import CROP, MODEL_NAME, Embedder
from .planogram import list_images, load_planogram, read_image

THUMB = 112  # side of the colour thumbnail kept next to the tokens


def thumbs_of(crops: list[np.ndarray]) -> np.ndarray:
    step = max(1, crops[0].shape[0] // THUMB)
    return np.stack([c[::step, ::step] for c in crops])


def build_bank(planogram_path, images_root, out_path, model_name: str = MODEL_NAME, size: int = CROP, embedder: Embedder | None = None, tta: bool = False) -> None:
    areas = load_planogram(planogram_path)
    emb = embedder or Embedder(model_name, size=size, tta=tta)
    meta, crops = [], []
    for cam, files in list_images(images_root).items():
        for t, f in enumerate(files):
            img = read_image(f)
            for a in areas.get(cam, []):
                meta.append((cam, a.area_id, a.product_id, f.name, t))
                crops.append(emb.crop(img, a))
    t0 = time.time()
    glob, patches = emb.embed(crops)
    print(f"{len(crops)} crops embedded in {time.time() - t0:.0f}s on {emb.device}")
    m = np.array(meta)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path, glob=glob.astype(np.float32), patches=patches, camera=m[:, 0], area=m[:, 1], product=m[:, 2],
        fname=m[:, 3], t=m[:, 4].astype(int), thumbs=thumbs_of(crops), model=np.array(emb.model_name), size=np.array(emb.size),
        tta=np.array(bool(emb.tta)),
    )
