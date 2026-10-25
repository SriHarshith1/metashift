from metashift.core.evaluate import EvalScore, score_extraction
from metashift.core.models import Change


def chg(entity: str, stat: str, direction: str = "buff") -> Change:
    return Change(
        entity=entity,
        entity_type="champion",
        target="Q",
        stat=stat,
        old="1",
        new="2",
        direction=direction,
        source_quote=f"{stat}: 1 ⇒ 2",
    )


def test_score_counts_matches_as_multiset():
    ahri_q_buff = chg("Ahri", "base damage")
    kaisa_nerf = chg("Kai'Sa", "attack speed", "nerf")
    garen_buff = chg("Garen", "armor")
    s = score_extraction([ahri_q_buff, ahri_q_buff, kaisa_nerf], [ahri_q_buff, garen_buff])
    assert (s.tp, s.fp, s.fn) == (1, 2, 1)


def test_score_ignores_name_and_stat_formatting():
    assert score_extraction([chg("Kai'Sa", "Base  Damage")], [chg("kaisa", "base damage")]).tp == 1


def test_score_direction_must_match():
    s = score_extraction([chg("Ahri", "base damage", "nerf")], [chg("Ahri", "base damage", "buff")])
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_precision_and_recall_are_one_when_empty():
    s = EvalScore(tp=0, fp=0, fn=0)
    assert (s.precision, s.recall) == (1.0, 1.0)


def test_precision_and_recall_values():
    s = EvalScore(tp=9, fp=1, fn=3)
    assert s.precision == 0.9
    assert s.recall == 0.75
