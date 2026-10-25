from metashift.core.checks import consistency_warnings, retry_problems
from metashift.core.models import AnalysisDraft, Change, VerdictDraft


def make_change(entity, direction):
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


ahri_buff = make_change("Ahri", "buff")
kaisa_nerf = make_change("Kai'Sa", "nerf")


def v(entity, verdict="stable"):
    return VerdictDraft(entity=entity, verdict=verdict, confidence="medium", reason="r", impact="i")


def draft(*verdicts):
    return AnalysisDraft(headline="h", themes=[], entities=list(verdicts), ripples=[])


def test_retry_problems_finds_missing_verdicts():
    probs = retry_problems(draft(v("Ahri")), [ahri_buff, kaisa_nerf])
    assert probs == ["missing verdict for Kai'Sa"]


def test_retry_problems_is_empty_for_a_complete_draft():
    d = draft(v("Ahri"), v("Kai'Sa"))
    assert retry_problems(d, [ahri_buff, kaisa_nerf]) == []


def test_retry_problems_ignores_verdicts_for_unchanged_entities():
    d = draft(v("Ahri"), v("Garen"))
    assert retry_problems(d, [ahri_buff]) == []


def test_consistency_flags_rise_with_only_nerfs():
    d = draft(v("Kai'Sa", "rise"), v("Ahri", "rise"))
    assert consistency_warnings(d, [ahri_buff, kaisa_nerf]) == [
        "Kai'Sa: verdict rise but all changes are nerfs"
    ]


def test_consistency_flags_fall_with_only_buffs():
    d = draft(v("Ahri", "fall"), v("Kai'Sa", "fall"))
    assert consistency_warnings(d, [ahri_buff, kaisa_nerf]) == [
        "Ahri: verdict fall but all changes are buffs"
    ]


def test_consistency_accepts_mixed_changes_and_stable_verdicts():
    changes = [ahri_buff, make_change("Ahri", "nerf"), kaisa_nerf]
    d = draft(v("Ahri", "rise"), v("Kai'Sa", "stable"))
    assert consistency_warnings(d, changes) == []
