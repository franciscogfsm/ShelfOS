"""Does remembering the first new frame (with its predicted levels) help the second one?

Validation has up to two frames per camera after the reference day. This replays that:
train on everything before the last two frames, predict frame A, then predict frame B
either independently or after adding A's confident predictions to the area memory.
Scores are against OUR OWN labels.

usage: python tools/lab_sequential.py [--min-conf 0.9]
"""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tools.lab  # noqa: E402,F401  (memoised occupancy fits)
from shelfos.engine import Engine, bank_labels  # noqa: E402
from shelfos.occupancy import occupancy_features, patch_tokens  # noqa: E402
from shelfos.scoring import LEVELS, STOCK_PAYOFF  # noqa: E402


def main():
    conf = float(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--min-conf=")), 0.9))
    bank = dict(np.load("cache/bank.npz"))
    y, ys, c, cs = bank_labels(bank, "labels/silver_labels.txt")
    cam, t = bank["camera"], bank["t"]
    last = np.array([t[cam == k].max() for k in cam])
    tot = {"independent": [], "sequential": [], "oracle": []}
    for back in (0, 2, 4, 6):
        a_rows, b_rows, train = last - t == back + 1, last - t == back, last - t > back + 1
        e = Engine.fit(bank, "labels/silver_labels.txt", "labels/background_rects.txt", rows=train)

        def run(engine, rows):
            idx = np.where(rows)[0]
            areas = [SimpleNamespace(area_id=str(bank["area"][i]), product_id=str(bank["product"][i])) for i in idx]
            out = engine.predict(bank["glob"][idx], bank["patches"][idx], bank["thumbs"][idx], areas)
            return idx, out

        ia, oa = run(e, a_rows)
        ib, ob = run(e, b_rows)
        tot["independent"] += [STOCK_PAYOFF[LEVELS.index(d["stock_level"]), y[i]] for i, d in zip(ib, ob) if y[i] >= 0]
        for mode in ("sequential", "oracle"):
            e2 = copy.copy(e)
            e2.memory = copy.deepcopy(e.memory)
            if mode == "sequential":
                keep = np.array([max(d["stock_probs"]) >= conf for d in oa])
                lab = np.array([LEVELS.index(d["stock_level"]) for d in oa])
            else:  # upper bound: frame A with its true labels
                keep, lab = y[ia] >= 0, y[ia]
            k = ia[keep]
            occ = occupancy_features(e.occ.maps(patch_tokens(bank["patches"][k], bank["thumbs"][k])))[:, 0]
            e2.memory.remember(bank["glob"][k], bank["patches"][k], occ, lab[keep], bank["area"][k], fname=bank["fname"][k], t=bank["t"][k])
            _, o2 = run(e2, b_rows)
            tot[mode] += [STOCK_PAYOFF[LEVELS.index(d["stock_level"]), y[i]] for i, d in zip(ib, o2) if y[i] >= 0]
        print(f"back={back}: " + "  ".join(f"{k} {np.mean(v[-b_rows.sum():]):+.3f}" for k, v in tot.items()), flush=True)
    for k, v in tot.items():
        v = np.array(v)
        print(f"{k:12s} second-frame stock pts {v.mean():+.3f}  acc {(v == 1).mean():.3f}  n={len(v)}")


if __name__ == "__main__":
    main()
