"""Second-round stock ablation: area-relative (temporal memory) features, forward-chaining splits.

Scores are against OUR OWN labels, not the hidden official annotations.

usage: python tools/exp2.py <bank.npz> <labels.txt> [split=late|fwd|lofo]
"""
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.occupancy import PatchOccupancy, load_background_rects, occupancy_features, patch_tokens  # noqa: E402
from shelfos.scoring import STOCK_PAYOFF, decide_stock  # noqa: E402
from tools.experiment import load, stock_knn, stock_lr  # noqa: E402


def folds(b, split):
    cam, t = b["camera"], b["t"]
    last = np.array([t[cam == c].max() for c in cam])
    if split == "late":
        yield last - t <= 1, np.ones(len(t), bool)
    elif split == "fwd":  # train on the past only, test the next two frames
        for back in (0, 2, 4, 6):
            te = (last - t >= back) & (last - t <= back + 1)
            yield te, last - t > back + 1
    elif split == "lofo":
        for k in np.unique(t):
            yield t == k, np.ones(len(t), bool)


def norm(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


def relative_feats(b, P, tr, y, occ_mean):
    """Per-crop features relative to the same area's training frames."""
    X, area, t = b["glob"], b["area"], b["t"]
    n = len(X)
    out = np.zeros((n, 10), np.float32)
    delta = np.zeros_like(X)
    for a in np.unique(area):
        m = np.where(area == a)[0]
        pool = m[tr[m] & (y[m] >= 0)]
        full = pool[y[pool] == 2]
        emp = pool[y[pool] == 0]
        ref = full if len(full) else pool
        if not len(ref):
            continue
        Pm = P[m]  # [k,196,768] normalised
        self_ref = (m[:, None] == ref[None, :])  # a training crop must not be its own reference
        if len(ref) < 2:
            self_ref[:] = False
        wr = (~self_ref).astype(np.float32)
        mu = (wr @ X[ref]) / wr.sum(1, keepdims=True)
        delta[m] = X[m] - mu
        sims = np.einsum("kpd,rpd->krp", Pm, P[ref])
        sims[self_ref] = -1
        sim_full = sims.max(1)  # [k,196]
        out[m, 0] = sim_full.mean(1)
        out[m, 1] = (sim_full < 0.6).mean(1)
        out[m, 2] = np.sort(sim_full, 1)[:, :49].mean(1)
        out[m, 3] = np.sum(X[m] * norm(mu), 1)
        self_emp = (m[:, None] == emp[None, :])
        if len(emp) >= 2 or (len(emp) == 1 and not self_emp.any()):
            se = np.einsum("kpd,rpd->krp", Pm, P[emp])
            se[self_emp] = -1
            sim_emp = se.max(1)
            out[m, 4] = sim_emp.mean(1)
            out[m, 5] = (sim_emp > sim_full).mean(1)
            out[m, 6] = 1
        else:
            out[m, 4] = 0.3
            out[m, 5] = (sim_full < 0.5).mean(1)
        om = (wr @ occ_mean[ref]) / wr.sum(1)
        out[m, 7] = occ_mean[m] / np.maximum(om, 0.15)
        out[m, 8] = occ_mean[m] - om
        # persistence: label of the most similar training frame of this area
        for i in m:
            cand = pool[pool != i]
            if len(cand):
                s = X[cand] @ X[i]
                out[i, 9] = y[cand[np.argmax(s)]] / 2
    return out, delta


def fold_features(bank, labels, split):
    """Occupancy + area-relative features per fold, cached on disk (they do not depend on the classifier)."""
    import pickle
    cache = Path(bank).with_name(f"folds_{Path(bank).stem}_{split}.pkl")
    b, y, ys, c, cs = load(bank, labels)
    if cache.exists():
        return b, y, ys, pickle.loads(cache.read_bytes())
    P = norm(b["patches"].astype(np.float32))
    tok = patch_tokens(b["patches"], b["thumbs"])
    out = []
    for te, allowed in folds(b, split):
        tr = ~te & allowed & (y >= 0)
        extra = load_background_rects("labels/background_rects.txt", b["area"], b["t"], tok, exclude=~tr)
        occ = PatchOccupancy().fit(tok[tr], y[tr], ys[tr], extra_bg=extra)
        f = occupancy_features(occ.maps(tok))
        R, D = relative_feats(b, P, tr, y, f[:, 0])
        out.append((te, tr, f, R, D))
    cache.write_bytes(pickle.dumps(out))
    return b, y, ys, out


def score(p, y, m):
    return STOCK_PAYOFF[decide_stock(p)[m], y[m]].mean()


if __name__ == "__main__":
    print("use tools/exp3.py")
