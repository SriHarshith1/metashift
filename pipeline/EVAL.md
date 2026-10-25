# Extraction eval

Command: `METASHIFT_OLLAMA_MODEL=<model> uv run metashift eval extract --game lol`
Golden set: `tests/golden/lol/` (26.19, 26.20, 26.21 — 133 changes, labeled from the official notes, rules in `tests/golden/lol/REVIEW.md`).
Targets: precision ≥ 0.95, recall ≥ 0.90.

## 2026-10-25 — `gemma4:31b-cloud` (Ollama Cloud, free plan, via local Ollama)

| Patch | P | R | tp | fp | fn |
|---|---|---|---|---|---|
| 26.19 | 0.95 | 0.90 | 36 | 2 | 4 |
| 26.20 | 1.00 | 1.00 | 34 | 0 | 0 |
| 26.21 | 0.93 | 0.97 | 57 | 4 | 2 |
| **total** | **0.95** | **0.95** | 127 | 6 | 6 |

Targets met. Run time: about 1 minute for all three patches.

Remaining mismatches:
- 26.19 Teleport: the model merges two cooldown lines into one row (model error).
- 26.19 "World Atlas and Runic Compass": the model labels it an item; it matches no Data Dragon name, so extract drops it (pipeline gap: combined item names).
- 26.21 Taric "Cast Behavior": model keeps it; the golden set skips it as a bug fix (debatable).
- 26.21 Taliyah "Monster Damage": the model skips it (model error).
- 26.21 Hubris per stack: model says adjust, golden says nerf (debatable).

## Models that could not run

- `qwen3.6:27b` (local): 17 GB, does not fit the 11.8 GB of GPU memory on a 16 GB Mac.
- `qwen3:14b` (local): fits only with a smaller context; with `num_ctx` 32768 it ran 25% on CPU. Not measured.
- `minimax-m3:cloud`: not in the Ollama Cloud free plan (HTTP 402).

## Manual check — first real reports (2026-10-25, `gemma4:31b-cloud`, no stats)

Reports for 26.19, 26.20 and 26.21 were built oldest first, so each one has the history of the earlier patches. No stats were given: every `stats.csv` is a template with blank values.

- 5 random changes from 26.21 checked against the notes (Nidalee E, Hubris, Lee Sin R, Rammus W, Varus W): all 5 correct, directions sensible.
- Reasons quote real values and use history (Lucian 26.20 refers to the mixed 26.19 change).
- One wrong detail: Vayne 26.20 reason says "base health"; the change is health regen per 5.
- No rise/fall consistency warnings in any report.
- Analyze takes 4–7 s per patch; the whole run for one patch is under 30 s.
