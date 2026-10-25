import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, read_run_log, write_model, write_text
from metashift.core.models import BaselineFile, Change, ChangesFile, EntityStats, HistoryEntry
from metashift.core.paths import patch_dir
from metashift.core.stages.baseline import run_baseline
from metashift.core.stages.context import StageContext
from tests.conftest import StubAdapter

PATCHES = ["26.21", "26.20", "26.19", "26.18", "26.17", "26.16", "26.15", "26.14"]
CSV = "entity,win_rate,pick_rate,ban_rate,tier\nahri, 49.1% ,6.2,3.0,\n"


def change(entity, direction="buff", target="Q", stat="Damage"):
    return Change(
        entity=entity,
        entity_type="champion",
        target=target,
        stat=stat,
        old="1",
        new="2",
        direction=direction,
        source_quote=f"{entity} {target} {stat}: 1 ⇒ 2",
    )


def write_changes(patch, *changes):
    write_model(
        patch_dir("lol", patch) / "changes.json",
        ChangesFile(game="lol", patch=patch, changes=list(changes)),
    )


def ctx(patches=PATCHES, **kw):
    return StageContext("lol", "26.21", StubAdapter(patches=patches, **kw), None)


def read_baseline() -> BaselineFile:
    return read_model(patch_dir("lol", "26.21") / "baseline.json", BaselineFile, "baseline")


def test_baseline_uses_previous_patch_and_csv_fallback(root):
    write_changes("26.21", change("Ahri"))
    write_text(root / "data/lol/26.21/stats.csv", CSV)
    log = run_baseline(ctx(patches=["26.21", "26.20", "26.19"]))
    b = read_baseline()
    assert b.stats_patch == "26.20" and b.stats_source == "csv"
    assert b.entities["Ahri"].win_rate == 49.1
    assert b.entities["Ahri"].tier is None
    assert log.stage == "baseline" and log.llm is None and log.warnings == []
    assert read_run_log("lol", "26.21").stages[-1] == log


def test_baseline_prefers_adapter_stats_when_available(root):
    write_changes("26.21", change("Ahri"))
    rows = [EntityStats(entity="Ahri", win_rate=51.0, pick_rate=5.0, ban_rate=2.0, tier="A")]
    run_baseline(ctx(stats=rows))
    b = read_baseline()
    assert b.stats_source == "lolalytics" and b.entities["Ahri"].win_rate == 51.0


def test_baseline_missing_csv_skips_stats_with_one_warning(root):
    write_changes("26.21", change("Ahri"), change("Kai'Sa"))
    log = run_baseline(ctx())
    b = read_baseline()
    assert b.stats_source == "none"
    assert b.entities["Ahri"].win_rate is None
    assert len(log.warnings) == 1
    assert "no stats for patch 26.20: stats skipped" in log.warnings[0]
    assert "data/lol/26.21/stats.csv" in log.warnings[0]
    assert "entity,win_rate,pick_rate,ban_rate,tier" in log.warnings[0]


def test_baseline_entity_without_a_row_gets_null_stats_and_warning(root):
    write_changes("26.21", change("Ahri"), change("Kai'Sa"))
    write_text(root / "data/lol/26.21/stats.csv", CSV)
    log = run_baseline(ctx())
    b = read_baseline()
    assert b.entities["Kai'Sa"].win_rate is None and b.entities["Kai'Sa"].tier is None
    assert log.warnings == ["no stats for Kai'Sa"]


def test_baseline_matches_csv_rows_by_name_key(root):
    write_changes("26.21", change("Kai'Sa"))
    write_text(
        root / "data/lol/26.21/stats.csv",
        "entity,win_rate,pick_rate,ban_rate,tier\nKAISA,50.5,8,1,S\n",
    )
    run_baseline(ctx())
    assert read_baseline().entities["Kai'Sa"].win_rate == 50.5


def test_baseline_history_last_five_with_mixed_as_adjust(root):
    write_changes("26.21", change("Ahri"))
    write_changes("26.20", change("Ahri", "buff"), change("Ahri", "nerf", target="W", stat="Cooldown"))
    write_changes("26.14", change("Ahri", "nerf"))  # 7 patches back: outside the window
    write_text(root / "data/lol/26.21/stats.csv", CSV)
    run_baseline(ctx())
    b = read_baseline()
    assert b.entities["Ahri"].history == [
        HistoryEntry(
            patch="26.20", direction="adjust", summary="Q Damage buff; W Cooldown nerf"
        )
    ]


def test_baseline_history_shared_direction_summary_cap_and_missing_files(root):
    write_changes("26.21", change("Ahri"))
    write_changes(
        "26.19",
        *[change("Ahri", "nerf", stat=f"S{i}") for i in range(4)],
        change("Kai'Sa", "buff"),
    )
    write_changes("26.17", change("Ahri", "buff"))
    # 26.20 and 26.18 have no changes.json: skipped without a warning
    write_text(root / "data/lol/26.21/stats.csv", CSV)
    log = run_baseline(ctx())
    history = read_baseline().entities["Ahri"].history
    assert [h.patch for h in history] == ["26.19", "26.17"]
    assert history[0].direction == "nerf"
    assert history[0].summary == "Q S0 nerf; Q S1 nerf; Q S2 nerf; …"
    assert history[1] == HistoryEntry(patch="26.17", direction="buff", summary="Q Damage buff")
    assert log.warnings == []


def test_baseline_first_patch_has_no_stats(root):
    write_changes("26.21", change("Ahri"))
    log = run_baseline(ctx(patches=["26.21"]))
    b = read_baseline()
    assert b.stats_patch is None and b.entities["Ahri"].win_rate is None
    assert log.warnings == ["no previous patch: stats skipped"]


def test_baseline_unknown_patch_fails_clearly(root):
    write_changes("26.21", change("Ahri"))
    with pytest.raises(MetashiftError, match="patch 26.21 not found in lol patch list"):
        run_baseline(ctx(patches=["26.20"]))


def test_baseline_without_changes_names_the_stage(root):
    with pytest.raises(MetashiftError, match="run stage 'extract' first"):
        run_baseline(ctx())
