"""Where does the time of one image go? Times every stage of the prediction path, read-only.

usage: python tools/profile_lite.py --images <folder> [--model models/engine_lite.pkl]
       [--planogram data/planogram.json] [--cpu] [--limit 40] [--warm 3]

Runs ShelfService.analyze() exactly as `run.py --images` does (nothing is written outside a
temporary run folder) and wraps the stages it calls with timers. GPU work is synchronised before
each clock read, so the embed time is real and not just the kernel launch. The first --warm images
are not counted (CUDA kernels, caches, lazy imports).
"""
from __future__ import annotations

import argparse
import functools
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos import camera_id, compliance, engine, features, memory, occupancy, service  # noqa: E402

TOTAL: dict[str, float] = defaultdict(float)
CALLS: dict[str, int] = defaultdict(int)
_depth = [0]
_sync = [lambda: None]


def timed(name, fn):
    """Wrap fn; only the outermost timed call is charged, so nested stages are not counted twice."""

    @functools.wraps(fn)
    def run(*a, **k):
        if _depth[0]:
            return fn(*a, **k)
        _depth[0] += 1
        _sync[0]()
        t0 = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            _sync[0]()
            TOTAL[name] += time.perf_counter() - t0
            CALLS[name] += 1
            _depth[0] -= 1

    return run


def patch(owner, attr, name):
    setattr(owner, attr, timed(name, getattr(owner, attr)))


def instrument():
    patch(cv2, "imdecode", "decode jpeg")
    patch(camera_id.CameraIdentifier, "identify", "camera signature")
    patch(service.ShelfService, "_fit_frame", "fit frame size")
    patch(features.Embedder, "crop", "rectify areas")
    patch(features.Embedder, "embed", "backbone (embed)")
    patch(service, "thumbs_of", "thumbnails")
    patch(engine, "patch_tokens", "occupancy: colour + tokens")
    patch(occupancy.PatchOccupancy, "maps", "occupancy: maps")
    patch(engine, "occupancy_features", "occupancy: summaries")
    patch(memory.AreaMemory, "rows_of", "memory: rows_of")
    patch(memory.AreaMemory, "_base_features", "memory: vs full/empty frames")
    patch(memory.AreaMemory, "_change_features", "memory: vs previous frames")
    patch(compliance.ComplianceModel, "predict", "product: compliance")
    patch(compliance.ComplianceModel, "identify", "product: looks like")
    patch(engine.Engine, "_finish", "answer fields")
    patch(service.ShelfService, "_frame_json", "frame json for the app")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--model", default="models/engine_lite.pkl")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--warm", type=int, default=3)
    a = ap.parse_args()

    root = Path(a.images)
    files = sorted(p for p in root.rglob("*") if p.is_file() and service.is_image(p.name))
    if not files:
        sys.exit(f"no images under {root}")
    with tempfile.TemporaryDirectory() as tmp:
        svc = service.ShelfService(a.model, a.planogram, reference_path=None, run_dir=Path(tmp) / "run", device="cpu" if a.cpu else None)
        dev = svc.embedder.device
        if dev == "cuda":
            import torch

            _sync[0] = torch.cuda.synchronize
        instrument()
        # the same image files over and over until --warm + --limit images were analysed
        todo = [files[i % len(files)] for i in range(a.warm + a.limit)]
        walls, areas = [], 0
        for k, p in enumerate(todo):
            rel = str(Path(root.name) / p.relative_to(root))
            data = p.read_bytes()
            if k == a.warm:
                TOTAL.clear()
                CALLS.clear()
            t0 = time.perf_counter()
            ev = svc.analyze(data, rel, save=False)
            _sync[0]()
            if k >= a.warm:
                walls.append(time.perf_counter() - t0)
                areas += len(ev.get("frame", {}).get("areas", {}))
    n = len(walls)
    wall = sum(walls)
    print(f"\n{n} images, {areas / n:.1f} areas per image, device {dev}, model {a.model}")
    print(f"per image: mean {1000 * wall / n:.1f} ms, median {1000 * float(np.median(walls)):.1f} ms  ->  {n / wall:.1f} images/s\n")
    print(f"{'stage':34s} {'ms/img':>8s} {'share':>7s} {'calls/img':>10s}")
    rows = sorted(TOTAL.items(), key=lambda kv: -kv[1])
    for name, t in rows:
        print(f"{name:34s} {1000 * t / n:8.1f} {100 * t / wall:6.1f}% {CALLS[name] / n:10.1f}")
    rest = wall - sum(TOTAL.values())
    print(f"{'(everything else)':34s} {1000 * rest / n:8.1f} {100 * rest / wall:6.1f}%")


if __name__ == "__main__":
    main()
