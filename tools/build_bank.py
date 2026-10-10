"""Embed every (area, frame) of the unlabelled day into a feature bank.

usage: python tools/build_bank.py <planogram.json> <images_root> <out.npz> [model] [size]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.bank import build_bank  # noqa: E402
from shelfos.features import CROP, MODEL_NAME  # noqa: E402

if __name__ == "__main__":
    plano, root, out = sys.argv[1:4]
    build_bank(plano, root, out, sys.argv[4] if len(sys.argv) > 4 else MODEL_NAME, int(sys.argv[5]) if len(sys.argv) > 5 else CROP)
