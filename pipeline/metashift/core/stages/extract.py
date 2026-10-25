import hashlib
import sys
import time
from pathlib import Path

from metashift.core.errors import MetashiftError
from metashift.core.io import record_stage, write_model
from metashift.core.llm import LLM, complete_with_retry
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
from metashift.games.base import GameAdapter

COVERAGE_RATIO = 0.8
CACHE_DIR = "extract-cache"


def _cache_path(cache_dir: Path, llm: LLM, chunk: str) -> Path:
    digest = hashlib.sha256((llm.name + chunk).encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.json"


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


def extract_changes(
    raw: str,
    adapter: GameAdapter,
    patch: str,
    llm: LLM,
    cache_dir: Path | None = None,
) -> tuple[list[Change], int, list[str]]:
    """Extract validated changes from patch notes markdown. Returns (changes, retries, warnings).

    With `cache_dir`, each chunk's draft is saved there and reused on the next call.
    """
    known = adapter.entities(patch)
    raw_plain = strip_markdown(raw)
    warnings: list[str] = []
    changes: list[Change] = []
    total_retries = 0
    chunks = split_sections(raw)
    for number, chunk in enumerate(chunks, start=1):
        cache = _cache_path(cache_dir, llm, chunk) if cache_dir is not None else None
        draft = _cached_draft(cache) if cache is not None else None
        if draft is not None:
            print(f"extract chunk {number}/{len(chunks)} (cached)", file=sys.stderr, flush=True)
        else:
            print(f"extract chunk {number}/{len(chunks)}", file=sys.stderr, flush=True)
            prompt = extract_prompt(chunk, adapter.glossary, adapter.entity_types)
            draft, retries, _ = complete_with_retry(llm, prompt, ExtractDraft)
            total_retries += retries
            if cache is not None:
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
    return changes, total_retries, warnings


def run_extract(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    raw = _read_raw(ctx)
    if ctx.llm is None:
        raise MetashiftError("stage 'extract' needs an LLM. Choose one with --llm")
    changes, retries, warnings = extract_changes(
        raw, ctx.adapter, ctx.patch, ctx.llm, cache_dir=ctx.dir / CACHE_DIR
    )
    write_model(
        ctx.dir / "changes.json",
        ChangesFile(game=ctx.game, patch=ctx.patch, changes=changes),
    )
    log = StageLog(
        stage="extract",
        llm=ctx.llm.name,
        duration_s=time.perf_counter() - started,
        retries=retries,
        warnings=warnings,
    )
    record_stage(ctx.game, ctx.patch, log)
    return log
