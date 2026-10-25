from datetime import UTC, date, datetime

import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import read_run_log, record_stage, write_model, write_text
from metashift.core.models import Change, IndexFile, ReportFile, StageLog
from metashift.core.paths import patch_dir
from metashift.core.stages.context import StageContext
from metashift.core.stages.publish import run_publish
from metashift.core.text import patch_sort_key
from tests.conftest import StubAdapter


def make_change(direction, entity="Ahri"):
    return Change(
        entity=entity,
        entity_type="champion",
        target="Q",
        stat="Damage",
        old="1",
        new="2",
        direction=direction,
        source_quote=f"{entity} Q Damage: 1 ⇒ 2",
    )


def make_report(patch, directions=("buff",)):
    return ReportFile(
        game="lol",
        patch=patch,
        compared_to=None,
        generated_at=datetime(2026, 10, 25, tzinfo=UTC),
        llm="fake",
        headline=f"headline {patch}",
        themes=[],
        entities=[],
        changes=[make_change(d) for d in directions],
        warnings=[],
    )


def publish(patch, directions=("buff",)):
    write_model(patch_dir("lol", patch) / "report.json", make_report(patch, directions))
    return run_publish(StageContext("lol", patch, StubAdapter(), None))


def read_index(root) -> IndexFile:
    return IndexFile.model_validate_json((root / "web/public/data/index.json").read_text())


def test_publish_rebuilds_index_newest_first(root):
    publish("26.9")
    publish("26.21")
    publish("26.10")
    idx = read_index(root)
    assert [e.patch for e in idx.games["lol"]] == ["26.21", "26.10", "26.9"]  # numeric order
    assert (root / "web/public/data/lol/26.10.json").exists()


def test_publish_copies_the_report(root):
    log = publish("26.21")
    copied = ReportFile.model_validate_json(
        (root / "web/public/data/lol/26.21.json").read_text(encoding="utf-8")
    )
    assert copied == make_report("26.21")
    assert log.stage == "publish" and log.llm is None and log.duration_s >= 0
    assert read_run_log("lol", "26.21").stages[-1] == log


def test_publish_counts_buffs_and_nerfs(root):
    publish("26.21", ("buff", "buff", "nerf", "adjust"))
    [entry] = read_index(root).games["lol"]
    assert (entry.buffs, entry.nerfs) == (2, 1)
    assert (entry.headline, entry.llm) == ("headline 26.21", "fake")


def test_publish_reads_patch_date_from_run_log_or_none(root):
    record_stage(
        "lol",
        "26.20",
        StageLog(stage="fetch", llm=None, duration_s=0, retries=0, warnings=[]),
        patch_date=date(2026, 10, 6),
    )
    publish("26.20")
    publish("26.21")  # no run log
    entries = {e.patch: e for e in read_index(root).games["lol"]}
    assert entries["26.20"].patch_date == date(2026, 10, 6)
    assert entries["26.21"].patch_date is None


def test_publish_without_report_names_the_stage(root):
    with pytest.raises(MetashiftError, match="run stage 'analyze' first"):
        run_publish(StageContext("lol", "26.21", StubAdapter(), None))


def test_publish_names_a_broken_report_file(root):
    write_text(root / "web/public/data/lol/26.1.json", "{not json")
    with pytest.raises(MetashiftError, match=r"web/public/data/lol/26.1.json"):
        publish("26.21")


def test_patch_sort_key_is_numeric():
    assert patch_sort_key("26.10") > patch_sort_key("26.9")
    assert patch_sort_key("26.21") == (26, 21)
