# Step 1 — Foundations + labels (2 engineers)

**Goal of Step 1:** by the end, we have (1) a program that turns any folder of images into a valid submission file, (2) a scorer that gives us the official score locally, and (3) our own labelled set to score against. No machine learning yet. Everything after this (the model) plugs into these pieces.

**Why this first:** a missing area costs −5 and an invalid file can cost everything. And without our own labels + scorer we can't tell if any model idea helps. Labels are needed **whatever the organisers answer to Q2**: if we may train on them, they train the model; if not, they still evaluate it.

Facts (checked): 181 images (1280×720) in 14 camera folders, filenames = Unix time, **no labels anywhere**. 152 planogram areas → **1,962 area crops** to label. Only the 26 hidden validation images have answers.

---

## 0. Together, first 15 minutes

1. Clone the repo, create a venv, install: `pip install opencv-python numpy` (nothing else for Step 1).
2. Unzip the images into `data/raw/` (add `data/` to `.gitignore`, never commit images or crops):
   ```bash
   mkdir -p data/raw && unzip -q "new_dataset_hackathon_junctionx_10_oct_2026_v2/Frutas e Legumes (train & test).zip" -x '__MACOSX/*' -d data/raw
   ```
3. Agree on the **contract** below (5 min). After that, A and B never wait for each other.
4. Create `HACKATHON_LOG.md` (template in the Project instructions) and write your names in it.

### The contract (both sides depend on this — don't change it without telling the other)

**Folder layout**
```
config.py                 # all paths + constants + thresholds (only place for magic numbers)
src/areas.py              # A
src/io_format.py          # A
src/score.py              # B
tools/make_crops.py       # A
tools/label_tool.py       # B
tests/test_score.py       # B
run.py                    # A  (the one command)
labels/labels_<name>.json # output of the label tool
```

**One JSON format for everything** (predictions, our labels, the official ground truth) — exactly the brief's `annotations.json`:
```json
{"6215": {"1751052241.jpg": {"6215_2": {"planogram_compliant": true, "stock_level": "half", "stock_value": 0.5}}}}
```
`stock_level` ∈ `empty|half|full`, `stock_value` ∈ `0|0.5|1` (must match), `planogram_compliant` is a real boolean.
Our labels may add one extra key per area: `"unsure": true` (occluded / can't tell). The scorer ignores extra keys.

**Crop files:** `data/crops/<cam>/<area_id>/<timestamp>.jpg`, 224×224.

**Function signatures**
```python
# src/areas.py  (A)
load_planogram(path) -> dict[cam_id, list[dict]]        # area_id, product_id, product_name, quad (4x2 float, TL,TR,BR,BL)
warp_area(img, quad, size=224) -> (crop, visible_frac)  # visible_frac = share of the quad inside the image (0..1)

# src/io_format.py  (A)
write_submission(preds, planogram, image_paths, out_path, fallback) -> None   # fills ANY missing area with `fallback`
validate_submission(path, planogram, image_paths) -> list[str]                # [] = valid, else list of problems

# src/score.py  (B)
score(pred: dict, gt: dict) -> dict   # {"total", "id_correct", "id_wrong", "stock_correct", "stock_below", "stock_above", "missing"}
```

---

## 1. Engineer A — "the pipeline" (≈ 75 min)

**A1. `src/areas.py` — cut out each area (≈ 25 min)**
- Read `planogram.json`; for each area build the quad in order TL, TR, BR, BL.
- `cv2.getPerspectiveTransform(quad, square_224)` + `cv2.warpPerspective(..., borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))`. Negative coordinates just work: the part outside the photo comes out black.
- `visible_frac`: draw the quad as a filled polygon on a canvas big enough to contain it, count how many of its pixels fall inside the 1280×720 frame, divide by the total. (5 areas have negative coords, e.g. top shelf of camera 6383.)
- ✅ Done when: overlay check — draw all quads on one image per camera and look at it; and a crop of 6215_6 shows the banana rack.

**A2. `tools/make_crops.py` (≈ 10 min)**
- For every image in `data/raw/.../<cam>/*.jpg` and every area of that camera → save crop to `data/crops/...`.
- ✅ Done when: 1,962 files exist. **Tell B as soon as this works** (B's label tool reads these).

**A3. `src/io_format.py` — writer + validator (≈ 25 min)**
- Writer: for every image given, for **every** area of that camera, write the prediction; if the model gave nothing for an area, write `fallback`. Map `stock_level`→`stock_value` in one place (`config.py`).
- Validator must catch: invalid JSON; missing camera/image/area; extra area_ids; `stock_level` not in the 3 values; `stock_value` not matching the level; `planogram_compliant` not a bool (e.g. the string `"true"`); image file names not matching the input folder.
- ✅ Done when: deleting one area from a valid file makes the validator complain; a fresh output passes.

**A4. `run.py` — the one command (≈ 15 min)**
```bash
python run.py --images data/raw/"Frutas e Legumes (train & test)" --out predictions.json
```
- For now the "model" is a placeholder: every area = compliant `true`, stock from `config.BASELINE_STOCK`. Then it calls the validator and **refuses to finish if the file is invalid**.
- ✅ Done when: the command produces a valid file for all 181 images. This is our insurance submission.

---

## 2. Engineer B — "the judge" (≈ 75 min)

**B1. `src/score.py` + `tests/test_score.py` — the official formula (≈ 30 min)**
- Loop over **every area in the ground truth** (match by camera → image file → area_id):
  - missing in prediction → `id_wrong` and `stock_above` (−2 −3 = −5) and count it in `missing`;
  - compliance: equal → +1, different → −2;
  - stock: equal → +1; predicted value lower than truth → −2; higher → −3.
- Predictions for areas not in the ground truth are ignored.
- Tests (all must pass):
  - every answer right → score = 2 × number of areas;
  - one area removed from prediction → exactly −5 for it;
  - rebuild the brief's example (289 areas: 270/19 identification, 230/35/24 stock) → **320**.
- ✅ Done when: `python -m pytest tests/` is green (or plain asserts if we skip pytest).

**B2. `tools/label_tool.py` — fast labelling (≈ 40 min)**
- Plain OpenCV window (`cv2.imshow` + `cv2.waitKey`), no web stack.
- Show, side by side: the **crop** big, and the **full photo with only this area's quad outlined** (context helps with occlusion, overlapping quads, off-image parts). Print area_id, expected product name and time on screen.
- Keys: `e` / `h` / `f` = empty / half / full · `x` = toggle "wrong product" · `u` = toggle unsure · `b` = back · `q` = save & quit.
- Order: per camera, **latest frames first** (validation is probably end of day, so those labels matter most).
- Saves to `labels/labels_<name>.json` after **every** key (crash-safe, resumable), in the contract format.
- Command: `python tools/label_tool.py --name joao --cameras 6215,6371,...`
- ✅ Done when: you label 20 crops, quit, restart, and it resumes where you stopped; the JSON loads in `score.py`.

**B3. `LABELING_GUIDE.md` — write 10 lines before anyone labels (≈ 5 min)**
Both labellers must use the same rules, otherwise the labels are noise. Draft:
- **empty** = container/rack basically bare (only a few loose units left).
- **full** = area covered, looks like just after restocking.
- **half** = anything in between.
- **wrong product** = only if what's visible is clearly a different product from the planogram name (e.g. bananas where oranges are expected; loose vs packaged also counts as different). Same fruit, variety you can't tell apart → not wrong.
- **empty area** → leave compliant `true` and press `u` (Q3 unanswered).
- Shopper/cart hides most of the area → best guess + `u`.
- **Label your honest best guess. Do NOT lean low while labelling.** The "lean low because −3 > −2" rule is applied later, in the decision step; doing it here too would count it twice.

---

## 3. Together again (≈ 60–75 min): label

1. Quick integration test: A's `run.py` output and B's label file both pass `validate_submission` and go through `score()`.
2. Split the 14 cameras 7 / 7. Each labels their cameras (~980 crops each; ~1 h at 3–4 s per crop with the montage-style tool).
3. **Overlap:** each person also labels **one camera of the other's set** (≈ 10%) into their own file. Measure how often the two agree → that's our realistic accuracy ceiling. If agreement on stock is below ~80%, stop and fix the guide before labelling more.
4. Run the scorer: baseline `predictions.json` vs our labels → write the baseline scores (always full / always half / always empty / always compliant) in `HACKATHON_LOG.md`.

**End of Step 1 checklist**
- [ ] `python run.py ...` → valid file for all 181 images, every area present
- [ ] `score.py` tests green, brief example = 320
- [ ] ~1,962 crops labelled, overlap agreement measured
- [ ] baseline scores in the log

Next: **Step 2 = first real model** (simple image features + calibrated classifier + the expected-value decision). Planned after Step 1 is done.

---

## Someone ask the Sensei mentors today (in this order)
1. **Q2** May we hand-label train/test images and **train** on them? Pretrained models / external APIs allowed?
2. **Q5** What separates half from full? How were occluded / off-image areas annotated?
3. **Q6** May we use other train/test frames of the same camera when predicting a validation image?
4. **Q7** At what times were the validation images taken?
5. **Q3** Empty area → compliant true or false? **Q4** Wrong product → stock of what's there?
6. **Q1** How many validation submissions, and when?

Write every answer in the header of `HACKATHON_LOG.md`.
