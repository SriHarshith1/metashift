import json
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from metashift.core.errors import MetashiftError
from metashift.core.evaluate import EvalScore, score_extraction
from metashift.core.io import write_text
from metashift.core.llm import LLM, make_llm
from metashift.core.models import ChangesFile, IndexFile, ReportFile, StageLog
from metashift.core.paths import repo_root, web_data_dir
from metashift.core.stages.analyze import run_analyze
from metashift.core.stages.baseline import run_baseline
from metashift.core.stages.context import StageContext
from metashift.core.stages.extract import extract_changes, run_extract
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
eval_app = typer.Typer(no_args_is_help=True, help="Measure pipeline quality")
app.add_typer(eval_app, name="eval")

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "golden"
TARGET_PRECISION = 0.95
TARGET_RECALL = 0.90


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


def _score_row(label: str, score: EvalScore) -> str:
    return (
        f"{label:<8} {score.precision:>5.2f} {score.recall:>5.2f}"
        f" {score.tp:>4} {score.fp:>4} {score.fn:>4}"
    )


@eval_app.command("extract")
def eval_extract(
    game: Annotated[str, typer.Option("--game", help="Game of the golden set")] = "lol",
    llm: Annotated[
        LlmKind, typer.Option("--llm", help="Model to measure")
    ] = LlmKind.ollama,
    golden_dir: Annotated[
        Path, typer.Option("--golden-dir", help="Folder with <game>/<patch>/ golden files")
    ] = GOLDEN_DIR,
) -> None:
    """Score the extract stage against the hand-labeled golden patches."""
    patch_dirs = sorted(
        (d for d in (golden_dir / game).glob("*") if (d / "changes.json").exists()),
        key=lambda d: tuple(int(p) for p in d.name.split(".")),
    )
    try:
        if not patch_dirs:
            raise MetashiftError(f"no golden patches in {golden_dir / game}")
        adapter = get_adapter(game)
        model = make_llm(llm.value)
        typer.echo(f"model: {model.name}")
        typer.echo(f"{'patch':<8} {'P':>5} {'R':>5} {'tp':>4} {'fp':>4} {'fn':>4}")
        total = EvalScore(0, 0, 0)
        for d in patch_dirs:
            gold = ChangesFile.model_validate_json((d / "changes.json").read_text("utf-8"))
            raw = (d / "raw.md").read_text("utf-8")
            predicted, _, _ = extract_changes(raw, adapter, d.name, model)
            score = score_extraction(predicted, gold.changes)
            total = total + score
            typer.echo(_score_row(d.name, score))
    except MetashiftError as err:
        raise _fail(str(err)) from err
    except (OSError, ValidationError) as err:
        raise _fail(f"cannot read golden set: {err}") from err
    typer.echo(_score_row("total", total))
    misses = []
    if total.recall < TARGET_RECALL:
        misses.append(f"recall {total.recall:.2f} < {TARGET_RECALL:.2f}")
    if total.precision < TARGET_PRECISION:
        misses.append(f"precision {total.precision:.2f} < {TARGET_PRECISION:.2f}")
    typer.echo(f"below target: {', '.join(misses)}" if misses else "targets met")


if __name__ == "__main__":
    app()
