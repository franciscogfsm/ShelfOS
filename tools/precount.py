"""Fill the "Count units" cache for the demo, so the button answers instantly and without a network.

Counts every area of an enabled product group (shelfos/counting.py) in the latest frame of each camera, or in
every frame with --all. Results land in runs/counts.json, the same cache the server reads. Already cached
answers are not asked again.

usage: python tools/precount.py [--images data/images] [--planogram data/planogram.json] [--all]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.assistant import config  # noqa: E402
from shelfos.counting import CountError, count_area, countable  # noqa: E402
from shelfos.planogram import list_images, load_planogram  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", default="data/images")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--all", action="store_true", help="every frame, not only the latest of each camera")
    a = ap.parse_args()
    key = config("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (environment or .env) first.")
    areas = load_planogram(a.planogram)
    asked = cached = failed = 0
    for cam, files in list_images(a.images).items():
        targets = [a for a in areas.get(cam, []) if countable(a.product_name)]
        if not targets:
            continue
        for f in files if a.all else files[-1:]:
            for area in targets:
                try:
                    out = count_area(f, cam, f.name, area, key)
                except CountError as e:
                    failed += 1
                    print(f"  {area.area_id} {f.name}: {e}")
                    continue
                cached += out["cached"]
                asked += not out["cached"]
                print(f"  {area.area_id} {f.name}: {out['count']} {out['unit']}(s){' (cached)' if out['cached'] else ''}")
    print(f"done: {asked} asked, {cached} already cached, {failed} failed")


if __name__ == "__main__":
    main()
