import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from metashift.core.errors import MetashiftError
from metashift.games import get_adapter
from metashift.games.base import StatsUnavailable
from metashift.games.lol.adapter import LolAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "lol"
VERSION = "16.21.1"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ddragon_transport(versions: list[str] | None = None) -> httpx.MockTransport:
    files = {
        "/api/versions.json": (
            json.dumps(versions) if versions is not None else fixture("versions.json")
        ),
        f"/cdn/{VERSION}/data/en_US/champion.json": fixture("champion.json"),
        f"/cdn/{VERSION}/data/en_US/item.json": fixture("item.json"),
        f"/cdn/{VERSION}/data/en_US/runesReforged.json": fixture("runesReforged.json"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = files.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


@pytest.fixture
def adapter() -> LolAdapter:
    return LolAdapter(http=httpx.Client(transport=ddragon_transport()))


def test_list_patches_maps_ddragon_versions(adapter):
    patches = adapter.list_patches()
    assert patches[:2] == ["26.21", "26.20"]
    # major < 15 and non-numeric ids (lolpatch_7.20) are skipped
    assert patches[-1] == "25.1"
    assert all(p.split(".")[0].isdigit() and int(p.split(".")[0]) >= 25 for p in patches)


def test_list_patches_removes_duplicates_and_keeps_order():
    versions = ["16.21.2", "16.21.1", "16.20.1", "16.21.1"]
    adapter = LolAdapter(http=httpx.Client(transport=ddragon_transport(versions)))
    assert adapter.list_patches() == ["26.21", "26.20"]


def test_entities_include_punctuated_names(adapter):
    ents = adapter.entities("26.21")
    assert ents["Kai'Sa"] == "champion" and ents["Nunu & Willump"] == "champion"
    assert ents["Dr. Mundo"] == "champion"
    assert ents["Infinity Edge"] == "item"
    assert ents["Electrocute"] == "rune"
    assert "Dragon Soul" not in ents


def test_entities_unknown_patch_fails_clearly(adapter):
    with pytest.raises(MetashiftError, match="no Data Dragon data for patch 26.99"):
        adapter.entities("26.99")


def test_icon_url_uses_ddragon_id_not_display_name(adapter):
    assert adapter.icon_url("26.21", "Wukong").endswith("/img/champion/MonkeyKing.png")
    assert adapter.icon_url("26.21", "Kai'Sa").endswith("/img/champion/Kaisa.png")
    assert adapter.icon_url("26.21", "Dr. Mundo").endswith("/img/champion/DrMundo.png")
    assert adapter.icon_url("26.21", "Nunu & Willump").endswith("/img/champion/Nunu.png")
    assert adapter.icon_url("26.21", "Dragon Soul") is None


def test_icon_url_for_items_and_runes(adapter):
    assert (
        adapter.icon_url("26.21", "Infinity Edge")
        == "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/item/3031.png"
    )
    assert (
        adapter.icon_url("26.21", "Electrocute")
        == "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Domination/Electrocute/Electrocute.png"
    )


def test_notes_to_markdown_keeps_change_lines(adapter):
    md = adapter.notes_to_markdown(fixture("patch-notes.html"))
    assert "⇒" in md and "<div" not in md


def test_notes_to_markdown_fails_clearly_on_other_layout(adapter):
    with pytest.raises(MetashiftError, match="layout changed"):
        adapter.notes_to_markdown("<html><body>hi</body></html>")


def test_patch_date_reads_publish_date(adapter):
    assert adapter.patch_date(fixture("patch-notes.html")) == date(2026, 2, 3)


def test_patch_date_is_none_without_time_tag(adapter):
    assert adapter.patch_date("<html><body>hi</body></html>") is None


def test_fetch_notes_uses_notes_url_pattern():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="<html>ok</html>")

    adapter = LolAdapter(http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert adapter.fetch_notes("26.21") == "<html>ok</html>"
    assert seen == ["https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-21-notes/"]


def test_fetch_notes_falls_back_to_zero_padded_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("patch-25-04-notes/"):
            return httpx.Response(200, text="padded")
        return httpx.Response(404)

    adapter = LolAdapter(http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert adapter.fetch_notes("25.4") == "padded"


def test_fetch_stats_is_not_implemented_yet(adapter):
    with pytest.raises(StatsUnavailable):
        adapter.fetch_stats("26.21")


def test_get_adapter_knows_lol_and_rejects_others():
    assert get_adapter("lol").game == "lol"
    with pytest.raises(MetashiftError, match="unknown game 'dota'. Known: lol"):
        get_adapter("dota")
