import time
from datetime import UTC, datetime

from metashift.core.checks import consistency_warnings, retry_problems
from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, read_run_log, record_stage, write_model
from metashift.core.llm import complete_with_retry
from metashift.core.models import (
    AnalysisDraft,
    BaselineFile,
    ChangesFile,
    EntityVerdict,
    PreviousStats,
    ReportFile,
    StageLog,
)
from metashift.core.prompts import analyze_prompt
from metashift.core.stages.context import StageContext

EARLIER_STAGES = ("fetch", "extract", "baseline")


def run_analyze(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    changes = read_model(ctx.dir / "changes.json", ChangesFile, "extract").changes
    baseline = read_model(ctx.dir / "baseline.json", BaselineFile, "baseline")
    if ctx.llm is None:
        raise MetashiftError("stage 'analyze' needs an LLM. Choose one with --llm")
    prompt = analyze_prompt(changes, baseline, ctx.adapter.glossary)
    draft, retries, problems = complete_with_retry(
        ctx.llm,
        prompt,
        AnalysisDraft,
        check=lambda d: retry_problems(d, changes),
    )
    types = {c.entity: c.entity_type for c in changes}
    order = {entity: i for i, entity in enumerate(types)}
    warnings = list(problems)
    kept = []
    seen: set[str] = set()
    for verdict in draft.entities:
        if verdict.entity not in types:
            warnings.append(f"verdict for unchanged entity {verdict.entity} dropped")
        elif verdict.entity in seen:
            warnings.append(f"duplicate verdict for {verdict.entity} dropped")
        else:
            seen.add(verdict.entity)
            kept.append(verdict)
    kept.sort(key=lambda v: order[v.entity])
    warnings.extend(consistency_warnings(draft.model_copy(update={"entities": kept}), changes))
    entities: list[EntityVerdict] = []
    for verdict in kept:
        base = baseline.entities.get(verdict.entity)
        previous = None
        if base is not None and any(
            x is not None for x in (base.win_rate, base.pick_rate, base.ban_rate, base.tier)
        ):
            previous = PreviousStats(
                win_rate=base.win_rate,
                pick_rate=base.pick_rate,
                ban_rate=base.ban_rate,
                tier=base.tier,
            )
        entities.append(
            EntityVerdict(
                entity=verdict.entity,
                entity_type=types[verdict.entity],
                verdict=verdict.verdict,
                confidence=verdict.confidence,
                previous=previous,
                reason=verdict.reason,
                change_refs=[i for i, c in enumerate(changes) if c.entity == verdict.entity],
                icon_url=ctx.adapter.icon_url(ctx.patch, verdict.entity),
            )
        )
    # Only earlier stages: a rerun must not copy the old analyze or publish warnings.
    earlier = [
        w
        for s in read_run_log(ctx.game, ctx.patch).stages
        if s.stage in EARLIER_STAGES
        for w in s.warnings
    ]
    write_model(
        ctx.dir / "report.json",
        ReportFile(
            game=ctx.game,
            patch=ctx.patch,
            compared_to=baseline.stats_patch,
            generated_at=datetime.now(UTC),
            llm=ctx.llm.name,
            headline=draft.headline,
            themes=draft.themes,
            entities=entities,
            changes=changes,
            warnings=earlier + warnings,
        ),
    )
    log = StageLog(
        stage="analyze",
        llm=ctx.llm.name,
        duration_s=time.perf_counter() - started,
        retries=retries,
        warnings=warnings,
    )
    record_stage(ctx.game, ctx.patch, log)
    return log
