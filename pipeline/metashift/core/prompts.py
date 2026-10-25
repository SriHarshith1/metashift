from metashift.core.models import BaselineEntity, BaselineFile, Change


def extract_prompt(chunk: str, glossary: str, entity_types: list[str]) -> str:
    types = ", ".join(entity_types)
    return f"""You extract structured balance changes from game patch notes.

Glossary:
{glossary}

Read the patch notes excerpt below. Return JSON with one key, "changes": a list with ONE entry per stat line (one value that changed). Each entry has these fields:
- entity: the display name of the champion, item, rune or game system the line belongs to (as written in the notes).
- entity_type: exactly one of: {types}. Use "system" for anything that is not a single champion, item or rune (objectives, game rules, maps, modes).
- target: the part of the entity that changed (for example "Q", "Passive", "Base stats", "Item").
- stat: the name of the changed stat (for example "Damage", "Cooldown").
- old: the old value as text, or null when the mechanic is new or the line has no old value.
- new: the new value as text, or null when the mechanic is removed.
- direction: "buff" when the change makes the entity stronger, "nerf" when weaker, "adjust" for mixed changes, reworks, or when the effect is unclear.
- source_quote: the exact line from the notes, copied character for character. Do not paraphrase.

Rules:
- Do not invent changes. Skip bug fixes, cosmetic text and lines with no gameplay change.
- Use only the excerpt. If it holds no balance change, return {{"changes": []}}.
- A line such as "A ⇒ B" means the value changed from A to B.

Patch notes excerpt:
---
{chunk}
---"""


def _rate(label: str, value: float | None) -> str:
    return f"{label} {value}%" if value is not None else f"{label} unknown"


def _stats_line(entity: BaselineEntity | None) -> str:
    if entity is None or all(
        v is None for v in (entity.win_rate, entity.pick_rate, entity.ban_rate, entity.tier)
    ):
        return "no stats available"
    parts = [
        _rate("win rate", entity.win_rate),
        _rate("pick rate", entity.pick_rate),
        _rate("ban rate", entity.ban_rate),
    ]
    if entity.tier:
        parts.append(f"tier {entity.tier}")
    return ", ".join(parts)


def analyze_prompt(
    changes: list[Change],
    baseline: BaselineFile,
    glossary: str,
    kits: dict[str, str] | None = None,
) -> str:
    """`kits` maps an entity to official text about its changed parts (see describe)."""
    kits = kits or {}
    numbered = "\n".join(
        f"[{i}] {c.entity} — {c.target} {c.stat}: {c.old if c.old is not None else '(none)'}"
        f" → {c.new if c.new is not None else '(removed)'} ({c.direction})"
        for i, c in enumerate(changes)
    )
    entity_names = list(dict.fromkeys(c.entity for c in changes))
    blocks: list[str] = []
    for name in entity_names:
        entity = baseline.entities.get(name)
        lines = [f"{name}", f"  stats before this patch: {_stats_line(entity)}"]
        if name in kits:
            lines.append("  official description of the changed parts:")
            lines.extend(f"    {line}" for line in kits[name].splitlines())
        if entity is not None and entity.history:
            lines.append("  recent changes:")
            lines.extend(
                f"    {h.patch}: {h.direction} ({h.summary})" for h in entity.history
            )
        else:
            lines.append("  recent changes: none in the last 5 patches")
        blocks.append("\n".join(lines))
    compared = baseline.stats_patch or "none"
    return f"""You analyze how a game patch shifts the balance of the game.

Glossary:
{glossary}

Changes in this patch, numbered by index:
{numbered}

Stats come from patch {compared}, the patch before this one. Per changed entity:
{chr(10).join(blocks)}

Return JSON with these keys:
- headline: one sentence that sums up the shift of the patch.
- themes: 2 to 4 short phrases for the main themes of the patch.
- entities: ONE verdict per changed entity listed above, and no other entity. Each verdict has:
  - entity: the name exactly as written above.
  - verdict: "rise" when the entity should get stronger, "fall" when weaker, "stable" when the meta position stays the same.
  - confidence: "low", "medium" or "high".
  - reason: a short explanation that cites the change, the stats and the trend of earlier patches. Refer to the changes by their stat and values; do not give change indexes.
  - impact: 1 or 2 sentences on what the change does in a game, not a repeat of the numbers. Say which part of the entity's power moves: damage output (burst or damage over time), laning, team fights, early or late game, survival. Example: "Headshot deals less damage with crit items, so her late-game damage drops. Her Q poke is stronger in lane."
  - build_shift: one sentence when the change probably moves the builds, runes, role or playstyle of the entity or of the champions that use it. Example: "Crit scaling drops and Q base damage rises, so lethality builds gain value." Use null when builds probably stay the same.
- ripples: 2 to 5 indirect effects of the whole patch on the meta. Examples: champions that gain because a rival or counter was nerfed, champions that use a changed item, build paths that an item or rune change pushes, a role that gets stronger or weaker as a group. Each ripple has:
  - title: a short phrase, for example "Lethality marksmen gain".
  - explanation: 1 or 2 sentences that name the changes that cause the effect.
  - entities: the names of the champions, items or runes involved, as written in the game. Changed and unchanged entities are both allowed.

Rules:
- Use only the data above and the official descriptions. Do not invent numbers or abilities.
- Impact, build shifts and ripples are predictions. Keep them to what the changes and descriptions support.
- A near-50% win rate together with a small change usually means "stable".
- A verdict must fit the changes: do not say "rise" when every change is a nerf, or "fall" when every change is a buff.
"""
