"""Temporal shelf memory: describe a crop relative to what the same area looked like earlier.

The cameras are fixed, so the rectified crops of one area are aligned patch for patch over
time. Comparing a crop with the area's own 'full' and 'empty' frames tells how much of the
shelf has changed without having to know the product, the crate or the liner.
"""
from __future__ import annotations

import numpy as np

N_FEATS = 10


def _norm(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


class AreaMemory:
    """Labelled crops of the reference day, grouped by planogram area."""

    PCA_DIM: int | None = None  # compress patch tokens to this many principal components (None = raw tokens)
    MAX_REFS: int | None = None  # compare with at most this many of the area's most recent full frames
    mean = basis = None

    def __init__(self, glob, patches, occ_mean, stock, area, fname=None, t=None):
        self.fname = None if fname is None else np.asarray(fname).astype(str)
        self.t = None if t is None else np.asarray(t).astype(int)
        self.X = glob.astype(np.float32)
        self.occ = occ_mean.astype(np.float32)
        self.y = stock.astype(int)
        self.area = np.asarray(area).astype(str)
        self.rows = {a: np.where(self.area == a)[0] for a in np.unique(self.area)}
        if self.PCA_DIM:
            rng = np.random.default_rng(0)
            flat = patches.reshape(-1, patches.shape[-1])
            sample = flat[rng.choice(len(flat), min(len(flat), 60000), replace=False)].astype(np.float32)
            self.mean = sample.mean(0)
            self.basis = np.linalg.svd(sample - self.mean, full_matrices=False)[2][: self.PCA_DIM].T.copy()
            self.P = np.concatenate([self.project(patches[i : i + 256]) for i in range(0, len(patches), 256)])
        else:
            self.P = patches.astype(np.float16)  # L2-normalised patch tokens [N, 196, D]

    def project(self, patches) -> np.ndarray:
        """Patch tokens in the space the memory compares them in (unit length)."""
        p = patches.astype(np.float32)
        if self.basis is not None:
            p = _norm((p - self.mean) @ self.basis)
        return p

    def remember(self, glob, patches, occ_mean, stock, area, fname=None, t=None) -> None:
        """Add crops whose level is now known (or trusted) to the memory."""
        n0 = len(self.y)
        self.X = np.concatenate([self.X, glob.astype(np.float32)])
        self.P = np.concatenate([self.P, self.project(patches).astype(self.P.dtype)])
        self.occ = np.concatenate([self.occ, np.asarray(occ_mean, np.float32)])
        self.y = np.concatenate([self.y, np.asarray(stock, int)])
        self.area = np.concatenate([self.area, np.asarray(area).astype(str)])
        if self.fname is not None:
            self.fname = np.concatenate([self.fname, np.broadcast_to(np.asarray("" if fname is None else fname).astype(str), (len(glob),))])
        if self.t is not None:
            self.t = np.concatenate([self.t, np.broadcast_to(np.asarray(self.t.max() + 1 if t is None else t), (len(glob),)).astype(int)])
        for i, a in enumerate(np.asarray(area).astype(str)):
            self.rows[a] = np.append(self.rows.get(a, np.zeros(0, int)), n0 + i).astype(int)

    def rows_of(self, area, fname) -> np.ndarray:
        """Memory row of each (area, image file) pair, -1 when that crop is not memorised."""
        area = np.asarray(area).astype(str)
        fname = np.broadcast_to(np.asarray(fname).astype(str), area.shape)
        out = np.full(len(area), -1)
        if self.fname is None:
            return out
        for i, (a, f) in enumerate(zip(area, fname)):
            pool = self.rows.get(a)
            if pool is not None:
                hit = pool[self.fname[pool] == f]
                if len(hit):
                    out[i] = hit[0]
        return out

    def features(self, glob, patches, occ_mean, area, self_row=None) -> np.ndarray:
        """[N, N_FEATS] for query crops. self_row[i] is the memory row of query i (or -1) so that
        a training crop is never compared with itself."""
        n = len(glob)
        out = np.zeros((n, N_FEATS), np.float32)
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        for a in np.unique(area):
            q = np.where(area == a)[0]
            pool = self.rows.get(a)
            if pool is None or not len(pool):
                out[q, 0], out[q, 2], out[q, 3], out[q, 4], out[q, 7], out[q, 9] = 0.6, 0.4, 0.8, 0.3, 1.0, 1.0
                continue
            full, emp = pool[self.y[pool] == 2], pool[self.y[pool] == 0]
            ref = full if len(full) else pool
            if self.MAX_REFS and len(ref) > self.MAX_REFS and self.t is not None:
                ref = ref[np.argsort(self.t[ref])][-self.MAX_REFS :]
            Pq = self.project(patches[q])
            is_self = self_row[q][:, None] == ref[None, :]
            if len(ref) < 2:
                is_self[:] = False
            w = (~is_self).astype(np.float32)
            mu = (w @ self.X[ref]) / w.sum(1, keepdims=True)
            sims = np.einsum("kpd,rpd->krp", Pq, np.asarray(self.P[ref], np.float32))
            sims[is_self] = -1
            sim_full = sims.max(1)
            out[q, 0] = sim_full.mean(1)
            out[q, 1] = (sim_full < 0.6).mean(1)
            out[q, 2] = np.sort(sim_full, 1)[:, :49].mean(1)
            out[q, 3] = np.sum(glob[q] * _norm(mu), 1)
            emp_self = self_row[q][:, None] == emp[None, :]
            if len(emp) >= 2 or (len(emp) == 1 and not emp_self.any()):
                se = np.einsum("kpd,rpd->krp", Pq, np.asarray(self.P[emp], np.float32))
                se[emp_self] = -1
                sim_emp = se.max(1)
                out[q, 4] = sim_emp.mean(1)
                out[q, 5] = (sim_emp > sim_full).mean(1)
                out[q, 6] = 1
            else:
                out[q, 4] = 0.3
                out[q, 5] = (sim_full < 0.5).mean(1)
            om = (w @ self.occ[ref]) / w.sum(1)
            out[q, 7] = occ_mean[q] / np.maximum(om, 0.15)
            out[q, 8] = occ_mean[q] - om
            # persistence: the level of the most similar earlier frame of this area
            S = glob[q] @ self.X[pool].T
            S[self_row[q][:, None] == pool[None, :]] = -9
            if len(pool) > 1 or not (self_row[q] >= 0).any():
                out[q, 9] = self.y[pool[S.argmax(1)]] / 2
        return out
