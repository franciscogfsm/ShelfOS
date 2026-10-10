"""Planogram compliance from product prototypes in DINOv3 space.

A crop is compared with the prototype of the product its area expects, with every other
product's prototype, and with what this same area looked like when it was known compliant.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

SELF = 0.9999  # a crop compared with its own stored copy


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


class ComplianceModel:
    def __init__(self, C: float = 1.0):
        self.C = C
        self.protos: dict[str, np.ndarray] = {}
        self.area_ok: dict[str, np.ndarray] = {}
        self.area_bad: dict[str, np.ndarray] = {}
        self.clf: LogisticRegression | None = None
        self.prior = 0.95

    def _build(self, X, area, product, comply, stocked):
        ok = (comply == 1) & stocked
        self.protos = {str(p): _unit(X[ok & (product == p)].mean(0)) for p in np.unique(product[ok])}
        self.area_ok = {str(a): X[ok & (area == a)] for a in np.unique(area[ok])}
        bad = (comply == 0) & stocked
        self.area_bad = {str(a): X[bad & (area == a)] for a in np.unique(area[bad])}
        self._names = list(self.protos)
        self._P = np.stack([self.protos[n] for n in self._names]) if self._names else np.zeros((0, X.shape[1]), np.float32)

    @staticmethod
    def _best(history, xi, known: bool, default: float) -> float:
        """Highest similarity to the area's history, never counting the crop's own stored copy."""
        if history is None or not len(history):
            return default
        s = history @ xi
        if known:
            s = s[s < SELF]
        return float(s.max()) if len(s) else default

    def _feats(self, X, area, product, known: np.ndarray | None = None) -> np.ndarray:
        """known[i] = crop i is itself part of the stored history (training crops, reference frames)."""
        sims = _unit(X) @ self._P.T
        out = np.zeros((len(X), 6), np.float32)
        for i in range(len(X)):
            exp = self._names.index(str(product[i])) if str(product[i]) in self.protos else -1
            s_exp = sims[i, exp] if exp >= 0 else 0.0
            others = np.delete(sims[i], exp) if exp >= 0 else sims[i]
            s_oth = others.max() if len(others) else 0.0
            xi = X[i] / 2  # glob is two unit vectors concatenated
            k = bool(known[i]) if known is not None else False
            s_ok = self._best(self.area_ok.get(str(area[i])), xi, k, 0.5)
            s_bad = self._best(self.area_bad.get(str(area[i])), xi, k, 0.3)
            out[i] = (s_exp, s_oth, s_exp - s_oth, s_ok, s_bad, s_ok - s_bad)
        return out

    def fit(self, X, area, product, comply, stocked, weight=None):
        """comply in {-1 unknown, 0 other product, 1 expected product}; stocked = not empty."""
        self._build(X, area, product, comply, stocked)
        m = (comply >= 0) & stocked
        F = self._feats(X[m], area[m], product[m], known=np.ones(m.sum(), bool))
        self.prior = float(comply[m].mean())
        self.clf = LogisticRegression(C=self.C, class_weight="balanced", max_iter=1000).fit(F, comply[m], sample_weight=None if weight is None else weight[m])
        return self

    def predict(self, X, area, product, known: np.ndarray | None = None) -> np.ndarray:
        """P(compliant | something is on the shelf), re-weighted from the balanced fit to the true prior."""
        p = self.clf.predict_proba(self._feats(X, area, product, known))[:, 1]
        odds = p / (1 - p + 1e-9) * self.prior / (1 - self.prior)
        return odds / (1 + odds)

    def identify(self, X, top: int = 3) -> list[list[tuple[str, float]]]:
        """Which catalogue products each crop looks like most: [(product_id, similarity), ...]."""
        if not self._names:
            return [[] for _ in X]
        sims = _unit(X) @ self._P.T
        order = np.argsort(-sims, 1)[:, :top]
        return [[(self._names[j], float(sims[i, j])) for j in row] for i, row in enumerate(order)]
