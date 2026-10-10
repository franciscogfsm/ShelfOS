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
from sklearn.linear_model import LogisticRegression  # noqa: E402

from shelfos.engine import MEM_SCALE, OCC_SCALE, Engine, official  # noqa: E402
from shelfos.memory import AreaMemory  # noqa: E402
from shelfos.scoring import LEVELS, VALUES, decide_stock  # noqa: E402
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


_INNER = np.array([r * 14 + c for r in range(1, 13) for c in range(1, 13)])


class ChangeMemory(AreaMemory):
    """+ patch-for-patch change against the area's latest earlier frame (the cameras are fixed, so an
    unchanged patch means an unchanged shelf). Features: share of unchanged inner patches, that
    frame's level, and level x unchanged (a 'copy the last answer' vote that fades as the shelf changes)."""

    CHANGE_SIM = 0.7

    def features(self, glob, patches, occ_mean, area, self_row=None):
        base = super().features(glob, patches, occ_mean, area, self_row)
        n = len(glob)
        extra = np.zeros((n, 7), np.float32)
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        Pq = self.project(patches)
        for i in range(n):
            pool = self.rows.get(area[i])
            if pool is None or not len(pool):
                continue
            tq = self.t[self_row[i]] if self_row[i] >= 0 else 10**9
            prev = pool[self.t[pool] < tq]
            if not len(prev):
                continue
            j = prev[np.argmax(self.t[prev])]
            sim = np.einsum("pd,pd->p", Pq[i], np.asarray(self.P[j], np.float32))[_INNER]
            same = float((sim > self.CHANGE_SIM).mean())
            extra[i, 0] = same
            extra[i, 1] = float(sim.mean())
            extra[i, 2] = self.y[j] / 2
            extra[i, 3 + self.y[j]] = same
            extra[i, 6] = float(occ_mean[i] - self.occ[j])
        return np.hstack([base, extra])


class Change2Memory(ChangeMemory):
    """Same, against the two latest earlier frames (the nearer one weighs double)."""

    def features(self, glob, patches, occ_mean, area, self_row=None):
        base = AreaMemory.features(self, glob, patches, occ_mean, area, self_row)
        n = len(glob)
        extra = np.zeros((n, 7), np.float32)
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        Pq = self.project(patches)
        for i in range(n):
            pool = self.rows.get(area[i])
            if pool is None or not len(pool):
                continue
            tq = self.t[self_row[i]] if self_row[i] >= 0 else 10**9
            prev = pool[self.t[pool] < tq]
            if not len(prev):
                continue
            js = prev[np.argsort(self.t[prev])][-2:][::-1]
            ws = np.array([2.0, 1.0][: len(js)])
            ws /= ws.sum()
            for w, j in zip(ws, js):
                sim = np.einsum("pd,pd->p", Pq[i], np.asarray(self.P[j], np.float32))[_INNER]
                same = float((sim > self.CHANGE_SIM).mean())
                extra[i, 0] += w * same
                extra[i, 1] += w * float(sim.mean())
                extra[i, 2] += w * self.y[j] / 2
                extra[i, 3 + self.y[j]] += w * same
                extra[i, 6] += w * float(occ_mean[i] - self.occ[j])
        return np.hstack([base, extra])


class PairEngine(Engine):
    """Baseline + a pairwise 'less / same / more stock than that frame' comparator.

    For every pair of labelled crops of one area the comparator sees how the two crops differ
    patch for patch (the cameras are fixed) and learns the sign of the level difference. At
    inference the query is compared with every memorised frame of its area; the levels that
    are consistent with those verdicts get the probability mass, and this posterior is blended
    with the baseline in log space."""

    PAIR_W = 0.5
    PAIR_C = 1.0

    @staticmethod
    def _pair_feats(Pq, Pr, oq, orr, gq, gr):
        sim = np.einsum("pd,pd->p", Pq, Pr)[_INNER]
        return np.array([sim.mean(), (sim < 0.5).mean(), (sim < 0.7).mean(), oq - orr, oq / max(orr, 0.1) - 1, float(gq @ gr), oq, orr], np.float32)

    @classmethod
    def fit(cls, bank, labels_path, rects_path, rows=None):
        e = super().fit(bank, labels_path, rects_path, rows)
        m = e.memory
        Xp, yp = [], []
        for a, pool in m.rows.items():
            P = np.asarray(m.P[pool], np.float32)
            for ii, i in enumerate(pool):
                for jj, j in enumerate(pool):
                    if i == j:
                        continue
                    Xp.append(cls._pair_feats(P[ii], P[jj], m.occ[i], m.occ[j], m.X[i], m.X[j]))
                    yp.append(int(np.sign(m.y[i] - m.y[j])) + 1)
        Xp, yp = np.array(Xp), np.array(yp)
        e.pair_mu, e.pair_sd = Xp.mean(0), Xp.std(0) + 1e-6
        e.pair_clf = LogisticRegression(C=cls.PAIR_C, max_iter=3000).fit((Xp - e.pair_mu) / e.pair_sd, yp)
        return e

    def predict(self, glob, patches, thumbs, areas, fname=None):
        out = super().predict(glob, patches, thumbs, areas, fname)
        m = self.memory
        area = np.array([a.area_id for a in areas])
        self_row = m.rows_of(area, fname) if fname is not None else np.full(len(area), -1)
        Pq = m.project(patches)
        occ = np.array([d["occupancy"] for d in out])
        for i, d in enumerate(out):
            pool = m.rows.get(area[i])
            if pool is None:
                continue
            pool = pool[pool != self_row[i]]
            if not len(pool):
                continue
            F = np.stack([self._pair_feats(Pq[i], np.asarray(m.P[j], np.float32), occ[i], m.occ[j], glob[i], m.X[j]) for j in pool])
            pr = np.zeros((len(pool), 3))
            pr[:, self.pair_clf.classes_] = self.pair_clf.predict_proba((F - self.pair_mu) / self.pair_sd)
            pr = np.clip(pr, 1e-3, 1)
            logpost = np.zeros(3)
            for L in range(3):
                s = np.sign(L - m.y[pool]).astype(int) + 1
                logpost[L] = np.log(pr[np.arange(len(pool)), s]).mean()
            base = np.clip(np.array(d["stock_probs"]), 1e-4, 1)
            lp = np.log(base) + self.PAIR_W * (logpost - logpost.max())
            p = np.exp(lp - lp.max())
            p /= p.sum()
            lv = int(decide_stock(p))
            d.update(stock_probs=[round(float(x), 4) for x in p], stock_level=LEVELS[lv], stock_value=VALUES[lv])
            d.update(official(d, self.empty_compliant))
        return out


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
    "change": variant(ChangeMemory),
    "change2": variant(Change2Memory),
    "change-s6": variant(type("C6", (ChangeMemory,), {"CHANGE_SIM": 0.6})),
    "pair": PairEngine,
    "pair-w1": type("P1", (PairEngine,), {"PAIR_W": 1.0}),
    "pair-w025": type("P025", (PairEngine,), {"PAIR_W": 0.25}),
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
