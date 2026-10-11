"""Temporal shelf memory: describe a crop relative to what the same area looked like earlier.

The cameras are fixed, so the rectified crops of one area are aligned patch for patch over
time. Comparing a crop with the area's own 'full' and 'empty' frames tells how much of the
shelf has changed without having to know the product, the crate or the liner.
"""
from __future__ import annotations

import numpy as np
import torch

N_BASE = 11
N_CHANGE = 7
N_FEATS = N_BASE + N_CHANGE
NOVEL_SIM = 0.5  # a patch that matches no earlier frame of its area better than this is something new on the shelf
NOVEL = 10  # index of the novelty feature: the share of such patches (people, carts, boxes, cloth, foreign product)
CHANGE_SIM = 0.7  # a patch at least this similar to the same patch of the previous frame has not changed
CHANGE_REFS = 2  # compare with this many of the latest earlier frames (the nearest weighs double)


_GRID = 14
_INNER = np.array([r * _GRID + c for r in range(1, _GRID - 1) for c in range(1, _GRID - 1)])  # the padded border belongs to neighbours


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

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != "_tP"}  # the tensor copy is rebuilt on demand

    def to(self, device) -> "AreaMemory":
        """Compare patches on this torch device ('cuda' keeps the memory's patch tokens on the GPU)."""
        self.device = str(device)
        self.__dict__.pop("_tP", None)
        return self

    def _tokens(self) -> torch.Tensor:
        """self.P as a tensor on self.device, built once (and again after remember/forget)."""
        cached = self.__dict__.get("_tP")
        if cached is None or cached[0] is not self.P:
            dev = getattr(self, "device", "cpu")
            cached = self._tP = (self.P, torch.from_numpy(np.ascontiguousarray(self.P)).to(dev))
        return cached[1]

    def _sims(self, Pq: np.ndarray, rows) -> np.ndarray:
        """Cosine similarity of aligned patches, [k, P, D] queries x memory rows -> [k, len(rows), P] (float32).
        On the CPU this is the original einsum on float32 copies. With .to("cuda") the memory's tokens stay
        on the GPU and this is one batched matmul there (same numbers up to float32 rounding, about 4e-7)."""
        if getattr(self, "device", "cpu") == "cpu":
            return np.einsum("kpd,rpd->krp", Pq, np.asarray(self.P[rows], np.float32))
        T = self._tokens()
        q = torch.from_numpy(np.ascontiguousarray(Pq, np.float32)).to(T.device)
        r = T[torch.as_tensor(np.array(rows, np.int64), device=T.device)].float()
        return torch.bmm(q.transpose(0, 1), r.permute(1, 2, 0)).permute(1, 2, 0).cpu().numpy()

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

    def __len__(self) -> int:
        return len(self.y)

    def forget(self, n0: int) -> None:
        """Drop everything remembered after the first n0 crops (undo remember())."""
        if len(self.y) <= n0:
            return
        self.X, self.P, self.occ, self.y, self.area = self.X[:n0], self.P[:n0], self.occ[:n0], self.y[:n0], self.area[:n0]
        if self.fname is not None:
            self.fname = self.fname[:n0]
        if self.t is not None:
            self.t = self.t[:n0]
        self.rows = {a: r[r < n0] for a, r in self.rows.items()}
        self.rows = {a: r for a, r in self.rows.items() if len(r)}

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

    def features(self, glob, patches, occ_mean, area, self_row=None, t_query=None) -> np.ndarray:
        """[N, N_FEATS] for query crops. self_row[i] is the memory row of query i (or -1) so that
        a training crop is never compared with itself. t_query[i] is the capture time of query i
        (None: the query is later than everything memorised)."""
        base = self._base_features(glob, patches, occ_mean, area, self_row)
        return np.hstack([base, self._change_features(glob, patches, occ_mean, area, self_row, t_query)])

    def _change_features(self, glob, patches, occ_mean, area, self_row, t_query) -> np.ndarray:
        """What changed since the area's latest earlier frames. The cameras are fixed, so a patch that
        still matches the same patch of the previous frame is an unchanged piece of shelf. Returns, per
        crop: share of unchanged inner patches, mean patch similarity, level of that frame, level
        one-hot x unchanged share (a 'same as before' vote that fades as the shelf changes), and the
        occupancy difference. The errors this targets are shelves that were full an hour ago and have
        since been half emptied: the appearance still says 'full', the change says otherwise."""
        n = len(glob)
        out = np.zeros((n, N_CHANGE), np.float32)
        if self.t is None:
            return out
        area = np.asarray(area).astype(str)
        self_row = np.full(n, -1) if self_row is None else np.asarray(self_row)
        Pq = self.project(patches)
        for i in range(n):
            pool = self.rows.get(area[i])
            if pool is None or not len(pool):
                continue
            if self_row[i] >= 0:
                tq = self.t[self_row[i]]
            elif t_query is not None and t_query[i] is not None:
                tq = int(t_query[i])
            else:
                tq = 10**9
            prev = pool[(self.t[pool] < tq) & (pool != self_row[i])]
            if not len(prev):  # earlier than anything memorised: use the nearest frames instead
                prev = pool[pool != self_row[i]]
                if not len(prev):
                    continue
                prev = prev[np.argsort(np.abs(self.t[prev] - tq))][::-1]
            js = prev[np.argsort(self.t[prev])][-CHANGE_REFS:][::-1]
            ws = np.array([2.0, 1.0][: len(js)])
            ws /= ws.sum()
            sims = self._sims(Pq[i : i + 1], js)[0]
            for w, j, sim in zip(ws, js, sims):
                sim = sim[_INNER]
                same = float((sim > CHANGE_SIM).mean())
                out[i, 0] += w * same
                out[i, 1] += w * float(sim.mean())
                out[i, 2] += w * self.y[j] / 2
                out[i, 3 + self.y[j]] += w * same
                out[i, 6] += w * float(occ_mean[i] - self.occ[j])
        return out

    def _base_features(self, glob, patches, occ_mean, area, self_row=None) -> np.ndarray:
        n = len(glob)
        out = np.zeros((n, N_BASE), np.float32)
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
            sims = self._sims(Pq, ref)
            sims[is_self] = -1
            sim_full = sims.max(1)
            out[q, 0] = sim_full.mean(1)
            out[q, 1] = (sim_full < 0.6).mean(1)
            out[q, 2] = np.sort(sim_full, 1)[:, :49].mean(1)
            out[q, 3] = np.sum(glob[q] * _norm(mu), 1)
            emp_self = self_row[q][:, None] == emp[None, :]
            sim_emp = None
            if len(emp) >= 2 or (len(emp) == 1 and not emp_self.any()):
                se = self._sims(Pq, emp)
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
            # novelty: inner patches that look like nothing this area has shown all day, at any stock level
            rest = pool[~np.isin(pool, ref) & ~np.isin(pool, emp)]
            best = sim_full if sim_emp is None else np.maximum(sim_full, sim_emp)
            if len(rest):
                sr = self._sims(Pq, rest)
                sr[self_row[q][:, None] == rest[None, :]] = -1
                best = np.maximum(best, sr.max(1))
            out[q, NOVEL] = (best[:, _INNER] < NOVEL_SIM).mean(1)
            # persistence: the level of the most similar earlier frame of this area
            S = glob[q] @ self.X[pool].T
            S[self_row[q][:, None] == pool[None, :]] = -9
            if len(pool) > 1 or not (self_row[q] >= 0).any():
                out[q, 9] = self.y[pool[S.argmax(1)]] / 2
        return out
