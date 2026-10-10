"""Official Sensei scoring and the score-optimal decision rule.

Per area:  identification  +1 correct / -2 wrong
           stock level     +1 correct / -2 predicted below truth / -3 predicted above truth
An annotated area missing from the output costs -2 and -3.
"""
from __future__ import annotations

import numpy as np

LEVELS = ("empty", "half", "full")
VALUES = (0.0, 0.5, 1.0)

# STOCK_PAYOFF[pred, truth]
STOCK_PAYOFF = np.array(
    [
        [1, -2, -2],  # predict empty
        [-3, 1, -2],  # predict half
        [-3, -3, 1],  # predict full
    ],
    float,
)
ID_PAYOFF = np.array([[1, -2], [-2, 1]], float)  # [pred, truth], index 1 = compliant


def stock_points(pred_value: float, true_value: float) -> int:
    if abs(pred_value - true_value) < 1e-6:
        return 1
    return -2 if pred_value < true_value else -3


def id_points(pred: bool, truth: bool) -> int:
    return 1 if bool(pred) == bool(truth) else -2


def decide_stock(probs: np.ndarray) -> np.ndarray:
    """probs [..., 3] over (empty, half, full) -> level index maximising expected official score."""
    return np.argmax(probs @ STOCK_PAYOFF.T, axis=-1)


def decide_compliant(p_compliant: np.ndarray) -> np.ndarray:
    """Symmetric +1/-2 payoff, so the best call is simply the more likely one."""
    return np.asarray(p_compliant) >= 0.5


def score_submission(pred: dict, truth: dict) -> dict:
    """Score a prediction file against an annotation file (both in the official nested format)."""
    out = {"id_correct": 0, "id_wrong": 0, "stock_correct": 0, "stock_below": 0, "stock_above": 0, "missing": 0, "areas": 0}
    for cam, images in truth.items():
        for fname, areas in images.items():
            for area_id, t in areas.items():
                out["areas"] += 1
                p = pred.get(cam, {}).get(fname, {}).get(area_id)
                if p is None:
                    out["missing"] += 1
                    out["id_wrong"] += 1
                    out["stock_above"] += 1
                    continue
                out["id_correct" if bool(p["planogram_compliant"]) == bool(t["planogram_compliant"]) else "id_wrong"] += 1
                s = stock_points(float(p["stock_value"]), float(t["stock_value"]))
                out[{1: "stock_correct", -2: "stock_below", -3: "stock_above"}[s]] += 1
    out["score"] = out["id_correct"] - 2 * out["id_wrong"] + out["stock_correct"] - 2 * out["stock_below"] - 3 * out["stock_above"]
    out["max"] = 2 * out["areas"]
    return out
