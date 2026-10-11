"""Cut an engine down to the cameras one shelf-side box serves (e.g. the camera over one fridge).

usage: python tools/edge_export.py --camera 6215[,6371] [--model models/engine_lite.pkl] [--out models/edge_6215.pkl]
       [--bank cache/bank_tta.npz]   (optional: proves the cut engine answers exactly like the full one)

The engine keeps every reference crop of every camera in memory (about 0.6 GB for the lite). An area
is only ever compared with its own earlier crops, so a box that serves one camera needs that camera's
crops only (lite: 655 MB -> 82 MB for one camera). Everything else (heads, product prototypes, camera signatures) is kept as is.
With --bank, the reference crops of those cameras are predicted with both engines and must agree exactly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.engine import Engine  # noqa: E402


def cut(engine: Engine, cameras: set[str]) -> Engine:
    m = engine.memory
    keep = np.array([a.split("_")[0] in cameras for a in m.area])
    if not keep.any():
        raise SystemExit(f"no reference crop of camera(s) {sorted(cameras)} in this engine")
    for name in ("X", "P", "occ", "y", "area", "fname", "t"):
        if getattr(m, name, None) is not None:
            setattr(m, name, getattr(m, name)[keep])
    m.rows = {a: np.where(m.area == a)[0] for a in np.unique(m.area)}
    m.__dict__.pop("_tP", None)
    c = engine.comply
    c.area_ok = {a: v for a, v in c.area_ok.items() if a.split("_")[0] in cameras}
    c.area_bad = {a: v for a, v in c.area_bad.items() if a.split("_")[0] in cameras}
    engine.last_seen = {a: v for a, v in engine.last_seen.items() if a.split("_")[0] in cameras}
    return engine


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--model", default="models/engine_lite.pkl")
    ap.add_argument("--out")
    ap.add_argument("--bank")
    a = ap.parse_args()
    cams = {c.strip() for c in a.camera.split(",") if c.strip()}
    out = Path(a.out or f"models/edge_{'_'.join(sorted(cams))}.pkl")
    small = cut(Engine.load(a.model), cams)
    small.save(out)
    print(f"{out}: {out.stat().st_size / 1e6:.0f} MB (full engine {Path(a.model).stat().st_size / 1e6:.0f} MB), "
          f"{len(small.memory.y)} reference crops of camera(s) {', '.join(sorted(cams))}")
    if a.bank:
        from types import SimpleNamespace

        b = np.load(a.bank)
        idx = np.where(np.isin(np.asarray(b["camera"]).astype(str), sorted(cams)))[0]
        areas = [SimpleNamespace(area_id=str(b["area"][i]), product_id=str(b["product"][i])) for i in idx]
        args = (b["glob"][idx], b["patches"][idx], b["thumbs"][idx], areas)
        full = Engine.load(a.model).predict(*args, fname=b["fname"][idx])
        mine = Engine.load(out).predict(*args, fname=b["fname"][idx])
        diff = sum(f["stock_probs"] != s["stock_probs"] or f["planogram_compliant"] != s["planogram_compliant"] for f, s in zip(full, mine))
        print(f"check on {len(idx)} reference crops: {diff} answers differ" + ("  -> identical" if diff == 0 else "  -> DO NOT USE"))
        if diff:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
