import json
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from metashift.core.errors import MetashiftError
from metashift.core.io import write_text
from metashift.core.llm import LLM, make_llm
from metashift.core.models import IndexFile, ReportFile, StageLog
from metashift.core.paths import repo_root, web_data_dir
from metashift.core.stages.analyze import run_analyze
from metashift.core.stages.baseline import run_baseline
from metashift.core.stages.context import StageContext
from metashift.core.stages.extract import run_extract
from metashift.core.stages.fetch import run_fetch
from metashift.core.stages.publish import run_publish
from metashift.games import get_adapter

STAGES = ["fetch", "extract", "baseline", "analyze", "publish"]
LLM_STAGES = {"extract", "analyze"}
RUNNERS: dict[str, Callable[[StageContext], StageLog]] = {
    "fetch": run_fetch,
    "extract": run_extract,
    "baseline": run_baseline,
    "analyze": run_analyze,
    "publish": run_publish,
}

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Metashift pipeline")


class LlmKind(str, Enum):
    ollama = "ollama"
    claude = "claude"


def run_pipeline(
    ctx: StageContext,
    from_stage: str = "fetch",
    to_stage: str = "publish",
    on_done: Callable[[StageLog], None] | None = None,
) -> list[StageLog]:
    """Run the stages from `from_stage` to `to_stage`. The stages record themselves."""
    first, last = STAGES.index(from_stage), STAGES.index(to_stage)
    logs: list[StageLog] = []
    for name in STAGES[first : last + 1]:
        log = RUNNERS[name](ctx)
        logs.append(log)
        if on_done is not None:
            on_done(log)
    return logs


def _usage_error(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(2)


def _check_stage(option: str, value: str) -> None:
    if value not in STAGES:
        raise _usage_error(
            f"unknown stage '{value}' for {option}. Valid stages: {', '.join(STAGES)}"
        )


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else plural or word + 's'}"


def _line(log: StageLog) -> str:
    parts = [f"✓ {log.stage}  {log.duration_s:.1f}s"]
    if log.retries:
        parts.append(_plural(log.retries, "retry", "retries"))
    if log.warnings:
        parts.append(_plural(len(log.warnings), "warning"))
    return "  ".join(parts)


def _shown(path: Path) -> str:
    try:
        return path.relative_to(repo_root()).as_posix()
    except ValueError:
        return str(path)


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


@app.command()
def run(
    game: str,
    patch: str,
    llm: Annotated[
        LlmKind, typer.Option("--llm", help="Model for extract and analyze")
    ] = LlmKind.ollama,
    notes_file: Annotated[
        Path | None, typer.Option("--notes-file", help="Saved patch notes HTML")
    ] = None,
    from_stage: Annotated[
        str, typer.Option("--from-stage", help=f"One of: {', '.join(STAGES)}")
    ] = "fetch",
    to_stage: Annotated[
        str, typer.Option("--to-stage", help=f"One of: {', '.join(STAGES)}")
    ] = "publish",
) -> None:
    """Run the pipeline for one GAME and PATCH."""
    _check_stage("--from-stage", from_stage)
    _check_stage("--to-stage", to_stage)
    if STAGES.index(from_stage) > STAGES.index(to_stage):
        raise _usage_error(f"--from-stage {from_stage} comes after --to-stage {to_stage}")
    stages = STAGES[STAGES.index(from_stage) : STAGES.index(to_stage) + 1]
    try:
        adapter = get_adapter(game)
        model: LLM | None = make_llm(llm.value) if LLM_STAGES & set(stages) else None
        ctx = StageContext(game, patch, adapter, model, notes_file=notes_file)
        logs = run_pipeline(ctx, from_stage, to_stage, on_done=lambda log: typer.echo(_line(log)))
    except MetashiftError as err:
        raise _fail(str(err)) from err
    except ValidationError as err:
        raise _fail(f"invalid data file: {err}") from err
    warnings = [w for log in logs for w in log.warnings]
    if warnings:
        typer.echo("warnings:")
        for w in warnings:
            typer.echo(f"  - {w}")
    if "publish" in stages:
        typer.echo(f"report: {_shown(web_data_dir() / game / f'{patch}.json')}")
    elif "analyze" in stages:
        typer.echo(f"report: {_shown(ctx.dir / 'report.json')}")


@app.command()
def schema(out_dir: Path) -> None:
    """Write the JSON schemas of the report and index files to OUT_DIR."""
    try:
        for name, model in (("ReportFile", ReportFile), ("IndexFile", IndexFile)):
            path = out_dir / f"{name}.schema.json"
            write_text(path, json.dumps(model.model_json_schema(), indent=2) + "\n")
            typer.echo(f"wrote {path}")
    except OSError as err:
        raise _fail(f"cannot write schema: {err}") from err


if __name__ == "__main__":
    app()
