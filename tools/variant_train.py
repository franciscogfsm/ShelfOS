"""Train engine variants on the full reference day into models/edgecases/ for tools/edgecases.py.
Never touches production models.

    python tools/variant_train.py swap1-w03 swap2-w05 [--bank=cache/bank_bl.npz]
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shelfos.engine import Engine  # noqa: E402
from shelfos.features import CROP, MODEL_NAME  # noqa: E402
from tools.lab import VARIANTS  # noqa: E402


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    bank_path = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--bank=")), "cache/bank_bl.npz")
    bank = dict(np.load(bank_path))
    prod = Engine.load(ROOT / ("models/engine_lite.pkl" if "tta" in Path(bank_path).stem else "models/engine.pkl"))
    for name in names:
        e = VARIANTS[name].fit(bank, "labels/silver_labels.txt", "labels/background_rects.txt")
        e.model_name = str(bank["model"]) if "model" in bank else MODEL_NAME
        e.crop_size = int(bank["size"]) if "size" in bank else CROP
        e.tta = bool(bank["tta"]) if "tta" in bank else False
        e.cameras, e.frame_size = prod.cameras, prod.frame_size
        out = ROOT / "models" / "edgecases" / f"{name}.pkl"
        e.save(out)
        print(f"saved {out}", flush=True)


if __name__ == "__main__":
    main()