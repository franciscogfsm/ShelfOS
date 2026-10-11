"""ShelfOS engine: fit on the reference day's feature bank, predict any image of a known camera."""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from .camera_id import CameraIdentifier
from .compliance import ComplianceModel
from .labels import load_labels
from .memory import NOVEL, AreaMemory
from .occupancy import PatchOccupancy, load_background_rects, occupancy_features, patch_tokens
from .planogram import Area
from .scoring import ID_PAYOFF, LEVELS, STOCK_PAYOFF, VALUES, decide_stock

OCC_SCALE = 0.5
MEM_SCALE = 0.5
OBSTRUCT_FROM = 0.30  # share of never-seen patches from which an area counts as partly obstructed
OBSTRUCT_FULL = 0.70  # ... and from which the discount is complete
OBSTRUCT_DISCOUNT = 0.6  # at most this much of P(full) is removed


def bank_labels(bank, labels_path):
    """Align silver labels to bank rows -> stock, stock_sure, comply, comply_sure."""
    labels = load_labels(labels_path)
    n = len(bank["area"])
    y, ys, c, cs = np.full(n, -1), np.zeros(n, bool), np.full(n, -1), np.zeros(n, bool)
    for i, (a, t) in enumerate(zip(bank["area"], bank["t"])):
        lab = labels[str(a)][int(t)]
        if lab.stock is not None:
            y[i], ys[i] = lab.stock, lab.stock_sure
        if lab.comply is not None:
            c[i], cs[i] = int(lab.comply), lab.comply_sure
    return y, ys, c, cs


def capture_times(fname, n: int):
    """Unix capture time of each crop from its image file name (e.g. 1751052241.jpg), None when the
    name is not a timestamp; the memory then treats the crop as later than everything it holds."""
    if fname is None:
        return None
    names = np.broadcast_to(np.asarray(fname).astype(str), (n,))
    out = []
    for s in names:
        stem = Path(s).stem
        out.append(int(stem) if stem.isdigit() and len(stem) >= 9 else None)
    return out


def hour_features(fname, n: int) -> np.ndarray:
    """[n, 2] time-of-day prior from the capture time: hour of day (Lisbon, centred on 13h, in units of
    6h) and an 'evening' ramp from 17h on. On the reference day the share of full areas falls from 90%
    mid-morning to 73% after 18h and the share of empties rises; the same day-cycle is expected on the
    validation day. Unknown capture time -> zeros (the mid-day prior)."""
    out = np.zeros((n, 2), np.float32)
    times = capture_times(fname, n)
    if times is None:
        return out
    for i, t in enumerate(times):
        if t is None:
            continue
        h = (t % 86400) / 3600 + 1  # UTC+1 (Lisbon summer time is a 1h shift either way; what matters is the cycle)
        out[i, 0] = np.clip((h - 13) / 6, -1.5, 1.5)
        out[i, 1] = np.clip((h - 17) / 3, 0, 1.5)
    return out


def p_identity(pred: dict, empty_compliant: bool = True) -> float:
    """P(planogram_compliant is annotated true), integrating over the stock uncertainty: with
    probability P(empty) there is nothing to identify and the convention for empty areas decides,
    otherwise the product model does."""
    pe = pred["stock_probs"][0]
    return pe * (1.0 if empty_compliant else 0.0) + (1 - pe) * pred["p_compliant"]


def official(pred: dict, empty_compliant: bool = True) -> dict:
    """The three fields of the official annotation format."""
    lv = LEVELS.index(pred["stock_level"])
    return {"planogram_compliant": bool(p_identity(pred, empty_compliant) >= 0.5), "stock_level": LEVELS[lv], "stock_value": VALUES[lv]}


@dataclass
class Engine:
    occ: PatchOccupancy = None
    stock_clf: LogisticRegression = None
    comply: ComplianceModel = None
    occ_mu: np.ndarray = None
    occ_sd: np.ndarray = None
    memory: AreaMemory = None  # labelled crops of the reference day, per area
    mem_mu: np.ndarray = None
    mem_sd: np.ndarray = None
    last_seen: dict = field(default_factory=dict)  # area -> (stock probs, P(compliant)) at the end of the reference day
    cameras: CameraIdentifier = None
    frame_size: tuple = (1280, 720)
    empty_compliant: bool = True
    model_name: str = ""
    crop_size: int = 224
    tta: bool = False  # the bank was embedded with mirror averaging, so new crops must be too
    glob_mean: np.ndarray = None  # PCA of the appearance embedding for the stock head (None = raw)
    glob_basis: np.ndarray = None
    memory_cls = AreaMemory  # not dataclass fields: swapped by experiments
    STOCK_HEAD = "hgb"  # 'hgb' gradient-boosted trees | 'logreg' logistic regression
    # (k, weight, max prototype sim): per labelled crop, k real crops of a visually different catalogue product are added as
    # non-compliant examples of this area. Fixes the synthetic "bananas in the tomato crate" case; neutral on the real-frame CV.
    COMPLY_SWAP = (1, 0.3, 0.85)
    GLOB_DIM: int | None = 32  # compress the appearance embedding to this many components in the stock head
    OCC_SCALE = OCC_SCALE
    MEM_SCALE = MEM_SCALE
    OCC_C = 0.2  # inverse regularisation of the patch product/background classifier (CV: late +0.618->+0.655, fwd +0.748->+0.766)
    STOCK_C = 1.0
    RECENCY_W = 0.0
    HOUR_SCALE = 0.0  # time-of-day prior off: organisers said the model must learn from the image, not the time of day (cost measured: late -0.5pp, fwd -0.1pp)
    ONLINE = False  # remember each predicted frame so the next frame of the same camera is compared with it
    ONLINE_MIN_CONF = 0.0  # ... but only crops whose level is at least this certain

    # ---- training -------------------------------------------------------------------------
    @classmethod
    def fit(cls, bank, labels_path, rects_path, rows: np.ndarray | None = None, *, stock_head: str | None = None) -> "Engine":
        """rows: boolean mask of the bank rows the engine may learn from (default: all)."""
        if stock_head not in (None, "ordinal"):
            raise ValueError(f"Unknown stock head: {stock_head}")
        y, ys, c, cs = bank_labels(bank, labels_path)
        n = len(y)
        rows = np.ones(n, bool) if rows is None else np.asarray(rows, bool)
        y, c = np.where(rows, y, -1), np.where(rows, c, -1)
        X, area, product = bank["glob"], bank["area"].astype(str), bank["product"].astype(str)
        tok = patch_tokens(bank["patches"], bank["thumbs"])
        e = cls()
        e.occ = PatchOccupancy(C=cls.OCC_C).fit(tok[rows], y[rows], ys[rows], extra_bg=load_background_rects(rects_path, area, bank["t"], tok, exclude=~rows))
        f = occupancy_features(e.occ.maps(tok))
        m = y >= 0
        e.occ_mu, e.occ_sd = f[m].mean(0), f[m].std(0) + 1e-6
        e.memory = cls.memory_cls(X[m], bank["patches"][m], f[m, 0], y[m], area[m], fname=bank["fname"][m], t=bank["t"][m])
        R = e.memory.features(X[m], bank["patches"][m], f[m, 0], area[m], self_row=np.arange(m.sum()))
        e.mem_mu, e.mem_sd = R.mean(0), R.std(0) + 1e-6
        sw = np.where(ys[m], 1.0, 0.5)
        if cls.RECENCY_W:  # frames from later in the day weigh more: validation images are expected late in the day
            t = bank["t"].astype(float)
            last = np.array([t[bank["camera"] == c].max() for c in bank["camera"]])
            sw = sw * (1.0 + cls.RECENCY_W * (t[m] / np.maximum(last[m], 1.0)))
        H = hour_features(bank["fname"][m], int(m.sum()))
        if cls.GLOB_DIM:
            e.glob_mean = X[m].mean(0)
            e.glob_basis = np.linalg.svd(X[m] - e.glob_mean, full_matrices=False)[2][: cls.GLOB_DIM].T.copy()
        if stock_head == "ordinal":
            from .stock_head import OrdinalStockHead
            classifier = OrdinalStockHead()
        else:
            classifier = cls.make_stock_clf()
        e.stock_head_name = stock_head or cls.STOCK_HEAD
        e.stock_clf = classifier.fit(e._design(X[m], f[m], R, H), y[m], sample_weight=sw)
        e.comply = ComplianceModel().fit(X, area, product, c, y >= 1, weight=np.where(cs, 1.0, 0.5), swap=cls.COMPLY_SWAP)
        e.last_seen = cls._last_seen(area, bank["t"], y, c, e.comply.prior)
        return e

    @staticmethod
    def _last_seen(area, t, y, c, prior):
        """What each area looked like in its last labelled frames: the fallback when an image is unreadable."""
        out = {}
        for a in np.unique(area):
            idx = np.where((area == a) & (y >= 0))[0]
            idx = idx[np.argsort(t[idx])][-2:]
            p = np.full(3, 0.1)
            for w, i in zip((0.3, 0.6)[-len(idx):], idx):
                p[y[i]] += w
            ci = [c[i] for i in idx if c[i] >= 0]
            out[str(a)] = ((p / p.sum()).tolist(), float(np.mean(ci)) if ci else float(prior))
        return out

    @classmethod
    def make_stock_clf(cls):
        """Gradient-boosted trees over the compact design (STOCK_HEAD='hgb', the default) or a logistic
        regression on the raw design ('logreg'). In cross-validation on the human labels the trees cut the
        costly over-estimations by a third (evening split +0.546 -> +0.641 pts/area; forward +0.711 -> +0.748)."""
        if cls.STOCK_HEAD == "logreg":
            return LogisticRegression(C=cls.STOCK_C, max_iter=3000)
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=5.0, min_samples_leaf=30, random_state=0)

    def _glob(self, glob):
        basis = getattr(self, "glob_basis", None)
        return glob if basis is None else (glob - self.glob_mean) @ basis

    def _design(self, glob, f, R, H=None):
        """Stock-level feature matrix: appearance ++ occupancy summaries ++ area-relative memory features
        ++ time-of-day prior."""
        H = np.zeros((len(glob), 2), np.float32) if H is None else H
        return np.hstack([self._glob(glob), (f - self.occ_mu) / self.occ_sd * self.OCC_SCALE, (R - self.mem_mu) / self.mem_sd * self.MEM_SCALE, H * self.HOUR_SCALE])

    # ---- inference ------------------------------------------------------------------------
    def predict(self, glob, patches, thumbs, areas: list[Area], fname=None) -> list[dict]:
        """One dict per crop: official fields plus the evidence behind them.

        fname: image file name(s) of the crops. A crop that is itself part of the memorised
        reference day is never used as evidence for its own prediction.
        """
        area = np.array([a.area_id for a in areas])
        product = np.array([a.product_id for a in areas])
        if self.ONLINE and fname is not None:
            times = capture_times(fname, len(areas))
            stamps = sorted({t for t in times if t is not None})
            if len(stamps) > 1:  # several moments in one batch: walk them in time order, each informing the next
                return self._predict_online(glob, patches, thumbs, areas, fname, times, stamps)
        self_row = self.memory.rows_of(area, fname) if fname is not None else np.full(len(area), -1)
        maps = self.occ.maps(patch_tokens(patches, thumbs))
        f = occupancy_features(maps)
        R = self.memory.features(glob, patches, f[:, 0], area, self_row, t_query=capture_times(fname, len(area)))
        probs = np.zeros((len(glob), 3))
        probs[:, self.stock_clf.classes_] = self.stock_clf.predict_proba(self._design(glob, f, R, hour_features(fname, len(area))))
        novelty = R[:, NOVEL] if R.shape[1] > NOVEL else np.zeros(len(glob))
        probs = self._obstruction_guard(probs, novelty)
        level = decide_stock(probs)
        p_ok = self.comply.predict(glob, area, product, known=self_row >= 0)
        looks = self.comply.identify(glob)
        out = []
        for i in range(len(areas)):
            lv = int(level[i])
            out.append(self._finish({
                "stock_level": LEVELS[lv],
                "stock_value": VALUES[lv],
                "stock_probs": [round(float(x), 4) for x in probs[i]],
                "p_compliant": round(float(p_ok[i]), 4),
                "occupancy": round(float(f[i, 0]), 4),
                "occupancy_map": np.round(maps[i], 2).tolist(),
                "looks_like": [[pid, round(s, 3)] for pid, s in looks[i]],
                "obstruction": round(float(novelty[i]), 3),
                "source": "image",
            }))
        return out

    def _predict_online(self, glob, patches, thumbs, areas, fname, times, stamps) -> list[dict]:
        """Predict one capture time after another; every predicted frame is remembered before the next
        one, then the memory is restored so the engine stays stateless between calls."""
        n0 = len(self.memory)
        fname = np.broadcast_to(np.asarray(fname).astype(str), (len(areas),))
        out: list = [None] * len(areas)
        try:
            for s in stamps + [None]:
                idx = [i for i, t in enumerate(times) if t == s]
                if not idx:
                    continue
                res = self.predict(glob[idx], patches[idx], thumbs[idx], [areas[i] for i in idx], fname=fname[idx])
                for i, d in zip(idx, res):
                    out[i] = d
                if s is not None:
                    self.observe(glob[idx], patches[idx], [areas[i] for i in idx], res, fname=fname[idx])
        finally:
            self.memory.forget(n0)
        return out

    def observe(self, glob, patches, areas, details: list[dict], fname=None) -> None:
        """Remember freshly predicted crops (at their predicted level) as the latest state of their areas,
        so that the next frame of the same camera is compared with them rather than with the reference day."""
        probs = np.array([d["stock_probs"] for d in details])
        keep = (probs.max(1) >= self.ONLINE_MIN_CONF) & np.array([d.get("source", "image") == "image" for d in details])
        if not keep.any():
            return
        area = np.array([a.area_id for a in areas])[keep]
        level = np.array([LEVELS.index(d["stock_level"]) for d in details])[keep]
        occ = np.array([d["occupancy"] for d in details])[keep]
        fn = None if fname is None else np.broadcast_to(np.asarray(fname).astype(str), (len(areas),))[keep]
        self.memory.remember(glob[keep], patches[keep], occ, level, area, fname=fn)

    OBSTRUCT = (OBSTRUCT_FROM, OBSTRUCT_FULL, OBSTRUCT_DISCOUNT)

    def _obstruction_guard(self, probs: np.ndarray, novelty: np.ndarray) -> np.ndarray:
        """Something that was never on this shelf covers part of the area (a shopper, a cart, boxes, a
        night cloth, a foreign product). What is under it cannot be seen, so the evidence for 'full'
        is discounted in proportion and the expected-score rule answers on the low side (over-estimating
        costs 3, under-estimating 2)."""
        lo, hi, discount = self.OBSTRUCT
        if not discount:
            return probs
        p = probs.copy()
        k = np.clip((novelty - lo) / (hi - lo), 0, 1)
        p[:, 2] *= 1 - k * discount
        return p / p.sum(1, keepdims=True)

    def fallback(self, areas: list[Area]) -> list[dict]:
        """No usable image: answer from what each area looked like at the end of the reference day,
        so that nothing is ever missing from the output (a missing area costs -5 points)."""
        out = []
        for a in areas:
            probs, p_ok = self.last_seen.get(a.area_id, ([0.1, 0.5, 0.4], self.comply.prior if self.comply else 0.95))
            lv = int(decide_stock(np.array(probs)))
            out.append(self._finish({
                "stock_level": LEVELS[lv], "stock_value": VALUES[lv], "stock_probs": [round(float(x), 4) for x in probs],
                "p_compliant": round(float(p_ok), 4), "occupancy": 0.0, "occupancy_map": [], "looks_like": [], "obstruction": 0.0, "source": "memory",
            }))
        return out

    def _finish(self, d: dict) -> dict:
        d.update(official(d, self.empty_compliant))
        p_true = p_identity(d, self.empty_compliant)
        lv = LEVELS.index(d["stock_level"])
        d["expected_points"] = round(float(np.array(d["stock_probs"]) @ STOCK_PAYOFF[lv] + ID_PAYOFF[int(d["planogram_compliant"])] @ [1 - p_true, p_true]), 3)
        return d

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(path) -> "Engine":
        with open(path, "rb") as fh:
            return pickle.load(fh)
