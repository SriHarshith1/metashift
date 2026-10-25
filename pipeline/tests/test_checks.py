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


def v(entity, verdict="stable", refs=None):
    return VerdictDraft(
        entity=entity, verdict=verdict, confidence="medium", reason="r", change_refs=refs or []
    )


def draft(*verdicts):
    return AnalysisDraft(headline="h", themes=[], entities=list(verdicts))


def test_retry_problems_finds_missing_and_bad_refs():
    probs = retry_problems(draft(v("Ahri", refs=[5])), [ahri_buff, kaisa_nerf])
    assert probs == ["missing verdict for Kai'Sa", "Ahri: change_ref 5 out of range"]


def test_retry_problems_is_empty_for_a_complete_draft():
    d = draft(v("Ahri", refs=[0]), v("Kai'Sa", refs=[1]))
    assert retry_problems(d, [ahri_buff, kaisa_nerf]) == []


def test_retry_problems_ignores_verdicts_for_unchanged_entities():
    d = draft(v("Ahri", refs=[0]), v("Garen", refs=[9]))
    assert retry_problems(d, [ahri_buff]) == []


def test_consistency_flags_rise_with_only_nerfs():
    d = draft(v("Kai'Sa", "rise", refs=[1]), v("Ahri", "rise", refs=[0]))
    assert consistency_warnings(d, [ahri_buff, kaisa_nerf]) == [
        "Kai'Sa: verdict rise but all changes are nerfs"
    ]


def test_consistency_flags_fall_with_only_buffs():
    d = draft(v("Ahri", "fall", refs=[0]), v("Kai'Sa", "fall", refs=[1]))
    assert consistency_warnings(d, [ahri_buff, kaisa_nerf]) == [
        "Ahri: verdict fall but all changes are buffs"
    ]


def test_consistency_accepts_mixed_changes_and_stable_verdicts():
    changes = [ahri_buff, make_change("Ahri", "nerf"), kaisa_nerf]
    d = draft(v("Ahri", "rise", refs=[0, 1]), v("Kai'Sa", "stable", refs=[2]))
    assert consistency_warnings(d, changes) == []
