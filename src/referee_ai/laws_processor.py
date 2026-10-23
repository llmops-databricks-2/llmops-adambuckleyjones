"""Split parsed Laws of the Game files into law sections and retrieval chunks.

laws_parsed (one ai_parse_document result per Law file)
   ↓ split_sections: numbered headers ("2. Offside offence") start a section,
   ↓ other headers are subheadings inside it, footers and page numbers are dropped
Section (one per numbered section, e.g. Law 12.4)      -> laws table
   ↓ chunk_section: one chunk per subheading block, long blocks split by paragraph
Chunk (text prefixed with its law and section)          -> laws_chunks table

Page numbers are mapped back to the full Laws of the Game with page_map.csv, so every section and chunk can cite
the original pages.
"""

import re
from dataclasses import dataclass, field
from html import unescape

NUMBERED_HEADER = re.compile(r"(\d{1,2})\.\s+(.+)")
LAW_FILE = re.compile(r"law_(\d{2})_")
SKIPPED_TYPES = {"page_header", "page_footer", "page_number", "figure", "caption"}
MAX_SUBHEADING_WORDS = 12
MAX_CHUNK_WORDS = 400


@dataclass
class Part:
    """A piece of section text, under an optional subheading, on one original page."""

    subheading: str | None
    text: str
    page: int


@dataclass
class Section:
    """One numbered section of a Law, e.g. Law 12.4 Disciplinary action."""

    law_number: int
    law_title: str
    section: str
    section_title: str
    parts: list[Part] = field(default_factory=list)

    @property
    def pages(self) -> list[int]:
        """Original pages the section appears on."""
        return sorted({part.page for part in self.parts})

    @property
    def text(self) -> str:
        """Section text, with each subheading on its own line before its text."""
        lines, subheading = [], None
        for part in self.parts:
            if part.subheading != subheading:
                subheading = part.subheading
                if subheading:
                    lines.append(subheading)
            lines.append(part.text)
        return "\n\n".join(lines)


@dataclass
class Chunk:
    """A retrieval chunk: one subheading block of a section, or part of a long one."""

    chunk_id: str
    law_number: int
    law_title: str
    section: str
    section_title: str
    subheading: str | None
    text: str
    pages: list[int]


def law_number_from_file(file_name: str) -> int | None:
    """Return the Law number in a file name such as law_11_offside.pdf, or None for other files."""
    match = LAW_FILE.match(file_name)
    return int(match[1]) if match else None


def normalise(text: str) -> str:
    """Collapse all whitespace, including line breaks, to single spaces."""
    return " ".join(text.split())


def clean_text(content: str) -> str:
    """Rejoin hard-wrapped lines into paragraphs, keeping bullets on their own lines."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", content):
        lines: list[str] = []
        for line in (line.strip() for line in block.splitlines()):
            if not line:
                continue
            if lines and not line.startswith("•"):
                lines[-1] = f"{lines[-1]} {line}"
            else:
                lines.append(line)
        if lines:
            paragraphs.append("\n".join(normalise(line) for line in lines))
    return "\n\n".join(paragraphs)


def table_to_text(html: str) -> str:
    """Turn an HTML table into one line per row, cells separated by ' | '."""
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)
        cells = [normalise(unescape(re.sub(r"<br\s*/?>", "; ", cell))) for cell in cells]
        rows.append(" | ".join(cell for cell in cells if cell))
    return "\n".join(row for row in rows if row)


def split_sections(file_name: str, elements: list[dict], page_map: dict[tuple[str, int], int]) -> list[Section]:
    """Split one parsed Law file into its numbered sections.

    Text before the first numbered header becomes section N.0, "Introduction". A header that is really a sentence
    (more than MAX_SUBHEADING_WORDS words) is kept as text. Sections with no text are dropped.
    """
    law_number = law_number_from_file(file_name)
    if law_number is None:
        raise ValueError(f"{file_name} is not a Law file")

    law_title = ""
    sections: list[Section] = []
    subheading: str | None = None

    def current() -> Section:
        if not sections:
            sections.append(Section(law_number, law_title, f"{law_number}.0", "Introduction"))
        return sections[-1]

    for element in elements:
        kind, content = element.get("type"), element.get("content") or ""
        if kind in SKIPPED_TYPES or not content.strip():
            continue
        page = page_map[(file_name, element["bbox"][0]["page_id"])]

        if kind == "title":
            law_title = law_title or normalise(content)
            continue

        if kind == "section_header":
            first, *rest = [line.strip() for line in content.strip().splitlines() if line.strip()]
            numbered = NUMBERED_HEADER.fullmatch(first)
            if numbered:
                sections.append(Section(law_number, law_title, f"{law_number}.{numbered[1]}", normalise(numbered[2])))
                subheading = normalise(" ".join(rest)) or None
                continue
            if len(content.split()) <= MAX_SUBHEADING_WORDS:
                current()
                subheading = normalise(content)
                continue

        text = table_to_text(content) if kind == "table" else clean_text(content)
        current().parts.append(Part(subheading, text, page))

    return [section for section in sections if section.parts]


def chunk_section(section: Section, max_words: int = MAX_CHUNK_WORDS) -> list[Chunk]:
    """Chunk a section by subheading block, splitting blocks longer than max_words at paragraph breaks."""
    blocks: list[tuple[str | None, list[tuple[str, int]]]] = []
    for part in section.parts:
        if not blocks or blocks[-1][0] != part.subheading:
            blocks.append((part.subheading, []))
        blocks[-1][1].extend((paragraph, part.page) for paragraph in part.text.split("\n\n"))

    chunks: list[Chunk] = []
    for subheading, paragraphs in blocks:
        pieces: list[list[tuple[str, int]]] = [[]]
        for paragraph, page in paragraphs:
            words = sum(len(text.split()) for text, _ in pieces[-1])
            if pieces[-1] and words + len(paragraph.split()) > max_words:
                pieces.append([])
            pieces[-1].append((paragraph, page))

        for piece in pieces:
            heading = f"Law {section.law_number} {section.law_title}, {section.section} {section.section_title}"
            if subheading:
                heading = f"{heading}, {subheading}"
            body = "\n\n".join(text for text, _ in piece)
            chunks.append(
                Chunk(
                    chunk_id=f"{section.section}-{len(chunks)}",
                    law_number=section.law_number,
                    law_title=section.law_title,
                    section=section.section,
                    section_title=section.section_title,
                    subheading=subheading,
                    text=f"{heading}\n\n{body}",
                    pages=sorted({page for _, page in piece}),
                )
            )
    return chunks
