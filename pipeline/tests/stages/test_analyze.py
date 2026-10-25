import json

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
    RippleDraft,
    StageLog,
    VerdictDraft,
)
from metashift.core.paths import patch_dir
from metashift.core.stages.analyze import run_analyze
from metashift.core.stages.context import StageContext
from tests.conftest import StubAdapter

ENTITIES = {
    "Ahri": "champion",
    "Kai'Sa": "champion",
    "Jhin": "champion",
    "Infinity Edge": "item",
    "Dragon Soul": "system",
}


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


def v(entity, verdict, build_shift=None):
    return VerdictDraft(
        entity=entity,
        verdict=verdict,
        confidence="high",
        reason=f"{entity} reason",
        impact=f"{entity} impact",
        build_shift=build_shift,
    )


def draft_json(*verdicts, headline="Ahri up, Kai'Sa down", ripples=()):
    return AnalysisDraft(
        headline=headline,
        themes=["mid lane", "marksmen"],
        entities=list(verdicts),
        ripples=list(ripples),
    ).model_dump_json()


GOOD = draft_json(v("Ahri", "rise"), v("Kai'Sa", "fall"))
MISSING_KAISA = draft_json(v("Ahri", "rise"))


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


def ctx(llm, adapter=None):
    return StageContext("lol", "26.21", adapter or StubAdapter(entities=ENTITIES), llm)


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
    bad = draft_json(v("Ahri", "rise"), v("Kai'Sa", "fall"), v("Garen", "rise"))
    run_analyze(ctx(FakeLLM([bad])))
    r = read_report()
    assert [e.entity for e in r.entities] == ["Ahri", "Kai'Sa"]
    assert "verdict for unchanged entity Garen dropped" in r.warnings


def test_analyze_adds_consistency_warnings(inputs):
    odd = draft_json(v("Ahri", "rise"), v("Kai'Sa", "rise"))
    run_analyze(ctx(FakeLLM([odd])))
    assert "Kai'Sa: verdict rise but all changes are nerfs" in read_report().warnings


def test_analyze_change_refs_are_code_owned_all_rows_of_the_entity(inputs):
    changes = [
        make_change("Ahri", "buff"),
        make_change("Kai'Sa", "nerf"),
        make_change("Ahri", "nerf", stat="Cooldown"),
    ]
    write_model(
        patch_dir("lol", "26.21") / "changes.json",
        ChangesFile(game="lol", patch="26.21", changes=changes),
    )
    run_analyze(ctx(FakeLLM([GOOD])))
    r = read_report()
    assert [(e.entity, e.change_refs) for e in r.entities] == [("Ahri", [0, 2]), ("Kai'Sa", [1])]


def test_analyze_ignores_change_refs_the_model_still_sends(inputs):
    raw = json.loads(GOOD)
    for e in raw["entities"]:
        e["change_refs"] = [9]
    run_analyze(ctx(FakeLLM([json.dumps(raw)])))
    assert [e.change_refs for e in read_report().entities] == [[0], [1]]


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


def test_analyze_copies_impact_and_build_shift(inputs):
    good = draft_json(
        v("Ahri", "rise", build_shift="AP burst builds gain value."),
        v("Kai'Sa", "fall", build_shift=""),
    )
    run_analyze(ctx(FakeLLM([good])))
    ahri, kaisa = read_report().entities
    assert ahri.impact == "Ahri impact" and ahri.build_shift == "AP burst builds gain value."
    assert kaisa.impact == "Kai'Sa impact" and kaisa.build_shift is None


def test_analyze_prompt_holds_official_descriptions_and_impact_rules(inputs):
    adapter = StubAdapter(
        entities=ENTITIES, details={"Ahri": "Mage\nQ Orb of Deception: Ahri throws her orb."}
    )
    llm = FakeLLM([GOOD])
    run_analyze(ctx(llm, adapter))
    prompt = llm.prompts[0]
    assert "  official description of the changed parts:\n    Mage\n    Q Orb of Deception" in prompt
    assert "impact:" in prompt and "build_shift:" in prompt and "ripples:" in prompt
    assert "Do not invent numbers or abilities" in prompt


class FailingDescribe(StubAdapter):
    def describe(self, patch, entity, targets):
        raise MetashiftError("Data Dragon down")


def test_analyze_continues_without_descriptions(inputs):
    run_analyze(ctx(FakeLLM([GOOD]), FailingDescribe(entities=ENTITIES)))
    r = read_report()
    assert len(r.entities) == 2
    assert "no description for Ahri: Data Dragon down" in r.warnings


def test_analyze_resolves_ripple_entities_and_drops_unknown_names(inputs):
    ripple = RippleDraft(
        title="Crit marksmen lose",
        explanation="Kai'Sa nerfs push players to Jhin.",
        entities=["kaisa", "Jhin", "Jhin", "ADCs", "Dragon Soul", "Infinity Edge"],
    )
    run_analyze(ctx(FakeLLM([draft_json(v("Ahri", "rise"), v("Kai'Sa", "fall"), ripples=[ripple])])))
    r = read_report()
    assert len(r.ripples) == 1
    got = r.ripples[0]
    assert (got.title, got.explanation) == ("Crit marksmen lose", "Kai'Sa nerfs push players to Jhin.")
    assert [(e.entity, e.entity_type, e.icon_url) for e in got.entities] == [
        ("Kai'Sa", "champion", "stub://Kai'Sa.png"),
        ("Jhin", "champion", "stub://Jhin.png"),
        ("Infinity Edge", "item", "stub://Infinity Edge.png"),
    ]
    assert "ripple 'Crit marksmen lose': unknown entity 'ADCs' dropped" in r.warnings
    assert "ripple 'Crit marksmen lose': unknown entity 'Dragon Soul' dropped" in r.warnings
