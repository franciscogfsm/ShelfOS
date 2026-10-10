# Large edge-case dataset

119 full synthetic camera images, including 96 new AI-generated images, plus 6 real source photographs in `reference_sources/` for visual comparison. References are not scored. Images are grouped by split and scenario under `images/`. Open `index.html` to browse and filter; click an image for the original full resolution. No pixels are changed by the assembly script. Where supported, image paths are hard links to their saved source files to avoid doubling disk use; treat this collection as read-only and save any edits into separate files.

`manifest.json` records image path, camera, original source family, generation prompt, hash, dimensions, review status and labels. `inventory.json` records actual counts. **Use `benchmark_manifest.json` for scoring:** its 65 images have all 806 areas visually reviewed for stock and compliance. Standalone image/label pairs are in `benchmark/images/` and `benchmark/labels/`. These are local Codex visual judgements, not official or independently human-adjudicated ground truth. Mentor agreement on half/full remains necessary before claiming official accuracy.

`excluded_cases.json` explains each rejected case: closed blind, occlusion, single-item boundary uncertainty, or older partial review. Excluded images remain available as raw diagnostic inputs. Prompts were not used as ground truth. `bulk_visual_annotations.json` in the parent folder preserves the review decisions, and `VISUAL_REVIEW.md` describes observed generation deviations.

Many images share six real frames. This gives scenario coverage, not 119 independent scenes. Production may know these real frames; use separate real temporal holdouts to judge deployment gains. Four previous TRAIN references are kept in `images/train`, never mixed into TEST scores. Keep all variants of one source family in one split when extending training.

Rebuild the folder and gallery from saved outputs:

```powershell
python tools/build_edgecase_dataset.py
```

Run inference using the existing evaluator (new images are prediction-only until reviewed):

```powershell
python tools/edgecases.py --manifest ai_generated_edgecases/dataset_large/benchmark_manifest.json --out outputs/edgecases_large_labelled
```

The existing reviewed benchmark and Fable brief remain in the parent folder. Existing benchmarks do not automatically include new cases. Do not train on this test folder; create a separate reviewed training set and compare against fixed tests first.
