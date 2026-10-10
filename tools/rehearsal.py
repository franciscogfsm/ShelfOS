"""Full dress rehearsal of the official submission, end to end.

    python tools/rehearsal.py [--per-camera 2] [--zip] [--keep]

Builds a fake validation set shaped like the real one (the last N frames of every camera,
14 cameras x 2 = 28 images, the official one has 26), runs the exact command the jury will
run (``python run.py --images <folder> --out predictions.json``), validates the output with
shelfos.validate, and scores it against the human annotations for those frames.

The score is optimistic because the engine has seen these frames in training; the point of
this script is to prove the whole chain works (folder and zip inputs, file names, every area
answered, official JSON shape) before the real folder arrives.  Everything lives in
cache/rehearsal/ and is removed at the end unless --keep is given.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shelfos.planogram import load_planogram  # noqa: E402
from shelfos.scoring import score_submission  # noqa: E402
from shelfos.validate import expected_images, summary, validate  # noqa: E402

IMAGES = ROOT / "data" / "images"
PLANOGRAM = ROOT / "data" / "planogram.json"
TRUTH = ROOT / "labeler" / "output" / "merged_annotations.json"
WORK = ROOT / "cache" / "rehearsal"


def build_fake_validation(per_camera: int) -> tuple[Path, dict]:
    """Copy the last `per_camera` frames of every camera into WORK/images and cut the matching truth."""
    truth_all = json.loads(TRUTH.read_text(encoding="utf-8"))
    out_dir = WORK / "images"
    if WORK.exists():
        shutil.rmtree(WORK)
    truth: dict = {}
    for cam_dir in sorted(p for p in IMAGES.iterdir() if p.is_dir()):
        frames = sorted(p for p in cam_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        for f in frames[-per_camera:]:
            (out_dir / cam_dir.name).mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out_dir / cam_dir.name / f.name)
            t = truth_all.get(cam_dir.name, {}).get(f.name)
            if t:
                truth.setdefault(cam_dir.name, {})[f.name] = t
    (WORK / "annotations.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    return out_dir, truth


def make_zip(folder: Path) -> Path:
    """Zip the folder the way organisers usually do: a wrapping directory plus macOS debris."""
    zpath = WORK / "validation.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in folder.rglob("*"):
            if p.is_file():
                zf.write(p, f"validation/{p.relative_to(folder).as_posix()}")
        zf.writestr("__MACOSX/validation/._x.jpg", b"debris")
        zf.writestr("validation/notes.txt", "not an image")
    return zpath


def run_official(images: Path, out: Path) -> float:
    t0 = time.time()
    cmd = [sys.executable, "run.py", "--images", str(images), "--out", str(out)]
    print(f"\n$ {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    sys.stdout.write(r.stdout[-1500:])
    if r.returncode != 0:
        sys.stdout.write(r.stderr[-3000:])
        sys.exit(f"run.py failed with exit code {r.returncode}")
    return time.time() - t0


def check(pred_path: Path, images: Path, truth: dict, label: str) -> bool:
    pred = json.loads(pred_path.read_text(encoding="utf-8-sig"))
    planogram = load_planogram(PLANOGRAM)
    problems = validate(pred, planogram, expected_images(images, set(planogram)))
    print(f"\n[{label}] {summary(pred)}")
    ok = not problems
    if problems:
        print(f"  {len(problems)} problem(s):")
        for p in problems[:30]:
            print("   -", p)
    else:
        print("  format OK: valid official JSON, every area of every image answered")
    s = score_submission(pred, truth)
    print(f"  score vs human labels: {s['score']} / {s['max']} ({100 * s['score'] / s['max']:.1f}%)  "
          f"stock exact {s['stock_correct']} below {s['stock_below']} above {s['stock_above']} | "
          f"id right {s['id_correct']} wrong {s['id_wrong']} | missing {s['missing']}")
    if s["missing"]:
        ok = False
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-camera", type=int, default=2)
    ap.add_argument("--zip", action="store_true", help="also hand the images in as a zip")
    ap.add_argument("--keep", action="store_true", help="leave cache/rehearsal/ in place")
    a = ap.parse_args()
    if not TRUTH.exists():
        sys.exit(f"{TRUTH} missing: run  python labeler/app.py --merge rodrigo francisco")

    folder, truth = build_fake_validation(a.per_camera)
    n_img = sum(len(v) for v in truth.values())
    n_area = sum(len(x) for v in truth.values() for x in v.values())
    print(f"fake validation set: {len(truth)} cameras, {n_img} images, {n_area} areas -> {folder}")

    ok = True
    dt = run_official(folder, WORK / "predictions.json")
    print(f"  {dt:.0f}s wall clock")
    ok &= check(WORK / "predictions.json", folder, truth, "folder")

    if a.zip:
        z = make_zip(folder)
        dt = run_official(z, WORK / "predictions_zip.json")
        print(f"  {dt:.0f}s wall clock")
        ok &= check(WORK / "predictions_zip.json", z, truth, "zip")
        same = json.loads((WORK / "predictions.json").read_text()) == json.loads((WORK / "predictions_zip.json").read_text())
        print(f"  zip and folder give identical predictions: {same}")
        ok &= same

    if not a.keep:
        shutil.rmtree(WORK, ignore_errors=True)
    print("\nREHEARSAL OK" if ok else "\nREHEARSAL FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
