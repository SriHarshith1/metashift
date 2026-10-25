from metashift.core.errors import MetashiftError
from metashift.games.base import GameAdapter, StatsUnavailable

KNOWN_GAMES = ["lol"]

__all__ = ["GameAdapter", "StatsUnavailable", "get_adapter"]


def get_adapter(game: str) -> GameAdapter:
    if game == "lol":
        from metashift.games.lol.adapter import LolAdapter

        return LolAdapter()
    raise MetashiftError(f"unknown game '{game}'. Known: {', '.join(KNOWN_GAMES)}")
