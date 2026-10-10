"""Build an edge-case manifest whose labels are the human review done in labeler/ (not the synthetic proposals).

    python tools/edge_manifest_from_labeler.py labeler/output/francisco_edge_annotations_reviewed.json \
        [more reviewed json...] --out ai_generated_edgecases/dataset_large/manifest_human.json

Only images that were reviewed are kept, all as split=test, so tools/edgecases.py scores exactly the human labels.
Where two reviewers labelled the same area and disagree, the area is dropped (and reported).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    srcs = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), "ai_generated_edgecases/dataset_large/manifest_human.json")
    base = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--manifest=")), "ai_generated_edgecases/dataset_large/manifest.json")
    manifest = json.loads((ROOT / base).read_text(encoding="utf-8"))
    by_stem = {Path(c["image"]).stem: c for c in manifest["cases"]}
    human: dict[str, dict[str, dict]] = {}  # stem -> area -> label
    conflicts = empty_fixed = 0
    for src in srcs:
        who = Path(src).stem.split("_")[0]
        data = json.loads((ROOT / src).read_text(encoding="utf-8"))
        for cam, frames in data.items():
            for stem, areas in frames.items():
                if stem not in by_stem:
                    print(f"skip {stem}: not in manifest")
                    continue
                for area, lab in areas.items():
                    ok = bool(lab["planogram_compliant"])
                    if lab["stock_level"] == "empty" and not ok:  # organiser rule: nothing to identify in an empty area
                        ok, empty_fixed = True, empty_fixed + 1
                    entry = {"stock_level": lab["stock_level"], "planogram_compliant": ok,
                             "scenario": by_stem[stem]["scenario"], "note": f"human review ({who})"}
                    prev = human.setdefault(stem, {}).get(area)
                    if prev is None:
                        human[stem][area] = entry
                    elif (prev["stock_level"], prev["planogram_compliant"]) != (entry["stock_level"], entry["planogram_compliant"]):
                        conflicts += 1
                        human[stem][area] = None
    cases = []
    for stem, labels in human.items():
        c = dict(by_stem[stem])
        c["labels"] = {a: l for a, l in labels.items() if l is not None}
        c["split"] = "test"
        c["reviewed"] = True
        cases.append(c)
    n_areas = sum(len(c["labels"]) for c in cases)
    new = dict(manifest, cases=cases, purpose="Human-reviewed edge-case labels (labeler/); test only, never train.",
               notes=[f"built from {', '.join(srcs)}", f"{len(cases)} images, {n_areas} labelled areas, {conflicts} reviewer conflicts dropped"])
    (ROOT / out).write_text(json.dumps(new, indent=2), encoding="utf-8")
    print(f"wrote {out}: {len(cases)} images, {n_areas} areas, {conflicts} conflicts dropped, {empty_fixed} empty areas forced compliant")


if __name__ == "__main__":
    main()
