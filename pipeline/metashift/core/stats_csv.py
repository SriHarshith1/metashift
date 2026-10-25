import csv
from pathlib import Path

from pydantic import ValidationError

from metashift.core.errors import MetashiftError
from metashift.core.models import EntityStats

COLUMNS = ["entity", "win_rate", "pick_rate", "ban_rate", "tier"]
_NUMBER_COLUMNS = ["win_rate", "pick_rate", "ban_rate"]


def _cell(row: dict[str, str | None], column: str) -> str:
    value = row.get(column)
    return (value or "").strip()


def _number(value: str, column: str, line: int) -> float | None:
    text = value.strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise MetashiftError(f"stats.csv line {line}: bad {column} '{value.strip()}'") from None


def read_stats_csv(path: Path) -> list[EntityStats]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as err:
        raise MetashiftError(f"stats file not found: {path}") from err
    except (OSError, UnicodeDecodeError) as err:
        raise MetashiftError(f"cannot read stats file {path}: {err}") from err
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise MetashiftError(f"stats.csv is empty. Expected columns {','.join(COLUMNS)}")
    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    missing = [c for c in COLUMNS if c not in reader.fieldnames]
    if missing:
        raise MetashiftError(
            f"stats.csv misses columns {','.join(missing)}. Expected columns {','.join(COLUMNS)}"
        )
    rows: list[EntityStats] = []
    for raw in reader:
        line = reader.line_num
        if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
            continue
        entity = _cell(raw, "entity")
        if not entity:
            raise MetashiftError(f"stats.csv line {line}: entity is empty")
        numbers = {c: _number(_cell(raw, c), c, line) for c in _NUMBER_COLUMNS}
        try:
            rows.append(EntityStats(entity=entity, tier=_cell(raw, "tier") or None, **numbers))
        except ValidationError as err:
            column = str(err.errors()[0]["loc"][0])
            raise MetashiftError(
                f"stats.csv line {line}: bad {column} '{_cell(raw, column)}'"
            ) from None
    return rows
