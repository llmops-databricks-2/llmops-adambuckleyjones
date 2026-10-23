"""Tests for splitting parsed Law files into sections and chunks, on elements shaped like ai_parse_document output."""

import pytest

from referee_ai.laws_processor import chunk_section, clean_text, split_sections, table_to_text

FILE = "law_12_fouls_and_misconduct.pdf"
PAGE_MAP = {(FILE, 0): 115, (FILE, 1): 116, (FILE, 2): 118}


def element(kind: str, content: str, page_id: int = 0) -> dict:
    """Build one parsed element."""
    return {"type": kind, "content": content, "bbox": [{"page_id": page_id}]}


ELEMENTS = [
    element("title", "Fouls and\nMisconduct"),
    element("text", "Direct and indirect free kicks are awarded for offences."),
    element("section_header", "1. Direct free kick"),
    element(
        "text",
        "A direct free kick is awarded if a player\ncommits any of the following offences:\n\n• charges\n• jumps at",
    ),
    element("page_footer", "Laws of the Game 2026/27"),
    element("page_number", "115"),
    element("text", "• kicks or attempts to kick", page_id=1),
    element("section_header", "Handling the ball", page_id=1),
    element("text", "It is an offence if a player deliberately touches the ball with their hand.", page_id=1),
    element("figure", "IFAB", page_id=1),
    element("section_header", "2. Indirect free kick\nProcedure", page_id=2),
    element(
        "section_header",
        "Subject to the conditions explained below, both teams take five kicks and the kicks are taken alternately",
        page_id=2,
    ),
    element(
        "table",
        "<table><tr><th>Offence</th><th>Restart</th></tr><tr><td>Offside</td><td>IFK<br>at offence</td></tr></table>",
        page_id=2,
    ),
]


def test_numbered_headers_start_sections() -> None:
    """Text before section 1 becomes 12.0; numbered headers give 12.1 and 12.2 with the cleaned Law title."""
    sections = split_sections(FILE, ELEMENTS, PAGE_MAP)

    assert [(s.section, s.section_title) for s in sections] == [
        ("12.0", "Introduction"),
        ("12.1", "Direct free kick"),
        ("12.2", "Indirect free kick"),
    ]
    assert {s.law_title for s in sections} == {"Fouls and Misconduct"}


def test_sections_cite_original_pages_and_skip_page_furniture() -> None:
    """Text continues across the page break into the same section; footers, page numbers and figures are dropped."""
    section = split_sections(FILE, ELEMENTS, PAGE_MAP)[1]

    assert section.pages == [115, 116]
    assert "kicks or attempts to kick" in section.text
    assert "Laws of the Game" not in section.text
    assert "IFAB" not in section.text


def test_subheadings_and_misread_headers() -> None:
    """A merged header keeps its second line as a subheading; a sentence tagged as a header is kept as text."""
    sections = split_sections(FILE, ELEMENTS, PAGE_MAP)

    assert sections[1].parts[-1].subheading == "Handling the ball"
    assert {part.subheading for part in sections[2].parts} == {"Procedure"}
    assert sections[2].parts[0].text.startswith("Subject to the conditions")


def test_chunks_are_prefixed_with_law_and_section() -> None:
    """Each subheading block is its own chunk, and the prefix names the Law, section and subheading."""
    chunks = chunk_section(split_sections(FILE, ELEMENTS, PAGE_MAP)[1])

    assert [c.chunk_id for c in chunks] == ["12.1-0", "12.1-1"]
    assert chunks[1].text.startswith("Law 12 Fouls and Misconduct, 12.1 Direct free kick, Handling the ball\n\n")
    assert chunks[1].pages == [116]


def test_long_blocks_split_at_paragraphs() -> None:
    """A block over the word limit is split between paragraphs, and every piece keeps the section prefix."""
    section = split_sections(FILE, ELEMENTS, PAGE_MAP)[1]
    chunks = chunk_section(section, max_words=12)

    assert len(chunks) == 3
    assert all(c.text.startswith("Law 12 Fouls and Misconduct, 12.1 Direct free kick") for c in chunks)


def test_clean_text_rejoins_wrapped_lines() -> None:
    """Wrapped lines join into one paragraph; bullets stay on their own lines."""
    assert clean_text("A player\ncommits:\n\n• charges\n• jumps") == "A player commits:\n\n• charges\n• jumps"


def test_table_to_text() -> None:
    """Each table row becomes one line, with line breaks inside cells turned into semicolons."""
    assert table_to_text(ELEMENTS[-1]["content"]) == "Offence | Restart\nOffside | IFK; at offence"


def test_missing_page_in_map_fails() -> None:
    """A page missing from page_map.csv is an error, so no chunk is stored without its original page."""
    with pytest.raises(KeyError):
        split_sections(FILE, ELEMENTS, {(FILE, 0): 115})
