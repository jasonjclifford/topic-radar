from pathlib import Path

from topic_radar.text import chunk_text, extract_text, normalize_quote, quote_found

SITES = Path(__file__).parent / "sites"


def page(name):
    return (SITES / "articles" / name).read_text(encoding="utf-8").replace("{BASE}", "http://x.test")


def doc(*sections, title="Guide"):
    """Markdown with an H1 and H2 sections of whole-line paragraphs: sections are (heading, [lines])."""
    out = [f"# {title}", ""]
    for heading, lines in sections:
        out += [f"## {heading}", ""]
        for line in lines:
            out += [line, ""]
    return "\n".join(out).strip()


def test_extraction_keeps_the_main_text_and_its_headings():
    text = extract_text(page("three-sections.html"))
    assert "## Safer defaults" in text.splitlines()
    assert "The sandbox change number 3 lands" in text
    assert "Copyright the Example Project" not in text


def test_a_page_with_three_sections_chunks_at_the_headings():
    text = extract_text(page("three-sections.html"))
    chunks = chunk_text(text, chunk_chars=700, max_chunks=None)
    assert len(chunks) == 3
    assert [c.splitlines()[0] for c in chunks] == ["# Cedar 2.0 release notes", "## Safer defaults", "## Migration"]
    assert "change number 1 " in chunks[0] and "change number 3 " in chunks[1] and "change number 5 " in chunks[2]


def test_a_long_sections_second_chunk_starts_with_its_heading_path():
    lines = [f"Line {i} of the scheduler section, written out in full." for i in range(1, 13)]
    text = doc(("Scheduler", lines))
    chunks = chunk_text(text, chunk_chars=300, max_chunks=None)
    assert len(chunks) >= 3
    assert chunks[0].startswith("# Guide\n\n## Scheduler")
    assert chunks[1].startswith("Under: Guide > Scheduler\n")
    assert chunks[2].startswith("Under: Guide > Scheduler\n")


def test_the_heading_path_follows_the_level_of_each_heading():
    lines = [f"Row {i} holds a sentence about the storage layer and nothing else." for i in range(1, 9)]
    text = "# Top\n\n## One\n\nshort\n\n## Two\n\n### Deep\n\n" + "\n\n".join(lines)
    chunks = chunk_text(text, chunk_chars=250, max_chunks=None)
    unders = [c.splitlines()[0] for c in chunks if c.startswith("Under:")]
    assert unders and set(unders) == {"Under: Top > Two > Deep"}


def test_no_chunk_exceeds_the_limit_or_splits_a_line():
    lines = [f"Paragraph {i}: " + "word " * (i % 7 + 3) for i in range(1, 40)]
    text = doc(("Alpha", lines[:20]), ("Beta", lines[20:]))
    source_lines = {l.strip() for l in text.splitlines() if l.strip()}
    chunks = chunk_text(text, chunk_chars=400, max_chunks=None)
    assert len(chunks) > 4
    assert all(len(c) <= 400 for c in chunks)
    seen = []
    for c in chunks:
        for l in c.splitlines():
            if l.strip() and not l.startswith("Under:"):
                assert l.strip() in source_lines
                seen.append(l.strip())
    assert set(seen) == source_lines


def test_a_single_line_longer_than_the_limit_stays_whole():
    text = "# T\n\n## S\n\n" + "x" * 900 + "\n\nshort line after it"
    chunks = chunk_text(text, chunk_chars=300, max_chunks=None)
    assert any("x" * 900 in c for c in chunks)


def test_max_chunks_keeps_the_first_chunks_only():
    text = extract_text(page("many-sections.html"))
    every = chunk_text(text, chunk_chars=500, max_chunks=None)
    assert len(every) >= 5
    assert chunk_text(text, chunk_chars=500, max_chunks=4) == every[:4]


def test_quote_found_passes_across_curly_quotes_dashes_case_and_whitespace():
    text = "The team says the legacy loader won’t go away – until the next major version."
    assert quote_found("the legacy   loader won't go\naway - until the NEXT major version", text)
    assert quote_found("“the legacy loader” won’t go away", 'He said "the legacy loader" won\'t go away.')


def test_quote_found_fails_on_a_paraphrase():
    text = "The team says the legacy loader won’t go away until the next major version."
    assert not quote_found("the old loader will be removed in the next major version", text)


def test_quote_found_fails_under_twelve_characters_even_when_present():
    text = "Cedar ships a new scheduler this year."
    assert quote_found("a new scheduler", text)
    assert not quote_found("new sched", text)


def test_the_twelve_character_boundary():
    text = "abcdefghijkl and abcdefghijk"
    assert quote_found("abcdefghijkl", text)
    assert not quote_found("abcdefghijk", text)
    assert normalize_quote("  A’B  ") == "a'b"


def test_a_quote_with_a_plain_identifier_matches_text_with_markdown_escapes():
    text = "The agent uses max\\_tool\\_calls to stop looping, and a\\*b is a \\[link\\]."
    assert quote_found("uses max_tool_calls to stop", text)
    assert quote_found("a*b is a [link].", text)


def test_a_paraphrase_still_fails_against_text_with_markdown_escapes():
    assert not quote_found("uses max tool calls to stop", "uses max\\_tool\\_calls to stop")


def test_the_under_prefix_never_pushes_a_chunk_over_the_limit():
    text = "# Title\n" + "a" * 20 + "\n" + "b" * 20 + "\n" + "c" * 50 + "\n" + "d" * 37 + "\n" + "e" * 20
    chunks = chunk_text(text, 50, None)
    assert all(len(c) <= 50 for c in chunks)
    assert "c" * 50 in chunks  # exactly at the limit, so the prefix is left off rather than overflow
    assert "Under: Title\n" + "d" * 37 in chunks  # exactly at the limit with its prefix, so it keeps it
    assert all(any(line in c for c in chunks) for line in ("a" * 20, "b" * 20, "e" * 20))  # no line lost


def test_a_single_line_longer_than_the_limit_stays_whole():
    chunks = chunk_text("# Title\n" + "a" * 20 + "\n" + "x" * 80, 50, None)
    assert any("x" * 80 in c for c in chunks) and len(chunks) == 2

