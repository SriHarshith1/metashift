import hashlib
import sys
import time
from pathlib import Path

from metashift.core.errors import MetashiftError
from metashift.core.io import record_stage, write_model
from metashift.core.llm import complete_with_retry
from metashift.core.models import Change, ChangesFile, ExtractDraft, StageLog
from metashift.core.paths import repo_root
from metashift.core.prompts import extract_prompt
from metashift.core.stages.context import StageContext
from metashift.core.text import (
    count_change_lines,
    resolve_entity,
    split_sections,
    strip_markdown,
)

COVERAGE_RATIO = 0.8
CACHE_DIR = "extract-cache"


def _cache_path(ctx: StageContext, chunk: str) -> Path:
    assert ctx.llm is not None
    digest = hashlib.sha256((ctx.llm.name + chunk).encode("utf-8")).hexdigest()[:16]
    return ctx.dir / CACHE_DIR / f"{digest}.json"


def _cached_draft(path: Path) -> ExtractDraft | None:
    try:
        return ExtractDraft.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # missing or broken: ask the model again
        return None


def _read_raw(ctx: StageContext) -> str:
    path = ctx.dir / "raw.md"
    if not path.exists():
        try:
            shown = path.relative_to(repo_root()).as_posix()
        except ValueError:
            shown = str(path)
        raise MetashiftError(f"missing {shown} — run stage 'fetch' first")
    return path.read_text(encoding="utf-8")


def run_extract(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    raw = _read_raw(ctx)
    if ctx.llm is None:
        raise MetashiftError("stage 'extract' needs an LLM. Choose one with --llm")
    known = ctx.adapter.entities(ctx.patch)
    raw_plain = strip_markdown(raw)
    warnings: list[str] = []
    changes: list[Change] = []
    total_retries = 0
    chunks = split_sections(raw)
    for number, chunk in enumerate(chunks, start=1):
        cache = _cache_path(ctx, chunk)
        draft = _cached_draft(cache)
        if draft is not None:
            print(f"extract chunk {number}/{len(chunks)} (cached)", file=sys.stderr, flush=True)
        else:
            print(f"extract chunk {number}/{len(chunks)}", file=sys.stderr, flush=True)
            prompt = extract_prompt(chunk, ctx.adapter.glossary, ctx.adapter.entity_types)
            draft, retries, _ = complete_with_retry(ctx.llm, prompt, ExtractDraft)
            total_retries += retries
            write_model(cache, draft)
        for change in draft.changes:
            if change.entity_type != "system":
                resolved = resolve_entity(change.entity, known)
                if resolved is None:
                    warnings.append(f"unknown entity '{change.entity}' dropped")
                    continue
                change = change.model_copy(
                    update={"entity": resolved, "entity_type": known[resolved]}
                )
            if strip_markdown(change.source_quote) not in raw_plain:
                warnings.append(
                    f"quote not found in notes, dropped: {change.entity} {change.stat}"
                )
                continue
            changes.append(change)
    expected = count_change_lines(raw)
    if len(changes) < COVERAGE_RATIO * expected:
        warnings.append(f"low coverage: extracted {len(changes)} of ~{expected} change lines")
    write_model(
        ctx.dir / "changes.json",
        ChangesFile(game=ctx.game, patch=ctx.patch, changes=changes),
    )
    log = StageLog(
        stage="extract",
        llm=ctx.llm.name,
        duration_s=time.perf_counter() - started,
        retries=total_retries,
        warnings=warnings,
    )
    record_stage(ctx.game, ctx.patch, log)
    return log
