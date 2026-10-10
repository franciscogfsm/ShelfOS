"""Scratch bench for stock-feature ideas: Engine variants compared with the same folds.

Occupancy models are memoised on disk, so a new idea costs seconds per fold.
Scores are against OUR OWN labels, not the hidden official annotations.

usage: python tools/lab.py [variant ...] [--split late,fwd]
"""
import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos import occupancy  # noqa: E402
from shelfos.engine import MEM_SCALE, OCC_SCALE, Engine  # noqa: E402
from shelfos.memory import AreaMemory  # noqa: E402
from tools.cv import evaluate, show  # noqa: E402

_fit = occupancy.PatchOccupancy.fit


def _memo_fit(self, tokens, stock, sure, extra_bg=None):
    h = hashlib.md5()
    for part in (stock, sure, tokens[:4, :4, :16], np.array(tokens.shape), extra_bg if extra_bg is not None else np.zeros(1), np.array([self.C, self.rounds])):
        h.update(np.ascontiguousarray(part).tobytes())
    path = Path("cache") / f"occ_{h.hexdigest()[:16]}.pkl"
    if path.exists():
        self.clf = pickle.loads(path.read_bytes())
        return self
    _fit(self, tokens, stock, sure, extra_bg)
    path.write_bytes(pickle.dumps(self.clf))
    return self


occupancy.PatchOccupancy.fit = _memo_fit


class SimMemory(AreaMemory):
    """+ global similarity to the area's nearest full / half / empty frame."""

    def features(self, glob, patches, occ_mean, area, self_row=None):
        base = super().features(glob, patches, occ_mean, area, self_row)
        n = len(glob)
        extra = np.zeros((n, 7), np.float32)
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        for a in np.unique(area):
            q = np.where(area == a)[0]
            pool = self.rows.get(a)
            if pool is None or not len(pool):
                continue
            S = glob[q] @ self.X[pool].T / 2
            S[self_row[q][:, None] == pool[None, :]] = -1
            best = []
            for k in range(3):
                cols = self.y[pool] == k
                s = S[:, cols].max(1) if cols.any() else np.full(len(q), -1.0)
                best.append(s)
                extra[q, k] = np.where(s > -1, s, 0.5)
                extra[q, 3 + k] = s > -1
            top = np.maximum(np.maximum(best[0], best[1]), best[2])
            w = np.exp((np.stack(best, 1) - top[:, None]) / 0.05)
            extra[q, 6] = (w @ np.array([0, 0.5, 1.0])) / w.sum(1)
        return np.hstack([base, extra])


class PrevMemory(AreaMemory):
    """+ the level of the latest earlier frame of the area and how similar the crop still is to it."""

    def features(self, glob, patches, occ_mean, area, self_row=None):
        base = super().features(glob, patches, occ_mean, area, self_row)
        n = len(glob)
        extra = np.zeros((n, 4), np.float32)
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        for a in np.unique(area):
            q = np.where(area == a)[0]
            pool = self.rows.get(a)
            if pool is None or not len(pool):
                continue
            for i in q:
                tq = self.t[self_row[i]] if self_row[i] >= 0 else 10**9
                prev = pool[self.t[pool] < tq]
                if not len(prev):
                    extra[i] = (0, 0, 0, 0)
                    continue
                j = prev[np.argmax(self.t[prev])]
                s = float(glob[i] @ self.X[j] / 2)
                extra[i, self.y[j]] = s
                extra[i, 3] = 1
        return np.hstack([base, extra])


def variant(memory_cls=AreaMemory, design=None, name="v", C=None, recency=None, obstruct=None):
    cls = type(name, (Engine,), {"memory_cls": memory_cls})
    if design:
        cls._design = design
    if C is not None:
        cls.STOCK_C = C
    if recency is not None:
        cls.RECENCY_W = recency
    if obstruct is not None:
        cls.OBSTRUCT = obstruct
    return cls


def no_memory(self, glob, f, R):
    return np.hstack([glob, (f - self.occ_mu) / self.occ_sd * OCC_SCALE])


def no_glob(self, glob, f, R):
    return np.hstack([(f - self.occ_mu) / self.occ_sd, (R - self.mem_mu) / self.mem_sd])


def mem1(self, glob, f, R):
    return np.hstack([glob, (f - self.occ_mu) / self.occ_sd * OCC_SCALE, (R - self.mem_mu) / self.mem_sd * 1.0])


def mem(**kw):
    return type("M", (AreaMemory,), kw)


VARIANTS = {
    "pca64": variant(mem(PCA_DIM=64)),
    "pca128": variant(mem(PCA_DIM=128)),
    "pca256": variant(mem(PCA_DIM=256)),
    "refs4": variant(mem(MAX_REFS=4)),
    "refs6": variant(mem(MAX_REFS=6)),
    "pca128+refs6": variant(mem(PCA_DIM=128, MAX_REFS=6)),
    "C=10": variant(C=10.0),
    "C=30": variant(C=30.0),
    "engine": Engine,
    "no-memory": variant(design=no_memory),
    "no-glob": variant(design=no_glob),
    "mem-scale-1": variant(design=mem1),
    "sim": variant(SimMemory),
    "prev": variant(PrevMemory),
    "C=0.1": variant(C=0.1),
    "C=0.3": variant(C=0.3),
    "C=3": variant(C=3.0),
    "recency1": variant(recency=1.0),
    "recency3": variant(recency=3.0),
    "no-guard": variant(obstruct=(0.3, 0.7, 0.0)),
    "guard-hard": variant(obstruct=(0.2, 0.5, 0.9)),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    splits = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--split=")), "late,fwd").split(",")
    bank = dict(np.load(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--bank=")), "cache/bank.npz")))
    for name in args or list(VARIANTS):
        for split in splits:
            r, _ = evaluate(bank, "labels/silver_labels.txt", "labels/background_rects.txt", split, engine_cls=VARIANTS[name], verbose=False)
            show(name, r)


if __name__ == "__main__":
    main()
