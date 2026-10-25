import json

import pytest
from typer.testing import CliRunner

import metashift.cli as cli
from metashift.cli import STAGES, app
from metashift.core.errors import MetashiftError
from metashift.core.io import read_run_log
from metashift.core.llm import FakeLLM
from metashift.core.models import (
    AnalysisDraft,
    Change,
    EntityStats,
    ExtractDraft,
    IndexFile,
    ReportFile,
    VerdictDraft,
)
from metashift.core.stages.context import StageContext
from tests.conftest import StubAdapter

runner = CliRunner()

NOTES = "## Champions\n\n#### Ahri\n\n* Q Damage: 40 ⇒ 50\n"
CHANGE = Change(
    entity="Ahri",
    entity_type="champion",
    target="Q",
    stat="Damage",
    old="40",
    new="50",
    direction="buff",
    source_quote="Q Damage: 40 ⇒ 50",
)
EXTRACT_JSON = ExtractDraft(changes=[CHANGE]).model_dump_json()
ANALYZE_JSON = AnalysisDraft(
    headline="Ahri rises",
    themes=["mid lane"],
    entities=[
        VerdictDraft(
            entity="Ahri", verdict="rise", confidence="high", reason="buff"
        )
    ],
).model_dump_json()
STATS = [EntityStats(entity="Ahri", win_rate=49.1, pick_rate=6.2, ban_rate=3.0, tier=None)]


@pytest.fixture
def stubs(root, monkeypatch):
    """Patch get_adapter and make_llm; return the list of make_llm calls."""
    made: list[str] = []
    llms: list[FakeLLM] = []

    def fake_make_llm(kind):
        made.append(kind)
        llm = FakeLLM([EXTRACT_JSON, ANALYZE_JSON])
        llms.append(llm)
        return llm

    adapter = StubAdapter(
        patches=["26.21", "26.20"],
        entities={"Ahri": "champion"},
        notes_md=NOTES,
        stats=STATS,
    )
    monkeypatch.setattr(cli, "get_adapter", lambda game: adapter)
    monkeypatch.setattr(cli, "make_llm", fake_make_llm)
    return made


def test_run_all_stages_writes_report_and_index(root, stubs):
    result = runner.invoke(app, ["run", "lol", "26.21"])
    assert result.exit_code == 0, result.output
    assert (root / "data/lol/26.21/report.json").exists()
    index = IndexFile.model_validate_json((root / "web/public/data/index.json").read_text())
    assert [e.patch for e in index.games["lol"]] == ["26.21"]
    assert [s.stage for s in read_run_log("lol", "26.21").stages] == STAGES
    assert stubs == ["ollama"]
    for stage in STAGES:
        assert f"✓ {stage}" in result.stdout
    assert "web/public/data/lol/26.21.json" in result.stdout


def test_run_prints_retries_and_warnings(root, stubs, monkeypatch):
    bad = AnalysisDraft(headline="h", themes=[], entities=[]).model_dump_json()
    monkeypatch.setattr(
        cli, "make_llm", lambda kind: FakeLLM([EXTRACT_JSON, bad, bad, bad], name="fake")
    )
    result = runner.invoke(app, ["run", "lol", "26.21", "--llm", "claude"])
    assert result.exit_code == 0, result.output
    assert "✓ analyze" in result.stdout and "2 retries" in result.stdout
    assert "1 warning" in result.stdout
    assert "missing verdict for Ahri" in result.stdout


def test_run_passes_llm_choice(root, stubs):
    result = runner.invoke(app, ["run", "lol", "26.21", "--llm", "claude", "--to-stage", "extract"])
    assert result.exit_code == 0, result.output
    assert stubs == ["claude"]


def test_from_stage_with_missing_input_prints_clean_error(root, stubs):
    result = runner.invoke(app, ["run", "lol", "26.21", "--from-stage", "analyze"])
    assert result.exit_code == 1
    assert "error: missing data/lol/26.21/changes.json — run stage 'extract' first" in result.stderr
    assert "Traceback" not in result.output
    assert "Traceback" not in result.stderr


def test_from_stage_publish_does_not_create_llm(root, stubs, monkeypatch):
    assert runner.invoke(app, ["run", "lol", "26.21"]).exit_code == 0

    def boom(kind):
        raise AssertionError("LLM must not be created")

    monkeypatch.setattr(cli, "make_llm", boom)
    result = runner.invoke(app, ["run", "lol", "26.21", "--from-stage", "publish"])
    assert result.exit_code == 0, result.output
    assert "✓ publish" in result.stdout and "✓ extract" not in result.stdout


def test_from_stage_baseline_does_not_create_llm(root, stubs, monkeypatch):
    assert runner.invoke(app, ["run", "lol", "26.21", "--to-stage", "extract"]).exit_code == 0
    monkeypatch.setattr(cli, "make_llm", lambda kind: pytest.fail("no LLM expected"))
    result = runner.invoke(
        app, ["run", "lol", "26.21", "--from-stage", "baseline", "--to-stage", "baseline"]
    )
    assert result.exit_code == 0, result.output


def test_llm_setup_failure_is_a_clean_error(root, stubs, monkeypatch):
    def no_key(kind):
        raise MetashiftError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(cli, "make_llm", no_key)
    result = runner.invoke(app, ["run", "lol", "26.21", "--llm", "claude"])
    assert result.exit_code == 1
    assert "error: ANTHROPIC_API_KEY is not set" in result.stderr


@pytest.mark.parametrize("option", ["--from-stage", "--to-stage"])
def test_unknown_stage_lists_valid_stages(root, stubs, option):
    result = runner.invoke(app, ["run", "lol", "26.21", option, "nope"])
    assert result.exit_code == 2
    assert "fetch, extract, baseline, analyze, publish" in result.stderr
    assert "'nope'" in result.stderr


def test_from_stage_after_to_stage_is_a_usage_error(root, stubs):
    result = runner.invoke(
        app, ["run", "lol", "26.21", "--from-stage", "publish", "--to-stage", "fetch"]
    )
    assert result.exit_code == 2
    assert "--from-stage" in result.stderr


def test_to_stage_extract_stops_before_baseline(root, stubs):
    result = runner.invoke(app, ["run", "lol", "26.21", "--to-stage", "extract"])
    assert result.exit_code == 0, result.output
    assert (root / "data/lol/26.21/changes.json").exists()
    assert not (root / "data/lol/26.21/baseline.json").exists()
    assert [s.stage for s in read_run_log("lol", "26.21").stages] == ["fetch", "extract"]


def test_unknown_game_is_a_clean_error(root):
    result = runner.invoke(app, ["run", "dota", "1.0", "--from-stage", "publish"])
    assert result.exit_code == 1
    assert "error: unknown game 'dota'" in result.stderr


def test_run_pipeline_runs_only_the_requested_range(root, monkeypatch):
    calls: list[str] = []
    ctx = StageContext("lol", "26.21", StubAdapter(), None)
    for name in STAGES:
        monkeypatch.setitem(cli.RUNNERS, name, lambda c, n=name: calls.append(n) or n)
    result = cli.run_pipeline(ctx, "extract", "baseline")
    assert calls == ["extract", "baseline"] and result == ["extract", "baseline"]


def test_schema_writes_both_files(tmp_path):
    out = tmp_path / "schemas"
    result = runner.invoke(app, ["schema", str(out)])
    assert result.exit_code == 0, result.output
    report = json.loads((out / "ReportFile.schema.json").read_text(encoding="utf-8"))
    index = json.loads((out / "IndexFile.schema.json").read_text(encoding="utf-8"))
    assert report == ReportFile.model_json_schema()
    assert index == IndexFile.model_json_schema()


def write_golden(base, patch, changes):
    from metashift.core.models import ChangesFile

    d = base / "lol" / patch
    d.mkdir(parents=True)
    (d / "raw.md").write_text(NOTES, encoding="utf-8")
    (d / "changes.json").write_text(
        ChangesFile(game="lol", patch=patch, changes=changes).model_dump_json(), encoding="utf-8"
    )


def test_eval_extract_prints_scores_and_target_verdict(stubs, tmp_path):
    write_golden(tmp_path / "golden", "26.21", [CHANGE])
    result = runner.invoke(
        app, ["eval", "extract", "--game", "lol", "--golden-dir", str(tmp_path / "golden")]
    )
    assert result.exit_code == 0, result.output
    assert "26.21" in result.output and "total" in result.output
    assert "targets met" in result.output


def test_eval_extract_reports_below_target(stubs, tmp_path, monkeypatch):
    extra = CHANGE.model_copy(update={"stat": "Mana Cost", "source_quote": "Q Damage: 40 ⇒ 50"})
    write_golden(tmp_path / "golden", "26.21", [CHANGE, extra])
    result = runner.invoke(
        app, ["eval", "extract", "--game", "lol", "--golden-dir", str(tmp_path / "golden")]
    )
    assert result.exit_code == 0, result.output
    assert "below target: recall 0.50 < 0.90" in result.output


def test_eval_extract_without_golden_set_fails_cleanly(stubs, tmp_path):
    result = runner.invoke(
        app, ["eval", "extract", "--game", "lol", "--golden-dir", str(tmp_path / "none")]
    )
    assert result.exit_code == 1
    assert "error: no golden patches" in result.stderr
