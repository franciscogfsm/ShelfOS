"""Smaller and faster engines, scored the same way as the shipped one: which keeps the quality?

usage: python tools/edge_sweep.py [--variants b-tta,b,b-int8,splus,splus-int8,s,s-int8] [--split late,fwd]

For every variant: build its bank of the reference day (once, kept in cache/), cross-validate it with
tools/cv.py's evaluate() on the same labels, rects and folds, and time the backbone on the CPU for one
image (11 crops, no GPU, the device a shelf-side box would have). Prints one table. A heavy job: run it
alone (see AGENTS_COORDINATION.md, machine limits). Int8 banks are built on the CPU (a few minutes each).

  b-tta       ViT-B + mirror (today's engine_lite)        s      ViT-S/16 (21.6 M parameters)
  b           ViT-B, no mirror                            splus  ViT-S+/16 (28.7 M parameters)
  *-int8      same backbone with int8 linear layers (SHELFOS_INT8=1, CPU)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv import evaluate  # noqa: E402

from shelfos.bank import build_bank  # noqa: E402

BACKBONE = {"b": "vit_base_patch16_dinov3.lvd1689m", "splus": "vit_small_plus_patch16_dinov3.lvd1689m", "s": "vit_small_patch16_dinov3.lvd1689m"}


def parse(v: str):
    """'splus-int8' -> (model name, tta, int8)."""
    parts = v.split("-")
    return BACKBONE[parts[0]], "tta" in parts[1:], "int8" in parts[1:]


def cpu_ms(model_name: str, tta: bool, int8: bool, n_crops: int = 11, repeat: int = 3) -> float:
    """Backbone time for one image's crops on the CPU."""
    import torch

    from shelfos.features import Embedder

    os.environ["SHELFOS_INT8"] = "1" if int8 else "0"
    emb = Embedder(model_name, device="cpu", tta=tta)
    crops = [np.full((emb.size, emb.size, 3), 124, np.uint8)] * n_crops
    emb.embed(crops, compact=False)
    t0 = time.perf_counter()
    for _ in range(repeat):
        emb.embed(crops, compact=False)
    del emb
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    return 1000 * (time.perf_counter() - t0) / repeat


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", default="b-tta,b,b-int8,splus,splus-int8,s,s-int8")
    ap.add_argument("--split", default="late,fwd")
    ap.add_argument("--labels", default="labels/silver_labels.txt")
    ap.add_argument("--rects", default="labels/background_rects.txt")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--images", default="data/images")
    a = ap.parse_args()
    rows = []
    for v in a.variants.split(","):
        name, tta, int8 = parse(v)
        bank_path = Path("cache") / f"bank_edge_{v}.npz"
        if not bank_path.exists():
            print(f"[{v}] building {bank_path} ...", flush=True)
            os.environ["SHELFOS_INT8"] = "1" if int8 else "0"
            from shelfos.features import Embedder

            emb = Embedder(name, device="cpu" if int8 else None, tta=tta)
            build_bank(a.planogram, a.images, bank_path, model_name=name, embedder=emb, tta=tta)
            del emb
        bank = dict(np.load(bank_path))
        res = {}
        for split in a.split.split(","):
            r, _ = evaluate(bank, a.labels, a.rects, split, verbose=False)
            res[split] = r
            print(f"[{v}] {split}: {100 * r['total']:.1f}% of max, stock {r['stock_pts']:+.3f} (over {r['above']}, under {r['below']}), id {r['id_acc']:.3f}", flush=True)
        ms = cpu_ms(name, tta, int8)
        rows.append((v, res, ms))
        print(f"[{v}] CPU backbone {ms:.0f} ms per image", flush=True)
    splits = a.split.split(",")
    print("\n" + f"{'variant':12s}" + "".join(f" {s + ' % max':>11s} {s + ' stock':>10s}" for s in splits) + f" {'CPU ms/img':>11s}")
    for v, res, ms in rows:
        print(f"{v:12s}" + "".join(f" {100 * res[s]['total']:11.1f} {res[s]['stock_pts']:+10.3f}" for s in splits) + f" {ms:11.0f}")


if __name__ == "__main__":
    main()
