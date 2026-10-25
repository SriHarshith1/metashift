import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, read_run_log, record_stage, write_model
from metashift.core.llm import FakeLLM
from metashift.core.models import (
    AnalysisDraft,
    BaselineEntity,
    BaselineFile,
    Change,
    ChangesFile,
    HistoryEntry,
    ReportFile,
    StageLog,
    VerdictDraft,
)
from metashift.core.paths import patch_dir
from metashift.core.stages.analyze import run_analyze
from metashift.core.stages.context import StageContext
from tests.conftest import StubAdapter

ENTITIES = {"Ahri": "champion", "Kai'Sa": "champion"}


def make_change(entity, direction, stat="Damage"):
    return Change(
        entity=entity,
        entity_type="champion",
        target="Q",
        stat=stat,
        old="40",
        new="50",
        direction=direction,
        source_quote=f"{entity} Q {stat}: 40 ⇒ 50",
    )


CHANGES = [make_change("Ahri", "buff"), make_change("Kai'Sa", "nerf")]


def v(entity, verdict, refs):
    return VerdictDraft(
        entity=entity, verdict=verdict, confidence="high", reason=f"{entity} reason", change_refs=refs
    )


def draft_json(*verdicts, headline="Ahri up, Kai'Sa down"):
    return AnalysisDraft(
        headline=headline, themes=["mid lane", "marksmen"], entities=list(verdicts)
    ).model_dump_json()


GOOD = draft_json(v("Ahri", "rise", [0]), v("Kai'Sa", "fall", [1]))
MISSING_KAISA = draft_json(v("Ahri", "rise", [0]))


@pytest.fixture
def inputs(root):
    write_model(
        patch_dir("lol", "26.21") / "changes.json",
        ChangesFile(game="lol", patch="26.21", changes=CHANGES),
    )
    write_model(
        patch_dir("lol", "26.21") / "baseline.json",
        BaselineFile(
            stats_patch="26.20",
            stats_source="csv",
            entities={
                "Ahri": BaselineEntity(
                    win_rate=49.1,
                    pick_rate=6.2,
                    ban_rate=3.0,
                    tier=None,
                    history=[HistoryEntry(patch="26.19", direction="nerf", summary="Q Damage nerf")],
                ),
                "Kai'Sa": BaselineEntity(win_rate=None, pick_rate=None, ban_rate=None, tier=None),
            },
        ),
    )
    return root


def ctx(llm):
    return StageContext("lol", "26.21", StubAdapter(entities=ENTITIES), llm)


def read_report() -> ReportFile:
    return read_model(patch_dir("lol", "26.21") / "report.json", ReportFile, "analyze")


def test_analyze_assembles_report_with_code_owned_fields(inputs):
    llm = FakeLLM([GOOD])
    log = run_analyze(ctx(llm))
    r = read_report()
    assert r.compared_to == "26.20"
    assert r.headline == "Ahri up, Kai'Sa down" and r.themes == ["mid lane", "marksmen"]
    assert r.entities[0].previous.win_rate == 49.1  # from baseline, not LLM
    assert r.entities[0].icon_url == "stub://Ahri.png"
    assert r.entities[0].entity_type == "champion"
    assert r.entities[1].previous is None  # all stat fields null
    assert r.changes == CHANGES and r.llm == "fake"
    assert r.generated_at.tzinfo is not None
    assert r.warnings == [] and log.warnings == []
    assert log.stage == "analyze" and log.llm == "fake" and log.retries == 0
    assert read_run_log("lol", "26.21").stages[-1] == log


def test_analyze_prompt_lists_numbered_changes_stats_and_history(inputs):
    llm = FakeLLM([GOOD])
    run_analyze(ctx(llm))
    prompt = llm.prompts[0]
    assert "[0] Ahri" in prompt and "[1] Kai'Sa" in prompt
    assert "win rate 49.1%" in prompt
    assert "26.19: nerf (Q Damage nerf)" in prompt
    assert "near-50% win rate" in prompt and "stable" in prompt


def test_analyze_retries_then_writes_with_warning(inputs):
    llm = FakeLLM([MISSING_KAISA] * 3)
    log = run_analyze(ctx(llm))
    assert log.retries == 2
    assert "missing verdict for Kai'Sa" in read_report().warnings
    assert "missing verdict for Kai'Sa" in log.warnings
    assert len(llm.prompts) == 3


def test_analyze_retry_can_fix_the_draft(inputs):
    llm = FakeLLM([MISSING_KAISA, GOOD])
    log = run_analyze(ctx(llm))
    assert log.retries == 1 and read_report().warnings == []


def test_analyze_carries_earlier_stage_warnings(inputs):
    record_stage(
        "lol",
        "26.21",
        StageLog(stage="extract", llm="fake", duration_s=1, retries=0, warnings=["low coverage"]),
    )
    run_analyze(ctx(FakeLLM([GOOD])))
    assert read_report().warnings == ["low coverage"]


def test_analyze_rerun_does_not_duplicate_its_own_warnings(inputs):
    run_analyze(ctx(FakeLLM([MISSING_KAISA] * 3)))
    run_analyze(ctx(FakeLLM([MISSING_KAISA] * 3)))
    assert read_report().warnings.count("missing verdict for Kai'Sa") == 1


def test_analyze_drops_verdicts_for_unchanged_entities(inputs):
    bad = draft_json(v("Ahri", "rise", [0]), v("Kai'Sa", "fall", [1]), v("Garen", "rise", [0]))
    run_analyze(ctx(FakeLLM([bad])))
    r = read_report()
    assert [e.entity for e in r.entities] == ["Ahri", "Kai'Sa"]
    assert "verdict for unchanged entity Garen dropped" in r.warnings


def test_analyze_adds_consistency_warnings_and_drops_bad_refs(inputs):
    odd = draft_json(v("Ahri", "rise", [0, 7]), v("Kai'Sa", "rise", [1]))
    run_analyze(ctx(FakeLLM([odd] * 3)))
    r = read_report()
    assert "Kai'Sa: verdict rise but all changes are nerfs" in r.warnings
    assert "Ahri: change_ref 7 out of range" in r.warnings
    assert r.entities[0].change_refs == [0]


def test_analyze_without_extract_or_baseline_names_the_stage(root):
    with pytest.raises(MetashiftError, match="run stage 'extract' first"):
        run_analyze(ctx(FakeLLM([])))
    write_model(
        patch_dir("lol", "26.21") / "changes.json",
        ChangesFile(game="lol", patch="26.21", changes=CHANGES),
    )
    with pytest.raises(MetashiftError, match="run stage 'baseline' first"):
        run_analyze(ctx(FakeLLM([])))


def test_analyze_requires_an_llm(inputs):
    with pytest.raises(MetashiftError, match="needs an LLM"):
        run_analyze(ctx(None))
