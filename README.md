# ShelfOS

Shelf intelligence for the Sensei challenge at JunctionX Lisbon 2026: for every planogram
area in a ceiling-camera image, say whether the right product is there and how full it is.

## Run it on the validation images

Images must be laid out like the training set: `<folder>/<camera_id>/<timestamp>.jpg`.

```
python -m shelfos.predict --images <folder> --out predictions.json
```

`predictions.json` is in the official annotation format and covers every planogram area of
every image, so nothing is scored as missing. Add `--empty-noncompliant` if the organisers
say an empty area counts as `planogram_compliant: false` (the default reports `true`).

To score a prediction file against an annotation file with the official rules:

```
python -c "import json,sys; from shelfos.scoring import score_submission as s; print(s(json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))))" predictions.json annotations.json
```

## How it works

1. **Geometry.** Each planogram quadrilateral is perspective-rectified to a square crop.
   Parts that fall outside the image (negative coordinates) are masked, not read as shelf.
2. **Features.** A frozen DINOv3 ViT-B/16 gives one global embedding and a 14x14 grid of
   patch tokens per crop. No fine-tuning.
3. **Occupancy.** A patch classifier separates product from background (crate, tray,
   cardboard, basket). It is seeded from crop-level labels only and self-trains to find
   background next to product. The share of the area covered is the main stock signal.
4. **Stock level.** Logistic regression on embedding + occupancy, blended with a nearest
   neighbour vote over the day's labelled crops. The final level is the one with the highest
   expected official score (+1 / -2 below / -3 above), so borderline cases lean low.
5. **Compliance.** Each product has a prototype embedding. A crop is compared with the
   expected product's prototype, the other products, and this area's own history.

## Rebuild from scratch

```
python tools/build_bank.py data/planogram.json data/images cache/bank.npz   # embed the day (~3 min on CPU)
python -m shelfos.train                                                      # -> models/engine.pkl
python tools/experiment.py cache/bank.npz labels/silver_labels.txt late      # stock ablation
python tools/experiment_compliance.py cache/bank.npz labels/silver_labels.txt late
```

## Web app

```
python -m shelfos.predict --images data/images --out outputs/predictions.json --details outputs/details.json
python tools/export_web.py outputs/details.json data/planogram.json data/images web/public
cd web && npm install && npx next dev
```

## Labels and measured results

The dataset ships without annotations. `labels/silver_labels.txt` holds our own labels for
all 1,962 area-frames, made by eye from `outputs/strips/`. They are not the official ground
truth, and the half/full boundary in particular is a judgement call.

Cross-validated against those labels, holding out whole images:

| split | stock accuracy | stock points/area | compliance points/area |
| --- | --- | --- | --- |
| one hour held out for all cameras | 95.6% | +0.83 | +0.98 |
| last two frames of every camera held out | 87.1% | +0.49 | +0.97 |

Maximum is +1.00 per area for each column. The official score on the hidden validation set
is unknown until the organisers run it.
