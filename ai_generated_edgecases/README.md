# Reviewed synthetic stress tests

15 existing AI images were audited; 8 controlled variants were generated and visually reviewed. Prompts are in `prompts.json`; observations, partial labels and train/test assignments are in `manifest.json`. Generated output, rather than the intended prompt, determines each label.

The test set contains 45 reviewed areas: 38 stock labels and 45 compliance labels. Ambiguous stock, occluded quantities and distorted geometry are excluded from scoring. Camera 6371 has an incompatible aspect ratio and is prediction-only. Four pineapple variants from camera 6468 are training-only. Controlled test edits use a different camera/source (6443). Existing image source provenance is unknown; they are test-only and should not become training data.

These are local, visually judged labels, not official ground truth. The selected difficult examples do not estimate real-world accuracy. Review half/full boundaries with the mentors before enlarging the dataset. Generation can change textures, geometry and unrelated objects; inspect every new output.

## Reproduce

From the repository root, with the existing Python environment and model checkpoints:

```powershell
python tools/edgecases.py
python tools/edgecase_train.py
python tools/edgecases.py --models models/edgecases/edge_baseline.pkl models/edgecases/edge_candidate.pkl --out outputs/edgecase_training/comparison
python -m unittest tools.test_edgecases
```

The evaluator creates `REPORT.md`, `results.json`, model predictions, a manifest snapshot and `review.html` with crop-by-crop failures. Training creates separate experimental checkpoints; production checkpoints are not overwritten. Exact image duplicates and source families cannot cross train/test splits. The trainer also checks that controlled training sources belong to the real training partition.

## Measured on 2026-10-10

| Comparison | Baseline points | Candidate points | Maximum |
|---|---:|---:|---:|
| Real holdout: last two frames/camera, 304 areas | 442 | 450 | 608 |
| Separate synthetic test labels | 36 | 40 | 83 |

The candidate refits only the stock head with four reviewed synthetic crops weighted 0.25. Real stock overestimates fell from 28 to 26; synthetic overestimates fell from 2 to 1. Compliance did not improve. This is a small pilot, not evidence to deploy the candidate: validate several forward-time folds and independent real edge cases first.

Production lite/full scored 30/83 and 36/83 respectively on these stress-test labels. Full detected 3/7 wrong-product cases, classified 3/9 sparse-stock cases correctly, and passed all five packaging-only cases. See `FABLE_BRIEF.md` for the actionable failures.

Measured median frame inference was 371 ms lite and 984 ms full, excluding model startup. Experimental baseline/candidate medians were 292/327 ms, but sequential runs on a shared GPU are noisy; these numbers are not a controlled speed comparison. The candidate uses the same backbone and inference structure. Benchmark speed again on an idle GPU before claiming equal or better latency.
