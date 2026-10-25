from metashift.core.models import AnalysisDraft, Change


def _changed_entities(changes: list[Change]) -> list[str]:
    return list(dict.fromkeys(c.entity for c in changes))


def retry_problems(draft: AnalysisDraft, changes: list[Change]) -> list[str]:
    """Problems worth another LLM attempt: missing verdicts and bad change indexes."""
    changed = _changed_entities(changes)
    have = {v.entity for v in draft.entities}
    problems = [f"missing verdict for {entity}" for entity in changed if entity not in have]
    for verdict in draft.entities:
        if verdict.entity not in changed:
            continue  # dropped later, so it is not worth a retry
        for ref in verdict.change_refs:
            if not 0 <= ref < len(changes):
                problems.append(f"{verdict.entity}: change_ref {ref} out of range")
    return problems


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
