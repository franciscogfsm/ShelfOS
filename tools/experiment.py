"""Ablation harness: cross-validated official score on the silver labels.

Every fold holds out whole images, so no crop of a test image is ever seen in training.
Scores are against OUR OWN labels, not the hidden official annotations.

usage: python tools/experiment.py <bank.npz> <labels.txt> [split=lofo|late|loco]
"""
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.labels import load_labels  # noqa: E402
from shelfos.occupancy import PatchOccupancy, load_background_rects, occupancy_features, patch_tokens  # noqa: E402
from shelfos.scoring import ID_PAYOFF, STOCK_PAYOFF, decide_stock  # noqa: E402


def load(bank_path, labels_path):
    b = np.load(bank_path, allow_pickle=False)
    labels = load_labels(labels_path)
    n = len(b["area"])
    y = np.full(n, -1)
    ys = np.zeros(n, bool)
    c = np.full(n, -1)
    cs = np.zeros(n, bool)
    for i, (a, t) in enumerate(zip(b["area"], b["t"])):
        lab = labels[a][t]
        if lab.stock is not None:
            y[i], ys[i] = lab.stock, lab.stock_sure
        if lab.comply is not None:
            c[i], cs[i] = int(lab.comply), lab.comply_sure
    return b, y, ys, c, cs


def folds(b, split):
    cam, t = b["camera"], b["t"]
    if split == "lofo":  # one image at a time
        keys = np.char.add(np.char.add(cam, "/"), t.astype(str))
        # group to 13 folds by frame index: all cameras' frame k held out together
        for k in np.unique(t):
            yield t == k
    elif split == "late":  # the last two frames of every camera
        last = {c: t[cam == c].max() for c in np.unique(cam)}
        yield np.array([ti >= last[ci] - 1 for ci, ti in zip(cam, t)])
    elif split == "loco":  # unseen camera
        for c in np.unique(cam):
            yield cam == c


def stock_lr(Xtr, ytr, wtr, Xte, C=1.0):
    clf = LogisticRegression(C=C, max_iter=2000)
    clf.fit(Xtr, ytr, sample_weight=wtr)
    p = np.zeros((len(Xte), 3))
    p[:, clf.classes_] = clf.predict_proba(Xte)
    return p


def stock_knn(b, tr, te, y, k=3, temp=0.07, same_area=True):
    """Similarity-weighted vote over labelled crops of the same area."""
    X = b["glob"]
    out = np.full((te.sum(), 3), 1 / 3)
    for j, i in enumerate(np.where(te)[0]):
        pool = tr & (y >= 0)
        if same_area:
            pool = pool & (b["area"] == b["area"][i])
        idx = np.where(pool)[0]
        if not len(idx):
            continue
        s = X[idx] @ X[i] / 2
        top = np.argsort(-s)[:k]
        w = np.exp((s[top] - s[top].max()) / temp)
        p = np.bincount(y[idx[top]], weights=w, minlength=3) + 0.05
        out[j] = p / p.sum()
    return out


TOKENS = []


def occ_feats(b, tr, te, y, ys, rects="labels/background_rects.txt"):
    """Occupancy summaries for every crop, plus occupancy relative to the area's fullest seen frame."""
    tok = TOKENS[0] if TOKENS else TOKENS.append(patch_tokens(b["patches"], b["thumbs"])) or TOKENS[0]
    extra = load_background_rects(rects, b["area"], b["t"], tok, exclude=te)
    occ = PatchOccupancy().fit(tok[tr], y[tr], ys[tr], extra_bg=extra)
    f = occupancy_features(occ.maps(tok))
    ref = np.zeros(len(f))
    for a in np.unique(b["area"]):
        m = b["area"] == a
        seen = m & ~te
        ref[m] = f[seen, 0].max() if seen.any() else f[m, 0].max()
    rel = f[:, :1] / np.maximum(ref[:, None], 0.2)
    return np.hstack([f, rel, ref[:, None]])


def report(name, probs, y, ys, mask):
    pred = decide_stock(probs)
    arg = probs.argmax(1)
    for tag, m in (("all", mask), ("sure", mask & ys)):
        pts = STOCK_PAYOFF[pred[m], y[m]]
        raw = STOCK_PAYOFF[arg[m], y[m]]
        print(f"  {name:28s} {tag:4s} n={m.sum():4d} acc={np.mean(pred[m] == y[m]):.3f} pts/area={pts.mean():+.3f} "
              f"(argmax {raw.mean():+.3f}) below={np.sum(pts == -2):3d} above={np.sum(pts == -3):3d}")


def main():
    bank, labels = sys.argv[1:3]
    split = sys.argv[3] if len(sys.argv) > 3 else "lofo"
    b, y, ys, c, cs = load(bank, labels)
    X = b["glob"]
    n = len(y)
    print(f"{n} crops, stock labelled {np.sum(y >= 0)} (sure {ys.sum()}), dist E/H/F {np.bincount(y[y >= 0])}")
    print(f"compliance labelled {np.sum(c >= 0)}: wrong-product {np.sum(c == 0)}")
    names = ("lr", "knn_area", "knn_global", "lr+knn", "occ", "occ+lr", "occ+lr+knn", "lr[glob+occ]", "ens")
    methods = {k: np.full((n, 3), np.nan) for k in names}
    for te in folds(b, split):
        tr = ~te & (y >= 0)
        w = np.where(ys[tr], 1.0, 0.5)
        methods["lr"][te] = stock_lr(X[tr], y[tr], w, X[te])
        methods["knn_area"][te] = stock_knn(b, tr, te, y)
        methods["knn_global"][te] = stock_knn(b, tr, te, y, k=5, same_area=False)
        methods["lr+knn"][te] = (methods["lr"][te] * methods["knn_area"][te]) ** 0.5
        F = occ_feats(b, tr, te, y, ys)
        Fs = (F - F[tr].mean(0)) / (F[tr].std(0) + 1e-6)
        methods["occ"][te] = stock_lr(Fs[tr], y[tr], w, Fs[te], C=10)
        methods["occ+lr"][te] = (methods["lr"][te] * methods["occ"][te]) ** 0.5
        methods["occ+lr+knn"][te] = (methods["lr"][te] * methods["occ"][te] * methods["knn_area"][te]) ** (1 / 3)
        Z = np.hstack([X, Fs * 0.5])
        methods["lr[glob+occ]"][te] = stock_lr(Z[tr], y[tr], w, Z[te])
        methods["ens"][te] = (methods["lr[glob+occ]"][te] * methods["knn_global"][te]) ** 0.5
    done = ~np.isnan(methods["lr"][:, 0]) & (y >= 0)
    print(f"split={split}  evaluated {done.sum()} crops; baseline all-half pts/area="
          f"{STOCK_PAYOFF[1, y[done]].mean():+.3f}, all-empty={STOCK_PAYOFF[0, y[done]].mean():+.3f}")
    for k, p in methods.items():
        p = np.nan_to_num(p, nan=1 / 3)
        p /= p.sum(1, keepdims=True)
        report(k, p, y, ys, done)
    np.savez(Path(bank).with_name(f"oof_{split}.npz"), **methods, y=y, ys=ys, done=done)


if __name__ == "__main__":
    main()


