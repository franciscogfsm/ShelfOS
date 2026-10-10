# Large edge-case dataset

119 full synthetic camera images, including 96 new AI-generated images, plus 6 real source photographs in `reference_sources/` for visual comparison. References are not scored. Images are grouped by split and scenario under `images/`. Open `index.html` to browse and filter; click an image for the original full resolution. No pixels are changed by the assembly script. Where supported, image paths are hard links to their saved source files to avoid doubling disk use; treat this collection as read-only and save any edits into separate files.

`manifest.json` records image path, camera, original source family, generation prompt, hash, dimensions, review status and any previously reviewed labels. `inventory.json` records actual counts and unfinished generation IDs. New generated images are **unlabelled**: inspect the output and planogram before adding area labels. Do not infer labels from a prompt, and do not score unreadable or displaced geometry.

Many images share six real frames. This gives scenario coverage, not 119 independent scenes. Production may know these real frames; use separate real temporal holdouts to judge deployment gains. Four previous TRAIN references are kept in `images/train`, never mixed into TEST scores. Keep all variants of one source family in one split when extending training.

Rebuild the folder and gallery from saved outputs:

```powershell
python tools/build_edgecase_dataset.py
```

Run inference using the existing evaluator (new images are prediction-only until reviewed):

```powershell
python tools/edgecases.py --manifest ai_generated_edgecases/dataset_large/manifest.json --out outputs/edgecases_large
```

The existing reviewed benchmark and Fable brief remain in the parent folder. Existing benchmarks do not automatically include new cases. Do not train on this test folder; create a separate reviewed training set and compare against fixed tests first.
