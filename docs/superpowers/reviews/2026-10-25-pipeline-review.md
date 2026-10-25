# Pipeline review: Metashift Tasks 1-10 (2050af9..768c08c)

Reviewer method: read the full diff, the spec, plan Tasks 3, 6-10 and Global Constraints, and the ledger. Then ran the real adapter (`.venv`, output to scratchpad only) on the saved real 26.21 notes fixture to produce `raw.md` and measured the chunker, the quote check and name matching on it. No repo file was changed.

Facts measured on the real 26.21 `raw.md` (40,986 chars, 142 `⇒` lines, 0 `→` lines):
- `split_sections` gives 10 chunks of 438 to 5,968 chars. Largest prompt about 2.5k tokens, far below `num_ctx` 32768. Prompt size is not a problem.
- 140 of the 142 change lines contain `**` (bold new value). All start with `* `.
- Zero backslash escapes in the markdown. Markdownify escaping is not a problem on this page.
- Arrow lines by `##` section: Champions 48, Items 7, Mid-Patch Updates 2, **Arena 72, Classic 13**. Only 57 of 142 (40%) are Summoner's Rift changes.
- The densest chunk (Arena, chunk 8) has 67 change lines in one LLM call.

## Strengths

- Constraints in the plan are met: retry limit 2 (`llm.py:126`), 5-patch history window, 0.8 coverage ratio, LLM built only when `extract`/`analyze` will run (`cli.py:116`), `error: <msg>` + exit 1, usage errors exit 2.
- Atomic write is real: temp file in the same directory, validated by re-parsing, `os.replace`, cleanup on any `BaseException` (`io.py:15-27`). `test_failed_write_keeps_previous_file` tests the property, not a mock.
- `read_model(..., produced_by)` gives the exact missing-file message the plan asks for. The CLI wraps `ValidationError` too.
- Chunker is sound on the real page: it splits at `##/###`, so each champion and item stays whole with its heading. Oversize sections repeat the `##` heading. Every chunk is below `max_chars`.
- `resolve_entity` handles `Kai'Sa`, `Dr. Mundo`, `Nunu (& Willump)`, `Nunu and Willump`, `Vel'Koz`. Icon URL uses the Data Dragon id (Wukong = MonkeyKing).
- Code-owned fields in analyze are right: `previous`, `icon_url`, `entity_type`, `compared_to`, `generated_at`, `llm`, `changes`. Verdicts for unchanged entities and duplicates are dropped with a warning. Entity order follows the changes.
- Warning flow is thought through: analyze copies only fetch/extract/baseline warnings, so a re-run does not duplicate its own (tested twice-run).
- Publish: numeric patch sort, index rebuilt from disk each time, idempotent on re-run, broken report file named in the error.
- Baseline stats CSV parser covers BOM, `%`, blank tier, case, whitespace and names the line and column of a bad value.
- Fetch URL fallback order and the `--notes-file` suggestion are tested. The fixture is a real page.
- 112 tests, `-W error`, no network. No Claude co-author trailers in the range.

## Issues

### Critical

None.

### Important

**I1. Extraction is mode-blind: 60% of the real change rows are Arena and Classic changes filed under the same champion names.**
`prompts.py:4-30`, `extract.py:41-60`, `lol/adapter.py:120-128` (`notes_to_markdown`).
On 26.21, 85 of 142 change lines sit under `## Arena` (72) and `## Classic` (13). The prompt has no mode context, and `entity_type` has no "mode" slot. Arena champion tweaks (for example Bel'Veth, Briar, Elise) become ordinary `champion` changes, resolve to the Summoner's Rift champion and enter `changes.json`, baseline history, the analyze prompt and the verdicts. Example: Irelia and Kassadin "Classic" nerfs and reverts become a Summoner's Rift "fall" or "rise" against SR win rates. Arena augments and items (for example "Nesting Doll") are not in Data Dragon: they are dropped one by one as `unknown entity` warnings, or kept as fake `system` entities with LLM "verdicts". The result is a plausible but wrong report, and the warning list gets dozens of noise lines.
Why it matters: the user wants the meta shift against all-rank SR stats. This is the first thing the real run in Task 15 will show.
Fix (pick one, decide before the web batch because option B changes the data shape): (A) in the LoL adapter, drop `##` sections that are other modes (ARAM*, Arena, Classic, URF, and so on) in `notes_to_markdown`, or skip them in `split_sections` through an adapter hook such as `skip_sections`, and count only kept lines for the coverage check; (B) keep them, add `mode: str` to `Change` filled by code from the nearest `##` heading, and let analyze/baseline use only the "Summoner's Rift" rows. Also compute coverage over the kept sections only.

**I2. `source_quote` check rejects any quote that drops markdown, and 140 of 142 real lines carry bold markers.**
`extract.py:54`, `text.py:10` (`normalize_ws`), `prompts.py:19`.
The check is a plain substring test after whitespace normalisation. Verified: `* **Mana Growth**: 40/Level ⇒ **50/Level**` passes, but `Mana Growth: 40/Level ⇒ 50/Level` fails, and so does the half-stripped `Mana Growth: 40/Level ⇒ **50/Level**`. LLMs, 14B local models especially, often print the readable form of a line. Each failure drops a correct change with a `quote not found` warning. A model that strips markup everywhere yields an almost empty `changes.json` plus a low-coverage warning, and the run still "succeeds" and publishes.
Fix: compare on a canonical form of both sides: remove `*`, `_`, backslashes, leading `* `/`> `/`#` markers and zero-width characters, map curly to straight quotes, and `=>`/`->` to `⇒`/`→`, then `normalize_ws`. Keep the strict check as the first try. Better: when the canonical quote matches, replace `source_quote` with the real raw line (find the line whose canonical form contains the quote) so the web "quote" box shows the notes text. Add a test that runs the real fixture `raw.md` with a stripped quote. The current tests use a toy `RAW` with no markdown and so cannot see this.

**I3. `complete_with_retry` throws away a usable result when a rule-retry returns bad JSON.**
`llm.py:126-160`.
Trace for analyze with a missing verdict: attempt 1 is valid but has a problem, so `retries=1`. Attempt 2 is invalid JSON, so `retries=2`. Attempt 3 is invalid JSON, so it raises `MetashiftError("... invalid JSON after 2 retries")`. The valid attempt-1 draft (maybe 95% right) is lost, and the stage fails. The spec says a rule failure ends in a report with a warning; only a schema failure stops the stage. A local 14B model produces malformed output often enough that this will happen on a 100-entity analyze.
Fix: keep `best = (result, problems)` from the last valid parse. On a schema failure after retries run out, if `best` exists return it (with its problems) instead of raising. Also name the rules in the schema-retry prompt when `problems` exist. Add a test: `[MISSING_KAISA, "nope", "nope"]` returns a result with problems, not an error.

**I4. ClaudeClient: `max_tokens=8192` is borderline for the real workload, and truncation is not detected.**
`llm.py:95-115`.
The densest real extract chunk has 67 changes. Each `Change` JSON repeats the line in `source_quote` and again in `old`/`new`, about 90-120 tokens, so roughly 6-8k tokens. Analyze emits one verdict with a sentence of reason per changed entity. With the Arena/Classic entities (I1) that is about 90-100 entities, roughly 8-10k tokens. When a tool-use response stops at `max_tokens`, the `input` is partial or empty; this surfaces as a pydantic `ValidationError`, is retried with the same prompt, truncates again and ends as `claude returned invalid JSON after 2 retries: <pydantic dump>`. The user sees a misleading message and pays for three calls.
Fix: raise `max_tokens` (16000 is still safe for a non-streaming call), check `message.stop_reason == "max_tokens"` and raise `MetashiftError("Claude output was cut off at N tokens; ...")` (not retried). Cap changes per chunk too (see M4) or let `split_sections` take a smaller `max_chars` when a chunk has more than about 30 arrow lines. (Not verified against the claude-api skill, as the ledger noted. The forced `tool_choice` shape, `input_schema` from `model_json_schema()` with `$defs` and the content-block loop are the documented pattern.)

**I5. `change_refs` are checked for range only. The verdict can point at another entity's changes, or at none.**
`checks.py:16-18`, `analyze.py:72`.
Spec: the card expands its source changes. Small models regularly cite wrong indexes (off by one after a long list, or an index belonging to the next entity). Range-valid but wrong refs pass silently, and the web card then shows another champion's change under it. An empty `change_refs` also passes. `consistency_warnings` judges by entity name, so it cannot see this either.
Fix: make the refs code-owned or code-validated: `valid = [i for i, c in enumerate(changes) if c.entity == verdict.entity]`. Keep only refs in `valid`, and if none are left, use all `valid` (plus a warning when the LLM's refs were changed). Add a test with a cross-entity ref and with `[]`.

**I6. A long Ollama run is fragile: fatal 600 s timeout, thinking on, greedy decoding, no progress, no reuse of finished chunks.**
`llm.py:16,53-76`, `extract.py:41-47`, `cli.py:127`.
- One non-streaming call must finish within 600 s. qwen3:14b is a thinking model; with thinking on, `temperature: 0` is discouraged by Qwen (repetition loops) and the thinking tokens count against the 600 s. A 67-line chunk or a 100-verdict analyze at 15-25 tokens/s can pass 10 minutes. `ReadTimeout` becomes a `MetashiftError` and is not retried.
- `run_extract` keeps results only in memory. A failure on chunk 9 of 10 loses 8 chunks of local compute; there is no cache and no per-chunk progress line (the CLI prints only when a stage ends), so a 30-60 minute run looks hung.
- No `"think": false` in the payload, so output shape and speed depend on the Ollama version (structured output with thinking changed between releases; not verified here).
Fix: send `"think": false`; make the timeout configurable (`METASHIFT_OLLAMA_TIMEOUT`, default higher) and retry once on timeout; write each chunk's draft to `data/<game>/<patch>/.extract-cache/` (or print progress to stderr per chunk at minimum). A progress callback in `StageContext` is enough.

### Minor

**M1. Small matching gaps.**
- `extract.py:46`: `entity_type == "system"` is compared case-sensitively. A model that writes `"System"` or `"Champion"` falls into the resolver: `System` goes to a drop. Lower-case and strip `entity_type` first (or constrain it to an enum in the schema).
- `text.py:20-29`: `resolve_entity("Nunu", known)` returns None (checked); the notes use "Nunu" in prose. `baseline.py:97` matches CSV rows by exact `name_key` only, so a stats sheet that says "Nunu" or "Renata" does not match "Nunu & Willump" / "Renata Glasc". Add a unique-prefix fallback on name keys in both places.
- `stats_csv.py:38`: semicolon-delimited exports (common from spreadsheets in some locales) give "misses columns" with no hint; sniff the delimiter.

**M2. Zero extracted changes still runs analyze and publishes.**
`extract.py:60-66`, `analyze.py:30`. If every quote is dropped (I2), `changes.json` holds `[]`, analyze sends an empty change list to the model and publishes a report with an invented headline and no entities. Stop in extract with a `MetashiftError` that points at the warnings, or skip the LLM in analyze and write an empty report with a warning.

**M3. Schema export for the web batch.** `cli.py:144`. `model_json_schema()` defaults to validation mode, so `icon_url` and `history` (fields with defaults) are optional in the generated TypeScript although they are always written. Use `mode="serialization"`. Pydantic also omits `additionalProperties: false`, so json-schema-to-typescript adds `[k: string]: unknown` to every interface unless the web batch passes `additionalProperties: false`/`--no-additionalProperties`. Tell the T12 builder.

**M4. Chunk boundaries can split a bold entity label from its body.** `text.py:62-90`. In long `##` sections the splitter cuts at any blank line. In the real data chunk 4 ends with `**Totentanz**` and its bullet opens chunk 5; chunk 6 ends with `**Irelia**` and the `#### Base Stats` block is in chunk 7. A body chunk then has stat lines but no entity (the model guesses or drops). Only the `##` heading is repeated. Prefer cutting before a bold-label paragraph or a `####` heading, and repeat the last bold label above a cut. This matters mostly if I1 option B is chosen.

**M5. Publish order leaves a half-published state on failure.** `publish.py:46-47`. The report is copied before `_build_index()` can fail on a broken sibling report. The new report file exists but is not in the index (the test `test_publish_names_a_broken_report_file` shows the error but not the state). Build the index entries first (read the others, add the new one in memory) and write both files at the end, or write the index first.

**M6. Fetch and Data Dragon error text.**
- `adapter.py:112-114,52-53`: only 404 gets the `--notes-file` hint. A 403/429/5xx or a network failure says "returned HTTP 403" with no hint. Spec: show URL and suggest `--notes-file` for page failures.
- `adapter.py:83-91`: on release day the notes can be live before Data Dragon has the version; the user gets "no Data Dragon data for patch 26.21" at the start of extract with no advice. Say so in the message (and consider falling back to the newest earlier version, with a warning).
- `llm.py:49,62-76`: `OLLAMA_HOST` is often set without a scheme (`0.0.0.0:11434`, the form Ollama's own docs use). Then httpx raises `UnsupportedProtocol`, which is not caught and shows as a traceback. Add `http://` when missing and catch `httpx.HTTPError` broadly (also `ReadError`, `RemoteProtocolError`). A 404 "model not found" could add "run: ollama pull <model>".

**M7. Test gaps that matter for a real run.**
- No test runs `split_sections` + `run_extract` on the real fixture `raw.md`. All extract tests use a four-line toy `RAW` without markdown, which is why I2 and I1 are invisible.
- `test_llm.py`: no test for Claude `APIError`, "no tool_use block", Ollama HTTP error/timeout, or the "valid result then malformed retry" path (I3). The Claude client is tested only against a `SimpleNamespace`; acceptable offline, but the error paths are the part users will meet.
- `test_publish_names_a_broken_report_file` does not assert the on-disk state after failure (M5).

**M8. Stale downstream files are not detected.** After `--from-stage extract --to-stage extract`, `baseline.json` and `report.json` still describe the old `changes.json`; `analyze` then reports `previous=None` for new entities without a warning. A cheap guard: compare entity sets of `changes.json` and `baseline.json` in analyze and warn or stop.

**M9. Warning noise.** `baseline.py:97-99` writes one `no stats for X` per entity, including items, runes and `system` entities, which never have champion win rates. Skip the warning for non-champion types, or emit one summary line ("no stats for 31 entities").

**M10. Quote check does not tie the quote to the values.** `extract.py:54`. A short quote such as `Cooldown` passes, and a quote from the next champion's line passes. Cheap extra check once I2 is fixed: the canonical quote must contain the `old` and `new` strings when they are not null.

## Declined to judge

- Choice of CSV as the only stats source (no lolalytics scraper): ledger ruling, spec §3.1 allows it. Only the CSV-matching details are reviewed (M1, M9).
- CSV file location (`data/lol/<current patch>/stats.csv` holding the previous patch's numbers): follows the plan text and STATS.md; the error message prints the path.
- Analyze copying warnings only from fetch/extract/baseline: ledger ruling; no concrete bug found, and the re-run test passes.
- `--to-stage` flag and the `patch_date`/`icon_url` adapter additions: noted in the plan as spec additions.
- Per-task review replaced by this batch review and TDD order (tests-after): ledger rulings, process only.
- Counting both `⇒` and `→` in coverage: ledger ruling; no `→` on the real page.
- Prompt wording quality and verdict accuracy of qwen3:14b (for example cooldown-up = nerf hints, "stable" near 50% win rate): needs a real model run (Task 15); cannot be judged from code.
- Whether Ollama's structured-output handling of `$defs`/`$ref` and thinking works on the user's installed version: needs a live run; only the missing `think` flag is raised (I6).
- Eval command `metashift eval extract` and golden set: Task 11, outside this range.
- JSON-schema-to-TS generation and all web behavior (null `old`/`new` rendering): Tasks 12-14, outside this range.
- Concurrency of two `metashift` processes on the same patch (run log read-modify-write): single-user tool, out of spec.
- Leftover `*.tmp` files after a hard kill (SIGKILL): outside the "failed stage never replaces a good file" guarantee, which holds.
- Marketing of Riot content / legal footer: web batch.

## Assessment

**Ready for the web batch? With fixes.**
The data shapes (`ReportFile`, `IndexFile`) are stable and the plumbing, error handling and tests are solid, so the web batch can start. Fix I1 (mode scope, which may add a `mode` field to `Change`) and I2/I3/I5 first, because they decide whether the first real run yields a correct report. I4 and I6 must be done before a real Claude or long Ollama run in Task 15.
