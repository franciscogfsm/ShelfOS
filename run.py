"""ShelfOS in one command.

    python run.py                         open the app at http://localhost:8000
    python run.py --images <folder|zip>   no interface: write predictions.json in the official format
    python run.py --train                 rebuild the model from data/images and labels/

The first start builds the model from the reference day (about a minute on a GPU).

options
    --out FILE              where --images writes the predictions (default predictions.json)
    --empty-noncompliant    report empty areas as planogram_compliant=false (default: true)
    --port N                port of the app (default 8000)
    --lan                   also reachable from other devices on the same network
    --no-browser            do not open the browser
    --cpu                   do not use the GPU
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CWD = Path.cwd()  # where the command was typed: relative --images / --out are meant from there
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

BANK, MODEL, REFERENCE = Path("cache/bank_bl.npz"), Path("models/engine.pkl"), Path("models/reference_day.json")
PLANOGRAM, IMAGES = Path("data/planogram.json"), Path("data/images")
# Shipped configuration: DINOv3 ViT-B + ViT-L ensemble with mirror TTA (best in cross-validation).
# A lighter ViT-B-only engine for CPU-only hosts is trained with
#   python -m shelfos.train --bank cache/bank_tta.npz --out models/engine_lite.pkl --reference models/reference_day_lite.json
BACKBONES = "vit_base_patch16_dinov3.lvd1689m+vit_large_patch16_dinov3.lvd1689m"


def typed_path(p: str, must_exist: bool = False) -> str:
    """A relative path is taken from where the command was typed; an input that is only found in the repo keeps working."""
    q = Path(p.strip().strip('"'))
    if q.is_absolute() or (must_exist and not (CWD / q).exists() and q.exists()):
        return str(q)
    return str(CWD / q)


def ensure_model(force: bool = False, reference: bool = True) -> None:
    """Embed the reference day and fit the engine if that has not been done on this machine yet.
    reference=False: the caller only needs the engine (--images never reads the reference day)."""
    if MODEL.exists() and (REFERENCE.exists() or not reference) and not force:
        return
    if not PLANOGRAM.exists() or not IMAGES.is_dir():
        sys.exit(f"The reference day is missing. Put the challenge images in {IMAGES}/<camera>/<timestamp>.jpg and the planogram in {PLANOGRAM}.")
    if force or not BANK.exists():
        from shelfos.bank import build_bank

        print("Embedding the reference day ...")
        build_bank(PLANOGRAM, IMAGES, BANK, model_name=BACKBONES, tta=True)
    from shelfos.train import train

    print("Fitting the engine ...")
    train(str(BANK), images=str(IMAGES), planogram=str(PLANOGRAM), out=str(MODEL), reference=str(REFERENCE))


def predict(a) -> None:
    from shelfos.predict import run

    t0 = time.time()
    service, events = run(a.images, str(MODEL), str(PLANOGRAM), empty_compliant=not a.empty_noncompliant, device="cpu" if a.cpu else None)
    pred = service.predictions("run")
    out = Path(a.out)
    if not pred:
        sys.exit(f"\nNo image in {a.images} was answered (see above), so {out} was not written.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pred, indent=1), encoding="utf-8")
    n_img = sum(len(v) for v in pred.values())
    n_area = sum(len(x) for v in pred.values() for x in v.values())
    skipped = [e for e in events if e["type"] in ("skip", "error")]
    warned = [e for e in events if e["type"] == "frame" and e["warnings"]]
    print(f"\n{out.resolve()}\n{n_img} images, {n_area} areas, {time.time() - t0:.1f}s on {service.embedder.device}"
          f"{f', {len(skipped)} files skipped' if skipped else ''}{f', {len(warned)} images with warnings' if warned else ''}")
    print(f"empty areas reported as planogram_compliant={'false' if a.empty_noncompliant else 'true'}")
    from shelfos.validate import expected_images, validate

    problems = validate(pred, service.areas, expected_images(a.images, set(service.areas)))
    if problems:  # reported, not fatal: the file is written and one of the notes is harmless
        print(f"\nWARNING: {len(problems)} problem(s) with the submission file:")
        for p in problems[:50]:
            print("  -", p)
    else:
        print("validated: official format, every area of every image answered")


def serve(a) -> None:
    import uvicorn

    from shelfos.server import create_app
    from shelfos.service import ShelfService

    built = ROOT / "web" / "out" / "index.html"
    if built.exists() and any(p.stat().st_mtime > built.stat().st_mtime for p in (ROOT / "web" / "app").rglob("*") if p.is_file()):
        print("NOTE: the built interface (web/out) is older than web/app. Run `npm run build` inside web/ to see the latest screens.")
    print("Loading the model ...")
    service = ShelfService(str(MODEL), str(PLANOGRAM), str(REFERENCE), str(IMAGES), device="cpu" if a.cpu else None, empty_compliant=not a.empty_noncompliant)
    app = create_app(service, ROOT / "web" / "out")
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    url = f"http://localhost:{a.port}"
    print(f"\nShelfOS is ready on {service.embedder.device}: {url}")
    if a.lan:
        try:
            print(f"On this network: http://{socket.gethostbyname(socket.gethostname())}:{a.port}")
        except OSError:
            pass
    if not a.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=host, port=a.port, log_level="warning")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images")
    ap.add_argument("--out", default="predictions.json")
    ap.add_argument("--empty-noncompliant", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--cpu", action="store_true")
    a = ap.parse_args()
    if a.images:
        a.images, a.out = typed_path(a.images, must_exist=True), typed_path(a.out)
        if not Path(a.images).exists():
            sys.exit(f"--images: nothing at {a.images}")
    ensure_model(force=a.train, reference=not a.images)
    if a.images:
        predict(a)
    elif not a.train:
        serve(a)


if __name__ == "__main__":
    main()
