from datetime import date
from typing import Protocol

from metashift.core.models import EntityStats


class StatsUnavailable(Exception):
    """The game adapter cannot supply win/pick/ban statistics for a patch."""


class GameAdapter(Protocol):
    game: str
    entity_types: list[str]
    glossary: str

    def list_patches(self) -> list[str]:
        """Known patch ids, newest first."""
        ...

    def fetch_notes(self, patch: str) -> str:
        """Return the patch notes page as HTML."""
        ...

    def notes_to_markdown(self, html: str) -> str: ...

    def patch_date(self, html: str) -> date | None: ...

    def entities(self, patch: str) -> dict[str, str]:
        """Display name -> entity type."""
        ...

    def icon_url(self, patch: str, entity: str) -> str | None: ...

    def fetch_stats(self, patch: str) -> list[EntityStats]:
        """Raises StatsUnavailable when no statistics source is available."""
        ...
