# Metashift — design spec

Date: 2026-10-25
Status: approved in chat, awaiting written-spec review

## 1. Goal

When a new game patch drops, Metashift produces a **meta shift report**: every buff
and nerf as structured data, and a verdict for each changed entity (rise, fall or
stable) compared with the previous meta.

"Previous meta" means two things together:

- **Stats** — win, pick and ban rates (and tier, when available) from the previous patch.
- **History** — the changes made to each entity in the last 5 patches.

The core is game-agnostic. Version 1 ships one game adapter: **League of Legends**.
Apex Legends gets its own adapter in a later, separate spec.

### Users and constraints

- One user (the author). No accounts.
- Zero running cost. No paid hosting. LLM runs locally by default.
- LLM is swappable: Ollama (default) or the Claude API.

### Out of scope for v1

- Apex Legends adapter.
- Scoring verdicts against the next patch's real stats (the "eval loop"). The data
  for it is saved (see §6), but no scoring code is written.
- Search, accounts, comments, live stats, charts.
- Scheduled runs (a GitHub Action can come later).

## 2. Architecture

Approach: **local pipeline + static web app**.

```
metashift/
  pipeline/                Python 3.12, managed with uv
    metashift/
      core/
        models.py          Pydantic models for every file
        llm.py             LLM interface + OllamaClient + ClaudeClient + FakeLLM
        stages/            fetch, extract, baseline, analyze, publish
        io.py              atomic write, run log
        cli.py             `metashift` command
      games/
        base.py            GameAdapter protocol
        lol/               LoL adapter
    tests/
      fixtures/            saved HTML pages, sample JSON
      golden/lol/<patch>/  hand-labeled changes.json (3 patches)
  data/lol/<patch>/        pipeline output, one folder per patch
  web/                     React + Vite static site
```

The web app never calls an LLM or a stats site. It only reads JSON that the
pipeline publishes.

## 3. Pipeline

Command: `metashift run <game> <patch> [--llm ollama|claude] [--notes-file PATH] [--from-stage NAME]`

Each stage reads the files of earlier stages and writes one file to
`data/<game>/<patch>/`. Any stage can be re-run alone with `--from-stage`.

| # | Stage | Input | Output | LLM |
|---|---|---|---|---|
| 1 | fetch | patch notes URL or `--notes-file`; keeps only meta sections (`select_sections`) | `raw.md` | no |
| 2 | extract | `raw.md`, adapter entity list | `changes.json` | yes |
| 3 | baseline | previous patch stats, last 5 `changes.json` | `baseline.json` | no |
| 4 | analyze | `changes.json`, `baseline.json` | `report.json` | yes |
| 5 | publish | `report.json` | `web/public/data/<game>/<patch>.json`, `web/public/data/index.json` | no |

The previous patch for the baseline is found from the adapter's patch list
(`list_patches()`), not by arithmetic on the patch number.

### 3.1 Game adapter

```python
class GameAdapter(Protocol):
    game: str                                   # "lol"
    entity_types: list[str]                     # ["champion", "item", "rune", "system"]
    glossary: str                               # game terms for prompts

    def list_patches(self) -> list[str]: ...    # newest first
    def fetch_notes(self, patch: str) -> str: ...        # returns HTML
    def notes_to_markdown(self, html: str) -> str: ...
    def select_sections(self, markdown: str) -> tuple[str, list[str]]: ...  # kept, dropped titles
    def entities(self, patch: str) -> dict[str, str]: ...  # name -> entity_type
    def fetch_stats(self, patch: str) -> list[EntityStats]: ...
```

**LoL adapter:**

- Notes: official patch notes page on leagueoflegends.com.
- Entities and icons: Riot Data Dragon (free, no API key).
- Sections (amended 2026-10-25): only Summoner's Rift sections count toward the meta.
  `select_sections` keeps the H2 sections `Mid-Patch Updates`, `Champions`, `Items`,
  `Runes`, `Systems` and any title starting with `Summoner's Rift`. Mode sections
  (Arena, ARAM, Classic, …) are dropped, and fetch adds one warning that names them.
- Stats: a scraper for lolalytics (all ranks, all roles combined). Its terms are checked
  before the scraper is written. Fallback: `data/lol/<patch>/stats.csv`
  with columns `entity,win_rate,pick_rate,ban_rate,tier` (`tier` may be empty).
  If the site blocks scraping or its terms forbid it, the CSV is the supported path.

### 3.2 LLM interface

```python
class LLM(Protocol):
    name: str                                   # e.g. "ollama:qwen3:14b"
    def complete_json(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...
```

- `OllamaClient` is the default. Model set by `METASHIFT_OLLAMA_MODEL`.
- `ClaudeClient` uses the Anthropic SDK. Key from `ANTHROPIC_API_KEY`. Model set by
  `METASHIFT_CLAUDE_MODEL`.
- `FakeLLM` returns fixed responses for tests.
- On a schema validation failure, the stage sends the validation error back to the LLM
  and retries, at most 2 times.

## 4. Data model

All files are Pydantic models in `core/models.py`. Each file is validated on write
and on read. TypeScript types for the web app are generated from the same models
(JSON Schema → TS) so the two sides stay in sync.

### 4.1 `changes.json`

```json
{
  "game": "lol",
  "patch": "26.21",
  "changes": [
    {
      "entity": "Ahri",
      "entity_type": "champion",
      "target": "Q - Orb of Deception",
      "stat": "base damage",
      "old": "40/65/90/115/140",
      "new": "45/70/95/120/145",
      "direction": "buff",
      "source_quote": "Q base damage: 40/65/90/115/140 ⇒ 45/70/95/120/145"
    }
  ]
}
```

- `entity_type`: one of the adapter's `entity_types`.
- `direction`: `buff` | `nerf` | `adjust` (`adjust` = mixed, unclear or rework).
- `old`, `new`: strings, nullable (new or removed mechanics). No math is done on them.
- `source_quote`: exact substring of `raw.md` (after whitespace normalisation).

### 4.2 `baseline.json`

```json
{
  "stats_patch": "26.20",
  "stats_source": "lolalytics",
  "entities": {
    "Ahri": {
      "win_rate": 49.1,
      "pick_rate": 6.2,
      "ban_rate": 3.0,
      "tier": "B",
      "history": [
        {"patch": "26.19", "direction": "nerf", "summary": "Q damage down"}
      ]
    }
  }
}
```

- Only entities that change in this patch.
- `stats_source`: the scraper name or `"csv"`.
- Stat fields and `tier` are nullable.
- `history`: up to 5 previous patches, built from their `changes.json`. One entry per
  patch per entity. `direction` is `adjust` when that patch had mixed directions.
  `summary` is built from the change rows without an LLM (target + stat + direction).

### 4.3 `report.json`

```json
{
  "game": "lol",
  "patch": "26.21",
  "compared_to": "26.20",
  "generated_at": "2026-10-25T12:00:00Z",
  "llm": "ollama:qwen3:14b",
  "headline": "Mage buffs push mid lane back toward burst",
  "themes": ["Burst mages buffed", "Tank items nerfed"],
  "entities": [
    {
      "entity": "Ahri",
      "entity_type": "champion",
      "verdict": "rise",
      "confidence": "medium",
      "previous": {"win_rate": 49.1, "pick_rate": 6.2, "ban_rate": 3.0, "tier": "B"},
      "reason": "Second buff after a 26.19 nerf. Below 50% WR, so the buff likely puts her back to average.",
      "change_refs": [0]
    }
  ],
  "changes": [],
  "warnings": []
}
```

- `verdict`: `rise` | `fall` | `stable`. `confidence`: `low` | `medium` | `high`.
- `change_refs`: indexes into `changes`, set by code to every row of that entity
  (amended 2026-10-25: the LLM no longer supplies them). The report embeds a copy of the change rows
  so the published file is self-contained for the web app.
- `previous` is copied from the baseline by code, not written by the LLM.
- `warnings`: collected from all stages (see §6).

### 4.4 `index.json` (published)

```json
{
  "games": {
    "lol": [
      {"patch": "26.21", "patch_date": "2026-10-22", "headline": "...",
       "buffs": 9, "nerfs": 6, "llm": "ollama:qwen3:14b"}
    ]
  }
}
```

- Rebuilt by the publish stage from all published reports. Newest patch first.
- `patch_date`: taken from the notes page by the fetch stage and stored in
  `run.log.json`. Nullable.
- `buffs`, `nerfs`: counts of change rows by `direction`.

## 5. Web app

React + Vite, TypeScript, hash routing (`#/lol/26.21`) so it works on any static host.
Light and dark themes. Works at phone width. Reads only `public/data/`.

Top bar: game switcher (LoL only in v1; a game appears when `index.json` lists it).

### 5.1 Patch list — `#/<game>`

Patches newest first. Each row: patch, date, headline, buff count, nerf count, model.

### 5.2 Patch report — `#/<game>/<patch>`

- Header: patch, "vs <compared_to> meta", headline, theme chips.
- Board with three columns: **Rise**, **Stable**, **Fall**, each with a count.
  On phone width the columns become three tabs.
- Card: entity icon, name, previous tier and win rate, confidence, reason.
- Clicking a card expands its source changes: target, stat, old → new, quote.
- Filters: entity type, confidence.
- Warnings from the report show in a collapsed panel.

### 5.3 Entity history — `#/<game>/<entity_type>/<entity>`

Timeline of every published patch that changed the entity: changes, verdict,
previous stats at each point.

### 5.4 Assets and legal

- Icons are loaded from Data Dragon URLs. No copies are stored.
- Footer carries Riot's fan-content disclaimer.

## 6. Error handling

Rules for all stages:

- **Atomic writes.** Write to a temp file, validate, then rename. A failed stage never
  replaces a good file.
- **Run log.** Each run writes `data/<game>/<patch>/run.log.json`: per stage, the
  model, duration, retry count and warnings.

| Stage | Failure | Behaviour |
|---|---|---|
| fetch | URL 404 or page layout changed | Stop. Show the URL tried. Suggest `--notes-file`. |
| extract | Invalid JSON / schema failure | Retry with the error, max 2. Then stop. |
| extract | Unknown entity name | Fuzzy-match against `entities()`. No match → drop the change, add a warning. |
| extract | `source_quote` not in `raw.md` | Drop the change, add a warning. |
| extract | Low coverage | Count `⇒` lines in `raw.md`. If extracted changes < 80% of that count, add a warning. |
| baseline | Scraper fails | Use `stats.csv`. If missing, stop and print the expected CSV path and columns. |
| baseline | Entity has no stats | Stats fields `null`. Card shows "no stats". |
| baseline | No earlier `changes.json` | `history` is empty. Not an error. |
| analyze | Bad `change_ref` or a changed entity missing from the report | Retry, max 2. Then write the report with a warning. |
| any | Ollama not reachable | Stop. Print `ollama serve`. |
| any | Claude selected but no API key | Stop. Print the missing variable name. |

The eval loop later compares each report's verdicts with the **next** patch's
`baseline.json`. No extra data needs to be saved for that.

## 7. Testing

1. **Unit tests (pytest).** Models, adapter parsing, each stage's input and output,
   atomic write, fuzzy matching, CLI wiring. Use `FakeLLM` and saved HTML fixtures.
   No network, no model.
2. **Extraction eval.** `metashift eval extract --game lol --llm <name>` runs stage 2
   on the 3 golden patches in `tests/golden/lol/` and scores (entity, stat, direction)
   triples. Targets: recall ≥ 90%, precision ≥ 95%. Golden labels are drafted by Claude
   and reviewed by the author. The eval is a command, not part of the default test run.
3. **Report rule checks.** Run inside stage 4 and as tests: every changed entity
   appears in the report; every `change_ref` is valid; a `rise` for an entity with only
   nerfs (or a `fall` with only buffs) adds a warning. These check consistency, not
   correctness.
4. **Web tests.** Vitest component tests for the card and board. One Playwright smoke
   test loads a fixture report and checks the three columns render.

## 8. Success criteria for v1

- `metashift run lol <patch>` produces a valid `report.json` for a real recent patch
  with Ollama, using either the scraper or `stats.csv`.
- Extraction eval with Ollama meets the recall and precision targets on the golden set,
  or the gap is measured and written down.
- The web app shows the patch list, the report board and an entity history page for
  at least 3 published patches, and deploys as a static site.
- All unit tests pass with no network access.
