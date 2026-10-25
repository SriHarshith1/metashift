import time

from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, record_stage, write_model
from metashift.core.models import (
    BaselineEntity,
    BaselineFile,
    Change,
    ChangesFile,
    Direction,
    EntityStats,
    HistoryEntry,
    StageLog,
)
from metashift.core.paths import patch_dir, repo_root
from metashift.core.stages.context import StageContext
from metashift.core.stats_csv import COLUMNS, read_stats_csv
from metashift.core.text import name_key
from metashift.games.base import StatsUnavailable

HISTORY_PATCHES = 5
SUMMARY_PARTS = 3


def _entity_order(changes: list[Change]) -> list[str]:
    seen: dict[str, None] = {}
    for change in changes:
        seen.setdefault(change.entity)
    return list(seen)


def _history_entry(patch: str, changes: list[Change]) -> HistoryEntry:
    directions = {c.direction for c in changes}
    direction: Direction = changes[0].direction if len(directions) == 1 else "adjust"
    parts = [f"{c.target} {c.stat} {c.direction}" for c in changes]
    summary = "; ".join(parts[:SUMMARY_PARTS])
    if len(parts) > SUMMARY_PARTS:
        summary += "; …"
    return HistoryEntry(patch=patch, direction=direction, summary=summary)


def _history(
    ctx: StageContext, older: list[str], entities: list[str]
) -> dict[str, list[HistoryEntry]]:
    history: dict[str, list[HistoryEntry]] = {entity: [] for entity in entities}
    for patch in older[:HISTORY_PATCHES]:
        path = patch_dir(ctx.game, patch) / "changes.json"
        if not path.exists():
            continue
        past = read_model(path, ChangesFile, "extract").changes
        for entity in entities:
            rows = [c for c in past if c.entity == entity]
            if rows:
                history[entity].append(_history_entry(patch, rows))
    return history


def _load_stats(
    ctx: StageContext, previous: str
) -> tuple[list[EntityStats], str, str | None]:
    """Return (rows, source, warning). A missing stats.csv skips stats with one warning."""
    try:
        return ctx.adapter.fetch_stats(previous), "lolalytics", None
    except StatsUnavailable:
        pass
    path = ctx.dir / "stats.csv"
    if not path.exists():
        try:
            shown = path.relative_to(repo_root()).as_posix()
        except ValueError:
            shown = str(path)
        return [], "none", (
            f"no stats for patch {previous}: stats skipped. To add them, create {shown} "
            f"with columns {','.join(COLUMNS)}"
        )
    return read_stats_csv(path), "csv", None


def run_baseline(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    changes = read_model(ctx.dir / "changes.json", ChangesFile, "extract").changes
    patches = ctx.adapter.list_patches()
    if ctx.patch not in patches:
        raise MetashiftError(f"patch {ctx.patch} not found in {ctx.game} patch list")
    index = patches.index(ctx.patch)
    older = patches[index + 1 :]
    entities = _entity_order(changes)
    warnings: list[str] = []
    stats_patch: str | None = older[0] if older else None
    by_key: dict[str, EntityStats] = {}
    stats_source = "none"
    if stats_patch is None:
        warnings.append("no previous patch: stats skipped")
    else:
        rows, stats_source, skipped = _load_stats(ctx, stats_patch)
        if skipped:
            warnings.append(skipped)
        for row in rows:
            by_key.setdefault(name_key(row.entity), row)
    history = _history(ctx, older, entities)
    result: dict[str, BaselineEntity] = {}
    for entity in entities:
        row = by_key.get(name_key(entity))
        if row is None and stats_source != "none":
            warnings.append(f"no stats for {entity}")
        result[entity] = BaselineEntity(
            win_rate=row.win_rate if row else None,
            pick_rate=row.pick_rate if row else None,
            ban_rate=row.ban_rate if row else None,
            tier=row.tier if row else None,
            history=history[entity],
        )
    write_model(
        ctx.dir / "baseline.json",
        BaselineFile(stats_patch=stats_patch, stats_source=stats_source, entities=result),
    )
    log = StageLog(
        stage="baseline",
        llm=None,
        duration_s=time.perf_counter() - started,
        retries=0,
        warnings=warnings,
    )
    record_stage(ctx.game, ctx.patch, log)
    return log
