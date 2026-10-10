"""Fit the ShelfOS engine from the reference day.

usage: python -m shelfos.train [--bank cache/bank.npz] [--labels labels/silver_labels.txt]
       [--rects labels/background_rects.txt] [--images data/images] [--planogram data/planogram.json]
       [--out models/engine.pkl] [--reference models/reference_day.json]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .camera_id import CameraIdentifier
from .engine import Engine
from .features import CROP, MODEL_NAME
from .planogram import list_images, load_planogram, read_image


def train(bank_path="cache/bank.npz", labels="labels/silver_labels.txt", rects="labels/background_rects.txt",
          images="data/images", planogram="data/planogram.json", out="models/engine.pkl", reference="models/reference_day.json") -> Engine:
    t0 = time.time()
    bank = dict(np.load(bank_path))
    engine = Engine.fit(bank, labels, rects)
    engine.model_name = str(bank["model"]) if "model" in bank else MODEL_NAME
    engine.crop_size = int(bank["size"]) if "size" in bank else CROP
    # camera signatures, so loose image files can be assigned to their camera
    engine.cameras = CameraIdentifier()
    if Path(images).is_dir():
        for cam, files in list_images(images).items():
            for f in files:
                img = read_image(f)
                engine.cameras.add(cam, img)
                engine.frame_size = (img.shape[1], img.shape[0])
    engine.save(out)
    # what the engine says about the reference day itself (each frame judged without its own crops in memory)
    areas = {a.area_id: a for cam_areas in load_planogram(planogram).values() for a in cam_areas}
    rows = [areas[str(a)] for a in bank["area"]]
    details = engine.predict(bank["glob"], bank["patches"], bank["thumbs"], rows, fname=bank["fname"])
    day: dict = {}
    for cam, fname, area, d in zip(bank["camera"], bank["fname"], bank["area"], details):
        day.setdefault(str(cam), {}).setdefault(str(fname), {})[str(area)] = d
    Path(reference).parent.mkdir(parents=True, exist_ok=True)
    Path(reference).write_text(json.dumps(day), encoding="utf-8")
    print(f"saved {out}: {len(engine.memory.y)} labelled crops, {len(engine.comply.protos)} product prototypes, "
          f"{len(np.unique(engine.cameras.cams))} cameras ({time.time() - t0:.0f}s)")
    return engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="cache/bank.npz")
    ap.add_argument("--labels", default="labels/silver_labels.txt")
    ap.add_argument("--rects", default="labels/background_rects.txt")
    ap.add_argument("--images", default="data/images")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--out", default="models/engine.pkl")
    ap.add_argument("--reference", default="models/reference_day.json")
    a = ap.parse_args()
    train(a.bank, a.labels, a.rects, a.images, a.planogram, a.out, a.reference)


if __name__ == "__main__":
    main()
