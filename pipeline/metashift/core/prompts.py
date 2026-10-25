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
