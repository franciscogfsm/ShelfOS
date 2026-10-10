# ShelfOS

Shelf intelligence for the Sensei challenge at JunctionX Lisbon 2026. For every planogram
area in a ceiling-camera image, ShelfOS says whether the right product is there and how
full the area is, and turns that into a to-do list a member of the store staff can act on.

## Rules confirmed by the organisers

Read this before changing how an answer is decided or how an image is labelled. These
questions are closed; do not reopen them.

**An empty area is `planogram_compliant: true`.** The organisers answered this on
10 Oct 2026 (it was question Q3 in `STEP1_PLAN.md`). What we take from the answer:

- `planogram_compliant: false` is only for an area where a product other than the expected
  one is present.
- A missing product is recorded in the stock fields alone: `stock_level: "empty"`,
  `stock_value: 0`.
- When labelling, an empty area is compliant and needs no "unsure" mark. In the labelling
  guide (`STEP1_PLAN.md`, B3) the rule "empty area: compliant true, plus `u`" is now just
  "empty area: compliant true".

The code already answers this way: `empty_compliant` is true by default in the engine, the
service, the command line and the cross-validation. The `--empty-noncompliant` switch and
the matching switch in the app are left over from before the answer. Leave them off for
anything that is submitted.

## Run it

```
pip install -r requirements.txt
python run.py
```

This opens the app at http://localhost:8000 (on Windows you can also double-click `run.bat`).
The first start embeds the reference day and fits the model; that takes about a minute on a
GPU. It expects the challenge data in `data/images/<camera>/<timestamp>.jpg` and
`data/planogram.json`.

To test on new images, press **Test on new images** and drop a folder, loose files or a
zip (or paste a folder path). Each image is answered as it finishes; then download
`predictions.json`, which is in the official annotation format.

Without the interface:

```
python run.py --images <folder or zip> --out predictions.json
```

Useful switches: `--lan` makes the app reachable from a phone or tablet on the same
network, `--cpu` skips the GPU, `--train` rebuilds the model after the labels change.

To score a prediction file against an annotation file with the official rules, drop
`annotations.json` on the results screen, or:

```
python -c "import json,sys; from shelfos.scoring import score_submission as s; print(s(json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))))" predictions.json annotations.json
```

## What it does with awkward input

| Input | What happens |
| --- | --- |
| Images in `<camera>/<file>` folders | The folder names the camera. |
| Loose files, no folders | The camera is recognised from the picture itself (the cameras never move). |
| A zip, with or without a wrapping folder, with macOS `._` files | Opened in place, debris ignored. |
| Another resolution | Resized onto the planogram's pixel grid, with a warning. |
| Greyscale, PNG, alpha channel | Converted and analysed. |
| A file that cannot be decoded | Every area is still answered, from its last known state, and flagged. A missing area would cost 5 points. |
| An image filed under the wrong camera | Kept under the folder it came in, with a warning naming the camera it looks like. |
| Areas partly outside the frame (negative coordinates) | The part outside is masked, not read as empty shelf. |

`python tools/selftest.py` runs these cases.

## How it works

1. **Geometry.** Each planogram quadrilateral is perspective-rectified to a square crop.
2. **Features.** A frozen DINOv3 ViT-B/16 gives one global embedding and a 14x14 grid of
   patch tokens per crop. No fine-tuning. One image (about 12 areas) is one forward pass.
3. **Occupancy.** A patch classifier separates product from background (crate, tray,
   cardboard, basket) and gives the share of the area that is covered.
4. **Shelf memory.** The cameras are fixed, so the crops of one area line up patch for patch
   over time. Each new crop is compared with what the same area looked like when it was
   full and when it was empty. This is what makes late-evening frames work: it measures
   how much has changed without needing to know the product.
5. **Stock level.** Logistic regression on embedding, occupancy and memory features. The
   level reported is the one with the highest expected official score (+1 / -2 below /
   -3 above), so a borderline shelf is called half rather than full.
6. **Compliance.** Each product has a prototype embedding. A crop is compared with the
   expected product, with all other products, and with the area's own history. The app
   also names the product the area looks like when it is not the expected one.

## Labels and measured results

The dataset ships without annotations. `labels/silver_labels.txt` holds our own labels for
the reference day: a first pass made by eye from image strips, then corrected by a person
with the review tool below. They are not the official ground truth, and the half/full
boundary in particular is a judgement call. The official score on the hidden validation set
is unknown until the organisers run it.

RESULTS_TABLE

Tried and dropped because they did not measure better: a larger backbone (ViT-L), 448 px
crops, blending in a nearest-neighbour vote, and shifting the decision towards "half".

### Human review tool

From the repository root, open the annotation tool with:

```
python tools/label_review.py
```

It opens a local browser and offers all **1,962 area-frames**. Use **1** = empty,
**2** = half, **3** = full, **4** = covered/unknown. Each answer saves and advances.
The exact crop and a wider view show the official area; only classify the interior
of the yellow outline. Purple pixels lie outside the photograph. Left arrow goes
back, right arrow skips without answering. Skipped cases remain unfinished.

Progress resumes automatically from `labels/review/session.json`. The 73 stock
answers already reviewed are included. To review product compliance as well:

```
python tools/label_review.py --task both
```

Choose stock with 1–4 and product with **5** = expected product, **6** = other
product, **7** = empty/unknown. The tool advances after both selections. In stock
mode, existing compliance labels are preserved. Unknown stock is written as `?`
and excluded by the stock label loader. Human labels are not official ground truth.

Answers generate `labels/review/reviewed_labels.txt`; the training source is only
updated by the following command. Stop the review server with **Ctrl+C** first:

```
python tools/label_review.py --apply
```

Applying creates a backup and preserves unrelated edits in `labels/silver_labels.txt`.
If another person changed a reviewed entry differently, the command refuses the
merge and lists conflicts in `labels/review/conflicts.json`. This does not retrain
the model. Dependencies are `numpy` and `opencv-python` (`python -m pip install
numpy opencv-python` if missing).

For a colleague to start a separate review of **every case from zero**:

```
python tools/label_review.py --state labels/review/colleague/session.json --task both
```

Use the same `--state` when applying that review. Separate sessions can run on
different computers; on the same computer also pass a different `--port`.
Other options: `--scope empty`, `--scope unsure`, `--no-browser`, `--images`,
`--labels`, and `--planogram`. Default data paths are relative to the repository,
so the tool has no machine-specific paths.

## Open question for the organisers

Are self-made labels on the train set allowed?

Whether an empty area is compliant is no longer open: see "Rules confirmed by the
organisers" at the top.

## Layout

```
run.py              one command: the app, or predictions for a folder
shelfos/            engine (features, occupancy, memory, compliance, scoring), service, server
web/                the interface (Next.js, exported to static files and served by run.py)
tools/cv.py         cross-validation of the shipped engine against our labels
tools/selftest.py   edge-case drill
tools/label_review.py   label review tool
labels/             our labels for the reference day
```
