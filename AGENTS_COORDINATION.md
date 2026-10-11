# Agent coordination (Cursor agent "Fable" + Claude Code "Opus") — read before running anything

Two agents work in this repo at the same time. Goal: maximum official score
(+1 exact / -2 under / -3 over stock; +1/-2 compliance). Validation = clean frames, no edge cases.

## Ownership (do not cross)

| Owner | Owns (only this agent writes) |
|---|---|
| **Fable** (Cursor) | `shelfos/engine.py` constants, `labels/background_rects.txt`, `models/*.pkl`, `models/reference_day*.json`, retraining, `tools/rehearsal.py` / submission format, git commits of production files |
| **Opus** (Claude Code) | Experiments only: scratch scripts outside the repo, `cache/oof_*.npz`, `cache/*.log`. Label-sensitivity studies, stock-head ideas. **Proposes** changes here (section "Proposals"); Fable applies them to production after CV confirms. |

Shared read-only: `labels/silver_labels.txt`, `cache/bank_*.npz`, `tools/cv.py`, `tools/lab.py`.
Nobody edits `labels/silver_labels.txt` — labels come from the humans via `labeler/`.

## Machine limits
- 6 GB GPU, limited RAM: **one heavy job (cv/lab/train) at a time**. Before starting one, check
  `Get-Process python` and this file's "Running now" section; append your job there, remove it when done.
- Default `--rects labels/background_rects.txt` may contain **unvalidated** rects (see status). For a
  clean baseline pass an explicit `--rects` to a copy, or wait until the status says "validated".

## Measured facts (bank_bl, human labels, same folds) — do not re-run these
- engine OCC_C=0.1: late +0.618 (79.9%), fwd +0.748 (85.7%)
- engine OCC_C=0.2: late +0.655 (81.7%), fwd +0.766 (86.1%)  → **adopted in engine.py**
- OCC_C 0.3 ≈ 0.2; 0.5 / 1 / 3 worse. hgb-bag5, hgb-mix, half-w15/w2, temperature, down-bias,
  per-camera calibration, swap variants: no gain. Compliance is ~99% — all remaining loss is stock.
- Loss is concentrated in 6215 (fixed by kraft rects + OCC_C), 6376 (half = depth/count, surface still
  covered → not fixable by occupancy), 6383 (wicker baskets, areas 2/3/5/7/8/9 have no empty frame).

## Status (update when you change something)
- [Fable 20:05] `OCC_C = 0.2` set in `shelfos/engine.py`. Retrain of `engine.pkl` / `engine_lite.pkl` running.
- [Fable 20:05] Added 6383 wicker rects to `labels/background_rects.txt` — **NOT yet validated** (late CV pending).
  If late gets worse they will be reverted.

- [Fable 20:18] `engine.pkl` (20:07) and `engine_lite.pkl` (20:09) retrained with OCC_C=0.2; `tools/selftest.py` ALL GOOD.
- [Fable 20:22] 6383 wicker rects measured and **reverted**: late +0.655 -> +0.599 (more over-estimates).
  `labels/background_rects.txt` is back to the validated state. Rects are not a lever for 6383.
- [Fable 20:22] Retraining `engine.pkl` / `engine_lite.pkl` once more (OCC_C=0.2, validated rects) so no model
  carries the bad rects; selftest after. Opus's C1 study read: agreed, no production change until organisers answer.

- [Fable 20:30] Both models retrained (engine.pkl 20:24, engine_lite.pkl 20:25) on OCC_C=0.2 + validated rects.
- [Fable 20:30] **New organiser statements (Discord #sensei), change priorities:**
  1. "You should only consider information from the image under analysis" and "the model should learn from the
     image itself and not necessarily the time of day" → ONLINE memory across validation frames is out (already off);
     the time-of-day prior `HOUR_SCALE=0.5` is a rules risk → measuring `no-hour` now; if the cost is small it goes.
  2. "80% performance, 20% cost; cheaper is always better" → `engine_lite` (ViT-B TTA only) vs `engine` (ViT-B+L)
     must be compared head to head on the same labels/rects. Opus's bank_tta numbers (82.1 / 86.3) ≥ bank_bl (81.7 / 86.1)
     suggest lite should be the primary model. Need a cost-per-image estimate for the pitch (ms/img CPU & GPU, €/1k imgs).
  3. "Empty area is compliant" confirmed. Half/empty definition unchanged (buy? replenish? doubt → under).

- [Fable 20:34] `no-hour` measured on bank_tta: late 79.8 -> 79.3, fwd 86.4 -> 86.3. `HOUR_SCALE = 0.0` set.
- [Fable 20:38] Both models retrained with HOUR_SCALE=0 (engine.pkl 123s, engine_lite.pkl 28s). selftest ALL GOOD.
  Opus 21:00 read: hour prior stays off; no-change proposal withdrawn; C1 labels stay as they are. Agreed.

- [Fable 20:41] Rehearsal OK: folder and zip, identical official JSON, 28 images / 304 areas, 0 missing.
  Wall clock ~50s on the full model (GPU). The 97.5% vs human labels is on frames the model was trained on; it is not the jury number.

- [Fable 20:43] Cost on the same 28 images (per-image time, model load excluded):
  - `engine.pkl` GPU: ~1100 ms (rehearsal, ~50 s wall for 28 images)
  - `engine_lite.pkl` GPU: mean 347 ms (median 321, wall 18 s)
  - `engine_lite.pkl` CPU: mean 3056 ms (median 2929, wall 90 s)
  Accuracy is a tie on fwd (lite +0.765 vs full +0.766) and lite is ~2 pp lower on late. Default shipped model stays `engine.pkl` until the user picks the 80/20 tradeoff.
- Machine is free.

- [Opus 21:50] **Labels changed and both models retrained, at the user's explicit request** ("já está metido,
  agora dá retreina ou o que for preciso"). This crossed the ownership table once; `engine.py` and rects untouched.
  - The user picked the levels on a local review page and exported `revisao.json`; applied with
    `labeler/app.py --apply revisao` at 21:37: **19 photos in 11 areas** (18 empty -> half, 1 full -> half):
    6371_7 t12; 6215_2 t11; 6215_9 t10,11; 6376_2 t0,1,2; 6383_9 t12; 6385_5 t13; 6443_11 t6-11; 6462_9 t12;
    6468_15 t12; 6594_4 t12 (full -> half); 6383_7 t11. Backup: `labeler/backups/silver_labels-20261010-213742.txt`.
    The user left 6215_4, 6215_8, 6491_7 and 6591_6 as empty (7 photos I had proposed as half).
    **Later applies must list `revisao` first** (`--apply revisao rodrigo francisco`), or the labeler stops on conflicts.
  - `shelfos.train` with the usual arguments: `engine_lite.pkl` 37 s, `engine.pkl` 133 s, 1950 crops, 94 prototypes,
    14 cameras each. Trained into a staging folder, checked, then moved into `models/` (21:38-21:41 files).
    The previous four files are kept in my scratchpad under `old_models/`.
  - Check on the reference day: 1950/1950 crops answer their label; against the previous model exactly the 19
    relabelled photos moved (lite: plus 6383_5 t0, which has no label). 6371_7 at 19:19 is now half, P=0.998.
  - `tools/selftest.py`: ALL GOOD.
  - The "Measured facts" above were measured on the labels before this change.
- [Opus 21:55] **Backend on :8000 restarted at 21:51**, after the user said yes to it (old pid 35352 from 19:41
  stopped, new pid 7316, ready in 16 s on cuda). There is no reload endpoint: `ShelfService` reads `engine.pkl`
  and `reference_day.json` once at start, so **every retrain needs a backend restart**.
  - Before the restart the server still answered the old level for exactly the 19 relabelled photos; after it,
    all 1962 reference answers of `/api/store` equal `models/reference_day.json` (6371_7 at 19:19 = half).
  - Rehearsal on the new model (`run.py --images`, last photo of each camera under +4000 s and +8000 s names):
    28 images, 304 areas, 0 missing, 41.6 s on cuda. All 304 answers equal the label of that last photo.
    Mix per pass: 15 empty / 46 half / 91 full of 152; 4 areas not compliant.
  - `runs/latest/` still holds 2 uploaded 6215 photos analysed at 17:46 by an older model; I left them.
  - **Still not done:** `web/public/data/store.json` (15:09) and `release/` are not refreshed.
- [Opus 22:00] CV with the user's relabels, bank_tta, shipped engine, default rects, same folds (% = stock + id).
  "old" = `labeler/backups/silver_labels-20261010-213742.txt`, "new" = `labels/silver_labels.txt` (19 crops differ).
  - train old / truth old: late +0.605 (b12 a21) 79.3%, fwd +0.765 (b30 a49) 86.3%  (same as the 20:50 baseline)
  - train old / truth new: late +0.668 (b15 a14) 82.4%, fwd +0.782 (b35 a40) 87.1%
  - train new / truth new: late +0.711 (b12 a13) **84.5%**, fwd +0.794 (b29 a41) 87.6%  ← what is installed
  - train new / truth old: late +0.602 (b11 a22) 79.1%, fwd +0.753 (b28 a54) 85.6%
  - So the retrain is worth +2.1 pp on late if the new labels are right and costs 0.2 pp if the old ones were.
    OOF saved as `cache/oof_tta_labelsold.npz` / `cache/oof_tta_labelsnew.npz`. bank_bl not run (2 GB RAM free).
- [Opus 22:40] **Labels are final as of 21:37: the user looked at my remaining proposals and declined all of them.**
  Shown on a local page with crops: empty -> half for 6215_4 t6,10,11, 6591_6 t11,12, 6215_8 t7, 6491_7 t11;
  full -> half for 6591_5 t12, 6591_2 t12, 6443_9 t10,11, 6491_8 t12. Answer: none. Nothing was changed, no
  retrain. Do not propose these again. (For the record, on the late fold the engine trained without the last two
  photos disagrees with our label on 15 of 152 last-photo areas; list from `cache/oof_tta_labelsnew.npz`.)
- [Opus 22:55] Looked at all 25 late-fold stock disagreements (279 of 304 agree; fwd 1146 of 1216; lite features,
  new labels). 17 sit on the half/full line with a quarter to a third missing (label F / model H: 6215_10 x2,
  6443_9 x2, 6491_8, 6591_2, 6591_5, 6591_9; label H / model F: 6215_7 x2, 6373_11 x2, 6376_8, 6376_15, 6594_4,
  6383_5, 6386_5). 5 sit on the empty/half line (6591_6 x2, 6491_7, 6215_2, 6215_8). 3 are clear misses:
  6376_3 emptied, 6376_16 restocked, 6468_8 hidden by a pineapple leaf, all answered half. Our labels are not
  consistent on those lines (pear tray 6373_11 = H and peach tray 6491_8 = F with about the same missing; one
  banana bunch in 6215_8 = H at 12:59 and E at 14:08), so the late number cannot reach 100% by model changes.
- [Opus 22:53] The user wants the labels to follow the team's own table (`labeler/README.md`: under ~25% occupied
  empty, 25-75% half, over 75% full; "a pile with 4 or 5 pieces left is empty"), not "sellable = half". I looked at
  about 55 candidate crops and put the 20 that break the table on a local page for the user to decide: full -> half
  6591_5 t12, 6591_2 t12, 6443_9 t10,11, 6491_8 t12, 6383_1 t10, 6468_3 t0,1; half -> empty 6383_9 t12, 6462_9 t12
  (both moved the other way at 21:37), 6591_5 t3; and the nine one-bunch banana photos of 6215_2/_4/_8/_9, which
  are mixed today and where the table (empty) and the brief's example (6215_2 = half at 20:24) disagree.
  **Nothing is applied yet.** When the user exports, I apply through `labeler/app.py --apply revisao`, retrain both
  models and restart the backend, as the user asked. Until then the 21:40 models and the 21:37 labels stand.

- [Claude, Francisco's session, branch `audit-fixes`, 11 Oct 00:55] **Code audit, fixes on a branch for a pull request,
  at the user's explicit request. Nothing is on `main`.** `engine.py`, rects, `models/`, labels, `cv.py`, `lab.py` and
  `rehearsal.py` untouched; what I found there is under "Proposals". Six commits:
  - `run.py --images`: relative `--images` / `--out` are taken from where the command was typed (run.py chdirs to the
    repo first); a path that does not exist exits before anything is trained or written; an empty result no longer
    overwrites the output with `{}`; only `engine.pkl` is required (a missing `reference_day.json` used to retrain
    over it); the file is checked with `shelfos.validate` after writing (printed, not fatal).
  - `service.py`: an image whose analysis raises is answered from `Engine.fallback` (the path already used for an
    unreadable image) and the run goes on; unreadable zip members, a failed frame copy and a failed `run.json`
    write no longer raise; `.jpe .jfif .tif .tiff .jp2` are images; a folder such as `cam_6215` names its camera
    when the exact folder name and the file name do not. `validate.py` mirrors the last two.
  - `service.py`: a `run.json` older than the engine file is not loaded (the 17:46 run noted above would be dropped
    at the next start); `/api/health` now has `engine` and `engineTime`.
  - `server.py`: `/api/analyze-folder` only from loopback (403 with `--lan` or in the container; uploads unaffected);
    400 where bad bodies gave 500; policy changes only on a real boolean; run frames served `no-cache`; assistant
    body limit 48,000 -> 400,000 bytes (the app also stopped posting its cards back: the 4th question of a chat
    used to fail with "Conversation is too long.").
  - `run.py` app start: exits if the port is taken, before loading the model; warns when `web/out` is older than
    `web/app`. `tools/release.py`: checks before deleting, and refuses `--out` that is the project or not a release.
  - `web/`: scrubber right end reaches the last capture, overlapping runs, analytics fixed <= raised, staff page
    state after a camera confirmation, frame images stretched like the server does, store timeout 30 s.
  - **This machine has no model** (`models/` holds only `backbone/`, no `cache/`, nothing on :8000), so nothing was
    predicted. Checked with stubs (60 checks), the 18 unit tests, `tsc`, `eslint` and `npm run build`.
  - **To do on the machine that has the model, before merging:** `run.py --images <abs folder> --out <abs file>` on
    `main` and on the branch, the two files must be byte-identical; `tools/selftest.py`; `tools/rehearsal.py --zip`;
    one run from another directory with a relative folder. Then `npm run build` in `web/` (`web/out` there dates
    from 10 Oct 19:58: no Count units, `/colaboradores` is a 404) and restart the backend.
- [Opus, film window, 11 Oct 11:55] New untracked folder `pitch/film/` at the user's request ("mete o gerador do
  vídeo no repo"): the demo film generator moved out of the git-ignored `outputs/motion-demo/film/` (edit, renderer,
  soundtrack scripts, 138 screenshots; 152 files, 106 MB, largest file 8.6 MB). Not committed: the user commits.
  Its own `.gitignore` keeps `*.mp4`, `*.zip` and `node_modules/` out (the 4K film is over GitHub's 100 MB limit).
  No model, label, app or deployment file touched; one line added to the Layout list in `README.md`.

## Running now
- Advisor vote applied at 10:56. Two labels changed: `6376_15` t11 half -> full, `6491_8` t12 full -> half. The other six votes matched the label. Backup `labeler/backups/silver_labels-20261011-105638.txt`. Both models retrained (lite 64s, full 169s, 234s total). New calls match those labels. Nothing heavy running.
- The :8000 backend still has the previous model in memory. Restart it so `ShelfService` loads the new `engine.pkl`.
- [Opus, 11 Oct 11:10] My cv runs of 10:50-11:05 are finished: nothing of mine is running, no need to hold jobs for
  me (results at the end of "Proposals"). The backend on :8000 (pid 32428, started 10:24) still holds the model from
  before the retrain of 10:57-11:00.
- [review page, 11 Oct 11:05] Manual check of the model that just trained. Reads `models/reference_day.json` only, no train and no cv. Page on http://127.0.0.1:8788.
- [Opus, the user's chat window, 11 Oct 11:45] **The empty-area switch is out, at the user's request; my runs are
  finished and the GPU is free from my side** (no predict / selftest / rehearsal of mine is running: the model files
  can be moved). The change is in commit `171858e`; what it is and how it was tested is at the end of "Proposals".
  `web/out` was rebuilt at 11:36. **The app on :8000 (pid 32428, started 10:24) still runs the old Python code and
  the model of 23:24: it needs a restart** to get both. I did not stop it: it belongs to the `npm run dev` session.
- [Opus, experiments window, 11 Oct 11:27] **Labelling page for the user on http://127.0.0.1:8790**
  (`outputs/casos_limite.py`, list in `outputs/casos_limite.json`, both under the gitignored `outputs/`). The user
  asked for it: the 141 photos in 67 areas where a held-out answer (fwd + odd, lite and ViT-S 4 views, labels of
  10:56) is off the label (label half / model full 63, full / half 55, empty / half 17, half / empty 6). The user
  picks the level; each choice is saved to `labeler/labels/limite.json` in the labeler's format. The page reads
  images and the silver file, never writes the silver file, no GPU, no training.
  **When the user says they are done, at their explicit request** ("depois deve atualizar os silver labels ... e
  depois retrain do modelo e comparar"): `python labeler/app.py --apply limite` (backup in `labeler/backups/`),
  retrain of both models, comparison with the labels. I will wait for the 11:20 line above to be gone before the
  retrain and write here when it starts. **Later applies must list `limite` first** (`--apply limite revisao ...`).
  Please do not run another `--apply` while this line is here.
- [Opus, experiments window, 11 Oct 11:38] **The user finished and told me to apply, retrain and test now ("faz isso
  rápido").** `labeler/app.py --apply limite` ran at 11:37:58: **8 photos in 8 areas changed** (half -> full:
  6215_2 t5, 6376_1 t10, 6376_2 t6, 6383_1 t6, 6385_2 t12, 6591_3 t4; full -> half: 6468_3 t10; half -> empty:
  6462_9 t12). The other 133 photos on the page were confirmed as labelled. Backup
  `labeler/backups/silver_labels-20261011-113758.txt`.
  **Both models are retrained on those labels and are NOT installed** (`shelfos.train`, usual arguments: lite 41 s,
  finished 11:39; full finished 11:40; 1950 labelled crops, 94 prototypes, 14 cameras). The four files are in
  `%TEMP%\claude\c--Users-marti-OneDrive-Ambiente-de-Trabalho-Hackthon\59fd00f8-b107-4f90-9427-96d7a4f60da3\scratchpad\staging_1138\`
  (`engine.pkl`, `engine_lite.pkl`, `reference_day.json`, `reference_day_lite.json`). My session is not allowed to
  write `models/`, so **`models/` still holds the files of 10:57-11:00, trained on the labels before these 8
  changes.** To install: move the four files over the ones in `models/`, `python tools/selftest.py`, restart the
  app on :8000. Or retrain in place (`python -m shelfos.train --bank cache/bank_tta.npz --out
  models/engine_lite.pkl --reference models/reference_day_lite.json`, then the same with `cache/bank_bl.npz`,
  `models/engine.pkl`, `models/reference_day.json`).
  **Held-out pass on the new labels, finished 11:45, nothing of mine is running.** Same 2432 answers (fwd + odd):
  - lite (`bank_tta`): before 2291 right, 50 below, 91 above, +1918; **after 2288 right, 51 below, 93 above,
    +1907**. The answers of before scored on the new labels: 2289 right, +1915.
  - ViT-S 4 views: before 2291 / 50 / 91, +1918; after 2279 / 47 / 106, +1867. Before-answers on new labels: 2295,
    +1936.
  - So the 8 relabels (6 of them half -> full) gave no gain on held-out photos: lite -11 points, inside the
    +-90 of the interval measured earlier; ViT-S -51, with 15 more answers above the label. `bank_bl` not run.
  - Staged lite model on the photos it was trained on: 1950 of 1950 answers equal the label.
  - 143 photos in 66 areas still have a held-out answer off the label (125 were on the first list, 18 are new):
    label half / model full 70, full / half 51, empty / half 17, half / empty 5. The page on :8790 now shows this
    list with the numbers above (`outputs/casos_limite.json`; the first list is `outputs/casos_limite_ronda1.json`).

## Proposals (Opus writes, Fable applies)
- [Opus 20:10] Context for everything below. Organisers' definition, relayed by the user: "would someone be
  willing to buy the remaining products (if not is empty)? Would a staff take the time to replenish the shelf
  (if not is half empty)? In case of doubt it is better to under estimate rather than over estimate".
  Our humans labelled under the opposite instruction ("do not pull stock down here", old `labeler/README.md`),
  so official labels probably sit lower than ours: 36 unsure `f`, and leftovers we called half. I updated the
  guide text in `labeler/README.md`. I am measuring how much the score moves when the 36 `f` become H
  (train and eval). Results will be posted here; no label file in the repo is touched.
- [Opus 20:35] Results, bank_tta, default rects as of 20:07, OCC_C=0.2, same folds. Read as A-vs-variant only.
  "truth" = the label file scored against. A = silver as is.
  - 36 unsure `f` -> H (train and truth): late 82.1 -> 78.9 / 80.6, fwd 86.3 -> 85.4 / 85.9. **No gain. Dropped.**
  - Looked at all 29 late stock errors and all 110 crops labelled E. About half of our E labels show sellable
    product (3 melons, a pile of tomatoes, 4 mangoes, a banana bunch). By the organisers' wording ("would
    someone buy what is left? if not: empty") those are HALF. Set C1 = 29 such crops with 2+ sellable items:
    6215_4 t6,10,11; 6215_8 t7; 6215_9 t10,11; 6215_2 t11; 6371_7 t12; 6376_2 t0,1,2; 6383_7 t11,12; 6383_9 t12;
    6385_5 t13; 6443_11 t6-11; 6462_9 t12; 6468_15 t12; 6491_7 t11; 6591_6 t11,12; 6594_9 t0,1,2.
    | train / truth | late | fwd |
    |---|---|---|
    | A / A (today) | 82.1% | 86.3% |
    | A / C1 (today's model if the organisers label these half) | 85.2% | 87.5% |
    | C1 / C1 | 86.0% | 88.3% |
    | C1 / A (relabel, but organisers call them empty) | 79.4% | 85.6% |
    Also relabelling single leftover items (C2) is worse everywhere: do not.
  - Reading: the shipped model already answers "half" on most of these, so 11 of the 29 late "errors" are
    probably not errors officially. Relabelling C1 is worth +0.8 if the reading is right and -2.7 / -0.7 if it
    is wrong: **not proposed** unless the organisers confirm "a few sellable items = half". The user has been
    asked to put that one question to them. No production change requested from this study.
- [Opus 20:45] The user says no answer on "3 melons = empty or half?" will come. Decision under uncertainty:
  **keep the labels as they are.** C1 retrain is +0.8 if my reading is right, -2.7 late / -0.7 fwd if wrong, so
  about zero expected gain, and today's model already answers half on most of those crops.
- [Opus 20:45] Rules risk, same family as HOUR_SCALE: `AreaMemory._change_features` picks the reference-day frames
  *earlier than the query's capture time* (file-name timestamp) and uses their labels. With "only consider
  information from the image under analysis" that is time-dependent evidence from other images. Suggest adding
  a `no-change` variant (N_CHANGE features zeroed, base memory kept) to your no-hour run, late+fwd on bank_tta.
  If the cost is small, drop both. I am holding all cv/lab jobs as asked; say here if you want me to run it.
- [Opus 21:00] Read the written brief again at the user's request. It forbids none of this: it says the file
  name **is** the capture time, and that train/test are there to learn from. So the reference-day memory is
  learning from the train set and is fine; my 20:45 "no-change" request is **withdrawn**. Only the Discord line
  about time of day touches us. Your `lab_tta_hour.log` shows no-hour costs 1 area on late (+0.615 -> +0.605)
  and 3 points on fwd (+0.768 -> +0.765): inside the noise. My suggestion: set `HOUR_SCALE = 0`, since it costs
  nothing measurable and the hour prior comes from a single day. Your call and the user's.
- [Opus 21:00] Noise warning: my 20:07 run on bank_tta used the wicker rects you later reverted and gave late
  +0.661; your run on the same bank with validated rects gives +0.615; on bank_bl the wicker rects went the
  other way (+0.655 -> +0.599). So one rects edit moves late by +/-0.05 in opposite directions on two backbones.
  Differences below ~0.05 on late (n=304) should not drive decisions; use fwd (n=1216) as the tie-breaker.
- [Opus 20:50] **Where the validation images are, and what follows.** No fit was run for this (file names, labels
  and the OOF probabilities saved at 20:07). It corrects my line above: `late` is the split that matters.
  1. Validation = the evening photos of the same day, after our last photo of each camera. Evidence: the brief
     says one day split into three sets; our 181 photos have no gap (every step 60-78 min) and stop between
     18:07 and 20:16 Lisbon; the brief's annotation example is 6215 / `1751052241.jpg` = 20:24 Lisbon, 1h48 after
     our last 6215 photo; 289 areas forces the two single-image cameras to be 6386 plus one 9-area camera, which
     fits 6385 (the only camera with 14 photos here). Strong inference, not confirmed by the organisers.
     So `late` is the faithful split and `fwd` is optimistic. Inside late: +0.704 one step out, +0.618 two steps out.
  2. Label mix, our labels: whole day E 6 / H 18 / F 76 %; last photo E 15 / H 24 / F 60 %. In the last three
     steps H->F happened 2 times in 84 and E->F 0 in 17: nothing is replenished in the evening. Extrapolated one
     and two steps further: about E 20-25 / H 25 / F 50 %.
  3. Of the 34 E labels in the last two photos, 17 are C1 crops (sellable product visible), 2 single items,
     15 bare. Today's model answers half on 10 of the 17 and empty on 7 (a model trained on C1: 13 and 4).
     In validation that is roughly 20-35 areas where the E/H rule decides +1 against -2 or -3.
  4. One official label exists: the brief's example gives 6215_2 at 20:24 as `half`. Our label for 6215_2 at
     18:35 is E and the photo shows one bunch of bananas. With evening replenishment that rare, the likelier
     story is that the organisers call one sellable bunch "half". The humans also labelled a similar single
     bunch H at 12:59, so our own labels are not consistent on this case.
  5. `AreaMemory._change_features` hands every later crop the labels of the area's last two photos. Those
     labels are inputs at inference for every validation crop, not only training targets.
  6. Caution rules on the saved probabilities (minimum P(empty) to answer empty, minimum P(full) to answer
     full): every setting loses against A, C1 and B on late and fwd, except P(empty)>=0.6 against C1 (+0.02).
     The decision rule stays as it is.
  **Proposal (humans first, then your retrain):** one consistent rule for "a few sellable items" (my reading:
  half) applied by the humans to the evening photos. `cache/opiniao_fim_do_dia.txt` is a second-opinion file for
  `labeler/app.py --resolver`: today's labels except the 29 C1 crops (-> H) and the last three photos where the
  model, trained on earlier photos only, answers lower or differs on E/H. It shows 26 areas, 48 photos (15 on
  Rodrigo's cameras, 11 on Francisco's). Upward model flags (H->F) are left out on purpose. After `--apply`,
  retrain; I can then measure late/fwd on the new labels if you want. Also worth adding to the rehearsal: the
  last photos under new, later file names, since validation names are not in the reference day.
- [Opus 21:15] **Label fix ready, measured, NOT applied (I am not allowed to write the shared label files; the
  user has the two commands).** The user reported the app answering "empty" on 6371_7 at 19:19 with three
  melons in the crate and said this must not happen. That crop is labelled E, so the shipped model learned it.
  I reviewed the last four photos of all 152 areas by eye (sheets cut from the originals) with the organisers'
  rule. Result, set **v3: 24 photos in 13 areas, E -> H** (sellable product visible; comply N -> T):
  6215_2 t11; 6215_4 t6,10,11; 6215_8 t7; 6215_9 t10,11; 6371_7 t12; 6376_2 t0,1,2; 6383_9 t12; 6385_5 t13;
  6443_11 t6-11; 6462_9 t12; 6468_15 t12; 6491_7 t11; 6591_6 t11,12. Dropped from the old C1 list: 6594_9 t0-2
  (one net of garlic = one unit) and 6383_7 t11,12 (wrong product in the basket). Single units stay E.
  Same engine as shipped (HOUR_SCALE=0, validated rects), bank_tta, same folds:
  | train / truth | late | late, 2 steps out | fwd |
  |---|---|---|---|
  | today / today | +0.605, 79.3% | +0.474 | +0.765, 86.3% |
  | today / v3 (what we score now if v3 is right) | +0.688, 83.4% | +0.599 | +0.794, 87.7% |
  | v3 / v3 | +0.730, 85.5% | +0.664 | +0.802, 88.0% |
  | v3 / today (cost if v3 is wrong) | +0.602, 79.1% | +0.493 | +0.756, 85.7% |
  So: +2.1 pp late / +0.3 pp fwd if right, -0.2 / -0.6 if wrong. CV understates it, because the shipped model
  has also seen the E labels of the last photos, which are its references for every validation crop.
  **Fable, after the user applies it (silver mtime changes from 17:18): retrain both models + selftest.**
  Later `--apply` runs must list the new reviewer first (`--apply claude rodrigo francisco`), otherwise the
  labeler reports 13 conflicts and writes nothing.
- [Opus 21:15] Also measured, same setup: **"causal memory"** (training crops described only from older frames
  of their area, as validation crops will be). Worse: late +0.586 / +0.559 (two variants) vs +0.605, fwd +0.733 /
  +0.707 vs +0.765, with more over-estimates. Rejected, do not retry. The 8 borderline full -> half relabels I
  considered add nothing measurable in training (+0.2 pp) and cost 1 pp if wrong: not proposed.
- [Opus 21:15] Note for the 80/20 choice: two steps after the last training photo the model is much weaker than
  one step after (+0.474 vs +0.737 on today's labels). About half of the validation images are two steps out.
- [Opus 21:30] **Rehearsal with unseen file names, shipped `engine.pkl` (read-only, output in my scratch).**
  The last photo of each camera copied under two later capture times (+4000 s, +8000 s): 28 images, 304 areas,
  0 missing, 0 malformed, 48.7 s on cuda. So later, unknown timestamps are handled.
  The answers equal the label of that last photo in **152 of 152 areas**, and the two times give identical
  answers. In practice the labels of the last photo are our submission wherever the shelf has not changed.
  On the 10 areas of set v3 that sit in the last photo (6215_2, 6215_4, 6215_9, 6371_7, 6383_9, 6385_5, 6443_11,
  6462_9, 6468_15, 6591_6) the shipped model answers **empty**, with sellable product in the crate. With two
  validation images for most cameras that is up to 19 area-answers.
- [Opus 21:30] State of the labels: **nothing changed.** `labels/silver_labels.txt` is still the 17:18 file and
  `labeler/labels/` holds only the humans' files. The user asked whether I had changed the hand-made labels
  (no) and told me to ignore `labeler/labels/francisco_edge.json` for now; I never read it.
- [Claude, Rodrigo's session, branch `count-units`, 21:30] UI-only feature, nothing for Fable to apply to the
  engine. "Count units" button: a vision model (OpenRouter, same key as the assistant) boxes the visible units
  of one slot on demand. New `shelfos/counting.py`; two additive routes in `shelfos/server.py`
  (`/api/count/policy`, `/api/count`, imported lazily). No GPU, no change to engine/predict/service, nothing
  reaches predictions.json. Off by default: product groups are enabled only after `tools/count_eval.py` passes
  on hand counts (`labels/unit_counts.txt`, new file, not silver labels). Please review `server.py` before merging to main.
`n- [Codex] Backend :8000 restarted for merged count-units routes (pid 38616, python -u run.py --no-browser). Logs: runs/count-backend.stdout.log / stderr.log. Counting policy configured, 16 large products enabled experimentally via .env; no counting API requests made. Static web/out refreshed with visible counting availability explanations.
- [Codex] At user request, SHELFOS_COUNT_GROUPS=all enables experimental counting for every product, including bunches and bulk produce. Backend :8000 now pid 26132 (python -u run.py --no-browser), logs runs/count-all-backend.stdout.log / stderr.log. Seven counting tests pass; static UI rebuilt. Wrong-product areas remain excluded; model may decline indistinguishable units. No external count requests made.
- [Codex] Counting speed: memory-backed disk cache, exact source/geometry cache invalidation, same-area requests share one in-flight call, OpenRouter latency routing, precount --workers 1-4 (default 3). Nine tests pass. Backend now pid 22252; logs runs/count-fast-backend.stdout.log / stderr.log. No external count calls or model/label changes.
- [Codex] Added optional visual banana-ripeness check in shelfos/ripeness.py and POST /api/ripeness, isolated from stock/official output. Uses cropped snapshot via OpenRouter, cautious appearance states, review advice, separate runs/ripeness.json cache, max 500 output tokens. Twelve tests and web build pass. Backend :8000 now pid 19932, logs runs/ripeness-backend.stdout.log / stderr.log.
- [Codex] Banana ripeness v3 follows an estimated strict majority (>50%) of individually visible bananas; a minority does not force mixed. Example real 6468_12 latest: 6 green / 1 ripe -> Mostly green (2094 ms). 15 tests and build pass. Backend :8000 pid 41024, logs runs/ripeness-majority-backend.stdout.log / stderr.log. Stock engine/labels unchanged.
- [Codex] Ripeness v4 assesses main peel body, ignoring isolated green tips/stems and isolated bruises. Real checks: 6215_4 at 11:49 -> Mostly ripe (10 ripe / 1 turning, 1904 ms); 6468_12 latest remains Mostly green (6 green / 1 turning). 15 tests pass. Backend :8000 pid 42760, logs runs/ripeness-v4-backend.stdout.log / stderr.log. No engine/stock/labels changes.
- [Claude, Francisco's session, 11 Oct 00:55] From a read-only audit; nothing was run, none of these files was
  touched. For Fable to decide:
  - Memory time: `AreaMemory.t` is the frame index (`bank.py:25-28`, `engine.py:134`) but `t_query` is a Unix time
    (`engine.py:203`), so `self.t[pool] < tq` (`memory.py:136`) is always true for a crop that is not in memory.
    Validation is unaffected (it is later than everything). `cv.py --split lofo` is affected: a held-out frame is
    described from later frames of its area. late/fwd are not touched. Suggest: keep as is and stop quoting lofo.
  - `memory.py:141` sorts by |t - tq| and line 142 re-sorts by time, so first-frame training rows are described
    from the last two frames of the day, not the nearest two. Changing it changes the features of those rows:
    retrain + CV, your call. Not the causal-memory study, which stays rejected.
  - `OCC_SCALE`, `MEM_SCALE`, `HOUR_SCALE`, `OBSTRUCT`, `ONLINE` are read from source at inference (`engine.py:184`,
    `195`, `260`), not from the pickle. A pkl fitted under other values loads without complaint. Suggest copying
    them onto the instance in `fit` and reading them through getattr with today's values as default.
  - `tools/rehearsal.py:35` scores against `labeler/output/merged_annotations.json`, which here is older than the
    19 relabels of 21:37: re-merge with `revisao` first. Line 95 divides by `s['max']` (0 if no frame has truth).
  - `tools/cv.py:58` lets a comply label win over "empty is compliant"; `tools/edgecase_train.py:71` does the
    opposite. Four crops are E with a sure F: 6376_5 t5-7, 6383_7 t12. At most 1 id answer in late, 4 in fwd.
    Suggest `truth_id = np.where(y == 0, int(empty_compliant), c)`. Measured facts were taken with the current line.
  - `tools/lab.py:6` documents `--split late,fwd`; only `--split=late,fwd` is parsed (427-430), the other form
    raises KeyError.
  - Pins: `requirements.txt` has only `>=` bounds and `engine.pkl` pickles sklearn and numpy objects. Please post
    `pip freeze` for scikit-learn, numpy, torch, timm and opencv from the training machine so they can be pinned.
  - Labeler: `--apply rodrigo francisco` as written in `README.md:157` and `labeler/README.md:62` now stops on
    conflicts; `revisao` has to come first, as noted above. The two READMEs still show the old command.
- [Claude, cloud session, 11 Oct 08:50] **Lite speed-up, branch `claude/fast-lite` — measured in a cloud copy, nothing on
  the shared machine was run or touched.** No DINOv3 weights there (Hugging Face is blocked), so the backbone had random
  weights: timings are real, accuracy has to be checked on your machine with the real weights.
  - `tools/profile_lite.py --images <folder> [--model models/engine_lite.pkl] [--cpu]`: ms per stage of one image,
    read-only. On the cloud CPU (4 cores) the lite takes 3.05 s/img, the same as your 3056 ms: backbone 95%,
    memory comparisons ~90 ms, everything else < 30 ms. **Run it on the GPU first** to see where the 347 ms go.
  - `memory.py`: with `AreaMemory.to("cuda")` (done by `ShelfService` when the embedder is on the GPU) the reference
    patch tokens stay on the GPU and the similarities are one batched matmul there. CPU path unchanged and
    **bit-identical** (0 differences in level, compliance and probabilities on all 1962 reference crops). GPU path:
    same numbers up to float32 rounding (max 4e-7; 0 level / compliance changes on the CPU-torch test of all 1962).
    VRAM: ~0.6 GB for the lite memory, ~1.4 GB for the full one.
  - `features.py`: `SHELFOS_INT8=1` (CPU only, opt-in, default off) quantizes the backbone's linear layers:
    backbone 1181 -> 622 ms per 10 crops, lite 3.05 -> 1.9 s/img with the mirror on. Without the mirror (bank built
    with `tta=False`, README: same stock points, product 0.980 -> 0.970) it would be ~1 s/img.
  - `tools/compare_predictions.py before.json after.json`: how many answers changed.
  - **To accept:** on the GPU machine, `run.py --images <folder>` on `main` and on the branch, then
    `compare_predictions.py`: must be 100% the same; then `profile_lite.py` on both. For INT8: build the bank and
    train with `SHELFOS_INT8=1` on the CPU, compare with the fp32 lite and run `cv.py --split fwd/late` on that bank.
- [Opus, 11 Oct 10:10] **Acceptance of `claude/fast-lite` on this machine, real weights, RTX 4050 on mains power.**
  The branch was merged into `main` at 09:55 before this was run. Code before = `81648df`, after = `44fe667`, both
  extracted into my scratchpad; models = the 23:22 / 23:24 pickles; 56 images (the last two photos of every camera
  under their own names and again under names 4000 s later), 608 areas.
  - **GPU memory path: accepted.** lite: 0 of 608 stock answers and 0 compliance answers changed, no probability
    differs; median 202 -> 149 ms per image. full: 0 and 0 changed, one probability differs by 0.0001; 500 -> 404 ms.
  - CPU fp32, lite, 14 images: 0 of 152 answers changed, no probability differs.
  - **`SHELFOS_INT8=1` must stay off with the pickles we have.** int8 inference on the fp32-trained `engine_lite.pkl`
    changes **56 of 152 stock answers and 62 of 152 compliance answers** (P(compliant) 0.999 -> 0.2-0.4, occupancy off
    by up to 0.44): the quantised features are not the fp32 features. It is only usable with a bank built and a model
    trained under the same setting, and that has not been cross-validated. Speed here: 2.5-3.1 s -> 2.0 s per image
    (14 threads), so about 1.3-1.5x, not 2x.
- [Opus, 11 Oct 10:45] **Study on the labels of 23:21 (the ones the installed models were trained on). Nothing in
  production was changed.** Same engine code, same folds, one bank per feature extractor; "vs lite" counts points
  answer by answer against `bank_tta`. % of max = stock + product. Logs `cache/opus11_*.log`, held-out predictions
  `cache/oof_opus11_*.npz`; scripts and scratch banks in my scratchpad. These replace the "Measured facts" at the top,
  which were taken on the labels before 21:37.

  | feature extractor, views of each crop | late (n=304) | fwd (n=1216) | vs lite, late / fwd | GPU ms per image | CPU s per image |
  |---|---|---|---|---|---|
  | ViT-B + ViT-L, mirror: `engine.pkl`, shipped | +0.717, 84.9% | +0.797, 87.6% | -1 / +1 | 400-470 | not run |
  | ViT-B, mirror: `engine_lite.pkl` | +0.720, 85.0% | +0.796, 87.7% | | 142-180 | 2.1-3.7 |
  | ViT-B, no mirror (`bank.npz`) | +0.661, 82.1% | +0.768, 86.3% | -18 / -34 | | |
  | ViT-B, 4 views | +0.737, 85.4% | +0.791, 87.8% | +5 / -6 | | |
  | ViT-B, 160 px crops, mirror | +0.714, 84.7% | +0.782, 87.1% | -2 / -17 | | |
  | ViT-S, mirror | +0.688, 83.4% | +0.787, 87.5% | -10 / -11 | 165 | 1.3 |
  | ViT-S, 4 views (crop, mirror, both upside down) | +0.776, 87.8% | +0.804, 88.6% | +17 / +10 | 170-217 | 1.4-1.6 |
  | ViT-S, 8 views | +0.766, 87.3% | +0.808, 88.8% | +14 / +14 | | |

  "vs lite" is in stock points. Noise: two extractors of the same quality differ by about 15 points on late and 25 on
  fwd (10-19 and 31-57 answers move, about half each way). Times are per image through `ShelfService` on this laptop on mains power and vary 20% on the GPU
  and 40% on the CPU from run to run; the ranges are what I saw. The lite row run again with the code now on `main`
  equals the run before the merge (0 answers, 0 probabilities differ).
  1. **Full is not better than lite on these labels** (late -1 point, fwd +1) and takes 2.8x the time. On the 96
     reviewed synthetic edge cases (1136 areas) full is ahead: 46.5% of max, ViT-S 4 views 45.0%, ViT-S mirror 44.9%,
     lite 44.3%; the difference is the product answer under packaging and shoppers (1084 right against 1064 for lite).
  2. *(The accuracy claim is superseded, see the correction of 11:10 at the end: on a second held-out split the
     advantage is gone.)* **ViT-S with 4 views is the best row on both splits and halves the CPU time of lite; on this GPU it is no faster
     than lite** (four small forward calls: backbone stage 110-137 ms against 98). Checked end to end in a scratch
     copy of `main`: patch `cache/opus11_tta4.patch` (`features.py` +17 -7, `bank.py`, `train.py`,
     `tools/build_bank.py`; `git apply --check` passes on `6dc1f57`). With the patch, `engine_lite.pkl` and
     `engine.pkl` give the same 608 answers and probabilities as without it. A ViT-S 4-view engine built with
     `build_bank` + `train` passes `tools/selftest.py` (ALL GOOD) and answers the last two photos of every camera
     under later names like our label in 303 of 304 areas (lite and full: 304).
  3. **Blob counts from the occupancy map: no effect.** Eight connected-component features at threshold 0.5 move 0 of
     1520 held-out answers; at three thresholds 4 move, 2 right and 2 wrong. The trees do use them (probabilities
     change by up to 0.17). Dropped.
  4. **Robustness** (late-holdout engine; the last two photos altered and answered again; clean = 85.0%).
     Brightness +-30%, gamma, contrast, colour temperature, saturation, noise, JPEG 40, half resolution: 83.2-86.5%,
     0 to 8 of 304 answers move. The reference day itself changes 0.8% in brightness from one photo to the next and
     4-6% over the open day. Blur sigma 2: 18 move. **A shifted camera is the weak point: 4 px moves 11 answers (10
     down), 8 px 28 (26 down), 16 px 70 (65 down), 63.5%.** Installed lite under later names: 0 stock answers move
     for light and colour (1-2 product answers at a 15% colour shift); 1 / 4 / 46 for 4 / 8 / 16 px. ViT-S 4 views: 85.0-89.0% for light and colour, 85.7 / 80.9 / 70.2% for the
     three shifts. On the reference day no camera moved (parts of every frame stay within 0.5 px all day; phase
     correlation outside the planogram areas, checked on known shifts); in 6373 pieces of furniture sit 3 to 7 px
     apart at different hours. No change proposed.
  5. `SHELFOS_INT8`: int8 features have cosine 0.38 (global) and 0.46 (patches) to the fp32 ones for ViT-B, 0.42 and
     0.52 for ViT-S. Suggest removing the switch.
  6. Averaging the saved probabilities of two extractors gains at most +19 / +22 points (ViT-S 4 views + ViT-B 4
     views, 2.5x the cost of lite); a softer or sharper decision (T 0.5 to 3) changes 0 to 5 points. Not proposed.

  **For the user to pick, Fable to apply:**
  - (a) No new code: ship lite. In `run.py`: `BANK = cache/bank_tta.npz`, `MODEL = models/engine_lite.pkl`,
    `REFERENCE = models/reference_day_lite.json`, `BACKBONES` = ViT-B alone. Same score on real frames as full, 2.8x
    less time per image.
  - (b) **Withdrawn at 11:10, see the correction below.** ViT-S 4 views: `git apply cache/opus11_tta4.patch`, then
    `python tools/build_bank.py data/planogram.json data/images cache/bank_s4.npz vit_small_patch16_dinov3.lvd1689m 224 --tta4`
    (the first run downloads 82 MB into `models/backbone/`) and
    `python -m shelfos.train --bank cache/bank_s4.npz --out models/engine_s4.pkl --reference models/reference_day_s4.json`;
    point `run.py` at those; `tools/selftest.py`, `tools/rehearsal.py --zip`, restart the backend.
- [Opus, 11 Oct 11:10] **Correction to finding 2 and to (b) above: ViT-S with 4 views is not better than lite.**
  Checked on a second held-out split, `odd`: photos 1-2, 3-4, 5-6 and 7-8 from the end held out, trained on the
  past only. With `fwd`, every photo from the last to the ninth from the end is answered twice, once one step and
  once two steps after the newest training photo: 2432 answers. Labels of 23:21.
  - ViT-S 4 views against lite on `odd`: +0.770 against +0.772 stock points per area. Over fwd + odd: **+7 stock
    points, 95% interval -86 to +98** (bootstrap over the 152 areas). The +17 / +10 in the table was noise.
    **(b) is withdrawn; (a) stands**: lite and full tie on late and fwd, and lite takes 2.8x less time.
  - Where the points are lost (lite, +1907 over the 2432 answers). Shelf at the same level as in the newest training
    photo: 2120 answers, 2086 right, +2013. **Shelf lower than in that photo: 225 answers, 132 right, 88 answered
    above, -142.** Shelf higher: 87 answers, 70 right. ViT-S 4 views loses them the same way (131 of 225 right, 89
    above).
  - Tried: training crops whose label differs from the previous photo of their area weigh 1 + W. ViT-S 4-view bank,
    same 2432 answers, engine +1914: W=1 -22, W=2 -14, W=4 +6, W=8 +21 (drops right 131 -> 141 of 225; same-level
    crops answered below 22 -> 27). Only the drops weighted: W=2 -4, W=4 -8, W=8 -15. `min_samples_leaf` 10: -8.
    Without the change features: -46. All of it is inside the interval above and none was repeated on `bank_tta`,
    so **there is nothing to propose**. The rows after W=8 ran after the label change of 10:56 (two labels) against
    a baseline from before it.
  - Logs in my scratchpad: `out/k_stats.log`, `l_errors.log`, `m_trans.log`, `n_diag.log`.
- [Opus, 11 Oct 11:10] **Code check asked by the user (a list from another assistant), against `f147488`.** Nothing
  in the repo was changed. Two things are worth a fix, both small:
  - **The empty-area switch is still on the run screen** (`web/app/run.tsx:148-159`, in the built `web/out` too;
    `POST /api/policy`, `?empty=` on `/api/predictions`) as well as in `run.py`, `shelfos/predict.py` and
    `tools/cv.py`. It is off by default everywhere. Its tooltip still says the brief leaves the question open. 93 of
    our 1950 labelled crops are empty (4.8%); with the switch on each of them goes from +1 to -2, about 7% of the
    maximum. **Done at 11:45 at the user's request: see the last entry of this section.**
  - `tools/edge_manifest_from_labeler.py`: the docstring shows `--out FILE`, the code reads only `--out=FILE`. Run
    in a scratch copy: with the space it stops with an error and writes nothing (`FileNotFoundError`, or
    `AttributeError` when the file exists, because the output path is read as one more input). `--out=FILE` works
    and gives the `manifest_human.json` we have, byte for byte. Fix: argparse, or `--out=` in the docstring.

  Checked and fine:
  - `run.py --images` does check the file since `2747a61` (00:49). `run.predict()` called with a stand-in for the
    model printed "validated" for a complete set of answers and listed all 4 faults planted in a damaged one. It
    reports them and exits 0; `python -m shelfos.predict` exits 1.
  - The three `folds()` (`tools/cv.py`, `exp2.py`, `experiment.py`) hold out and train on the same rows for `late`
    (304 / 1646 on `bank_tta`) and `lofo`, and the first two for `fwd`. They differ in what they return, not in the
    split.
  - `tools/cut_product_assets.py` reads a folder of this laptop (it exists here); Pillow comes with torchvision.
  - Unused, safe to delete, housekeeping only: `tools/exp2.py`, `exp3.py`, `experiment.py`,
    `experiment_compliance.py`, `occ_probe.py`, `lab_sequential.py` (nothing outside these six imports them; `tools/` is not
    copied into `release/`); `STOCK`, `LEVELS`, `VALUES` in `shelfos/labels.py` and `id_points`, `decide_compliant`
    in `shelfos/scoring.py` (no other file uses them and neither pickle refers to them).
- [Opus, 11 Oct 11:15] **Rules on top of the engine's answer: nothing to propose. Labels of 10:56 (after the vote).**
  Same 2432 held-out answers (fwd + odd), engine fitted per fold on today's labels: lite (`bank_tta`) 2291 right,
  50 below, 91 above, +1918 stock points; ViT-S 4 views the same 2291 / 50 / 91, +1918. They tie to the point.
  - Answered half and occupancy below T -> empty: T=0.03 +12 (lite) / +4 (ViT-S); from T=0.05 up it is 0 or negative
    on both (T=0.10: -11 / -7). Labelled-half crops go down to occupancy 0.04.
  - Answered half and occupancy below 0.3 x the lowest training 'half' of the same area -> empty: +12 (3 answers
    moved, 0 worse) on lite, +24 (6 moved, 0 worse) on ViT-S. At 0.5: +16 / +7, at 0.7: +26 / -5, at 0.9: -49 / -67.
    Three to six answers out of 2432; too few to call.
  - Answered full and occupancy / full references below T -> half: negative at every T (0.7: -20 / -11).
  - Answered full and occupancy fell by more than T since the last photos -> half: T=0.15 +14 / +2, T=0.10 -39 / +2.
  - Why: of the 91 answers above the label, about 71 are 'full' answered on a 'half' label. Their occupancy against
    the full references has median 0.91 (quartiles 0.87 to 0.97); the 1886 right 'full' answers have median 1.00
    (0.98 to 1.02), and 5% of them are below 0.89. Contact sheet of the 11 missed drops of the late fold: six are
    full -> half with a few fruits gone from one corner, five are half -> empty with one to three items left.
  - Scripts and logs in my scratchpad: `p_feats.py`, `q_rules.py`, `out/q_rules.log`, `out/diag_S224t4_*.jpg`.
  Nothing of mine is running.
- [Opus, the user's chat window, 11 Oct 11:45] **Applied at the user's request: the empty-area switch is gone
  (commit `171858e`). Nothing in `shelfos/engine.py`, `models/`, labels or rects was touched.**
  - What changed. `run.py`, `python -m shelfos.predict` and `tools/cv.py` no longer take `--empty-noncompliant`
    (they stop with "unrecognized arguments"). `ShelfService` takes no `empty_compliant`, has no such property, and
    sets `engine.empty_compliant = True` on every engine it loads, the lite variant in `server.py` too.
    `predictions()` and `score()` take no policy. `POST /api/policy` is removed and `?empty=` is ignored. The switch
    and its tooltip are off the run screen (`run.tsx`, `page.tsx`, `api.ts`); `web/out` was rebuilt at 11:36 from
    the same sources (the build of 10 Oct 23:39 is saved in my scratchpad, `p3/web_out_backup`). The store and
    health payloads keep `"emptyCompliant": true` as a constant, for the assistant's context.
  - What stays, on purpose: `Engine.empty_compliant`, `official(pred, empty_compliant=True)` and `p_identity` in
    `engine.py` (not mine to edit) and the `empty_compliant=True` argument of `cv.evaluate`. Nothing a person can
    reach sets them to false any more.
  - `tools/selftest.py`: its last check flipped the switch, so it is replaced by "an area seen as empty
    (P(empty) >= 0.5) is reported planogram_compliant true", over every image the selftest analyses.
  - Tested with the models of 10:57 / 11:00. Same 56 images (the last two photos of every camera, twice) before
    and after: `predictions.json` byte for byte the same, lite and full (608 areas, 48 answered empty, all
    compliant). The old switch turned exactly those 48 answers to false. `tools/selftest.py` ALL GOOD (42 empty
    areas in the new check). `tools/rehearsal.py --zip` REHEARSAL OK (28 images, 304 areas, folder and zip
    identical). The 27 unit tests pass. Server with the real lite model and a model file loaded as if saved with the
    switch on: 20 checks pass. The app started through `run.py`'s own `main()` on a spare port with the full model:
    folder in, `predictions.json` out, equal to the command line's. `next build` and eslint clean.
  - **For Fable.** (1) `tools/rehearsal.py` scores against `labeler/output/merged_annotations.json` of 10 Oct 17:38:
    13 of its 304 stock labels on those images differ from the labels of 10:56, so it prints 90.3% where the same
    answers score 98.5% against the labels the model was trained on (the same before and after my change). Its
    format check is what counts; the score line misleads. (2) `release/` is the build of 10 Oct and still has the
    old switch: run `python tools/release.py` before it is used again. (3) The app on :8000 needs a restart (old
    code, model of 23:24).
