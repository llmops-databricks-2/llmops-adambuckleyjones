"""Split the Laws of the Game PDF into one PDF per Law, plus one for the law changes, without images.

Page ranges come from the contents pages (PDF pages 6-7). Each Law starts one page early, on its "Law N" divider,
and ends before the next Law's divider. Once images are removed, pages with almost no text are dropped: photo pages
left with only a page number, the dividers themselves, and diagram pages that keep only their labels.

The law changes run from their own divider up to the Glossary divider.

Pages keep their original numbers as PDF page labels. ai_parse_document counts pages from 0 in each file and
ignores labels, so page_map.csv maps (file, file_page) back to the original page for citations.

Run from the repo root:
    uv run --with pypdf python scripts/split_laws.py
"""

import csv
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

SOURCE = Path("Laws of the Game 2026_27_single pages.pdf")
OUT_DIR = Path("data/laws")
CONTENTS_PAGES = (5, 6)
HEADER_LINES = {"Contents", "Laws of the Game 2026/27   |  Contents"}
MIN_PAGE_CHARS = 20
LAW_CHANGES_ENTRY = "Law changes 2026/27"
# Pages that are only diagram labels once images are removed (signals, goal line, handball). Checked by hand for
# 2026/27: recheck when a new edition is used.
DIAGRAM_PAGES = {79, 88, 89, 90, 104, 117}
MAX_LABEL_WORDS = 7


def read_contents(reader: PdfReader) -> list[tuple[str, int]]:
    """Return (entry, start page) pairs from the contents pages, in order."""
    entries: list[tuple[str, int]] = []
    for index in CONTENTS_PAGES:
        lines = [line.strip() for line in reader.pages[index].extract_text().splitlines()]
        lines = [line for line in lines[1:] if line and line not in HEADER_LINES]
        names = [line for line in lines if not line.isdigit()]
        pages = [int(line) for line in lines if line.isdigit()]
        if len(names) != len(pages):
            raise ValueError(f"Contents page {index + 1}: {len(names)} entries but {len(pages)} page numbers")
        entries.extend(zip(names, pages, strict=True))
    return entries


def law_ranges(entries: list[tuple[str, int]]) -> list[tuple[int, str, int, int]]:
    """Return (law number, title, first page, last page) for Laws 1-17, as 1-based PDF page numbers."""
    ranges = []
    for i, (name, start) in enumerate(entries):
        match = re.fullmatch(r"(\d{1,2}) (.+)", name)
        if match:
            next_start = entries[i + 1][1]
            ranges.append((int(match[1]), match[2], start - 1, next_start - 2))
    if [number for number, *_ in ranges] != list(range(1, 18)):
        raise ValueError(f"Expected Laws 1-17, found {[number for number, *_ in ranges]}")
    return ranges


def law_changes_range(entries: list[tuple[str, int]]) -> tuple[int, int]:
    """Return (first page, last page) of the law changes: from their divider up to the Glossary divider."""
    starts = dict(entries)
    return starts[LAW_CHANGES_ENTRY], starts["Glossary"] - 1


def write_part(reader: PdfReader, path: Path, title: str, first: int, last: int) -> list[int]:
    """Write pages first-last without images, near-empty or diagram pages, and return the original page numbers kept.

    Each kept page is labelled with its original page number, so a PDF viewer shows the same numbers as the full
    Laws of the Game. The printed number at the top or bottom of each page must match, or the page ranges are wrong.
    """
    writer = PdfWriter()
    for page_number in range(first, last + 1):
        writer.add_page(reader.pages[page_number - 1])
    writer.remove_images()

    originals = list(range(first, last + 1))
    texts = [page.extract_text().strip() for page in writer.pages]
    for n, text in zip(originals, texts, strict=True):
        body = [line for line in text.splitlines() if "Laws of the Game 2026/27" not in line]
        if n in DIAGRAM_PAGES and max(len(line.split()) for line in body) > MAX_LABEL_WORDS:
            raise ValueError(f"Page {n} has running text, so it is not a diagram page: update DIAGRAM_PAGES")
    kept = [
        (page, n)
        for page, n, text in zip(writer.pages, originals, texts, strict=True)
        if len(text) >= MIN_PAGE_CHARS and n not in DIAGRAM_PAGES
    ]
    for page, n in kept:
        lines = page.extract_text().strip().splitlines()
        if not (lines[0].startswith(str(n)) or lines[-1].strip() == str(n)):
            raise ValueError(f"{path.name}: page {n} does not carry its printed page number")
    for page in list(writer.pages):
        if all(page is not k for k, _ in kept):
            writer.remove_page(page)

    for index, (_, n) in enumerate(kept):
        writer.set_page_label(index, index, style="/D", start=n)
    writer.add_metadata({"/Title": title})
    with path.open("wb") as f:
        writer.write(f)
    return [n for _, n in kept]


def main() -> None:
    """Write one PDF per Law, one for the law changes, and page_map.csv linking file pages to original pages."""
    reader = PdfReader(SOURCE)
    entries = read_contents(reader)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    parts = []
    for number, title, first, last in law_ranges(entries):
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower().replace("’", "")).strip("_")
        parts.append((f"law_{number:02d}_{slug}.pdf", f"Law {number}: {title}", first, last))
    first, last = law_changes_range(entries)
    parts.append(("law_changes_2026_27.pdf", LAW_CHANGES_ENTRY, first, last))

    rows = []
    for file_name, title, first, last in parts:
        kept = write_part(reader, OUT_DIR / file_name, title, first, last)
        rows.extend((file_name, file_page, original) for file_page, original in enumerate(kept))
        print(f"{title:<42} pages {first}-{last}  kept {len(kept):>2}  -> {file_name}")

    with (OUT_DIR / "page_map.csv").open("w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows([("file", "file_page", "original_page"), *rows])
    print(f"Wrote {len(rows)} rows to {OUT_DIR / 'page_map.csv'}")


if __name__ == "__main__":
    main()
