import pytest

from metashift.core.errors import MetashiftError
from metashift.core.io import read_model, read_run_log, write_text
from metashift.core.llm import FakeLLM
from metashift.core.models import Change, ChangesFile, ExtractDraft
from metashift.core.paths import patch_dir
from metashift.core.stages.context import StageContext
from metashift.core.stages.extract import run_extract
from tests.conftest import StubAdapter

RAW = "## Champions\n\n#### Ahri\n\n* Q Damage: 40 ⇒ 50\n\n#### Kai'Sa\n\n* W Cooldown: 20 → 18\n"
ENTITIES = {"Ahri": "champion", "Kai'Sa": "champion"}


def change(entity, quote, stat="Q Damage", entity_type="champion", old="40", new="50"):
    return Change(
        entity=entity,
        entity_type=entity_type,
        target="Q",
        stat=stat,
        old=old,
        new=new,
        direction="buff",
        source_quote=quote,
    )


def json_of(*changes: Change) -> str:
    return ExtractDraft(changes=list(changes)).model_dump_json()


def ctx(root, llm, raw=RAW, entities=None):
    write_text(root / "data/lol/26.21/raw.md", raw)
    adapter = StubAdapter(entities=entities if entities is not None else ENTITIES)
    return StageContext("lol", "26.21", adapter, llm)


def read_changes():
    return read_model(patch_dir("lol", "26.21") / "changes.json", ChangesFile, "extract").changes


def test_extract_resolves_names_and_drops_bad_rows(root):
    ahri_ok = change("Ahri", "Q Damage: 40 ⇒ 50")
    kaisa = change("Kaisa", "W Cooldown: 20 → 18", stat="W Cooldown", old="20", new="18")
    garen = change("Garen", "Q Damage: 40 ⇒ 50")
    fake = change("Ahri", "R Damage: 1 ⇒ 2", stat="R Damage")
    llm = FakeLLM([json_of(ahri_ok, kaisa, garen, fake)])
    log = run_extract(ctx(root, llm))
    changes = read_changes()
    assert [c.entity for c in changes] == ["Ahri", "Kai'Sa"]
    assert any("unknown entity 'Garen'" in w for w in log.warnings)
    assert any("quote not found" in w for w in log.warnings)
    assert "quote not found in notes, dropped: Ahri R Damage" in log.warnings
    assert log.stage == "extract" and log.llm == "fake"
    assert read_run_log("lol", "26.21").stages[-1].warnings == log.warnings


def test_extract_uses_known_entity_type_and_ignores_whitespace_in_quotes(root):
    c = change("ahri", "Q Damage:\n 40   ⇒ 50", entity_type="item")
    run_extract(ctx(root, FakeLLM([json_of(c)])))
    [kept] = read_changes()
    assert (kept.entity, kept.entity_type) == ("Ahri", "champion")


def test_extract_keeps_system_entities_unresolved(root):
    raw = "## Neutral\n\n* Dragon Soul: Duration 10 ⇒ 12\n"
    c = change("Dragon Soul", "Dragon Soul: Duration 10 ⇒ 12", entity_type="system")
    log = run_extract(ctx(root, FakeLLM([json_of(c)]), raw=raw, entities={}))
    [kept] = read_changes()
    assert (kept.entity, kept.entity_type) == ("Dragon Soul", "system")
    assert log.warnings == []


def test_extract_low_coverage_warns(root):
    raw = "## A\n\n" + "\n".join(f"* Stat {i}: {i} ⇒ {i + 1}" for i in range(5)) + "\n"
    c = change("Ahri", "Stat 0: 0 ⇒ 1")
    log = run_extract(ctx(root, FakeLLM([json_of(c)]), raw=raw))
    assert any("low coverage: extracted 1 of ~5" in w for w in log.warnings)


def test_extract_without_fetch_names_the_stage(root):
    with pytest.raises(MetashiftError, match="run stage 'fetch' first"):
        run_extract(StageContext("lol", "26.21", StubAdapter(), FakeLLM([])))


def test_extract_requires_an_llm(root):
    write_text(root / "data/lol/26.21/raw.md", RAW)
    with pytest.raises(MetashiftError, match="needs an LLM"):
        run_extract(StageContext("lol", "26.21", StubAdapter(), None))


def test_extract_runs_one_llm_call_per_chunk_and_sums_retries(root, monkeypatch):
    import metashift.core.stages.extract as extract_mod

    monkeypatch.setattr(extract_mod, "split_sections", lambda md: ["part one ⇒", "part two ⇒"])
    raw = RAW
    first = change("Ahri", "Q Damage: 40 ⇒ 50")
    second = change("Kai'Sa", "W Cooldown: 20 → 18", stat="W Cooldown")
    llm = FakeLLM(["not json", json_of(first), json_of(second)])
    log = run_extract(ctx(root, llm, raw=raw))
    assert [c.entity for c in read_changes()] == ["Ahri", "Kai'Sa"]
    assert len(llm.prompts) == 3
    assert "part one" in llm.prompts[0] and "part two" in llm.prompts[2]
    assert log.retries == 1


def test_extract_prompt_mentions_types_and_glossary(root):
    llm = FakeLLM([json_of(change("Ahri", "Q Damage: 40 ⇒ 50"))])
    run_extract(ctx(root, llm))
    prompt = llm.prompts[0]
    assert "champion, item, rune, system" in prompt
    assert "AD: attack damage." in prompt
    assert "* Q Damage: 40 ⇒ 50" in prompt


def test_extract_accepts_readable_quote_for_a_bold_markdown_line(root):
    raw = "## Champions\n\n### Azir\n\n* **Mana Growth**: 40/Level ⇒ **50/Level**\n"
    c = change(
        "Azir", "Mana Growth: 40/Level ⇒ 50/Level", stat="Mana Growth", old="40/Level", new="50/Level"
    )
    log = run_extract(ctx(root, FakeLLM([json_of(c)]), raw=raw, entities={"Azir": "champion"}))
    assert [k.entity for k in read_changes()] == ["Azir"]
    assert log.warnings == []
    half = change("Azir", "Mana Growth: 40/Level ⇒ **50/Level**", stat="Mana Growth")
    run_extract(ctx(root, FakeLLM([json_of(half)]), raw=raw, entities={"Azir": "champion"}))
    assert [k.entity for k in read_changes()] == ["Azir"]


def two_chunks(monkeypatch):
    import metashift.core.stages.extract as extract_mod

    monkeypatch.setattr(extract_mod, "split_sections", lambda md: ["part one ⇒", "part two ⇒"])


def test_extract_caches_finished_chunks_so_a_rerun_skips_them(root, monkeypatch):
    two_chunks(monkeypatch)
    first = change("Ahri", "Q Damage: 40 ⇒ 50")
    second = change("Kai'Sa", "W Cooldown: 20 → 18", stat="W Cooldown")
    failing = FakeLLM([json_of(first), "nope", "nope", "nope"])
    with pytest.raises(MetashiftError, match="invalid JSON"):
        run_extract(ctx(root, failing))
    assert len(list((root / "data/lol/26.21/extract-cache").glob("*.json"))) == 1
    assert not (root / "data/lol/26.21/changes.json").exists()

    rerun = FakeLLM([json_of(second)])
    log = run_extract(ctx(root, rerun))
    assert len(rerun.prompts) == 1 and "part two" in rerun.prompts[0]
    assert [c.entity for c in read_changes()] == ["Ahri", "Kai'Sa"]
    assert log.retries == 0

    again = FakeLLM([])
    run_extract(ctx(root, again))
    assert again.prompts == []
    assert [c.entity for c in read_changes()] == ["Ahri", "Kai'Sa"]


def test_extract_cache_is_per_llm_name_and_ignores_broken_files(root, monkeypatch):
    two_chunks(monkeypatch)
    one = change("Ahri", "Q Damage: 40 ⇒ 50")
    run_extract(ctx(root, FakeLLM([json_of(one), json_of()], name="a")))
    other = FakeLLM([json_of(one), json_of()], name="b")
    run_extract(ctx(root, other))
    assert len(other.prompts) == 2  # a different model never reuses the cache
    for f in (root / "data/lol/26.21/extract-cache").glob("*.json"):
        f.write_text("{broken", encoding="utf-8")
    redo = FakeLLM([json_of(one), json_of()], name="a")
    run_extract(ctx(root, redo))
    assert len(redo.prompts) == 2


def test_extract_prints_chunk_progress_to_stderr(root, monkeypatch, capsys):
    two_chunks(monkeypatch)
    run_extract(ctx(root, FakeLLM([json_of(change("Ahri", "Q Damage: 40 ⇒ 50")), json_of()])))
    err = capsys.readouterr().err
    assert "extract chunk 1/2" in err and "extract chunk 2/2" in err


def test_extract_changes_needs_no_files(tmp_path):
    from metashift.core.stages.extract import extract_changes

    llm = FakeLLM([json_of(change("Ahri", "Q Damage: 40 ⇒ 50"))])
    changes, retries, warnings = extract_changes(RAW, StubAdapter(entities=ENTITIES), "26.21", llm)
    assert [c.entity for c in changes] == ["Ahri"]
    assert retries == 0
    assert warnings == ["low coverage: extracted 1 of ~2 change lines"]
    assert list(tmp_path.iterdir()) == []


def test_extract_with_zero_changes_stops_before_writing(root):
    with pytest.raises(MetashiftError, match="no changes extracted from data/lol/26.21/raw.md"):
        run_extract(ctx(root, FakeLLM([json_of()])))
    assert not (root / "data/lol/26.21/changes.json").exists()
