"""Cross-validated compliance score on the silver labels (stocked crops with a T/F label).

usage: python tools/experiment_compliance.py <bank.npz> <labels.txt> [split=lofo|late]
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.compliance import ComplianceModel  # noqa: E402
from shelfos.scoring import ID_PAYOFF  # noqa: E402
from tools.experiment import folds, load  # noqa: E402


def main():
    bank, labels = sys.argv[1:3]
    split = sys.argv[3] if len(sys.argv) > 3 else "lofo"
    b, y, ys, c, cs = load(bank, labels)
    X, area, product = b["glob"], b["area"], b["product"]
    p = np.full(len(c), np.nan)
    for te in folds(b, split):
        tr = ~te
        ctr = np.where(tr, c, -1)
        m = ComplianceModel().fit(X, area, product, ctr, (y >= 1) & tr, weight=np.where(cs, 1.0, 0.5))
        p[te] = m.predict(X[te], area[te], product[te])
    ev = ~np.isnan(p) & (c >= 0) & (y >= 1)
    for tag, mk in (("all", ev), ("sure", ev & cs)):
        pred = (p[mk] >= 0.5).astype(int)
        pts = ID_PAYOFF[pred, c[mk]]
        base = ID_PAYOFF[1, c[mk]]
        fa = np.sum((pred == 0) & (c[mk] == 1))
        miss = np.sum((pred == 1) & (c[mk] == 0))
        print(f"split={split} {tag:4s} n={mk.sum()} wrong-product={np.sum(c[mk] == 0)} acc={np.mean(pred == c[mk]):.3f} "
              f"pts/area={pts.mean():+.3f} (always-true {base.mean():+.3f}) false-alarms={fa} missed={miss}")
    bad = np.where(ev & ((p >= 0.5).astype(int) != c))[0]
    for i in bad[:60]:
        print(f"   {area[i]:8s} t{b['t'][i]:<2d} label={'T' if c[i] else 'F'}{'' if cs[i] else '?'} p={p[i]:.2f}")


if __name__ == "__main__":
    main()
