"""Cross-validate the shipped engine, end to end, against the silver labels.

Every fold trains a fresh Engine on some frames and predicts whole held-out frames with the
same code path the app uses. Scores follow the official rules but are measured against
OUR OWN labels, not the hidden official annotations.

usage: python tools/cv.py [--bank cache/bank.npz] [--split late|fwd|lofo] [--empty-noncompliant] [--save oof.npz]

  late  the last two frames of every camera, trained on everything before (what validation looks like)
  fwd   four such steps back through the day, always trained on the past only
  lofo  one frame index held out across all cameras, trained on the rest of the day
"""
import argparse
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.engine import Engine, bank_labels, p_identity  # noqa: E402
from shelfos.scoring import ID_PAYOFF, LEVELS, STOCK_PAYOFF  # noqa: E402


def folds(bank, split):
    cam, t = bank["camera"], bank["t"]
    last = np.array([t[cam == c].max() for c in cam])
    if split == "late":
        yield last - t <= 1, last - t > 1
    elif split == "fwd":
        for back in (0, 2, 4, 6):
            yield (last - t >= back) & (last - t <= back + 1), last - t > back + 1
    elif split == "lofo":
        for k in np.unique(t):
            yield t == k, t != k
    else:
        raise SystemExit(f"unknown split {split}")


def evaluate(bank, labels, rects, split, empty_compliant=True, engine_cls=Engine, verbose=True):
    y, ys, c, cs = bank_labels(bank, labels)
    n = len(y)
    probs, p_ok, level, tested = np.zeros((n, 3)), np.zeros(n), np.zeros(n, int), np.zeros(n, bool)
    for te, tr in folds(bank, split):
        t0 = time.time()
        e = engine_cls.fit(bank, labels, rects, rows=tr)
        e.empty_compliant = empty_compliant
        idx = np.where(te)[0]
        areas = [SimpleNamespace(area_id=str(bank["area"][i]), product_id=str(bank["product"][i])) for i in idx]
        out = e.predict(bank["glob"][idx], bank["patches"][idx], bank["thumbs"][idx], areas)
        for i, d in zip(idx, out):
            probs[i], p_ok[i], level[i] = d["stock_probs"], p_identity(d, empty_compliant), LEVELS.index(d["stock_level"])
        tested |= te
        if verbose:
            print(f"  fold: train {tr.sum()} crops, test {te.sum()} crops, {time.time() - t0:.0f}s", flush=True)
    # identity truth: silver label where a product is visible; the convention where the area is empty
    truth_id = np.where(c >= 0, c, np.where(y == 0, int(empty_compliant), -1))
    ms, mi = tested & (y >= 0), tested & (truth_id >= 0)
    sp = STOCK_PAYOFF[level[ms], y[ms]]
    ip = ID_PAYOFF[(p_ok[mi] >= 0.5).astype(int), truth_id[mi]]
    res = {
        "split": split, "n_stock": int(ms.sum()), "n_id": int(mi.sum()),
        "stock_acc": float((sp == 1).mean()), "stock_pts": float(sp.mean()), "below": int((sp == -2).sum()), "above": int((sp == -3).sum()),
        "id_acc": float((ip == 1).mean()), "id_pts": float(ip.mean()), "id_wrong": int((ip == -2).sum()),
        "sure_stock_pts": float(STOCK_PAYOFF[level[ms & ys], y[ms & ys]].mean()),
    }
    res["total"] = (res["stock_pts"] + res["id_pts"]) / 2
    return res, dict(probs=probs, p_ok=p_ok, level=level, tested=tested, y=y, ys=ys, c=c, truth_id=truth_id)


def show(name, r):
    print(f"{name:22s} {r['split']:5s} stock acc {r['stock_acc']:.3f} pts {r['stock_pts']:+.3f} (below {r['below']}, above {r['above']}; sure {r['sure_stock_pts']:+.3f})"
          f" | id acc {r['id_acc']:.3f} pts {r['id_pts']:+.3f} (wrong {r['id_wrong']}) | {100 * r['total']:.1f}% of max  n={r['n_stock']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default="cache/bank.npz")
    ap.add_argument("--labels", default="labels/silver_labels.txt")
    ap.add_argument("--rects", default="labels/background_rects.txt")
    ap.add_argument("--split", default="late")
    ap.add_argument("--empty-noncompliant", action="store_true")
    ap.add_argument("--save")
    a = ap.parse_args()
    bank = dict(np.load(a.bank))
    for split in a.split.split(","):
        r, oof = evaluate(bank, a.labels, a.rects, split, empty_compliant=not a.empty_noncompliant)
        show("engine", r)
        if a.save:
            np.savez(a.save.replace(".npz", f"_{split}.npz"), **oof)


if __name__ == "__main__":
    main()
