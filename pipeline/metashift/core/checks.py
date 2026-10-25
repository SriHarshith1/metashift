from metashift.core.models import AnalysisDraft, Change


def _changed_entities(changes: list[Change]) -> list[str]:
    return list(dict.fromkeys(c.entity for c in changes))


def retry_problems(draft: AnalysisDraft, changes: list[Change]) -> list[str]:
    """Problems worth another LLM attempt: a changed entity without a verdict."""
    have = {v.entity for v in draft.entities}
    return [
        f"missing verdict for {entity}"
        for entity in _changed_entities(changes)
        if entity not in have
    ]


def consistency_warnings(draft: AnalysisDraft, changes: list[Change]) -> list[str]:
    """Verdicts that contradict the direction of all of an entity's changes."""
    warnings: list[str] = []
    for verdict in draft.entities:
        directions = {c.direction for c in changes if c.entity == verdict.entity}
        if verdict.verdict == "rise" and directions == {"nerf"}:
            warnings.append(f"{verdict.entity}: verdict rise but all changes are nerfs")
        elif verdict.verdict == "fall" and directions == {"buff"}:
            warnings.append(f"{verdict.entity}: verdict fall but all changes are buffs")
    return warnings
