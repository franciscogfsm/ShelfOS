"""Silver label loading. These are our own annotations, not the official ground truth."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STOCK = {"E": 0.0, "H": 0.5, "F": 1.0}
LEVELS = ("empty", "half", "full")
VALUES = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class Label:
    stock: int | None  # index into LEVELS, None = unlabeled
    stock_sure: bool
    comply: bool | None  # None = nothing to judge (empty/covered) or unlabeled
    comply_sure: bool


def load_labels(path: str | Path) -> dict[str, list[Label]]:
    """Return {area_id: [Label per frame, in timestamp order]}."""
    out: dict[str, list[Label]] = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        area, stock, comply = (p.strip() for p in line.split("|"))
        if len(stock) != len(comply):
            raise ValueError(f"{area}: stock/comply length mismatch")
        labels = []
        for s, c in zip(stock, comply):
            si = "EHF".index(s.upper()) if s.upper() in "EHF" else None
            ci = {"T": True, "F": False}.get(c.upper())
            labels.append(Label(si, s.isupper(), ci, c.isupper()))
        out[area] = labels
    return out
