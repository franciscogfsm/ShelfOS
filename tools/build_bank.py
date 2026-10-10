"""Embed every (area, frame) of the unlabelled day into a feature bank.

usage: python tools/build_bank.py <planogram.json> <images_root> <out.npz> [model] [size] [--tta]

model may name an ensemble, e.g. "vit_base_patch16_dinov3.lvd1689m+vit_large_patch16_dinov3.lvd1689m".
--tta also embeds the mirrored crop and averages the two.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.bank import build_bank  # noqa: E402
from shelfos.features import CROP, MODEL_NAME  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plano, root, out = args[:3]
    build_bank(plano, root, out, args[3] if len(args) > 3 else MODEL_NAME, int(args[4]) if len(args) > 4 else CROP, tta="--tta" in sys.argv)
