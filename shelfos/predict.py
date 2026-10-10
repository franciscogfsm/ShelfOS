"""Run ShelfOS on a folder of camera images and write the official submission file.

usage: python -m shelfos.predict --images <folder> --out predictions.json
       [--model models/engine.pkl] [--planogram data/planogram.json] [--details details.json]
       [--empty-noncompliant] [--cpu]

The folder may be laid out as <folder>/<camera>/<file>.jpg, or hold loose files (the camera
is then recognised from the picture), or be a .zip. Every planogram area of every image
gets a prediction, so nothing is scored as missing.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .service import ShelfService


def run(images, model="models/engine.pkl", planogram="data/planogram.json", empty_compliant=True, device=None, verbose=True):
    """-> (service, list of events). The run is kept in memory only."""
    service = ShelfService(model, planogram, reference_path=None, run_dir=Path("runs") / "cli", device=device, empty_compliant=empty_compliant)
    service.reset()
    events = []
    for ev in service.analyze_folder(str(images)):
        events.append(ev)
        if not verbose:
            continue
        if ev["type"] == "frame":
            note = f"  ! {'; '.join(ev['warnings'])}" if ev["warnings"] else ""
            print(f"  cam {ev['camera']}  {ev['file']}  {len(ev['frame']['areas'])} areas  {ev['ms']} ms{note}")
        elif ev["type"] in ("skip", "error"):
            print(f"  skipped {ev.get('file', '')}: {ev.get('reason') or ev.get('message')}")
    return service, events


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="models/engine.pkl")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--details", help="also write per-area evidence (probabilities, occupancy maps)")
    ap.add_argument("--empty-noncompliant", action="store_true", help="report empty areas as planogram_compliant=false")
    ap.add_argument("--cpu", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    service, events = run(a.images, a.model, a.planogram, empty_compliant=not a.empty_noncompliant, device="cpu" if a.cpu else None)
    pred = service.predictions("run")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(pred, indent=1), encoding="utf-8")
    if a.details:
        Path(a.details).write_text(json.dumps(service.run), encoding="utf-8")
    n_img = sum(len(v) for v in pred.values())
    n_area = sum(len(x) for v in pred.values() for x in v.values())
    print(f"wrote {a.out}: {n_img} images, {n_area} areas, {time.time() - t0:.1f}s on {service.embedder.device}")
    from .validate import expected_images, validate

    problems = validate(json.loads(Path(a.out).read_text(encoding="utf-8")), service.areas, expected_images(a.images, set(service.areas)))
    if problems:
        print(f"\nWARNING: {len(problems)} problem(s) with the submission file:")
        for p in problems[:50]:
            print("  -", p)
        raise SystemExit(1)
    print("validated: official format, every area of every image answered")


if __name__ == "__main__":
    main()
