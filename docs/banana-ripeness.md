# Visual banana ripeness (experimental)

Open **Camera → a banana slot**. The visual check starts automatically. It uses the selected frame and only the slot's
polygon; neighbouring pixels are greyed out. The result is a short appearance estimate: green,
ripening, ripe, very ripe, mixed, unclear or no bananas visible. Extensive browning triggers
**Review shelf**; a few brown spots do not. Poor visibility yields **Cannot assess**.
Limited visibility can still yield a stage estimate when the visible peel colour is readable;
the UI explicitly labels that result as an estimate from visible peels.

The stage follows an estimated distribution of individually visible bananas: **more than 50%**
must be in one stage to display **Mostly green / Mostly ripening / Mostly ripe / Mostly very ripe**.
A minority of differently coloured bananas does not change the majority. Without a majority,
the result is **Mixed ripeness**. These stage counts are visual estimates, not verified inventory counts.

This does not establish freshness, spoilage, food safety, age or expiry. Review quality in person.
It has not been validated against human ripeness annotations.

The optional OpenRouter request starts when a connected banana slot is opened. It uses `OPENROUTER_API_KEY` and
`OPENROUTER_RIPENESS_MODEL` (falls back to `OPENROUTER_MODEL`). Uses low reasoning effort and a
1600-token budget; an unreadable/empty response is retried once with 3000 tokens.
Results are cached separately in `runs/ripeness.json`; changes to the image, polygon, model or
prompt version invalidate the result. Identical simultaneous requests share one call.

`shelfos/ripeness.py` and `POST /api/ripeness` are separate from stock inference. They do not
train a model, update labels, write `predictions.json` or alter `ShelfService` predictions.
Slots holding a wrong product are refused. Existing stock/API inference remains unchanged.

Verification: `python -m unittest tools.test_ripeness tools.test_counting`.
