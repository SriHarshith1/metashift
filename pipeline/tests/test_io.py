import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import (
    read_model,
    read_run_log,
    record_stage,
    stage_warnings,
    write_model,
    write_text,
)
from metashift.core.models import ChangesFile, StageLog
from metashift.core.paths import patch_dir


def stage(name, warnings):
    return StageLog(stage=name, llm=None, duration_s=1.0, retries=0, warnings=warnings)


def test_failed_write_keeps_previous_file(tmp_path):
    p = tmp_path / "changes.json"
    good = ChangesFile(game="lol", patch="26.21", changes=[])
    write_model(p, good)
    bad = ChangesFile.model_construct(game="lol", patch="26.21", changes="oops")
    with pytest.raises(Exception):
        write_model(p, bad)
    assert ChangesFile.model_validate_json(p.read_text()) == good
    assert list(tmp_path.iterdir()) == [p]  # no temp file left


def test_read_missing_file_names_the_stage(monkeypatch, tmp_path):
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    with pytest.raises(
        MetashiftError, match=r"missing data/lol/26.21/changes.json — run stage 'extract' first"
    ):
        read_model(patch_dir("lol", "26.21") / "changes.json", ChangesFile, "extract")


def test_record_stage_replaces_same_stage(monkeypatch, tmp_path):
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    assert read_run_log("lol", "26.21").stages == []
    assert stage_warnings("lol", "26.21") == []
    record_stage("lol", "26.21", stage("fetch", ["w-fetch"]))
    record_stage("lol", "26.21", stage("extract", ["w-extract-1"]))
    record_stage("lol", "26.21", stage("extract", ["w-extract-2"]))
    log = read_run_log("lol", "26.21")
    assert [s.stage for s in log.stages] == ["fetch", "extract"]
    assert stage_warnings("lol", "26.21") == ["w-fetch", "w-extract-2"]


def test_write_text_is_atomic_and_creates_parents(tmp_path):
    p = tmp_path / "a" / "b" / "note.txt"
    write_text(p, "hello")
    assert p.read_text() == "hello"
    assert list(p.parent.iterdir()) == [p]
