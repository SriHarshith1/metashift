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
        f"/cdn/{VERSION}/data/en_US/champion/Ahri.json": fixture("champion/Ahri.json"),
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


def test_select_sections_keeps_summoners_rift_sections_of_the_real_notes(adapter):
    md = adapter.notes_to_markdown(fixture("patch-notes.html"))
    kept, dropped = adapter.select_sections(md)
    for title in ("## Arena", "## Classic", "## ARAM"):
        assert title not in kept
    assert "### Azir" in kept and "### Bastion Breaker" in kept
    assert "## Champions" in kept and "## Items" in kept and "## Mid-Patch Updates" in kept
    assert {"Arena", "Classic", "ARAM: Mayhem"} <= set(dropped)
    assert "Bugfixes & QoL Changes" in dropped and "Patch Highlights" in dropped
    assert "Champions" not in dropped


def test_select_sections_accepts_summoners_rift_prefix_and_curly_apostrophe(adapter):
    md = (
        "## Summoner’s Rift Updates\n\n* a: 1 ⇒ 2\n\n## RUNES\n\n* b: 1 ⇒ 2\n\n"
        "## Systems\n\n* c: 1 ⇒ 2\n\n## URF\n\n* d: 1 ⇒ 2\n"
    )
    kept, dropped = adapter.select_sections(md)
    assert "a: 1" in kept and "b: 1" in kept and "c: 1" in kept and "d: 1" not in kept
    assert dropped == ["URF"]


def test_select_sections_keeps_everything_when_nothing_is_dropped(adapter):
    md = "## Champions\n\n* a: 1 ⇒ 2\n"
    assert adapter.select_sections(md) == (md, [])


def test_notes_to_markdown_fails_clearly_on_other_layout(adapter):
    with pytest.raises(MetashiftError, match="layout changed"):
        adapter.notes_to_markdown("<html><body>hi</body></html>")


def test_patch_date_reads_publish_date(adapter):
    assert adapter.patch_date(fixture("patch-notes.html")) == date(2026, 10, 20)


def test_patch_date_is_none_without_time_tag(adapter):
    assert adapter.patch_date("<html><body>hi</body></html>") is None


BASE = "https://www.leagueoflegends.com/en-us/news/game-updates/"


def recording_adapter(ok_slug: str | None) -> tuple[LolAdapter, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if ok_slug is not None and request.url.path.endswith(f"/{ok_slug}/"):
            return httpx.Response(200, text=f"page:{ok_slug}")
        return httpx.Response(404)

    return LolAdapter(http=httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_fetch_notes_tries_prefixed_url_first():
    adapter, seen = recording_adapter("league-of-legends-patch-26-21-notes")
    assert adapter.fetch_notes("26.21") == "page:league-of-legends-patch-26-21-notes"
    assert seen == [BASE + "league-of-legends-patch-26-21-notes/"]


def test_fetch_notes_falls_back_to_unprefixed_url():
    adapter, seen = recording_adapter("patch-26-3-notes")
    assert adapter.fetch_notes("26.3") == "page:patch-26-3-notes"
    assert seen == [
        BASE + "league-of-legends-patch-26-3-notes/",
        BASE + "patch-26-3-notes/",
    ]


def test_fetch_notes_falls_back_to_zero_padded_url():
    adapter, seen = recording_adapter("patch-25-04-notes")
    assert adapter.fetch_notes("25.4") == "page:patch-25-04-notes"
    assert seen[-1] == BASE + "patch-25-04-notes/" and len(seen) == 3


def test_fetch_notes_all_404_lists_urls_and_suggests_notes_file():
    adapter, seen = recording_adapter(None)
    with pytest.raises(MetashiftError, match="--notes-file") as err:
        adapter.fetch_notes("25.4")
    for url in seen:
        assert url in str(err.value)
    assert len(seen) == 3


def test_fetch_notes_does_not_zero_pad_two_digit_minor():
    adapter, seen = recording_adapter(None)
    with pytest.raises(MetashiftError):
        adapter.fetch_notes("26.21")
    assert seen == [
        BASE + "league-of-legends-patch-26-21-notes/",
        BASE + "patch-26-21-notes/",
    ]


def test_fetch_stats_is_unavailable_and_points_to_stats_md(adapter):
    with pytest.raises(StatsUnavailable, match="lolalytics not used: see STATS.md"):
        adapter.fetch_stats("26.21")


def test_get_adapter_knows_lol_and_rejects_others():
    assert get_adapter("lol").game == "lol"
    with pytest.raises(MetashiftError, match="unknown game 'dota'. Known: lol"):
        get_adapter("dota")


def listing_transport(html: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/en-us/news/game-updates/":
            return httpx.Response(status, text=html)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_available_patches_reads_the_game_updates_page():
    adapter = LolAdapter(http=httpx.Client(transport=listing_transport(fixture("game-updates.html"))))
    patches = adapter.available_patches()
    assert patches[:3] == ["26.21", "26.20", "26.19"]
    assert patches[-1] == "25.4"            # zero-padded "patch-25-04-notes" → 25.4
    assert "25.9" in patches and "25.09" not in patches
    assert len(patches) == len(set(patches))


def test_available_patches_ignores_teamfight_tactics_and_sorts_numerically():
    html = (
        '<a href="/en-us/news/game-updates/teamfight-tactics-patch-16-5-notes">tft</a>'
        '<a href="/en-us/news/game-updates/league-of-legends-patch-26-9-notes">a</a>'
        '<a href="/en-us/news/game-updates/league-of-legends-patch-26-10-notes">b</a>'
        '<a href="/en-us/news/game-updates/patch-26-2-notes">c</a>'
    )
    adapter = LolAdapter(http=httpx.Client(transport=listing_transport(html)))
    assert adapter.available_patches() == ["26.10", "26.9", "26.2"]


def test_available_patches_fails_clearly_when_no_links_found():
    adapter = LolAdapter(http=httpx.Client(transport=listing_transport("<html></html>")))
    with pytest.raises(MetashiftError, match="no patch notes links found"):
        adapter.available_patches()


def test_available_patches_reports_http_errors():
    adapter = LolAdapter(http=httpx.Client(transport=listing_transport("", status=503)))
    with pytest.raises(MetashiftError, match="HTTP 503"):
        adapter.available_patches()


def test_describe_champion_gives_roles_and_only_the_changed_abilities(adapter):
    text = adapter.describe("26.21", "Ahri", ["Q - Orb of Deception", "Passive", "Base stats"])
    lines = text.splitlines()
    assert lines[0] == "Mage, Assassin; resource: Mana"
    assert lines[1] == (
        "P Essence Theft: After killing 9 minions or monsters, Ahri heals. "
        "After taking down an enemy champion, Ahri heals for a greater amount."
    )
    assert lines[2].startswith("Q Orb of Deception: Ahri sends out and pulls back her orb")
    assert len(lines) == 3


def test_describe_champion_splits_combined_targets_and_skips_base_stats(adapter):
    text = adapter.describe("26.21", "Ahri", ["RW - Spirit Rush", "Base Stats"])
    assert [line.split(":")[0] for line in text.splitlines()[1:]] == [
        "W Fox-Fire",
        "R Spirit Rush",
    ]
    assert adapter.describe("26.21", "Ahri", ["Base stats"]) == "Mage, Assassin; resource: Mana"


def test_describe_unknown_target_uses_the_passive(adapter):
    text = adapter.describe("26.21", "Ahri", ["Calibrum"])
    assert text.splitlines()[1].startswith("P Essence Theft:")


def test_describe_item_prefers_the_summoners_rift_entry_and_strips_markup(adapter):
    text = adapter.describe("26.21", "Infinity Edge", ["Item"])
    assert text == (
        "Massively enhances critical strikes 75 Attack Damage 25% Critical Strike Chance "
        "Infinite Precision Critical strikes deal 250% damage. Cost 3500 gold."
    )


def test_describe_rune_and_unknown_entity(adapter):
    assert adapter.describe("26.21", "Electrocute", []) == (
        "Domination rune. Hitting a champion with 3 separate attacks or abilities in 3s "
        "deals bonus adaptive damage."
    )
    assert adapter.describe("26.21", "Dragon Soul", []) is None
