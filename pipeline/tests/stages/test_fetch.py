from datetime import date
from pathlib import Path

import httpx
import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import read_run_log
from metashift.core.stages.context import StageContext
from metashift.core.stages.fetch import run_fetch
from metashift.games.lol.adapter import LolAdapter
from tests.conftest import StubAdapter

FIXTURE_HTML = (Path(__file__).parents[1] / "fixtures/lol/patch-notes.html").read_text(
    encoding="utf-8"
)


def client(status: int, text: str = "") -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text=text)))


def test_fetch_writes_raw_md_from_notes_file(root, tmp_path):
    html = tmp_path / "p.html"
    html.write_text(FIXTURE_HTML, encoding="utf-8")
    adapter = LolAdapter(http=client(404))  # the network must not be used
    log = run_fetch(StageContext("lol", "26.21", adapter, None, notes_file=html))
    assert "⇒" in (root / "data/lol/26.21/raw.md").read_text(encoding="utf-8")
    assert log.stage == "fetch"
    assert read_run_log("lol", "26.21").patch_date == date(2026, 10, 20)


def test_fetch_downloads_when_no_notes_file(root):
    adapter = LolAdapter(http=client(200, FIXTURE_HTML))
    log = run_fetch(StageContext("lol", "26.21", adapter, None))
    assert "⇒" in (root / "data/lol/26.21/raw.md").read_text(encoding="utf-8")
    run_log = read_run_log("lol", "26.21")
    assert [s.stage for s in run_log.stages] == ["fetch"]
    assert run_log.stages[0].duration_s == log.duration_s >= 0


def test_fetch_404_suggests_notes_file(root):
    with pytest.raises(MetashiftError, match="--notes-file"):
        run_fetch(StageContext("lol", "26.21", LolAdapter(http=client(404)), None))


def test_fetch_missing_notes_file_fails_clearly(root, tmp_path):
    ctx = StageContext("lol", "26.21", StubAdapter(), None, notes_file=tmp_path / "nope.html")
    with pytest.raises(MetashiftError, match="notes file not found"):
        run_fetch(ctx)


def test_fetch_warns_when_publish_date_missing(root):
    adapter = StubAdapter(notes_html="x", notes_md="a: 1 ⇒ 2\n", published=None)
    log = run_fetch(StageContext("lol", "26.21", adapter, None))
    assert any("publish date" in w for w in log.warnings)
    assert read_run_log("lol", "26.21").stages[0].warnings == log.warnings


def test_context_dir_is_the_patch_dir(root):
    ctx = StageContext("lol", "26.21", StubAdapter(), None)
    assert ctx.dir == root / "data" / "lol" / "26.21"


def test_fetch_writes_only_kept_sections_and_warns_once(root):
    class Selecting(StubAdapter):
        def select_sections(self, markdown):
            return "## Champions\n* a: 1 ⇒ 2\n", ["Arena", "Classic"]

    log = run_fetch(StageContext("lol", "26.21", Selecting(notes_md="ignored"), None))
    assert (root / "data/lol/26.21/raw.md").read_text(encoding="utf-8") == "## Champions\n* a: 1 ⇒ 2\n"
    assert log.warnings == ["skipped sections: Arena, Classic", "publish date not found in patch notes"]


def test_fetch_real_notes_skip_other_modes(root, tmp_path):
    html = tmp_path / "p.html"
    html.write_text(FIXTURE_HTML, encoding="utf-8")
    log = run_fetch(StageContext("lol", "26.21", LolAdapter(http=client(404)), None, notes_file=html))
    raw = (root / "data/lol/26.21/raw.md").read_text(encoding="utf-8")
    assert "## Arena" not in raw and "### Azir" in raw
    [warning] = [w for w in log.warnings if w.startswith("skipped sections:")]
    assert "Arena" in warning and "Classic" in warning and "ARAM: Mayhem" in warning
