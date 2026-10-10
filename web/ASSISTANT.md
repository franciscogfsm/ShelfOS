# ShelfOS AI

The conversation waveform icon in the main navigation opens the theme-aware chat widget. It supports streaming, keyboard sending, stopping a response, new conversations and clicking known area IDs to inspect that shelf. Chat state lasts for this browser session; it is not written to disk.

Copy `.env.example` to `.env` in the project root and set `OPENROUTER_API_KEY`. The optional `OPENROUTER_MODEL` defaults to `google/gemini-3.8-flash`. Never prefix the key with `NEXT_PUBLIC_`; it remains exclusively in the Python server. Restart the ShelfOS backend after updating its code. The root `.env` is read for configuration on each request.

The existing static frontend remains compatible with `web/out`. Build it with `npm run build` in `web/`; the ShelfOS server hosts it alongside `/api/assistant` and `/api/assistant/chat`. During Next.js development, use `?api=http://localhost:8000` or set `NEXT_PUBLIC_API=http://localhost:8000` so the dashboard and assistant use the same backend.

The server supplies its authoritative snapshot: selected time, camera/area, all camera histories, current predictions, confidence, obstructions, memory sources, product catalogue and current run metadata. User-completed task flags are identified as UI state. Occupancy heatmaps and raw camera images are not uploaded. The assistant cannot visually inspect photos or change store data. It does not have sales/back-room inventory or official ground truth unless those are added as actual data sources.

The model receives compact history and current-state data on each request. This is fast enough to avoid GPU inference, but provider latency and context cost still need measurement with your actual key. The current model recommendation was verified against https://openrouter.ai/google/gemini-3.8-flash. Set a different model ID in `.env` to compare.

Provider authentication, credit and connection failures are surfaced in the chat. Tests mock the provider stream; a live paid request requires your OpenRouter key and credits. Keep the local ShelfOS service private; deploying publicly requires authentication and usage limits for this paid endpoint.
