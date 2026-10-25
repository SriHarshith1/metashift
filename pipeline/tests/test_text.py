from metashift.core.text import (
    count_change_lines,
    name_key,
    normalize_ws,
    resolve_entity,
    split_sections,
)


def test_normalize_ws_collapses_runs_and_strips():
    assert normalize_ws("  a \n\t b   c\n") == "a b c"


def test_name_key_keeps_only_lowercase_alphanumerics():
    assert name_key("Kai'Sa") == "kaisa"
    assert name_key("Nunu & Willump") == "nunuwillump"


def test_resolve_entity_handles_punctuation_and_typos():
    known = {"Kai'Sa": "champion", "Dr. Mundo": "champion", "Nunu & Willump": "champion"}
    assert resolve_entity("Kaisa", known) == "Kai'Sa"
    assert resolve_entity("dr mundo", known) == "Dr. Mundo"
    assert resolve_entity("Nunu and Willump", known) == "Nunu & Willump"
    assert resolve_entity("Garen", known) is None


def test_resolve_entity_prefers_exact_match_and_handles_empty_names():
    known = {"Ahri": "champion", "Ahri!": "item"}
    assert resolve_entity("Ahri!", known) == "Ahri!"
    assert resolve_entity("???", known) is None


def test_count_change_lines_counts_both_arrows():
    assert count_change_lines("a: 1 ⇒ 2\nb: 3 → 4\nc: text") == 2


def test_split_sections_respects_max_chars():
    md = "## A\n" + "x" * 5000 + "\n## B\n" + "y" * 5000
    assert len(split_sections(md, 6000)) == 2


def test_split_sections_packs_small_sections_together():
    md = "# T\nintro\n## A\nalpha\n### B\nbeta\n"
    assert split_sections(md, 6000) == ["# T\nintro\n\n## A\nalpha\n\n### B\nbeta"]


def test_split_sections_does_not_split_at_deeper_headings():
    md = "## Champions\n#### Ahri\n* a ⇒ b\n#### Zed\n* c ⇒ d\n"
    chunks = split_sections(md, 6000)
    assert len(chunks) == 1 and "#### Zed" in chunks[0]


def test_split_sections_splits_oversize_section_at_blank_lines():
    para = "p" * 400
    md = "## Big\n" + "\n\n".join([para] * 10)
    chunks = split_sections(md, 1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert all(c.startswith("## Big") for c in chunks)
    assert sum(c.count(para) for c in chunks) == 10


def test_split_sections_hard_splits_a_single_huge_line():
    chunks = split_sections("## H\n" + "z" * 2500, 1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(c.count("z") for c in chunks) == 2500


def test_strip_markdown_removes_emphasis_bullets_and_escapes():
    from metashift.core.text import strip_markdown

    assert strip_markdown("* **Mana Growth**: 40/Level ⇒ **50/Level**") == (
        "Mana Growth: 40/Level ⇒ 50/Level"
    )
    assert strip_markdown("- __a__ \\*b\\* _c_\n+ d") == "a b c d"
