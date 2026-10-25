from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from metashift.core.models import (
    Change,
    EntityStats,
    EntityVerdict,
    ReportFile,
)
from metashift.core.paths import patch_dir


def make_change(**overrides):
    fields = dict(
        entity="Ahri",
        entity_type="champion",
        target="Passive",
        stat="new effect",
        old=None,
        new="Heals 5%",
        direction="buff",
        source_quote="NEW: Heals 5%",
    )
    fields.update(overrides)
    return Change(**fields)


def test_change_allows_null_old_for_new_mechanic():
    c = make_change()
    assert c.old is None


def test_change_rejects_unknown_direction():
    with pytest.raises(ValidationError):
        make_change(direction="up")


def test_entity_stats_rejects_win_rate_over_100():
    with pytest.raises(ValidationError):
        EntityStats(entity="Ahri", win_rate=149.1, pick_rate=None, ban_rate=None, tier=None)


def test_report_round_trips_through_json():
    r = ReportFile(
        game="lol",
        patch="26.21",
        compared_to="26.20",
        generated_at=datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
        llm="fake",
        headline="Ahri rises",
        themes=["mid lane"],
        entities=[
            EntityVerdict(
                entity="Ahri",
                entity_type="champion",
                verdict="rise",
                confidence="medium",
                previous=None,
                reason="Passive heals",
                change_refs=[0],
            )
        ],
        changes=[make_change()],
        warnings=[],
    )
    assert ReportFile.model_validate_json(r.model_dump_json()) == r


def test_patch_dir_uses_metashift_root(monkeypatch, tmp_path):
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    assert patch_dir("lol", "26.21") == tmp_path / "data" / "lol" / "26.21"
