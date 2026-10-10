"""Assemble a self-contained deployable copy of ShelfOS in release/.

    python tools/release.py [--out release] [--no-ui-build]

release/ holds exactly what the Dockerfile needs (code, model, backbone weights, planogram,
reference frames, built web UI) plus its own Dockerfile and a Hugging Face Space README, so it
can be pushed as-is to a Space (Docker SDK) or built anywhere with `docker build`.

Large files are listed in release/.gitattributes for git-lfs.
"""
from __future__ import annotations

import argparse
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SPACE_README = """---
title: ShelfOS
emoji: 🥑
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: true
license: mit
short_description: Fresh produce shelf monitoring (Sensei / JunctionX Lisbon 2026)
---

# ShelfOS

Drop ceiling-camera images (folders, loose files or a zip) and get, for every planogram area,
the stock level and whether the right product is there, in the official annotation format.

- `/` the app
- `/api/health`, `/docs` the API
"""


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "._*", ".DS_Store"))
    else:
        shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="release")
    ap.add_argument("--no-ui-build", action="store_true", help="reuse web/out instead of running `next build`")
    a = ap.parse_args()
    out = ROOT / a.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    engine_path = ROOT / "models" / "engine.pkl"
    if not engine_path.exists():
        sys.exit("models/engine.pkl is missing: run `python run.py --train` first")
    with open(engine_path, "rb") as fh:
        engine = pickle.load(fh)
    from shelfos.features import split_names

    names = split_names(engine.model_name or "vit_base_patch16_dinov3.lvd1689m")
    for n in names:
        w = ROOT / "models" / "backbone" / f"{n}.pt"
        if not w.exists():
            sys.exit(f"backbone weights {w} are missing: start the app once so they are downloaded")
        copy(w, out / "models" / "backbone" / w.name)
    copy(engine_path, out / "models" / "engine.pkl")
    copy(ROOT / "models" / "reference_day.json", out / "models" / "reference_day.json")
    copy(ROOT / "data" / "planogram.json", out / "data" / "planogram.json")
    copy(ROOT / "data" / "images", out / "data" / "images")

    if not a.no_ui_build:
        print("building the web interface ...")
        subprocess.run("npm run build", cwd=ROOT / "web", shell=True, check=True)
    if not (ROOT / "web" / "out" / "index.html").exists():
        sys.exit("web/out/index.html is missing: run `npm run build` inside web/")
    copy(ROOT / "web" / "out", out / "web" / "out")

    copy(ROOT / "shelfos", out / "shelfos")
    copy(ROOT / "run.py", out / "run.py")
    copy(ROOT / "requirements.txt", out / "requirements.txt")
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8").replace("COPY release/", "COPY ")
    (out / "Dockerfile").write_text(docker, encoding="utf-8")
    (out / ".dockerignore").write_text("**/__pycache__/\n.git/\n", encoding="utf-8")
    (out / "README.md").write_text(SPACE_README, encoding="utf-8")
    (out / ".gitattributes").write_text(
        "*.pkl filter=lfs diff=lfs merge=lfs -text\n*.pt filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n"
        "*.png filter=lfs diff=lfs merge=lfs -text\n*.woff2 filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"release/ ready: {size:.0f} MB, backbones {names}, engine {engine_path.stat().st_size / 1e6:.0f} MB")
    print("next: see DEPLOY.md")


if __name__ == "__main__":
    main()
