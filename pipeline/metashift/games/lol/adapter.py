import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from metashift.core.errors import MetashiftError
from metashift.core.models import EntityStats
from metashift.games.base import StatsUnavailable

DDRAGON = "https://ddragon.leagueoflegends.com"
NOTES_URL = "https://www.leagueoflegends.com/en-us/news/game-updates/patch-{yy}-{n}-notes/"
# Verified against the live site: the article body is the element with this id, and the
# publish date is the first <time datetime> in the page header (div.metadata).
ARTICLE_SELECTOR = "#patch-notes-container"
DATE_SELECTOR = "div.metadata time[datetime]"
MIN_DDRAGON_MAJOR = 15
HTTP_TIMEOUT_S = 30

GLOSSARY = """\
AD: attack damage. AP: ability power. AS: attack speed. CDR: cooldown reduction.
AH: ability haste (replaces CDR). MR: magic resist. HP: health points. CC: crowd control.
"base" means the value at level 1 or the base stat, before bonuses. "ratio" means the
scaling of a stat with AD, AP or HP (for example "60% AP").
In a change line "A ⇒ B" means the value changed from A to B."""

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.\d+)*$")


class LolAdapter:
    game = "lol"
    entity_types = ["champion", "item", "rune", "system"]
    glossary = GLOSSARY

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=HTTP_TIMEOUT_S, follow_redirects=True)
        self._versions: list[str] | None = None
        self._catalogs: dict[str, dict[str, tuple[str, str | None]]] = {}

    # --- HTTP helpers -------------------------------------------------------------

    def _get(self, url: str) -> httpx.Response:
        try:
            return self._http.get(url)
        except httpx.HTTPError as err:
            raise MetashiftError(f"could not reach {url}: {err}") from err

    def _get_json(self, url: str):
        response = self._get(url)
        if response.status_code != 200:
            raise MetashiftError(f"{url} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as err:
            raise MetashiftError(f"{url} did not return JSON") from err

    # --- patches ------------------------------------------------------------------

    def _ddragon_versions(self) -> list[str]:
        if self._versions is None:
            data = self._get_json(f"{DDRAGON}/api/versions.json")
            if not isinstance(data, list):
                raise MetashiftError(f"{DDRAGON}/api/versions.json has an unexpected shape")
            self._versions = [str(v) for v in data]
        return self._versions

    def list_patches(self) -> list[str]:
        patches: list[str] = []
        for version in self._ddragon_versions():
            match = _VERSION_RE.match(version)
            if not match:
                continue
            major, minor = int(match.group(1)), int(match.group(2))
            if major < MIN_DDRAGON_MAJOR:
                continue
            patch = f"{major + 10}.{minor}"
            if patch not in patches:
                patches.append(patch)
        return patches

    def _version_for(self, patch: str) -> str:
        match = re.fullmatch(r"(\d+)\.(\d+)", patch)
        if not match:
            raise MetashiftError(f"invalid patch id '{patch}'. Expected a form like 26.21")
        major, minor = int(match.group(1)) - 10, int(match.group(2))
        for version in self._ddragon_versions():
            m = _VERSION_RE.match(version)
            if m and int(m.group(1)) == major and int(m.group(2)) == minor:
                return version
        raise MetashiftError(f"no Data Dragon data for patch {patch}")

    # --- notes --------------------------------------------------------------------

    def _notes_urls(self, patch: str) -> list[str]:
        yy, n = patch.split(".")
        urls = [NOTES_URL.format(yy=yy, n=n)]
        if len(n) == 1:
            # Riot zero-pads minor numbers for some seasons (patch-25-04-notes).
            urls.append(NOTES_URL.format(yy=yy, n=f"0{n}"))
        return urls

    def fetch_notes(self, patch: str) -> str:
        if not re.fullmatch(r"\d+\.\d+", patch):
            raise MetashiftError(f"invalid patch id '{patch}'. Expected a form like 26.21")
        urls = self._notes_urls(patch)
        for url in urls:
            response = self._get(url)
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise MetashiftError(f"{url} returned HTTP {response.status_code}")
            return response.text
        raise MetashiftError(
            f"patch notes not found at {urls[0]}. Save the page and pass --notes-file"
        )

    def notes_to_markdown(self, html: str) -> str:
        body = BeautifulSoup(html, "html.parser").select_one(ARTICLE_SELECTOR)
        if body is None:
            raise MetashiftError("patch notes page layout changed: article body not found")
        for tag in body.find_all(["script", "style"]):
            tag.decompose()
        md = markdownify(str(body), heading_style="ATX", strip=["img", "a"])
        md = re.sub(r"[ \t]+\n", "\n", md)
        return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"

    def patch_date(self, html: str) -> date | None:
        soup = BeautifulSoup(html, "html.parser")
        node = soup.select_one(DATE_SELECTOR) or soup.select_one("time[datetime]")
        if node is None:
            return None
        raw = str(node.get("datetime", "")).strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None

    # --- entities and icons -------------------------------------------------------

    def _catalog(self, patch: str) -> dict[str, tuple[str, str | None]]:
        """Display name -> (entity type, icon url) for one Data Dragon version."""
        version = self._version_for(patch)
        if version in self._catalogs:
            return self._catalogs[version]
        base = f"{DDRAGON}/cdn/{version}"
        catalog: dict[str, tuple[str, str | None]] = {}
        champions = self._get_json(f"{base}/data/en_US/champion.json")["data"]
        for champ in champions.values():
            catalog.setdefault(
                champ["name"], ("champion", f"{base}/img/champion/{champ['id']}.png")
            )
        items = self._get_json(f"{base}/data/en_US/item.json")["data"]
        for key, item in items.items():
            catalog.setdefault(item["name"], ("item", f"{base}/img/item/{key}.png"))
        trees = self._get_json(f"{base}/data/en_US/runesReforged.json")
        for tree in trees:
            for slot in tree["slots"]:
                for rune in slot["runes"]:
                    catalog.setdefault(
                        rune["name"], ("rune", f"{DDRAGON}/cdn/img/{rune['icon']}")
                    )
        self._catalogs[version] = catalog
        return catalog

    def entities(self, patch: str) -> dict[str, str]:
        return {name: kind for name, (kind, _) in self._catalog(patch).items()}

    def icon_url(self, patch: str, entity: str) -> str | None:
        entry = self._catalog(patch).get(entity)
        return entry[1] if entry else None

    # --- stats --------------------------------------------------------------------

    def fetch_stats(self, patch: str) -> list[EntityStats]:
        raise StatsUnavailable("not implemented")
