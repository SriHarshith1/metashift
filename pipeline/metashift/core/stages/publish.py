import time

from pydantic import ValidationError

from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, read_run_log, record_stage, write_model
from metashift.core.models import IndexEntry, IndexFile, ReportFile, StageLog
from metashift.core.paths import repo_root, web_data_dir
from metashift.core.stages.context import StageContext
from metashift.core.text import patch_sort_key


def _shown(path) -> str:
    try:
        return path.relative_to(repo_root()).as_posix()
    except ValueError:
        return str(path)


def _build_index() -> IndexFile:
    games: dict[str, list[IndexEntry]] = {}
    for path in sorted(web_data_dir().glob("*/*.json")):
        try:
            report = ReportFile.model_validate_json(path.read_text(encoding="utf-8"))
            patch_sort_key(report.patch)  # a patch id that is not numeric is an error
        except (ValidationError, ValueError) as err:
            raise MetashiftError(f"cannot read published report {_shown(path)}: {err}") from err
        games.setdefault(report.game, []).append(
            IndexEntry(
                patch=report.patch,
                patch_date=read_run_log(report.game, report.patch).patch_date,
                headline=report.headline,
                buffs=sum(1 for c in report.changes if c.direction == "buff"),
                nerfs=sum(1 for c in report.changes if c.direction == "nerf"),
                llm=report.llm,
            )
        )
    for entries in games.values():
        entries.sort(key=lambda e: patch_sort_key(e.patch), reverse=True)
    return IndexFile(games=games)


def run_publish(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    report = read_model(ctx.dir / "report.json", ReportFile, "analyze")
    write_model(web_data_dir() / ctx.game / f"{ctx.patch}.json", report)
    write_model(web_data_dir() / "index.json", _build_index())
    log = StageLog(
        stage="publish",
        llm=None,
        duration_s=time.perf_counter() - started,
        retries=0,
        warnings=[],
    )
    record_stage(ctx.game, ctx.patch, log)
    return log
