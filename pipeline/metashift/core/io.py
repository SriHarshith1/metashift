import os
import tempfile
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from metashift.core.errors import MetashiftError
from metashift.core.models import RunLog, StageLog
from metashift.core.paths import patch_dir, repo_root

T = TypeVar("T", bound=BaseModel)

RUN_LOG_NAME = "run.log.json"


def _atomic_write(path: Path, text: str, validate: type[BaseModel] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    tmp_path = Path(tmp.name)
    try:
        with tmp:
            tmp.write(text)
        if validate is not None:
            validate.model_validate_json(tmp_path.read_text(encoding="utf-8"))
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_model(path: Path, model: BaseModel) -> None:
    text = model.model_dump_json(indent=2, warnings="error")
    _atomic_write(path, text, validate=type(model))


def write_text(path: Path, text: str) -> None:
    _atomic_write(path, text)


def _relative(path: Path) -> str:
    try:
        return path.relative_to(repo_root()).as_posix()
    except ValueError:
        return str(path)


def read_model(path: Path, cls: type[T], produced_by: str) -> T:
    if not path.exists():
        raise MetashiftError(f"missing {_relative(path)} — run stage '{produced_by}' first")
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def _run_log_path(game: str, patch: str) -> Path:
    return patch_dir(game, patch) / RUN_LOG_NAME


def read_run_log(game: str, patch: str) -> RunLog:
    path = _run_log_path(game, patch)
    if not path.exists():
        return RunLog(game=game, patch=patch)
    return RunLog.model_validate_json(path.read_text(encoding="utf-8"))


def record_stage(
    game: str, patch: str, log: StageLog, patch_date: date | None = None
) -> None:
    run_log = read_run_log(game, patch)
    stages = list(run_log.stages)
    for i, existing in enumerate(stages):
        if existing.stage == log.stage:
            stages[i] = log
            break
    else:
        stages.append(log)
    run_log.stages = stages
    if patch_date is not None:
        run_log.patch_date = patch_date
    write_model(_run_log_path(game, patch), run_log)


def stage_warnings(game: str, patch: str) -> list[str]:
    return [w for s in read_run_log(game, patch).stages for w in s.warnings]
