"""Classifier variations on cached fold features. Scores are against OUR OWN labels."""
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.scoring import STOCK_PAYOFF, decide_stock  # noqa: E402
from tools.exp2 import fold_features  # noqa: E402


def lr(Xtr, ytr, w, Xte, C=1.0):
    clf = LogisticRegression(C=C, max_iter=3000).fit(Xtr, ytr, sample_weight=w)
    p = np.zeros((len(Xte), 3))
    p[:, clf.classes_] = clf.predict_proba(Xte)
    return p


def soften(X, y, ys, q):
    """Unsure half/full labels become a q / 1-q mixture of the two classes."""
    u = ~ys & (y >= 1)
    other = np.where(y == 1, 2, 1)
    return (np.concatenate([X, X[u]]), np.concatenate([y, other[u]]),
            np.concatenate([np.where(u, q, 1.0), np.full(u.sum(), 1 - q)]))


VARIANTS = {
    "base": lambda X, F, R, D: np.hstack([X, F * 0.5]),
    "all": lambda X, F, R, D: np.hstack([X, F * 0.5, R * 0.5]),
    "all+delta": lambda X, F, R, D: np.hstack([X, D * 2, F * 0.5, R * 0.5]),
}


def main():
    bank, labels = sys.argv[1], "labels/silver_labels.txt"
    for split in sys.argv[2:] or ["late", "fwd"]:
        b, y, ys, fo = fold_features(bank, labels, split)
        X = b["glob"]
        n = len(y)
        res = {}
        for name, build in VARIANTS.items():
            for soft in (None,):
                p = np.full((n, 3), 1 / 3)
                ev = np.zeros(n, bool)
                for te, tr, f, R, D in fo:
                    z = lambda A: (A - A[tr].mean(0)) / (A[tr].std(0) + 1e-6)
                    Z = build(X, z(f), z(R), D)
                    if soft:
                        Xa, ya, wa = soften(Z[tr], y[tr], ys[tr], soft)
                    else:
                        Xa, ya, wa = Z[tr], y[tr], np.where(ys[tr], 1.0, 0.5)
                    p[te] = lr(Xa, ya, wa, Z[te])
                    ev |= te
                m = ev & (y >= 0)
                pred = decide_stock(p)
                pts = STOCK_PAYOFF[pred[m], y[m]]
                ms = m & ys
                key = f"{name}{'/soft' if soft else ''}"
                res[key] = p
                print(f"{split:5s} {key:22s} n={m.sum()} acc={np.mean(pred[m] == y[m]):.3f} pts={pts.mean():+.3f} below={np.sum(pts == -2):3d} "
                      f"above={np.sum(pts == -3):3d} | sure pts={STOCK_PAYOFF[pred[ms], y[ms]].mean():+.3f}")
        np.savez(f"cache/oof3_{Path(bank).stem}_{split}.npz", **res, y=y, ys=ys, done=m)


if __name__ == "__main__":
    main()
