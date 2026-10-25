from dataclasses import dataclass
from pathlib import Path

from metashift.core.llm import LLM
from metashift.core.paths import patch_dir
from metashift.games.base import GameAdapter


@dataclass
class StageContext:
    game: str
    patch: str
    adapter: GameAdapter
    llm: LLM | None
    notes_file: Path | None = None

    @property
    def dir(self) -> Path:
        return patch_dir(self.game, self.patch)
