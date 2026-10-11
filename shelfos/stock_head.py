"""Ordered stock probabilities for the opt-in Shelf Lite stock head."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier


class OrdinalStockHead:
    """Learn P(stock > empty) and P(stock > half), with ordered probabilities.

    The class vocabulary and predict_proba contract match the existing stock head,
    so the official cost-sensitive decision and obstruction guard remain in use.
    """

    classes_ = np.array([0, 1, 2])

    def fit(self, x, y, sample_weight=None):
        self.models = []
        for threshold in (0, 1):
            model = HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                l2_regularization=5.0, min_samples_leaf=30, random_state=0,
            )
            self.models.append(model.fit(x, y > threshold, sample_weight=sample_weight))
        return self

    def predict_proba(self, x):
        present, full = [model.predict_proba(x)[:, 1] for model in self.models]
        # Project crossing estimates onto the constraint P(full) <= P(nonempty).
        crossing = full > present
        midpoint = (present + full) / 2
        present = np.where(crossing, midpoint, present)
        full = np.where(crossing, midpoint, full)
        return np.column_stack([1 - present, present - full, full])
