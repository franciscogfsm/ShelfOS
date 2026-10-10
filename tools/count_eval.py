"""Test the "Count units" button against hand counts, per product group, with the pass mark fixed in Plano.md.

A group may be switched on (shelfos/counting.py, ENABLED_GROUPS) only if it has at least 5 hand-counted areas and
at least 80% of them land within max(2, 15%) of the hand count. Calls the vision model once per area (a few cents).

usage: python tools/count_eval.py [--counts labels/unit_counts.txt] [--images data/images] [--planogram data/planogram.json]
       needs OPENROUTER_API_KEY in the environment or the project .env
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.assistant import config  # noqa: E402
from shelfos.counting import CountError, count_area, group_of  # noqa: E402
from shelfos.planogram import load_planogram  # noqa: E402

MIN_AREAS = 5
MIN_SHARE = 0.8
tolerance = lambda truth: max(2.0, 0.15 * truth)


def read_counts(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        area, frame, visible, partial, group, *note = (p.strip() for p in line.split("|"))
        rows.append(dict(area=area, frame=frame, visible=int(visible), partial=int(partial), group=group))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--counts", default="labels/unit_counts.txt")
    ap.add_argument("--images", default="data/images")
    ap.add_argument("--planogram", default="data/planogram.json")
    ap.add_argument("--model")
    a = ap.parse_args()
    key = config("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (environment or .env) first.")
    areas = {x.area_id: x for v in load_planogram(a.planogram).values() for x in v}
    by_group = defaultdict(list)
    for r in read_counts(a.counts):
        area = areas[r["area"]]
        cam = r["area"].split("_")[0]
        if group_of(area.product_name) != r["group"]:
            print(f"  note: {r['area']} is labelled {r['group']} but the code puts it in {group_of(area.product_name)}")
        try:
            out = count_area(Path(a.images) / cam / r["frame"], cam, r["frame"], area, key, a.model, cache_path=None)
            got, err = out["count"], out["count"] - r["visible"]
        except CountError as e:
            got, err = None, None
            print(f"  {r['area']}: no count ({e})")
        by_group[r["group"]].append((r, got, err))
        if got is not None:
            flag = "" if abs(err) <= tolerance(r["visible"]) else "   <-- outside tolerance"
            print(f"  {r['area']:8s} {r['group']:6s} hand {r['visible']:3d}  model {got:3d}  ({err:+d}){flag}")

    print("\ngroup   areas  within  median |error|  verdict")
    for g, rows in sorted(by_group.items()):
        errs = [abs(e) for _, _, e in rows if e is not None]
        ok = sum(1 for r, _, e in rows if e is not None and abs(e) <= tolerance(r["visible"]))
        share = ok / len(rows)
        med = sorted(errs)[len(errs) // 2] if errs else float("nan")
        verdict = "ENABLE" if len(rows) >= MIN_AREAS and share >= MIN_SHARE else "keep off"
        print(f"{g:7s} {len(rows):5d}  {100 * share:5.0f}%  {med:14.1f}  {verdict}")
    print(f"\npass mark: >= {MIN_AREAS} areas and >= {int(100 * MIN_SHARE)}% within max(2, 15%) of the hand count."
          "\nA failed count (model error, 'not countable') counts as outside. Put the ENABLE groups in ENABLED_GROUPS.")


if __name__ == "__main__":
    main()
