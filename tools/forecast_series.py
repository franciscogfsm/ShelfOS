"""Out-of-fold shelf readings of every area through the day, for the run-out forecast backtest.

Each frame index is held out in turn (the lofo split of tools/cv.py): a fresh Engine is fitted on
the rest of the day and reads the held-out frame, so no reading comes from a model that saw that
frame's label. The silver label rides along as the truth. Read-only: predictions.json is untouched.

usage: python tools/forecast_series.py [--bank cache/bank.npz] [--out cache/forecast_series.json]
then:  node --experimental-strip-types tools/forecast_backtest.ts cache/forecast_series.json
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.engine import Engine, bank_labels, capture_times  # noqa: E402
from tools.cv import folds  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default="cache/bank.npz")
    ap.add_argument("--labels", default="labels/silver_labels.txt")
    ap.add_argument("--rects", default="labels/background_rects.txt")
    ap.add_argument("--out", default="cache/forecast_series.json")
    a = ap.parse_args()
    bank = dict(np.load(a.bank))
    y, _, _, _ = bank_labels(bank, a.labels)
    n = len(y)
    reads = [None] * n
    for te, tr in folds(bank, "lofo"):
        t0 = time.time()
        e = Engine.fit(bank, a.labels, a.rects, rows=tr)
        idx = np.where(te)[0]
        areas = [SimpleNamespace(area_id=str(bank["area"][i]), product_id=str(bank["product"][i])) for i in idx]
        out = e.predict(bank["glob"][idx], bank["patches"][idx], bank["thumbs"][idx], areas, fname=bank["fname"][idx])
        for i, d in zip(idx, out):
            reads[i] = d
        print(f"  fold: train {tr.sum()} crops, test {te.sum()} crops, {time.time() - t0:.0f}s", flush=True)

    ts = capture_times(bank["fname"], n)
    series: dict[str, list[dict]] = {}
    for i, d in enumerate(reads):
        if d is None or ts[i] is None:
            continue
        series.setdefault(str(bank["area"][i]), []).append({
            "ts": ts[i],
            "probs": d["stock_probs"],
            "occ": d["occupancy"],
            "obstruction": d.get("obstruction", 0.0),
            "source": d.get("source", "image"),
            "label": int(y[i]) if y[i] >= 0 else None,  # 0 empty, 1 half, 2 full; None unlabelled
        })
    for points in series.values():
        points.sort(key=lambda p: p["ts"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(series), encoding="utf-8")
    print(f"{a.out}: {len(series)} areas, {sum(len(v) for v in series.values())} readings")


if __name__ == "__main__":
    main()
