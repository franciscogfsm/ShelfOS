# Visual review notes

The generated collection was checked in contact sheets for full camera framing, visible scene content and obvious generation artifacts. This is image-level inspection, not area-level ground-truth annotation. No new stock/compliance labels were inferred from prompts.

Observed deviations that matter when annotating:

- `bulk_6215_empty` empties the banana display AND the bottom citrus crates. Label the actual output, not just the intended target.
- `bulk_6215_full_stock` fills several previously empty banana compartments. It changes more than one area.
- `bulk_6215_wrong_bananas` adds bananas to originally empty compartments; it does not show the intended tomato substitution. Do not automatically count it as a wrong-product negative.
- `bulk_6215_mixed_products` visibly changes the bottom citrus crates as well as the intended region.
- Fridge camera 6383 has glass, glare, small packages and a closed roller blind: several stock variants look very similar at thumbnail size. Review rectified crops at full resolution before calling these labels or distinct stock states reliable. Some wrong-product variants affect multiple fridge compartments.
- Some severe glare outputs produce exaggerated reflections; use these as severe synthetic stress tests, not evidence of real-world prevalence.
- Occluded quantities are unknown. A visible hand or person is not proof of the amount of food behind it.
- `degraded_cctv` is an AI-generated approximation of degradation, not calibrated blur/compression severity.

Use the real reference frames in `reference_sources/` to compare geometry and unintended edits. Camera 6371 in the older collection has a mismatched aspect ratio and stays prediction-only. Near-full/half boundaries need the agreed competition labelling convention.

Keep these images as test inputs. For training, generate a separate source-family-disjoint collection, review labels, use a low synthetic weight, and validate gains on untouched real temporal holdouts.
