"""Bundle predictions, planogram geometry and frames for the ShelfOS web app.

usage: python tools/export_web.py <details.json> <planogram.json> <images_root> <web/public>
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import list_images, load_planogram  # noqa: E402

SMALL = {"CNT", "KG", "IMP", "CAT", "I", "EMB.", "EMB", "SC", "INT", "R0", "CAL", "CAL.", "IGP", "P/", "S/", "A/AA", "A/AA/AAA", "EMB:."}


def pretty(name: str) -> str:
    """'BANANA CAT I CNT KG' -> 'Banana'; keeps pack sizes and varieties, drops catalogue codes."""
    words = [w for w in name.split() if w.upper() not in SMALL and "/" not in w]
    return " ".join(w if any(ch.isdigit() for ch in w) else w.capitalize() for w in words) or name.title()


def main():
    details_path, plano_path, images_root, public = sys.argv[1:5]
    details = json.loads(Path(details_path).read_text(encoding="utf-8"))
    areas = load_planogram(plano_path)
    images = list_images(images_root)
    cams = []
    for cam, files in images.items():
        if cam not in details:
            continue
        frames = []
        for f in files:
            pred = details[cam].get(f.name)
            if pred is None:
                continue
            dst = Path(public) / "frames" / cam / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copyfile(f, dst)
            frames.append(
                {
                    "file": f.name,
                    "ts": int(f.stem),
                    "areas": {
                        aid: {
                            "ok": p["planogram_compliant"],
                            "level": p["stock_level"],
                            "probs": [round(x, 3) for x in p["stock_probs"]],
                            "pOk": round(p["p_compliant"], 3),
                            "occ": round(p["occupancy"], 3),
                            "map": [[round(v, 1) for v in row] for row in p["occupancy_map"]],
                        }
                        for aid, p in pred.items()
                    },
                }
            )
        cams.append(
            {
                "id": cam,
                "areas": [
                    {"id": a.area_id, "productId": a.product_id, "product": pretty(a.product_name), "rawName": a.product_name,
                     "quad": [[round(float(x), 1), round(float(y), 1)] for x, y in a.quad]}
                    for a in areas[cam]
                ],
                "frames": frames,
            }
        )
    out = Path(public) / "data" / "store.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"store": "Continente Bom Dia S. Romão, Leiria", "section": "Frutas e Legumes", "width": 1280, "height": 720, "cameras": cams}), encoding="utf-8")
    print(f"{out}: {len(cams)} cameras, {sum(len(c['frames']) for c in cams)} frames, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
