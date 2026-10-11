"""Check a predictions file against the official format before it leaves the building.

    python -m shelfos.validate predictions.json [--images <folder or zip>] [--planogram data/planogram.json]

Catches every way a submission can silently lose points: an area, image or camera that is
missing (-5 per area), unknown area ids, levels that do not match values, strings where
booleans should be, image names that do not match the files handed in.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from .planogram import load_planogram
from .scoring import LEVELS, VALUES

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".webp", ".tif", ".tiff", ".jp2"}  # same set in service.py


def expected_images(images: str | Path, cameras: set[str]) -> dict[str, set[str]]:
    """{camera: {image file name}} for a folder laid out as <camera>/<file> or a zip of it."""
    root = Path(images)
    out: dict[str, set[str]] = {}
    names: list[str] = []
    if root.is_file() and root.suffix.lower() == ".zip":
        with zipfile.ZipFile(root) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
    elif root.is_dir():
        names = [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()]
    for n in names:
        parts = n.split("/")
        base = parts[-1]
        if Path(base).suffix.lower() not in IMAGE_EXT or base.startswith("._") or "__MACOSX" in n:
            continue
        cam = next((p for p in reversed(parts[:-1]) if p in cameras), None)
        if cam is None:
            hits = [c for c in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", Path(base).stem) if c in cameras]
            cam = hits[0] if len(set(hits)) == 1 else None
        if cam is None:  # a folder that carries the id among other text: cam_6215
            for p in reversed(parts[:-1]):
                hits = {c for c in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", p) if c in cameras}
                if len(hits) == 1:
                    cam = hits.pop()
                    break
        if cam is not None:
            out.setdefault(cam, set()).add(base)
    return out


def validate(pred: dict, planogram: dict, images: dict[str, set[str]] | None = None) -> list[str]:
    """-> list of problems ([] = ready to submit)."""
    problems: list[str] = []
    if not isinstance(pred, dict):
        return ["top level is not an object {camera: {...}}"]
    area_ids = {cam: {a.area_id for a in areas} for cam, areas in planogram.items()}
    for cam, files in pred.items():
        if cam not in area_ids:
            problems.append(f"camera {cam!r} is not in the planogram")
            continue
        if not isinstance(files, dict):
            problems.append(f"camera {cam}: expected {{image: {{area: ...}}}}")
            continue
        for fname, areas in files.items():
            if not isinstance(areas, dict):
                problems.append(f"{cam}/{fname}: expected {{area_id: {{...}}}}")
                continue
            missing = area_ids[cam] - set(areas)
            extra = set(areas) - area_ids[cam]
            if missing:
                problems.append(f"{cam}/{fname}: {len(missing)} area(s) missing (-5 each): {', '.join(sorted(missing))}")
            if extra:
                problems.append(f"{cam}/{fname}: unknown area id(s): {', '.join(sorted(extra))}")
            for aid, v in areas.items():
                if not isinstance(v, dict):
                    problems.append(f"{cam}/{fname}/{aid}: not an object")
                    continue
                for k in ("planogram_compliant", "stock_level", "stock_value"):
                    if k not in v:
                        problems.append(f"{cam}/{fname}/{aid}: missing {k}")
                if not isinstance(v.get("planogram_compliant"), bool):
                    problems.append(f"{cam}/{fname}/{aid}: planogram_compliant must be a JSON boolean, got {v.get('planogram_compliant')!r}")
                lv = v.get("stock_level")
                if lv not in LEVELS:
                    problems.append(f"{cam}/{fname}/{aid}: stock_level must be one of {LEVELS}, got {lv!r}")
                sv = v.get("stock_value")
                if isinstance(sv, bool) or not isinstance(sv, (int, float)):
                    problems.append(f"{cam}/{fname}/{aid}: stock_value must be a number, got {sv!r}")
                elif lv in LEVELS and abs(float(sv) - VALUES[LEVELS.index(lv)]) > 1e-9:
                    problems.append(f"{cam}/{fname}/{aid}: stock_value {sv} does not match stock_level {lv}")
    if images:
        for cam, names in images.items():
            got = set(pred.get(cam, {}))
            for n in sorted(names - got):
                problems.append(f"{cam}/{n}: image handed in but absent from the predictions (-5 per area)")
        for cam, files in pred.items():
            for n in files:
                if cam in images and n not in images[cam]:
                    problems.append(f"{cam}/{n}: predicted but no such image was handed in (harmless, but check the names)")
    return problems


def summary(pred: dict) -> str:
    n_img = sum(len(v) for v in pred.values())
    n_area = sum(len(x) for v in pred.values() for x in v.values())
    levels = {lv: 0 for lv in LEVELS}
    bad = 0
    for v in pred.values():
        for x in v.values():
            for a in x.values():
                if isinstance(a, dict):
                    levels[a.get("stock_level", "?")] = levels.get(a.get("stock_level", "?"), 0) + 1
                    bad += a.get("planogram_compliant") is False
    return f"{len(pred)} cameras, {n_img} images, {n_area} areas; stock {levels}; {bad} non-compliant"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("predictions")
    ap.add_argument("--images", help="the folder or zip the predictions were made from")
    ap.add_argument("--planogram", default="data/planogram.json")
    a = ap.parse_args()
    try:
        pred = json.loads(Path(a.predictions).read_text(encoding="utf-8-sig"))
    except ValueError as e:
        sys.exit(f"INVALID JSON: {e}")
    planogram = load_planogram(a.planogram)
    images = expected_images(a.images, set(planogram)) if a.images else None
    problems = validate(pred, planogram, images)
    print(summary(pred))
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems[:200]:
            print("  -", p)
        sys.exit(1)
    print("OK: valid official format, every area of every image answered")


if __name__ == "__main__":
    main()
