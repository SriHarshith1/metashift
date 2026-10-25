from collections import Counter
from dataclasses import dataclass

from metashift.core.models import Change
from metashift.core.text import name_key, normalize_ws


@dataclass(frozen=True)
class EvalScore:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        found = self.tp + self.fp
        return self.tp / found if found else 1.0

    @property
    def recall(self) -> float:
        expected = self.tp + self.fn
        return self.tp / expected if expected else 1.0

    def __add__(self, other: "EvalScore") -> "EvalScore":
        return EvalScore(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)


def _key(change: Change) -> tuple[str, str, str]:
    return (name_key(change.entity), normalize_ws(change.stat).lower(), change.direction)


def score_extraction(predicted: list[Change], gold: list[Change]) -> EvalScore:
    """Match (entity, stat, direction) triples as a multiset."""
    found = Counter(_key(c) for c in predicted)
    expected = Counter(_key(c) for c in gold)
    tp = sum((found & expected).values())
    return EvalScore(tp=tp, fp=sum(found.values()) - tp, fn=sum(expected.values()) - tp)
