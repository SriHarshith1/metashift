# Metashift

Metashift turns a game patch into a **meta shift report**. It reads the official patch notes, pulls out every buff and nerf as structured data, and says for each changed champion or item whether it rises, falls or stays stable compared with the previous patch.

Version 1 supports **League of Legends** (Summoner's Rift only). The core is game-agnostic, so other games plug in as adapters.

```
metashift/
  pipeline/   Python CLI: fetch → extract → baseline → analyze → publish
  data/       pipeline output, one folder per patch
  web/        static React site that shows the published reports
  docs/       design spec and implementation plan
```

## Setup

You need [uv](https://docs.astral.sh/uv/), Node 20 or newer, and [Ollama](https://ollama.com).

```bash
cd pipeline && uv sync
```

```bash
cd web && npm install
```

## Choose a model

The pipeline calls an LLM through Ollama. Set the model with `METASHIFT_OLLAMA_MODEL`.

- **Ollama Cloud, free plan (default choice for v1):** sign in to Ollama once, then use a `-cloud` model. `gemma4:31b-cloud` meets the eval targets (see `pipeline/EVAL.md`).
- **Local model:** `ollama pull qwen3:14b`. It needs about 15 GB with the default 32k context, so on a 16 GB Mac part of it runs on the CPU and runs are slow.
- **Ollama Cloud API directly:** set `OLLAMA_HOST=https://ollama.com` and `OLLAMA_API_KEY` in your shell.
- **Claude:** pass `--llm claude` and set `ANTHROPIC_API_KEY`. The model comes from `METASHIFT_CLAUDE_MODEL`.

Other settings: `OLLAMA_HOST` (default `http://localhost:11434`), `METASHIFT_OLLAMA_TIMEOUT` (seconds, default 600).

## Run a patch

```bash
cd pipeline && METASHIFT_OLLAMA_MODEL=gemma4:31b-cloud uv run metashift run lol 26.21
```

Run older patches first, so each report has the history of the patches before it.

Useful options:

- `--from-stage NAME` / `--to-stage NAME` — run part of the pipeline (`fetch`, `extract`, `baseline`, `analyze`, `publish`). Extract caches each chunk, so a re-run does not call the model again for chunks that already worked.
- `--notes-file page.html` — use a saved patch notes page when the URL does not work.

The pipeline keeps only Summoner's Rift sections of the notes. The fetch warning lists the sections it skipped (Arena, ARAM, and so on).

### Stats

There is no automatic stats source (see `pipeline/metashift/games/lol/STATS.md`). The baseline stage reads the **previous** patch's stats from `data/lol/<patch>/stats.csv`:

```
entity,win_rate,pick_rate,ban_rate,tier
Ahri,49.1%,6.2,3.0,B
```

Empty cells are allowed. A file with names only gives reports that show "no stats" and judge from the changes and patch history alone.

## Measure extraction quality

```bash
cd pipeline && METASHIFT_OLLAMA_MODEL=gemma4:31b-cloud uv run metashift eval extract --game lol
```

This scores the extract stage against the hand-labeled golden set in `pipeline/tests/golden/lol/`. Targets: precision ≥ 0.95, recall ≥ 0.90. Results are in `pipeline/EVAL.md`.

## Tests

```bash
cd pipeline && uv run pytest
```

```bash
cd web && npm test
```

```bash
cd web && npm run e2e
```

The pipeline tests use no network and no model.

## Web app and deploy

```bash
cd web && npm run dev
```

The publish stage writes reports to `web/public/data/`. `npm run build` makes a static site in `web/dist/`. Because `vite.config.ts` uses `base: "./"` and the site uses hash routes, `web/dist/` works on GitHub Pages, Vercel or any static host with no server rules.

Metashift isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
