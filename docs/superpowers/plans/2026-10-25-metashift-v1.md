# Metashift v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local pipeline that turns a League of Legends patch into a meta shift report (`report.json`), and a static web app that shows those reports.

**Architecture:** A Python CLI runs five stages (fetch → extract → baseline → analyze → publish). Each stage writes one validated JSON/Markdown file to `data/<game>/<patch>/`. All game-specific code sits behind a `GameAdapter`. All LLM calls go through one `LLM` interface (Ollama default, Claude optional). A React + Vite static site reads only the published JSON in `web/public/data/`.

**Tech Stack:** Python 3.12, uv, Pydantic 2, httpx, BeautifulSoup4, markdownify, Typer, anthropic SDK, pytest. Node 20, Vite, React 18, TypeScript, react-router-dom (HashRouter), Vitest + Testing Library, Playwright, json-schema-to-typescript.

**Spec:** `docs/superpowers/specs/2026-10-25-metashift-design.md`

## Global Constraints

- Python 3.12, managed with uv. Package `metashift` lives in `pipeline/metashift/`, tests in `pipeline/tests/`.
- Zero running cost. Nothing requires a paid service. Claude is optional.
- Default LLM: Ollama. Env vars: `METASHIFT_OLLAMA_MODEL` (default `qwen3:14b`), `OLLAMA_HOST` (default `http://localhost:11434`), `METASHIFT_CLAUDE_MODEL` (default `claude-sonnet-5-5`), `ANTHROPIC_API_KEY`.
- Repo root is found by `metashift.core.paths.repo_root()`: env `METASHIFT_ROOT` if set, else three levels up from the package (`pipeline/metashift/core/` → repo). Tests set `METASHIFT_ROOT` to `tmp_path`.
- LLM retry on schema failure or rule failure: at most **2** retries.
- History window: last **5** patches. Coverage warning below **80%**. Eval targets: recall ≥ **90%**, precision ≥ **95%**.
- All unit tests run with no network and no model (`FakeLLM`, `httpx.MockTransport`, saved fixtures).
- The web app never calls an LLM or a stats site. Hash routing. Works at 375 px width. Light and dark themes.
- Every user-facing failure raises `MetashiftError(message)`. The CLI prints `error: <message>` to stderr and exits 1.
- Commits carry no `Co-Authored-By` trailer (user rule).

## Review Focus

1. **Entity names with punctuation or Data Dragon id mismatch** (`Kai'Sa`/`KaiSa`, `Dr. Mundo`, `Nunu & Willump`, Wukong = id `MonkeyKing`). Expect: the display name resolves, and the icon URL uses the Data Dragon id. Tests in Task 4 and Task 6.
2. **Messy `stats.csv`** (UTF-8 BOM, `49.1%` values, names in other case, empty `tier`). Expect: it parses, and names match changed entities. Test in Task 7.
3. **`--from-stage` when an earlier file is missing.** Expect: `error: missing data/lol/26.21/changes.json — run stage 'extract' first`, not a traceback. Tests in Task 2 and Task 10.
4. **New or removed mechanics (`old` or `new` is null).** Expect: the card shows `— → 45` or `40 → —`, never `null`. Test in Task 12.
5. **Arrow variants in notes (`⇒` and `→`).** Expect: the coverage count includes both, so a correct extraction gets no false warning. Test in Task 6.

---

### Task 1: Pipeline scaffold and data models

**Files:**
- Create: `pipeline/pyproject.toml`, `pipeline/metashift/__init__.py`, `pipeline/metashift/core/__init__.py`, `pipeline/metashift/core/models.py`, `pipeline/metashift/core/errors.py`, `pipeline/metashift/core/paths.py`, `.gitignore`
- Test: `pipeline/tests/test_models.py`

**Interfaces:**
- Produces (in `core/models.py`, all `pydantic.BaseModel`):
  - `Direction = Literal["buff", "nerf", "adjust"]`
  - `Change(entity: str, entity_type: str, target: str, stat: str, old: str | None, new: str | None, direction: Direction, source_quote: str)` — `source_quote` min length 1
  - `ChangesFile(game: str, patch: str, changes: list[Change])`
  - `EntityStats(entity: str, win_rate: float | None, pick_rate: float | None, ban_rate: float | None, tier: str | None)` — rates `ge=0, le=100`
  - `HistoryEntry(patch: str, direction: Direction, summary: str)`
  - `BaselineEntity(win_rate, pick_rate, ban_rate: float | None, tier: str | None, history: list[HistoryEntry] = [])`
  - `BaselineFile(stats_patch: str | None, stats_source: str, entities: dict[str, BaselineEntity])`
  - `PreviousStats(win_rate, pick_rate, ban_rate: float | None, tier: str | None)`
  - `Verdict = Literal["rise", "fall", "stable"]`, `Confidence = Literal["low", "medium", "high"]`
  - `EntityVerdict(entity, entity_type: str, verdict: Verdict, confidence: Confidence, previous: PreviousStats | None, reason: str, change_refs: list[int], icon_url: str | None = None)` — refs `ge=0`
  - `ReportFile(game, patch: str, compared_to: str | None, generated_at: datetime, llm: str, headline: str, themes: list[str], entities: list[EntityVerdict], changes: list[Change], warnings: list[str])`
  - `IndexEntry(patch: str, patch_date: date | None, headline: str, buffs: int, nerfs: int, llm: str)`, `IndexFile(games: dict[str, list[IndexEntry]])`
  - `StageLog(stage: str, llm: str | None, duration_s: float, retries: int, warnings: list[str])`, `RunLog(game, patch: str, patch_date: date | None = None, stages: list[StageLog] = [])`
  - LLM drafts: `ExtractDraft(changes: list[Change])`, `VerdictDraft(entity: str, verdict: Verdict, confidence: Confidence, reason: str, change_refs: list[int])`, `AnalysisDraft(headline: str, themes: list[str], entities: list[VerdictDraft])`
- Produces: `core/errors.py` → `class MetashiftError(Exception)`; `core/paths.py` → `repo_root() -> Path`, `patch_dir(game: str, patch: str) -> Path` (= `repo_root()/"data"/game/patch`), `web_data_dir() -> Path` (= `repo_root()/"web/public/data"`)

`icon_url` is an addition to spec §4.3: the web app needs a resolved icon, and Data Dragon ids differ from display names (Review Focus 1).

- [ ] **Step 1: Create the uv project**

Run: `cd pipeline && uv init --package --name metashift --python 3.12 . && uv add pydantic httpx beautifulsoup4 markdownify typer anthropic && uv add --dev pytest`
`uv init` puts the package in `src/`. Move it to `pipeline/metashift/` and set the build backend's module root to the project root (for `uv_build`: `[tool.uv.build-backend] module-root = ""`). Check that `uv run python -c "import metashift"` works. Add `[project.scripts] metashift = "metashift.cli:app"` to `pyproject.toml`. `.gitignore`: `.venv/`, `__pycache__/`, `node_modules/`, `web/dist/`, `.pytest_cache/`.

- [ ] **Step 2: Write the failing tests**

```python
def test_change_allows_null_old_for_new_mechanic():
    c = Change(entity="Ahri", entity_type="champion", target="Passive", stat="new effect",
               old=None, new="Heals 5%", direction="buff", source_quote="NEW: Heals 5%")
    assert c.old is None

def test_change_rejects_unknown_direction():
    with pytest.raises(ValidationError):
        Change(..., direction="up", ...)

def test_entity_stats_rejects_win_rate_over_100():
    with pytest.raises(ValidationError):
        EntityStats(entity="Ahri", win_rate=149.1, pick_rate=None, ban_rate=None, tier=None)

def test_report_round_trips_through_json():
    r = ReportFile(...)  # one entity, one change, generated_at UTC
    assert ReportFile.model_validate_json(r.model_dump_json()) == r

def test_patch_dir_uses_metashift_root(monkeypatch, tmp_path):
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    assert patch_dir("lol", "26.21") == tmp_path / "data" / "lol" / "26.21"
```

- [ ] **Step 3: Run and verify failure** — `uv run pytest tests/test_models.py -v` → FAIL (import errors).
- [ ] **Step 4: Implement the models, `MetashiftError` and `paths`.**
- [ ] **Step 5: Run and verify pass** — `uv run pytest tests/test_models.py -v` → 5 passed.
- [ ] **Step 6: Commit** — `git add pipeline .gitignore && git commit -m "feat: pipeline scaffold and data models"`

---

### Task 2: Atomic file IO and run log

**Files:**
- Create: `pipeline/metashift/core/io.py`
- Test: `pipeline/tests/test_io.py`

**Interfaces:**
- Consumes: models, `MetashiftError` (Task 1)
- Produces:
  - `write_model(path: Path, model: BaseModel) -> None` — creates parent dirs, writes indented JSON to a temp file in the same dir, re-validates it with `type(model).model_validate_json`, then `os.replace`.
  - `write_text(path: Path, text: str) -> None` — same atomic pattern, no validation.
  - `read_model(path: Path, cls: type[T], produced_by: str) -> T` — missing file raises `MetashiftError(f"missing {rel} — run stage '{produced_by}' first")`, where `rel` is the path relative to `repo_root()`.
  - `record_stage(game: str, patch: str, log: StageLog, patch_date: date | None = None) -> None` — reads or creates `patch_dir/run.log.json`, replaces any entry with the same `stage`, sets `patch_date` when given, writes atomically.
  - `read_run_log(game: str, patch: str) -> RunLog` — an empty `RunLog` if the file does not exist.
  - `stage_warnings(game: str, patch: str) -> list[str]` — all warnings from `run.log.json`, in stage order; `[]` if no log.

- [ ] **Step 1: Write the failing tests**

```python
def test_failed_write_keeps_previous_file(tmp_path):
    p = tmp_path / "changes.json"
    good = ChangesFile(game="lol", patch="26.21", changes=[])
    write_model(p, good)
    bad = ChangesFile.model_construct(game="lol", patch="26.21", changes="oops")
    with pytest.raises(Exception):
        write_model(p, bad)
    assert ChangesFile.model_validate_json(p.read_text()) == good
    assert list(tmp_path.iterdir()) == [p]          # no temp file left

def test_read_missing_file_names_the_stage(monkeypatch, tmp_path):
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    with pytest.raises(MetashiftError, match=r"missing data/lol/26.21/changes.json — run stage 'extract' first"):
        read_model(patch_dir("lol", "26.21") / "changes.json", ChangesFile, "extract")

def test_record_stage_replaces_same_stage(monkeypatch, tmp_path):
    ...  # record "extract" twice with different warnings
    assert [s.stage for s in log.stages] == ["fetch", "extract"]
    assert stage_warnings("lol", "26.21") == ["w-fetch", "w-extract-2"]
```

- [ ] **Step 2: Run and verify failure** — `uv run pytest tests/test_io.py -v` → FAIL.
- [ ] **Step 3: Implement `core/io.py`.** Use `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)` and remove the temp file in a `finally` on failure.
- [ ] **Step 4: Run and verify pass** — 3 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: atomic file IO and run log"`

---

### Task 3: LLM interface, retry, Ollama and Claude clients

**Files:**
- Create: `pipeline/metashift/core/llm.py`
- Test: `pipeline/tests/test_llm.py`

**Interfaces:**
- Consumes: `MetashiftError`
- Produces:
  - `class LLM(Protocol): name: str; def complete_json(self, prompt: str, schema: type[T]) -> T` — raises `pydantic.ValidationError` (or `ValueError` for non-JSON) on bad output.
  - `FakeLLM(responses: list[str], name: str = "fake")` — returns `schema.model_validate_json(next(responses))`; keeps every prompt in `.prompts: list[str]`.
  - `OllamaClient(model: str | None = None, host: str | None = None, transport: httpx.BaseTransport | None = None)` — `name = f"ollama:{model}"`.
  - `ClaudeClient(model: str | None = None, client: anthropic.Anthropic | None = None)` — `name = f"claude:{model}"`.
  - `make_llm(kind: Literal["ollama", "claude"]) -> LLM`
  - `complete_with_retry(llm: LLM, prompt: str, schema: type[T], check: Callable[[T], list[str]] | None = None, max_retries: int = 2) -> tuple[T, int, list[str]]` — returns (result, retries used, problems left).

Retry rules: on a schema/JSON error, re-prompt with `prompt + "\n\nYour previous answer was invalid:\n" + str(err) + "\nReturn corrected JSON only."`. After `max_retries` schema failures, raise `MetashiftError(f"{llm.name} returned invalid JSON after {max_retries} retries: {err}")`. When `check` returns problems, re-prompt the same way with the problems listed. When retries run out, return the last result with its problems (the caller turns them into warnings).

Ollama call: `POST {host}/api/chat` with `{"model", "messages": [{"role": "user", "content": prompt}], "stream": false, "format": schema.model_json_schema(), "options": {"temperature": 0, "num_ctx": 32768}}`, timeout 600 s. Parse `response["message"]["content"]`. `httpx.ConnectError` → `MetashiftError(f"Ollama is not reachable at {host}. Start it with: ollama serve")`.

Claude call: read the `claude-api` skill first. Use forced tool use: one tool named `emit` with `input_schema = schema.model_json_schema()`, `tool_choice={"type": "tool", "name": "emit"}`, `max_tokens=8192`, then `schema.model_validate(tool_use.input)`. With no `ANTHROPIC_API_KEY`, the constructor raises `MetashiftError("ANTHROPIC_API_KEY is not set")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_retry_feeds_validation_error_back():
    llm = FakeLLM(['{"changes": "x"}', '{"changes": []}'])
    result, retries, problems = complete_with_retry(llm, "P", ExtractDraft)
    assert result.changes == [] and retries == 1 and problems == []
    assert "Your previous answer was invalid" in llm.prompts[1]

def test_retry_gives_up_after_two():
    llm = FakeLLM(['nope'] * 3)
    with pytest.raises(MetashiftError, match="after 2 retries"):
        complete_with_retry(llm, "P", ExtractDraft)
    assert len(llm.prompts) == 3

def test_check_problems_returned_when_retries_run_out():
    llm = FakeLLM(['{"changes": []}'] * 3)
    _, retries, problems = complete_with_retry(llm, "P", ExtractDraft, check=lambda r: ["missing Ahri"])
    assert retries == 2 and problems == ["missing Ahri"]

def test_ollama_unreachable_says_ollama_serve():
    def boom(request): raise httpx.ConnectError("refused")
    llm = OllamaClient(model="m", host="http://x", transport=httpx.MockTransport(boom))
    with pytest.raises(MetashiftError, match="ollama serve"):
        llm.complete_json("P", ExtractDraft)

def test_ollama_sends_schema_and_parses_content():
    ...  # MockTransport asserts body["format"] == ExtractDraft.model_json_schema(), returns {"message": {"content": '{"changes": []}'}}

def test_claude_without_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MetashiftError, match="ANTHROPIC_API_KEY is not set"):
        ClaudeClient()
```

- [ ] **Step 2: Run and verify failure** — `uv run pytest tests/test_llm.py -v` → FAIL.
- [ ] **Step 3: Implement `core/llm.py`.**
- [ ] **Step 4: Run and verify pass** — 6 passed.
- [ ] **Step 5: Commit** — `git commit -m "feat: LLM interface with retry, Ollama and Claude clients"`

---

### Task 4: Game adapter protocol and LoL adapter (notes + entities)

**Files:**
- Create: `pipeline/metashift/games/__init__.py`, `pipeline/metashift/games/base.py`, `pipeline/metashift/games/lol/__init__.py`, `pipeline/metashift/games/lol/adapter.py`
- Create fixtures: `pipeline/tests/fixtures/lol/versions.json`, `champion.json`, `item.json`, `runesReforged.json`, `patch-notes.html`
- Test: `pipeline/tests/test_lol_adapter.py`

**Interfaces:**
- Consumes: `EntityStats`, `MetashiftError`
- Produces (`games/base.py`):
  - `class StatsUnavailable(Exception)`
  - `class GameAdapter(Protocol)`: `game: str`, `entity_types: list[str]`, `glossary: str`, `list_patches() -> list[str]` (newest first), `fetch_notes(patch: str) -> str` (HTML), `notes_to_markdown(html: str) -> str`, `patch_date(html: str) -> date | None`, `entities(patch: str) -> dict[str, str]` (display name → entity_type), `icon_url(patch: str, entity: str) -> str | None`, `fetch_stats(patch: str) -> list[EntityStats]` (raises `StatsUnavailable`)
- Produces (`games/__init__.py`): `get_adapter(game: str) -> GameAdapter`; unknown game → `MetashiftError(f"unknown game '{game}'. Known: lol")`.
- Produces: `LolAdapter(http: httpx.Client | None = None)`, `entity_types = ["champion", "item", "rune", "system"]`. `fetch_stats` raises `StatsUnavailable("not implemented")` until Task 7.

`patch_date` is an addition to spec §3.1. The fetch stage needs it for `index.json` (spec §4.4).

LoL rules:
- Patch ids: Data Dragon `versions.json` lists `"16.21.1"`. Map major − 10 → `"26.21"`. Skip versions with major < 15. Remove duplicates and keep order.
- Notes URL: `https://www.leagueoflegends.com/en-us/news/game-updates/patch-{yy}-{n}-notes/` for patch `yy.n` (verified in Step 1 on patch 26.3). `n` is not zero-padded for 2026 (`patch-26-3-notes`), but it is for 2025 (`patch-25-04-notes`): on a 404 for a one-digit `n`, try the zero-padded form before failing. The page is server-rendered, so plain HTTP gets the article. Article body selector: `#patch-notes-container`. Publish date: the first `time[datetime]` inside `div.metadata` (ISO UTC, for example `2026-02-03T19:00:00.000Z`); other `<time>` tags on the page belong to related articles. Change lines are `<li>old <span class="change-indicator">⇒</span> new</li>`.
- Entities: `champion.json` `data[*].name` → `champion`; `item.json` `data[*].name` → `item`; `runesReforged.json` `[*].slots[*].runes[*].name` → `rune`. Cache each JSON per Data Dragon version.
- Icons: champion `https://ddragon.leagueoflegends.com/cdn/{ver}/img/champion/{data[*].id}.png`, item `.../cdn/{ver}/img/item/{item key}.png`, rune `https://ddragon.leagueoflegends.com/cdn/img/{icon}`. `system` → `None`.
- `notes_to_markdown`: select the article body with the selector found in Step 1, then `markdownify`. If the selector finds nothing → `MetashiftError("patch notes page layout changed: article body not found")`.

- [ ] **Step 1: Capture real fixtures (network, one time)**

Download `versions.json`, and the three Data Dragon JSON files for the newest version, into `tests/fixtures/lol/`. Trim `champion.json` to Ahri, Kai'Sa, Dr. Mundo, Nunu & Willump, Wukong. Trim `item.json` to 5 items and `runesReforged.json` to one tree. Save a recent patch notes page as `patch-notes.html`. Open it, confirm the URL pattern above, and write down the CSS selector of the article body and where the publish date is (for example a `<time datetime>`). If the URL pattern is different, update the rule above in this plan in the same commit.

- [ ] **Step 2: Write the failing tests** (all with `httpx.MockTransport` serving the fixtures)

```python
def test_list_patches_maps_ddragon_versions():
    assert adapter.list_patches()[:2] == ["26.21", "26.20"]   # use the real values from the fixture

def test_entities_include_punctuated_names():
    ents = adapter.entities("26.21")
    assert ents["Kai'Sa"] == "champion" and ents["Nunu & Willump"] == "champion"

def test_icon_url_uses_ddragon_id_not_display_name():
    assert adapter.icon_url("26.21", "Wukong").endswith("/img/champion/MonkeyKing.png")
    assert adapter.icon_url("26.21", "Kai'Sa").endswith("/img/champion/Kaisa.png")
    assert adapter.icon_url("26.21", "Dragon Soul") is None

def test_notes_to_markdown_keeps_change_lines():
    md = adapter.notes_to_markdown(fixture("patch-notes.html"))
    assert "⇒" in md and "<div" not in md

def test_notes_to_markdown_fails_clearly_on_other_layout():
    with pytest.raises(MetashiftError, match="layout changed"):
        adapter.notes_to_markdown("<html><body>hi</body></html>")

def test_patch_date_reads_publish_date():
    assert adapter.patch_date(fixture("patch-notes.html")) == date(...)  # value from Step 1
```

- [ ] **Step 3: Run and verify failure** — `uv run pytest tests/test_lol_adapter.py -v` → FAIL.
- [ ] **Step 4: Implement `games/base.py`, `games/__init__.py`, `games/lol/adapter.py`.** Write a short `glossary` (AD, AP, AS, CDR/AH, MR, HP, CC, "base", "ratio").
- [ ] **Step 5: Run and verify pass** — 6 passed.
- [ ] **Step 6: Commit** — `git commit -m "feat: game adapter protocol and LoL notes/entities adapter"`

---

### Task 5: Stage context and fetch stage

**Files:**
- Create: `pipeline/metashift/core/stages/__init__.py`, `pipeline/metashift/core/stages/context.py`, `pipeline/metashift/core/stages/fetch.py`
- Test: `pipeline/tests/stages/test_fetch.py`, `pipeline/tests/conftest.py`

**Interfaces:**
- Consumes: `GameAdapter`, `write_text`, `record_stage`, `patch_dir`
- Produces:
  - `@dataclass StageContext(game: str, patch: str, adapter: GameAdapter, llm: LLM | None, notes_file: Path | None = None)` with property `dir -> Path` (= `patch_dir(game, patch)`)
  - `run_fetch(ctx: StageContext) -> StageLog` — HTML from `ctx.notes_file` if set, else `adapter.fetch_notes`. Writes `raw.md`. Records the stage with `patch_date`.
  - Rule for every `run_*` stage (this task and Tasks 6–9): the stage measures its own `duration_s` with `time.perf_counter`, calls `record_stage` before it returns, and returns the same `StageLog`. So a stage run alone in a test still leaves a correct `run.log.json`.
  - `conftest.py`: fixture `root` (sets `METASHIFT_ROOT` to `tmp_path`), and `StubAdapter` — a `GameAdapter` with in-memory data that later stage tests reuse.

On an HTTP 404 from `fetch_notes`, the adapter raises `MetashiftError(f"patch notes not found at {url}. Save the page and pass --notes-file")`. Add this check to `LolAdapter.fetch_notes` in this task.

- [ ] **Step 1: Write the failing tests**

```python
def test_fetch_writes_raw_md_from_notes_file(root, tmp_path):
    html = tmp_path / "p.html"; html.write_text(FIXTURE_HTML)
    log = run_fetch(StageContext("lol", "26.21", LolAdapter(http=mock), None, notes_file=html))
    assert "⇒" in (root / "data/lol/26.21/raw.md").read_text()
    assert log.stage == "fetch"
    assert read_run_log("lol", "26.21").patch_date == date(...)

def test_fetch_404_suggests_notes_file(root):
    with pytest.raises(MetashiftError, match="--notes-file"):
        run_fetch(StageContext("lol", "26.21", LolAdapter(http=mock_404), None))
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement. Step 4: Run, verify pass** (`uv run pytest tests/stages/test_fetch.py -v` → 2 passed).
- [ ] **Step 5: Commit** — `git commit -m "feat: fetch stage"`

---

### Task 6: Extract stage

**Files:**
- Create: `pipeline/metashift/core/prompts.py`, `pipeline/metashift/core/text.py`, `pipeline/metashift/core/stages/extract.py`
- Test: `pipeline/tests/test_text.py`, `pipeline/tests/stages/test_extract.py`

**Interfaces:**
- Consumes: `StageContext`, `complete_with_retry`, `read_model`/`write_model`, `ExtractDraft`, `ChangesFile`
- Produces (`core/text.py`):
  - `normalize_ws(s: str) -> str` — collapses all whitespace runs to one space and strips.
  - `name_key(s: str) -> str` — lower case, only `[a-z0-9]` kept (`"Kai'Sa"` → `"kaisa"`).
  - `resolve_entity(name: str, known: dict[str, str]) -> str | None` — tries an exact match, then a `name_key` match, then `difflib.get_close_matches` on the keys with `cutoff=0.85`. Returns the known display name.
  - `split_sections(md: str, max_chars: int = 6000) -> list[str]` — splits at `#`/`##`/`###` headings, then packs sections into chunks ≤ `max_chars`. A single section longer than `max_chars` is split at blank lines.
  - `count_change_lines(md: str) -> int` — counts lines that contain `⇒` or `→`.
- Produces (`core/prompts.py`): `extract_prompt(chunk: str, glossary: str, entity_types: list[str]) -> str`, `analyze_prompt(changes: list[Change], baseline: BaselineFile, glossary: str) -> str` (the analyze prompt is written in Task 8).
- Produces: `run_extract(ctx: StageContext) -> StageLog` — writes `changes.json`.

Extract rules, in order, for each chunk's `ExtractDraft`:
1. `entity_type == "system"`: keep the name as it is.
2. Otherwise `resolve_entity`. No match → drop the change, warn `f"unknown entity '{name}' dropped"`. A match → use the display name and the known `entity_type`.
3. `normalize_ws(source_quote)` not in `normalize_ws(raw)` → drop the change, warn `f"quote not found in notes, dropped: {entity} {stat}"`.
4. After all chunks: if `len(changes) < 0.8 * count_change_lines(raw)`, warn `f"low coverage: extracted {n} of ~{m} change lines"`.

The extract prompt asks for one `Change` per stat line. It sets `source_quote` to the exact line from the notes, `direction` to `adjust` for mixed changes or reworks, `old`/`new` to null for new or removed mechanics, and `entity_type` to one of the given types.

- [ ] **Step 1: Write the failing tests**

```python
# test_text.py
def test_resolve_entity_handles_punctuation_and_typos():
    known = {"Kai'Sa": "champion", "Dr. Mundo": "champion", "Nunu & Willump": "champion"}
    assert resolve_entity("Kaisa", known) == "Kai'Sa"
    assert resolve_entity("dr mundo", known) == "Dr. Mundo"
    assert resolve_entity("Nunu and Willump", known) == "Nunu & Willump"
    assert resolve_entity("Garen", known) is None

def test_count_change_lines_counts_both_arrows():
    assert count_change_lines("a: 1 ⇒ 2\nb: 3 → 4\nc: text") == 2

def test_split_sections_respects_max_chars():
    md = "## A\n" + "x" * 5000 + "\n## B\n" + "y" * 5000
    assert len(split_sections(md, 6000)) == 2

# stages/test_extract.py  (StubAdapter knows Ahri, Kai'Sa; raw.md has 2 change lines)
def test_extract_resolves_names_and_drops_bad_rows(root):
    llm = FakeLLM([json_of(ExtractDraft(changes=[ahri_ok, kaisa_as_Kaisa, garen_unknown, ahri_fake_quote]))])
    log = run_extract(ctx(llm))
    changes = read_changes()
    assert [c.entity for c in changes] == ["Ahri", "Kai'Sa"]
    assert any("unknown entity 'Garen'" in w for w in log.warnings)
    assert any("quote not found" in w for w in log.warnings)

def test_extract_keeps_system_entities_unresolved(root): ...  # "Dragon Soul", entity_type system → kept

def test_extract_low_coverage_warns(root):
    ...  # raw.md with 5 arrow lines, LLM returns 1 change
    assert any("low coverage: extracted 1 of ~5" in w for w in log.warnings)

def test_extract_without_fetch_names_the_stage(root):
    with pytest.raises(MetashiftError, match="run stage 'fetch' first"):
        run_extract(ctx(FakeLLM([])))
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement `text.py`, `extract_prompt`, `extract.py`. Step 4: Run, verify pass** (`uv run pytest tests/test_text.py tests/stages/test_extract.py -v` → 7 passed).
- [ ] **Step 5: Commit** — `git commit -m "feat: extract stage with name resolution, quote check and coverage warning"`

---

### Task 7: Stats sources and baseline stage

**Files:**
- Create: `pipeline/metashift/core/stats_csv.py`, `pipeline/metashift/games/lol/stats.py`, `pipeline/metashift/core/stages/baseline.py`
- Modify: `pipeline/metashift/games/lol/adapter.py` (`fetch_stats`)
- Test: `pipeline/tests/test_stats_csv.py`, `pipeline/tests/stages/test_baseline.py`, `pipeline/tests/test_lol_stats.py`

**Interfaces:**
- Consumes: `name_key`, `StatsUnavailable`, `read_model`/`write_model`, `patch_dir`
- Produces:
  - `read_stats_csv(path: Path) -> list[EntityStats]` — reads with `encoding="utf-8-sig"`, columns `entity,win_rate,pick_rate,ban_rate,tier`. Strips whitespace and a trailing `%`. An empty cell → `None`. A bad number → `MetashiftError(f"stats.csv line {n}: bad {column} '{value}'")`.
  - `scrape_lolalytics(patch: str, http: httpx.Client) -> list[EntityStats]` — raises `StatsUnavailable` on any HTTP or parse failure.
  - `run_baseline(ctx: StageContext) -> StageLog` — writes `baseline.json`.

Baseline rules:
- Previous patch = the patch after `ctx.patch` in `adapter.list_patches()`. `ctx.patch` not in the list → `MetashiftError(f"patch {patch} not found in {game} patch list")`. No older patch → `stats_patch=None`, no stats, warn `"no previous patch: stats skipped"`.
- Stats: `adapter.fetch_stats(prev)`. On `StatsUnavailable`, read `ctx.dir / "stats.csv"`. If that file is missing → `MetashiftError` that names the path relative to the repo root and the columns `entity,win_rate,pick_rate,ban_rate,tier`. `stats_source` = `"lolalytics"` or `"csv"`.
- Match stats to changed entities by `name_key`. An entity with no row gets null stats and warn `f"no stats for {entity}"`.
- History: for each of the 5 patches older than `ctx.patch` that has `changes.json`, add one `HistoryEntry` per changed entity. `direction` is the shared direction, or `adjust` when mixed. `summary` = up to 3 `f"{target} {stat} {direction}"` parts joined with `"; "`, plus `"; …"` when there are more. A missing older file is skipped without a warning.

- [ ] **Step 1: Check lolalytics before writing the scraper**

Read the lolalytics terms of use and robots.txt. Find whether a stable JSON endpoint gives all-rank win, pick and ban rates for a patch. Write the result in `pipeline/metashift/games/lol/STATS.md` (one paragraph: allowed or not, endpoint, fields). **If scraping is not allowed or not feasible:** `fetch_stats` always raises `StatsUnavailable("lolalytics not used: see STATS.md")`, skip `scrape_lolalytics` and its test, and say so in the task report. CSV becomes the supported path (spec §3.1).

- [ ] **Step 2: Write the failing tests**

```python
def test_stats_csv_handles_bom_percent_and_blank_tier(tmp_path):
    p = tmp_path / "stats.csv"
    p.write_bytes("﻿entity,win_rate,pick_rate,ban_rate,tier\nahri, 49.1% ,6.2,3.0,\n".encode())
    [row] = read_stats_csv(p)
    assert (row.entity, row.win_rate, row.tier) == ("ahri", 49.1, None)

def test_stats_csv_bad_number_names_line_and_column(tmp_path): ...  # match "line 2: bad win_rate 'abc'"

def test_baseline_uses_previous_patch_and_csv_fallback(root):
    # StubAdapter patches ["26.21","26.20","26.19"], fetch_stats raises StatsUnavailable,
    # changes.json(26.21) changes Ahri; stats.csv row "ahri"
    run_baseline(ctx)
    b = read_baseline()
    assert b.stats_patch == "26.20" and b.stats_source == "csv"
    assert b.entities["Ahri"].win_rate == 49.1

def test_baseline_missing_csv_prints_path_and_columns(root):
    with pytest.raises(MetashiftError, match=r"data/lol/26.21/stats.csv.*entity,win_rate,pick_rate,ban_rate,tier"):
        run_baseline(ctx)

def test_baseline_history_last_five_with_mixed_as_adjust(root):
    # changes.json for 26.20 (Ahri buff + nerf) and 26.14 (Ahri nerf, 7 patches back)
    assert b.entities["Ahri"].history == [HistoryEntry(patch="26.20", direction="adjust", summary=...)]

def test_baseline_first_patch_has_no_stats(root): ...  # warning "no previous patch: stats skipped"
```

- [ ] **Step 3: Run, verify failure. Step 4: Implement. Step 5: Run, verify pass** (`uv run pytest tests/test_stats_csv.py tests/stages/test_baseline.py tests/test_lol_stats.py -v`).
- [ ] **Step 6: Commit** — `git commit -m "feat: baseline stage with lolalytics/CSV stats and patch history"`

---

### Task 8: Analyze stage

**Files:**
- Create: `pipeline/metashift/core/stages/analyze.py`, `pipeline/metashift/core/checks.py`
- Modify: `pipeline/metashift/core/prompts.py` (`analyze_prompt`)
- Test: `pipeline/tests/test_checks.py`, `pipeline/tests/stages/test_analyze.py`

**Interfaces:**
- Consumes: `complete_with_retry`, `AnalysisDraft`, `ChangesFile`, `BaselineFile`, `stage_warnings`, `adapter.icon_url`
- Produces (`core/checks.py`):
  - `retry_problems(draft: AnalysisDraft, changes: list[Change]) -> list[str]` — `f"missing verdict for {entity}"` for each changed entity with no verdict; `f"{entity}: change_ref {i} out of range"`.
  - `consistency_warnings(draft: AnalysisDraft, changes: list[Change]) -> list[str]` — `f"{entity}: verdict rise but all changes are nerfs"`, and the same for fall with all buffs.
- Produces: `run_analyze(ctx: StageContext) -> StageLog` — writes `report.json`.

Report assembly (code, not LLM): `previous` copied from the baseline, or `None` when all stat fields are null; `icon_url` from the adapter; `changes` copied from `changes.json`; `compared_to = baseline.stats_patch`; `generated_at = datetime.now(UTC)`; `llm = ctx.llm.name`; `warnings` = `stage_warnings` from earlier stages + problems left after retries + consistency warnings. Verdicts for entities that did not change are dropped with warn `f"verdict for unchanged entity {entity} dropped"`.

`analyze_prompt` lists the changes numbered by index and, per entity, the baseline stats and history. It asks for a headline (one sentence), 2–4 themes, and one verdict per changed entity, with a reason that cites the change, the stats and the trend, and `change_refs` as indexes. It also says that a near-50% win rate with a small change usually means `stable`.

- [ ] **Step 1: Write the failing tests**

```python
def test_retry_problems_finds_missing_and_bad_refs():
    probs = retry_problems(AnalysisDraft(headline="h", themes=[], entities=[v("Ahri", refs=[5])]), [ahri_buff, kaisa_nerf])
    assert probs == ["missing verdict for Kai'Sa", "Ahri: change_ref 5 out of range"]

def test_consistency_flags_rise_with_only_nerfs():
    assert consistency_warnings(draft_rise("Kai'Sa", refs=[1]), [ahri_buff, kaisa_nerf]) == \
        ["Kai'Sa: verdict rise but all changes are nerfs"]

def test_analyze_assembles_report_with_code_owned_fields(root):
    llm = FakeLLM([good_draft_json])
    run_analyze(ctx(llm))
    r = read_report()
    assert r.compared_to == "26.20"
    assert r.entities[0].previous.win_rate == 49.1        # from baseline, not LLM
    assert r.entities[0].icon_url == "stub://Ahri.png"
    assert r.changes == changes_file.changes and r.llm == "fake"

def test_analyze_retries_then_writes_with_warning(root):
    llm = FakeLLM([missing_kaisa_json] * 3)
    log = run_analyze(ctx(llm))
    assert log.retries == 2
    assert "missing verdict for Kai'Sa" in read_report().warnings

def test_analyze_carries_earlier_stage_warnings(root): ...  # record_stage extract warning → in report.warnings
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement. Step 4: Run, verify pass** (`uv run pytest tests/test_checks.py tests/stages/test_analyze.py -v` → 5 passed).
- [ ] **Step 5: Commit** — `git commit -m "feat: analyze stage with rule checks"`

---

### Task 9: Publish stage

**Files:**
- Create: `pipeline/metashift/core/stages/publish.py`
- Test: `pipeline/tests/stages/test_publish.py`

**Interfaces:**
- Consumes: `ReportFile`, `RunLog`, `IndexFile`, `web_data_dir`
- Produces: `run_publish(ctx: StageContext) -> StageLog` — copies the report to `web/public/data/<game>/<patch>.json`, then rebuilds `web/public/data/index.json` from every `web/public/data/*/*.json` report. Entries per game are sorted newest first by `tuple(int(p) for p in patch.split("."))`. `patch_date` comes from that patch's `run.log.json` (`None` if missing). `buffs`/`nerfs` count `report.changes` by direction.
- Also produces: `patch_sort_key(patch: str) -> tuple[int, ...]` in `core/text.py`.

- [ ] **Step 1: Write the failing tests**

```python
def test_publish_rebuilds_index_newest_first(root):
    publish("26.9"); publish("26.21"); publish("26.10")
    idx = IndexFile.model_validate_json((root / "web/public/data/index.json").read_text())
    assert [e.patch for e in idx.games["lol"]] == ["26.21", "26.10", "26.9"]   # numeric, not string sort

def test_publish_counts_buffs_and_nerfs(root): ...  # 2 buffs, 1 nerf, 1 adjust → buffs=2, nerfs=1
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement. Step 4: Run, verify pass. Step 5: Commit** — `git commit -m "feat: publish stage and index"`

---

### Task 10: CLI `run` and `schema` commands

**Files:**
- Create: `pipeline/metashift/cli.py`
- Test: `pipeline/tests/test_cli.py`

**Interfaces:**
- Consumes: all `run_*` stages, `get_adapter`, `make_llm`, `record_stage`
- Produces:
  - `STAGES = ["fetch", "extract", "baseline", "analyze", "publish"]` and `run_pipeline(ctx: StageContext, from_stage: str = "fetch", to_stage: str = "publish") -> list[StageLog]`. It runs the stages in order. The stages record themselves (Task 5 rule).
  - `metashift run GAME PATCH [--llm ollama|claude] [--notes-file PATH] [--from-stage NAME] [--to-stage NAME]` — `--llm` default `ollama`. `--to-stage` is an addition to the spec. The golden-set step (Task 11) needs to stop after `extract`. Prints one line per stage: `✓ extract  12.3s  1 retry  2 warnings`. At the end, prints all warnings and the report path.
  - `metashift schema OUT_DIR` — writes `ReportFile.schema.json` and `IndexFile.schema.json`.
  - `MetashiftError` → `error: <message>` on stderr, exit code 1. An unknown `--from-stage` → exit 2 with the list of valid stages.
  - The LLM is created only when a stage that needs it (`extract`, `analyze`) will run. So `--from-stage publish` works with Ollama stopped.

- [ ] **Step 1: Write the failing tests** (Typer `CliRunner`; patch `make_llm` to return `FakeLLM`, patch `get_adapter` to return `StubAdapter`)

```python
def test_run_all_stages_writes_report_and_index(root): ...  # exit 0, report.json + index.json exist, run.log has 5 stages

def test_from_stage_with_missing_input_prints_clean_error(root):
    result = runner.invoke(app, ["run", "lol", "26.21", "--from-stage", "analyze"])
    assert result.exit_code == 1
    assert "error: missing data/lol/26.21/changes.json — run stage 'extract' first" in result.stderr
    assert "Traceback" not in result.output

def test_from_stage_publish_does_not_create_llm(root): ...  # make_llm patched to raise → still exit 0

def test_unknown_stage_lists_valid_stages(root): ...  # exit 2, "fetch, extract, baseline, analyze, publish"

def test_to_stage_extract_stops_before_baseline(root): ...  # changes.json exists, baseline.json does not, exit 0

def test_schema_writes_both_files(tmp_path): ...
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement. Step 4: Run all pipeline tests** — `uv run pytest -v` → all pass, with no network access.
- [ ] **Step 5: Commit** — `git commit -m "feat: metashift CLI run and schema commands"`

---

### Task 11: Golden set and extraction eval

**Files:**
- Create: `pipeline/metashift/core/evaluate.py`, `pipeline/tests/golden/lol/<patch>/raw.md` and `changes.json` × 3
- Modify: `pipeline/metashift/cli.py` (add `eval extract`)
- Test: `pipeline/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `run_extract` logic. Factor out `extract_changes(raw: str, adapter: GameAdapter, patch: str, llm: LLM) -> tuple[list[Change], int, list[str]]` from `extract.py`, with no file IO, so the eval can call it.
- Produces:
  - `EvalScore(tp: int, fp: int, fn: int)` with properties `precision`, `recall` (1.0 when the denominator is 0).
  - `score_extraction(predicted: list[Change], gold: list[Change]) -> EvalScore` — matches on `(name_key(entity), normalize_ws(stat).lower(), direction)` as a multiset.
  - `metashift eval extract --game lol [--llm ollama|claude]` — prints one row per golden patch and a total row: `patch  P  R  tp fp fn`. Then it prints `targets met` or `below target: recall 0.84 < 0.90`. The exit code is always 0, because this is a measurement.

- [ ] **Step 1: Write the failing tests**

```python
def test_score_counts_matches_as_multiset():
    s = score_extraction([ahri_q_buff, ahri_q_buff, kaisa_nerf], [ahri_q_buff, garen_buff])
    assert (s.tp, s.fp, s.fn) == (1, 2, 1)

def test_score_ignores_name_and_stat_formatting():
    assert score_extraction([chg("Kai'Sa", "Base  Damage")], [chg("kaisa", "base damage")]).tp == 1
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement `evaluate.py`, `extract_changes`, CLI command. Step 4: Run, verify pass.**
- [ ] **Step 5: Build the golden set (needs network + Ollama, human gate)**

Run `metashift run lol <p> --to-stage extract` for the 3 most recent patches. Copy `raw.md` and `changes.json` into `tests/golden/lol/<p>/`. Fix each `changes.json` by hand against `raw.md`: Claude drafts the fixes, then **the user reviews and approves each file**. Do not commit the golden set before that approval.

- [ ] **Step 6: Run the eval** — `uv run metashift eval extract --game lol` → table printed. Put the numbers in `pipeline/EVAL.md` with the model name and the date.
- [ ] **Step 7: Commit** — `git commit -m "feat: extraction eval with golden set"`

---

### Task 12: Web scaffold, types, data loading, patch list

**Files:**
- Create: `web/` (Vite React TS template), `web/src/types/generated.ts`, `web/src/data.ts`, `web/src/format.ts`, `web/src/App.tsx`, `web/src/components/Layout.tsx`, `web/src/pages/PatchList.tsx`, `web/src/theme.css`
- Create fixtures: `web/src/test/fixtures/index.json`, `web/src/test/fixtures/report-26.21.json`
- Test: `web/src/format.test.ts`, `web/src/pages/PatchList.test.tsx`

Read the `frontend-design` skill before you write any page styles.

**Interfaces:**
- Consumes: `metashift schema` (Task 10)
- Produces:
  - `npm run gen:types` = `uv run --project ../pipeline metashift schema src/types/schema && json2ts` → `src/types/generated.ts` exporting `ReportFile`, `IndexFile`, `EntityVerdict`, `Change`. Commit the generated file.
  - `data.ts`: `fetchIndex(): Promise<IndexFile>`, `fetchReport(game: string, patch: string): Promise<ReportFile>`. Both use `${import.meta.env.BASE_URL}data/...`. A failed fetch throws `Error(\`could not load ${path}\`)`, and the page shows that text.
  - `format.ts`: `formatChange(old: string | null, next: string | null): string` → `"40 → 45"`, `"— → 45"`, `"40 → —"`; `formatRate(v: number | null): string` → `"49.1%"` or `"no stats"`.
  - Routes in `App.tsx` (`HashRouter`): `/` → redirect to the first game in the index; `/:game` → `PatchList`; `/:game/:patch` → `ReportPage` (Task 13); `/:game/:entityType/:entity` → `EntityHistory` (Task 14).
  - `Layout`: top bar with a game switcher (games from `index.games` keys), a light/dark toggle saved in `localStorage` inside try/catch (default `prefers-color-scheme`), and a footer with this exact text: "Metashift isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc."
  - `vite.config.ts`: `base: "./"`.

- [ ] **Step 1: Scaffold** — `npm create vite@latest web -- --template react-ts && cd web && npm i react-router-dom && npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom json-schema-to-typescript @playwright/test`. Run `npm run gen:types`.
- [ ] **Step 2: Write the failing tests**

```ts
test("formatChange shows a dash for null values", () => {
  expect(formatChange(null, "45")).toBe("— → 45");
  expect(formatChange("40", null)).toBe("40 → —");
});
test("formatRate shows no stats for null", () => expect(formatRate(null)).toBe("no stats"));
test("PatchList renders rows newest first with counts", async () => {
  // mock fetchIndex with the fixture
  expect(rows[0]).toHaveTextContent("26.21");
  expect(rows[0]).toHaveTextContent("9 buffs");
  expect(rows[0]).toHaveTextContent("ollama:qwen3:14b");
});
```

- [ ] **Step 3: Run, verify failure** — `npx vitest run` → FAIL. **Step 4: Implement. Step 5: Run, verify pass.**
- [ ] **Step 6: Commit** — `git commit -m "feat: web scaffold, generated types, patch list"`

---

### Task 13: Patch report page (board, cards, filters, warnings)

**Files:**
- Create: `web/src/pages/ReportPage.tsx`, `web/src/components/Board.tsx`, `web/src/components/EntityCard.tsx`, `web/src/components/Filters.tsx`, `web/src/components/WarningsPanel.tsx`
- Test: `web/src/components/Board.test.tsx`, `web/src/components/EntityCard.test.tsx`

**Interfaces:**
- Consumes: `fetchReport`, `formatChange`, `formatRate`, generated types
- Produces:
  - `Board({ report }: { report: ReportFile })` — three columns: Rise, Stable, Fall, each with a count. Filters: entity type (from the entity types in the report) and confidence (`all | low | medium | high`). Below 640 px the board becomes three tabs (CSS media query plus tab state). Default tab: Rise.
  - `EntityCard({ verdict, changes }: { verdict: EntityVerdict; changes: Change[] })` — icon (`<img alt="">`, hidden when `icon_url` is null), name linked to `#/<game>/<entity_type>/<entity>` (with `encodeURIComponent`), previous tier and win rate, confidence, reason. A button expands the list of `verdict.change_refs`: target, stat, `formatChange(old, new)`, quote.
  - `WarningsPanel({ warnings })` — a collapsed `<details>` with the count in the summary. It renders nothing when `warnings` is empty.
  - Header: `Patch {patch} · vs {compared_to} meta` (or `· no previous patch` when `compared_to` is null), headline, theme chips.

- [ ] **Step 1: Write the failing tests**

```tsx
test("Board groups verdicts into columns with counts", () => {
  render(<Board report={fixture} />);       // fixture: 2 rise, 1 stable, 1 fall
  expect(screen.getByRole("heading", { name: /rise \(2\)/i })).toBeInTheDocument();
});
test("confidence filter hides low-confidence cards", async () => { ... });
test("EntityCard expands source changes with null-safe values", async () => {
  render(<EntityCard verdict={v} changes={[{ ...c, old: null, new: "45" }]} />);
  await user.click(screen.getByRole("button", { name: /show changes/i }));
  expect(screen.getByText("— → 45")).toBeInTheDocument();
  expect(screen.queryByText(/null/)).not.toBeInTheDocument();
});
test("EntityCard links to entity history with encoded name", () => {
  // Kai'Sa → href "#/lol/champion/Kai'Sa" encoded
});
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement. Step 4: Run, verify pass. Step 5: Commit** — `git commit -m "feat: patch report board"`

---

### Task 14: Entity history page and Playwright smoke test

**Files:**
- Create: `web/src/pages/EntityHistory.tsx`, `web/e2e/smoke.spec.ts`, `web/playwright.config.ts`, `web/e2e/fixtures/` (index + 2 reports)
- Test: `web/src/pages/EntityHistory.test.tsx`

**Interfaces:**
- Consumes: `fetchIndex`, `fetchReport`, `EntityCard` formatting helpers
- Produces: `EntityHistory` — loads the index, then every report of the game. Keeps the patches whose `changes` include the entity, newest first. Each row shows the patch, the changes (`formatChange`), the verdict, the confidence and the previous stats. When there are no rows, it shows `No published patch changed {entity}.`

- [ ] **Step 1: Write the failing tests**

```tsx
test("EntityHistory lists only patches that changed the entity, newest first", async () => {
  // reports 26.21 (Ahri), 26.20 (Kai'Sa only), 26.19 (Ahri)
  expect(rows.map(r => r.textContent)).toEqual([expect.stringContaining("26.21"), expect.stringContaining("26.19")]);
});
test("EntityHistory shows empty message", async () => { ... });
```

```ts
// e2e/smoke.spec.ts — page.route("**/data/**") serves e2e/fixtures
test("report page shows three columns", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  for (const col of ["Rise", "Stable", "Fall"]) await expect(page.getByRole("heading", { name: new RegExp(col) })).toBeVisible();
});
test("phone width shows tabs", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/#/lol/26.21");
  await expect(page.getByRole("tab", { name: /rise/i })).toBeVisible();
});
```

`playwright.config.ts`: `webServer: { command: "npm run build && npm run preview -- --port 4173", port: 4173 }`.

- [ ] **Step 2: Run, verify failure** — `npx vitest run && npx playwright install chromium && npx playwright test` → FAIL.
- [ ] **Step 3: Implement. Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat: entity history page and e2e smoke test"`

---

### Task 15: Real run, README, deploy check

**Files:**
- Create: `README.md`
- Create (output): `data/lol/<patch>/*` and `web/public/data/*` for 3 real patches

- [ ] **Step 1: Real end-to-end run** (needs network + Ollama with `qwen3:14b` pulled)

Run: `cd pipeline && uv run metashift run lol <newest patch>`, then the two patches before it, oldest first, so the history fills in.
Expected: every stage ✓, `report.json` exists, warnings are printed. If lolalytics is not used, write `stats.csv` for each patch first. The baseline error shows the path.

- [ ] **Step 2: Check the report by eye** — open 5 random changes and compare them with the patch notes. Record what was wrong in `pipeline/EVAL.md` under "manual check".
- [ ] **Step 3: Build and preview the site** — `cd web && npm run build && npm run preview`. Open the patch list, a report and an entity history page at desktop width and at 375 px, in light and dark mode.
- [ ] **Step 4: Write `README.md`** — what Metashift is, setup (`uv sync`, `ollama pull qwen3:14b`, `npm i`), `metashift run`, the `stats.csv` format, how to switch to Claude, `metashift eval extract`, and deploy (`web/dist` to GitHub Pages or Vercel, works because `base: "./"`).
- [ ] **Step 5: Check the spec success criteria (spec §8)** — tick each one in the task report, with evidence: command output, eval numbers, screenshots.
- [ ] **Step 6: Commit** — `git add README.md data web/public/data pipeline/EVAL.md && git commit -m "docs: README and first three published patches"`
