import difflib
import re

_HEADING = re.compile(r"^#{1,3}\s")
_NON_ALNUM = re.compile(r"[^a-z0-9]")
FUZZY_CUTOFF = 0.85
CHANGE_ARROWS = ("⇒", "→")


def normalize_ws(s: str) -> str:
    return " ".join(s.split())


_BULLET = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)
_ESCAPE = re.compile(r"\\(.)")
_EMPHASIS = re.compile(r"[*_]")


def strip_markdown(s: str) -> str:
    """Plain, whitespace-normalised text of a markdown fragment, for quote comparison."""
    s = _BULLET.sub("", s)
    s = _ESCAPE.sub(r"\1", s)
    return normalize_ws(_EMPHASIS.sub("", s))


def name_key(s: str) -> str:
    return _NON_ALNUM.sub("", s.lower())


def resolve_entity(name: str, known: dict[str, str]) -> str | None:
    if name in known:
        return name
    key = name_key(name)
    if not key:
        return None
    by_key: dict[str, str] = {}
    for display in known:
        by_key.setdefault(name_key(display), display)
    if key in by_key:
        return by_key[key]
    close = difflib.get_close_matches(key, list(by_key), n=1, cutoff=FUZZY_CUTOFF)
    return by_key[close[0]] if close else None


def count_change_lines(md: str) -> int:
    return sum(1 for line in md.splitlines() if any(a in line for a in CHANGE_ARROWS))


def _sections(md: str) -> list[str]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in md.splitlines():
        if _HEADING.match(line) and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    texts = ["\n".join(lines).strip() for lines in sections]
    return [t for t in texts if t]


def _hard_split(text: str, limit: int) -> list[str]:
    """Split text that has no blank lines: by line, and by character as a last resort."""
    pieces: list[str] = []
    for line in text.split("\n"):
        while len(line) > limit:
            pieces.append(line[:limit])
            line = line[limit:]
        pieces.append(line)
    return pieces


def _pack(units: list[str], limit: int, sep: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(sep) + len(unit) > limit:
            chunks.append(current)
            current = unit
        else:
            current = f"{current}{sep}{unit}" if current else unit
    if current:
        chunks.append(current)
    return chunks


def _split_long_section(section: str, max_chars: int) -> list[str]:
    first_line = section.split("\n", 1)[0]
    header = first_line if _HEADING.match(first_line) else ""
    # Keep room for the repeated heading so no piece exceeds max_chars.
    limit = max(max_chars - len(header) - 2, 1) if header else max_chars
    units: list[str] = []
    for paragraph in section.split("\n\n"):
        if len(paragraph) <= limit:
            units.append(paragraph)
        else:
            units.extend(_pack(_hard_split(paragraph, limit), limit, "\n"))
    pieces = _pack(units, limit, "\n\n")
    if not header:
        return pieces
    return [pieces[0]] + [f"{header}\n\n{p}" for p in pieces[1:]]


def split_sections(md: str, max_chars: int = 6000) -> list[str]:
    units: list[str] = []
    for section in _sections(md):
        if len(section) <= max_chars:
            units.append(section)
        else:
            units.extend(_split_long_section(section, max_chars))
    return _pack(units, max_chars, "\n\n")


def patch_sort_key(patch: str) -> tuple[int, ...]:
    return tuple(int(p) for p in patch.split("."))
