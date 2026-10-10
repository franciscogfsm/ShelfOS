"""Fill the "Count units" cache for the demo, so the button answers instantly and without a network.

Counts every area of an enabled product group (shelfos/counting.py) in the latest frame of each camera, or in
every frame with --all. Results land in runs/counts.json, the same cache the server reads. Already cached
answers are not asked again.

usage: python tools/precount.py [--images data/images] [--planogram data/planogram.json] [--all]
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
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
    ap.add_argument("--workers", type=int, default=3, choices=range(1, 5), help="parallel requests (1-4, default 3)")
    a = ap.parse_args()
    key = config("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (environment or .env) first.")
    areas = load_planogram(a.planogram)
    asked = cached = failed = 0
    jobs = [(cam, f, area) for cam, files in list_images(a.images).items()
            for f in (files if a.all else files[-1:])
            for area in areas.get(cam, []) if countable(area.product_name)]
    def run(job):
        cam, f, area = job
        try:
            return job, count_area(f, cam, f.name, area, key), None
        except CountError as e:
            return job, None, str(e)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for (_, f, area), out, error in pool.map(run, jobs):
            if error is not None:
                failed += 1
                print(f"  {area.area_id} {f.name}: {error}")
                continue
            cached += out["cached"]
            asked += not out["cached"]
            print(f"  {area.area_id} {f.name}: {out['count']} {out['unit']}(s){' (cached)' if out['cached'] else ''}")
    print(f"done: {asked} asked, {cached} already cached, {failed} failed")


if __name__ == "__main__":
    main()
