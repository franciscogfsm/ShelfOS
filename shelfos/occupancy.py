"""Patch-level product/background model on DINOv3 patch tokens -> occupancy maps.

Trained from crop-level labels only: every patch of an 'empty' crop is background and
the central patches of a confidently 'full' crop are product. A few self-training rounds
then pull confident background out of stocked crops (crate floor next to product), which
is what stops the model from calling a whole crate 'product' because one bag sits in it.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression

GRID = 14
INNER = slice(1, GRID - 1)  # the padded border belongs to neighbours
CORE = slice(3, GRID - 3)
COLOR_WEIGHT = 0.35


def patch_colors(thumbs: np.ndarray) -> np.ndarray:
    """Mean and spread of Lab colour per patch, [N, GRID*GRID, 6]. Local, context-free evidence."""
    n, h, w, _ = thumbs.shape
    lab = np.stack([cv2.cvtColor(t, cv2.COLOR_BGR2LAB) for t in thumbs]).astype(np.float32) / 255
    ph, pw = h // GRID, w // GRID
    blocks = lab[:, : ph * GRID, : pw * GRID].reshape(n, GRID, ph, GRID, pw, 3)
    return np.concatenate([blocks.mean((2, 4)), blocks.std((2, 4))], -1).reshape(n, GRID * GRID, 6)


def patch_tokens(patches: np.ndarray, thumbs: np.ndarray) -> np.ndarray:
    """DINO patch tokens with the colour summary appended, [N, P, D + 6]."""
    return np.concatenate([patches.astype(np.float32), patch_colors(thumbs) * COLOR_WEIGHT], -1)


def _grid(p: np.ndarray) -> np.ndarray:
    return p.reshape(len(p), GRID, GRID, -1)


class PatchOccupancy:
    def __init__(self, C: float = 0.1, rounds: int = 3, seed: int = 0):
        self.C, self.rounds = C, rounds
        self.clf: LogisticRegression | None = None
        self.rng = np.random.default_rng(seed)

    def _fit_once(self, bg, fg, extra_bg, max_per_class=25000):
        bg = bg[self.rng.permutation(len(bg))[:max_per_class]]
        fg = fg[self.rng.permutation(len(fg))[:max_per_class]]
        if extra_bg is not None and len(extra_bg):
            # rare liners get as much total weight as the plentiful crate/shelf background
            bg = np.concatenate([bg, np.repeat(extra_bg, max(1, len(bg) // len(extra_bg)), axis=0)])
        X = np.concatenate([bg, fg])
        y = np.r_[np.zeros(len(bg)), np.ones(len(fg))]
        w = np.r_[np.full(len(bg), 0.5 / len(bg)), np.full(len(fg), 0.5 / len(fg))] * len(y)
        self.clf = LogisticRegression(C=self.C, max_iter=400).fit(X, y, sample_weight=w)

    def fit(self, tokens: np.ndarray, stock: np.ndarray, sure: np.ndarray, extra_bg: np.ndarray | None = None):
        """tokens [N, P, D'] from patch_tokens(); stock in {-1, 0, 1, 2}."""
        g = _grid(tokens)
        d = g.shape[-1]
        seed_bg = g[stock == 0][:, INNER, INNER].reshape(-1, d)
        seed_fg = g[(stock == 2) & sure][:, CORE, CORE].reshape(-1, d)
        self._fit_once(seed_bg, seed_fg, extra_bg)
        stocked = g[stock >= 1][:, INNER, INNER].reshape(-1, d)
        for _ in range(self.rounds - 1):
            p = self.clf.predict_proba(stocked)[:, 1]
            self._fit_once(np.concatenate([seed_bg, stocked[p < 0.15]]), stocked[p > 0.85], extra_bg)
        return self

    def maps(self, tokens: np.ndarray) -> np.ndarray:
        """[N, P, D'] -> product probability maps [N, GRID, GRID]."""
        n = len(tokens)
        return self.clf.predict_proba(tokens.reshape(-1, tokens.shape[-1]))[:, 1].reshape(n, GRID, GRID)


def load_background_rects(path, area: np.ndarray, t: np.ndarray, tokens: np.ndarray, exclude: np.ndarray | None = None) -> np.ndarray:
    """Collect patch tokens inside the hand-marked background rectangles (skipping held-out crops)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        spec, r0, r1, c0, c1 = line.split()
        a, ti = spec.split(":")
        idx = np.where((area == a) & (t == int(ti)))[0]
        if not len(idx) or (exclude is not None and exclude[idx[0]]):
            continue
        g = tokens[idx[0]].reshape(GRID, GRID, -1)
        out.append(g[int(r0) : int(r1) + 1, int(c0) : int(c1) + 1].reshape(-1, g.shape[-1]))
    return np.concatenate(out) if out else np.zeros((0, tokens.shape[-1]), np.float32)


def occupancy_features(maps: np.ndarray) -> np.ndarray:
    """Summaries of the inner occupancy map: mean, hard fraction, core mean, emptiest/fullest row band."""
    m = maps[:, INNER, INNER]
    hard = (m > 0.5).mean((1, 2))
    rows = m.mean(2)
    cols = m.mean(1)
    return np.stack(
        [m.mean((1, 2)), hard, maps[:, CORE, CORE].mean((1, 2)), rows.min(1), rows.max(1), cols.min(1), cols.max(1),
         np.sort(m.reshape(len(m), -1), 1)[:, : m[0].size // 4].mean(1)],
        1,
    )
