import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("METASHIFT_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def patch_dir(game: str, patch: str) -> Path:
    return repo_root() / "data" / game / patch


def web_data_dir() -> Path:
    return repo_root() / "web" / "public" / "data"
