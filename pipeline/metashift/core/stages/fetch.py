import time

from metashift.core.errors import MetashiftError
from metashift.core.io import record_stage, write_text
from metashift.core.models import StageLog
from metashift.core.stages.context import StageContext


def run_fetch(ctx: StageContext) -> StageLog:
    started = time.perf_counter()
    warnings: list[str] = []
    if ctx.notes_file is not None:
        try:
            html = ctx.notes_file.read_text(encoding="utf-8")
        except FileNotFoundError as err:
            raise MetashiftError(f"notes file not found: {ctx.notes_file}") from err
        except (OSError, UnicodeDecodeError) as err:
            raise MetashiftError(f"cannot read notes file {ctx.notes_file}: {err}") from err
    else:
        html = ctx.adapter.fetch_notes(ctx.patch)
    markdown = ctx.adapter.notes_to_markdown(html)
    write_text(ctx.dir / "raw.md", markdown)
    published = ctx.adapter.patch_date(html)
    if published is None:
        warnings.append("publish date not found in patch notes")
    log = StageLog(
        stage="fetch",
        llm=None,
        duration_s=time.perf_counter() - started,
        retries=0,
        warnings=warnings,
    )
    record_stage(ctx.game, ctx.patch, log, patch_date=published)
    return log
