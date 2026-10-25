# Final review: Metashift v1 (feat/v1, 2050af9..1098e7b)

Reviewer method: I read the combined diff file in passes: pipeline source, pipeline tests, web source, web tests and CSS. I also read the spec, the plan (Global Constraints, Review Focus, Tasks 10-15), the ledger, pipeline-review.md and EVAL.md. I read the current source files at HEAD 1098e7b directly, plus the real reports in `web/public/data/lol/` and `data/lol/`. I ran two offline probes with the project `.venv` (no repo writes) to confirm the Ollama error types. I did not re-run the test suites.

## Strengths

- The I1-I6 fixes are real and tested. Most tests run the real 26.21 page fixture or prove the failure path (see the table below).
- The data contract holds end to end. `models.py` → `metashift schema` → `generated.ts` gives `compared_to: string | null`, `previous: PreviousStats | null`, `old/new: string | null`, `patch_date: string | null` and `icon_url?: string | null`. The web handles each one. `formatChange` gives a dash for null. `formatPrevious` handles null and undefined. The icon is hidden when it is falsy. The header shows "no previous patch" when `compared_to` is null. The Board drops out-of-range `change_refs` (`Board.tsx:72`). `additionalProperties: false` removes the `[k: string]: unknown` noise.
- `change_refs` are now owned by code (`analyze.py:72`). `VerdictDraft` has no refs field. A test proves that refs from the model are ignored. This removes a full class of wrong-card bugs.
- The secret handling is clean. The key exists only in `OllamaClient._headers`. No error message, log line, `run.log.json` or report contains it. A test asserts this for 401 (`test_ollama_rejected_key_names_the_variable_not_the_key`). Typer 0.27.3 has `pretty_exceptions_show_locals=False` by default, so an uncaught traceback does not print header values. No published file contains "Bearer", "token" or a key (grep).
- The real-run experience is good. You see per-chunk progress on stderr and a `✓ stage  Ns` line per stage. The extract cache makes a re-run after a failure cheap. Every report carries the stage warnings. A full patch takes under 30 s on gemma4 cloud.
- The eval is honest. The golden labels come from `raw.md`, not from model output. The multiset scorer is simple and correct. The command always exits 0. EVAL.md lists every mismatch with a cause.
- The web meets its constraints. It uses HashRouter and `base: "./"`. It never calls an LLM or a stats site. The e2e test checks for no horizontal scroll at 375 px. Light and dark tokens exist for both the media query and `data-theme`. The theme choice is saved in `localStorage` inside try/catch.
- Rise/Stable/Fall never depend on color alone. ▲/●/▼ marks are `aria-hidden` and sit beside text labels. Change rows carry a visually hidden "(buff)". Focus is visible. Tabs support arrow keys and `aria-selected`.
- No commit in the range has a `Co-Authored-By` trailer.

## I1-I6 verification

| Item | Status | Evidence |
|---|---|---|
| I1 mode-blind extraction | **Fixed** | `adapter.py:136-155` `select_sections` keeps only the allowlisted H2 sections and the `Summoner's Rift*` prefix (curly apostrophe handled). `fetch.py:21-23` writes one "skipped sections" warning. `test_select_sections_keeps_summoners_rift_sections_of_the_real_notes` and `test_fetch_real_notes_skip_other_modes` use the real 26.21 page. The real 26.21 run.log lists Arena, Classic and ARAM: Mayhem as skipped, and the report has 61 SR rows. Coverage now counts only the kept text, because `raw.md` holds only kept sections. |
| I2 quote check vs markdown | **Fixed** | `extract.py:86` compares `strip_markdown(quote)` with `strip_markdown(raw)`. `text.py:14-23` removes bullets, escapes and `*`/`_`, then normalises whitespace. `test_extract_accepts_readable_quote_for_a_bold_markdown_line` covers the fully stripped and the half-stripped forms. The real runs have 0 "quote not found" warnings. The optional parts (map `=>`/`->` and curly quotes, replace the quote with the raw line) were not done. That is acceptable. |
| I3 retry loses valid result | **Fixed** | `llm.py:185-196` keeps `best`. When the retries run out after a schema failure, it returns `best` and adds a note. The schema-retry prompt now lists the remaining rule problems (`llm.py:198-202`). Tests: `test_malformed_retry_after_a_valid_result_keeps_the_valid_result`, `..._can_still_recover_...`, `test_no_valid_result_ever_still_raises`. |
| I4 Claude truncation | **Fixed** | `CLAUDE_MAX_TOKENS = 16000` (`llm.py:18`). `stop_reason == "max_tokens"` raises `MetashiftError` at once (`llm.py:153-156`). That error is not caught by `complete_with_retry`, so there is no retry. Test: `test_claude_truncated_output_fails_at_once_without_retry`. |
| I5 change_refs | **Fixed** | Refs are owned by code (`analyze.py:72`). `VerdictDraft` has no `change_refs` (`models.py:119-123`). The prompt says "do not give change indexes". Tests: `test_analyze_change_refs_are_code_owned_all_rows_of_the_entity`, `test_analyze_ignores_change_refs_the_model_still_sends`. The spec §4.3 amendment matches. |
| I6 long Ollama run | **Fixed (as ruled)** | `"think": False` (`llm.py:91`). `METASHIFT_OLLAMA_TIMEOUT` is validated (`llm.py:52-64`). The timeout gives a clear message with the env hint. There is a per-chunk cache in `data/<game>/<patch>/extract-cache/` (git-ignored) and progress on stderr. Tests cover cache reuse, per-model keys, broken cache files and progress. A timeout is not retried, as the ledger ruling says. |

## Issues

### Critical

None.

### Important

**I-1. Ollama network errors other than connect and timeout escape as tracebacks. This breaks the binding constraint "every user-facing failure raises MetashiftError".**
`pipeline/metashift/core/llm.py:95-117`, `cli.py:130-133`.
`complete_json` catches only `ConnectError`, `HTTPStatusError` and `TimeoutException`. I confirmed these cases offline:
- A `ReadError` (connection reset), a `RemoteProtocolError` or a `WriteError` in the middle of a call is not caught.
- `OLLAMA_HOST=0.0.0.0:11434` has no scheme. Ollama's own docs use this form. It raises `httpx.UnsupportedProtocol`, which is not caught.

The CLI catches only `MetashiftError` and `ValidationError`, so the user gets a Python traceback. Commit 474cbb5 made remote Ollama Cloud a documented path, so a dropped connection during a long run is now a normal event. This was M6 in the pipeline review. The switch to cloud raises its weight. No secret leaks, because locals are off.
Fix: (1) After the specific handlers, add `except httpx.HTTPError as err: raise MetashiftError(f"Ollama request to {self.host} failed: {err}") from err`. The message must not include headers. (2) In `__init__`, add `http://` when the host has no scheme. (3) Add `0.0.0.0` to `_is_local`. Add one MockTransport test that raises `httpx.ReadError`.

**I-2. A run that extracts zero changes still calls the LLM and publishes an empty report with an invented headline (pipeline-review M2, still open). The I1 allowlist makes this reachable.**
`extract.py:92-95`, `analyze.py:29-35`, `publish.py:46-47`.
`select_sections` keeps only exact H2 titles. Suppose Riot renames a heading, for example "Champions" to "Champion Changes", or adds an SR section such as "Summoner Spells". That section is then dropped, and only the "skipped sections" warning names it. If every balance section is renamed, `raw.md` has 0 arrow lines. The low-coverage check is `0 < 0.8 * 0`, which is false, so no warning appears. Analyze then sends an empty change list. The model writes a headline and themes from nothing. Publish adds that report to `index.json` and to the site. The user sees a normal "✓" run.
Fix (small): in `extract_changes`/`run_extract`, when `count_change_lines(raw) == 0` or `changes == []`, raise `MetashiftError("no changes extracted from data/<game>/<patch>/raw.md. Check the 'skipped sections' warning: a section title may have changed")`. Alternatively, analyze can skip the LLM and stop. Add a test. I do not challenge the ruling to use an allowlist. This guard only removes its silent failure mode.

### Minor

**m1. Published and data files are written with mode 0600.** `core/io.py:20-29`. `NamedTemporaryFile` creates the file 0600, and `os.replace` keeps that mode. `web/public/data/index.json` and `lol/*.json` are `-rw-------` on disk. `vite build` copies the mode into `dist/`. GitHub Pages, Vercel and git do not care, but a copy-based deploy (for example rsync to a server where nginx runs as another user) returns 403 for the data files. Fix: `os.chmod(tmp_path, 0o666 & ~umask)` before `os.replace`.

**m2. The extract cache key ignores the prompt.** `extract.py:25-27` hashes `llm.name + chunk`. A change to `extract_prompt`, the glossary or `entity_types` then reuses stale drafts without notice. Fix: hash `llm.name + prompt`. Also, the README says the cache skips finished chunks, but it does not say how to force a fresh model call (delete `extract-cache/`). Add one line.

**m3. The 401/403 hint is wrong for a local Ollama that uses a `-cloud` model.** `llm.py:105-109` always says "Check OLLAMA_API_KEY". The README's default path is a local Ollama signed in to Ollama Cloud, which needs no key. For that path the fix is `ollama signin`. When `_is_local()` is true, say both.

**m4. Analyze can lose a finished LLM result to a Data Dragon failure.** `analyze.py:73` calls `adapter.icon_url()`, which loads the network catalog, after the LLM call. If Data Dragon is down, the stage fails and the model output is lost. Fix: build the icon map before `complete_with_retry`.

**m5. The fence strip handles only one form.** `llm.py:43` matches only a body that is all fence and has newlines. A one-line form (```` ```json{...}``` ````) or prose before the fence fails validation and costs retries. Optional: search for the first fenced block, or take the text between the first `{` and the last `}`.

**m6. No offline test checks the golden set against the real pipeline helpers.** A cheap test could do these checks on `tests/golden/lol/*`: `ChangesFile` validates, each golden `source_quote` passes the `strip_markdown` check against its `raw.md`, and `split_sections(raw)` keeps every `####` entity heading in the same chunk as its first change line. This would tie I2 and M4 to the real data. Today they are tested only on toy strings.

**m7. Web tests use only hand-made fixtures.** Vitest mocks `fetch`, and Playwright serves `e2e/fixtures`. Nothing loads the real `web/public/data/*.json`. Contract drift between real pipeline output and the web is caught only by the generated types. Add one Vitest that imports the real published files and renders `Board`. Or add a Playwright test with no route override.

**m8. Small accessibility gaps.** `Board.tsx:60`: the column `<section>` has no `role="tabpanel"` or `aria-labelledby` to its tab, so at phone width the tab/panel link is not exposed. Home and End keys are not handled on the tabs. `PatchList.tsx:32-33`: "▲"/"▼" are not `aria-hidden`, so screen readers say "black up-pointing triangle". (The card and the history page do this right.)

**m9. README gaps for a real user.**
- `npm run e2e` needs `npx playwright install chromium` first.
- A new patch stops at baseline until `data/lol/<patch>/stats.csv` exists. Say that a header-only file is enough for a run with no stats. Or offer to write a template.
- The code default model is `qwen3:14b`. The README recommends `gemma4:31b-cloud`. A user who skips the env var gets "Ollama returned HTTP 404 ... model not found".

**m10. Stale downstream files (pipeline-review M8, still open).** A run `--from-stage extract --to-stage extract` followed by `--from-stage analyze` uses an old `baseline.json`. New entities then get no stats and no history, with no warning. A one-line guard in analyze can warn when the entity sets of `changes.json` and `baseline.json` differ.

## Deferred-minor triage

| Item | Decision | Why |
|---|---|---|
| Task 7: TDD order not tests-first | leave | Process only. The tests exist and pass. |
| Task 11: combined item names ("World Atlas and Runic Compass") dropped | leave | 1 row of 133. It is written in EVAL.md and the warning names it. |
| Task 15: EntityHistory shows "Lol" | leave | Cosmetic. `text-transform: capitalize` on `.history-sub`. A display-name map is a one-line fix if wanted. |
| Task 15: "no stats for Teleport Cooldown" for system entities | leave | One noise line per patch. It is the same as M9. |
| M1 matching gaps (case of `entity_type`, Nunu prefix, `;` CSV) | leave | The eval meets targets. None of these appeared in the real runs. |
| M2 zero changes still publishes | **must-fix** | See I-2. The I1 allowlist makes it reachable, and it publishes invented content. |
| M3 schema export mode / additionalProperties | leave | `additionalProperties: false` is passed. `icon_url?` is optional in TS, and the web handles it. |
| M4 chunk splits a bold label from its body | leave | Eval P 0.95 / R 0.95 on the real chunks. See m6 for a cheap guard. |
| M5 half-published state on index failure | leave | The error names the broken file. A re-run after the fix is clean. |
| M6 fetch / Data Dragon / OLLAMA_HOST error text | **must-fix (Ollama part only)** | See I-1. The Data Dragon release-day hint and the non-404 `--notes-file` hint can stay minor. |
| M7 test gaps | leave | Partly fixed (real-page fetch test, retry tests). The rest is in m6/m7. |
| M8 stale downstream files | leave | See m10. A normal full run does not hit it. |
| M9 warning noise for non-champions | leave | Cosmetic. |
| M10 quote not tied to values | leave | A precision of 0.95 shows it does not matter much in practice. |

## Declined to judge

- Allowlist vs denylist for LoL sections (I1 ruling): it is a ruling. I flag only the silent empty-report effect (I-2).
- CSV as the only stats path and "lolalytics" never used: ledger ruling, and spec §3.1 allows it.
- `stats_source: "none"` and `compared_to` set to the previous patch even when every stat is blank: spec-consistent. The header text is still true (it is the previous patch).
- A timeout is not retried: ledger I6 ruling.
- Analyze copies warnings only from earlier stages: ledger ruling, and a test covers it.
- EntityCard `game` prop defaults to "lol": ledger ruling. Board passes the real game.
- The golden labels and the "debatable" mismatches (Taric cast behavior, Hubris adjust vs nerf): the user approved them. This is a judgment on content, not code.
- Verdict quality (for example the Vayne "base health" slip): model output, recorded in EVAL.md.
- `OLLAMA_API_KEY` is sent to any configured host, including plain-http hosts: the user sets both variables. This is a reasonable expectation for a single-user tool, and it is outside the spec.
- Deploy to a real host: spec §8 says "deploys as a static site". The ledger says build and preview were checked, not deployed. That is a process gap, not a code defect.
- Patch ids or entity names with `/` or `%` in hash routes: Data Dragon has none today.
- Two concurrent `metashift` runs on one patch: single-user tool.
- Model pricing and plan limits (402 on minimax): outside the code.
- Visual design taste of the site: outside the requirements.

## Assessment

**Ready to merge? With fixes.**
The architecture, the data contract and the I1-I6 fixes are sound, and the real three-patch run proves the full flow. Fix I-1 (catch every `httpx.HTTPError` and add a scheme to `OLLAMA_HOST`) and I-2 (stop on zero extracted changes) before merge. Both are small, local changes with one test each. The minors can wait.
