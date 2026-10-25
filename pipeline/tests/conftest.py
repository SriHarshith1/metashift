from datetime import date
from pathlib import Path

import pytest

from metashift.core.models import EntityStats
from metashift.games.base import StatsUnavailable


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("METASHIFT_ROOT", str(tmp_path))
    return tmp_path


class StubAdapter:
    """In-memory GameAdapter. Later stage tests reuse it.

    `notes_html` is what fetch_notes returns. `notes_to_markdown` returns `notes_md`
    when it is set, else the HTML unchanged. `fetch_stats` raises StatsUnavailable
    unless `stats` rows are given. Icons follow `stub://{entity}.png` for every
    entity of type champion, item or rune; `system` entities have none.
    """

    def __init__(
        self,
        patches: list[str] | None = None,
        entities: dict[str, str] | None = None,
        notes_html: str = "<html>notes</html>",
        notes_md: str | None = None,
        published: date | None = None,
        stats: list[EntityStats] | None = None,
        game: str = "lol",
        entity_types: list[str] | None = None,
        glossary: str = "AD: attack damage.",
    ) -> None:
        self.game = game
        self.entity_types = entity_types or ["champion", "item", "rune", "system"]
        self.glossary = glossary
        self._patches = patches if patches is not None else ["26.21", "26.20"]
        self._entities = dict(entities) if entities is not None else {}
        self.notes_html = notes_html
        self.notes_md = notes_md
        self.published = published
        self.stats = stats
        self.fetch_calls: list[str] = []

    def list_patches(self) -> list[str]:
        return list(self._patches)

    def fetch_notes(self, patch: str) -> str:
        self.fetch_calls.append(patch)
        return self.notes_html

    def notes_to_markdown(self, html: str) -> str:
        return self.notes_md if self.notes_md is not None else html

    def select_sections(self, markdown: str) -> tuple[str, list[str]]:
        return markdown, []

    def patch_date(self, html: str) -> date | None:
        return self.published

    def entities(self, patch: str) -> dict[str, str]:
        return dict(self._entities)

    def icon_url(self, patch: str, entity: str) -> str | None:
        if self._entities.get(entity) in (None, "system"):
            return None
        return f"stub://{entity}.png"

    def fetch_stats(self, patch: str) -> list[EntityStats]:
        if self.stats is None:
            raise StatsUnavailable("stub has no stats")
        return list(self.stats)
