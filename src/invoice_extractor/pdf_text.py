"""Text extraction from PDF files (the only module that depends on pdfplumber).

Real-world invoices are messier than their on-screen look suggests, so the text
is rebuilt from word positions instead of relying on the PDF's internal order:

* **Fake bold** - some generators draw every glyph twice with a tiny offset
  ("FFaaccttuurraa"). Overlapping duplicate characters are removed.
* **Label/value on one visual line** - a label and its value are often separate
  text objects in different fonts, with slightly different baselines. Words are
  grouped into a line when their vertical centre falls inside the line's band.
* **Columns** - a wide horizontal gap between two words on the same line is
  rendered as :data:`COLUMN_SEPARATOR`, so the parser can tell
  "Vendor Ltd   Customer ID: 7" apart from a single phrase.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import IO, Any

import pdfplumber

COLUMN_SEPARATOR = "   "
# Gap (in PDF points) above which two words are considered separate columns.
# Ordinary word spacing is ~2-4 pt at typical invoice font sizes.
COLUMN_GAP = 10.0


class PdfTextError(Exception):
    """Raised when a PDF cannot be opened or contains no extractable text."""


def extract_text(source: str | Path | IO[bytes], name: str | None = None) -> str:
    """Return the text of all pages, one visual line per text line.

    ``source`` is a path or a binary file object (e.g. an uploaded file held in
    memory). ``name`` is only used in error messages.

    Raises:
        PdfTextError: the file is missing, is not a valid PDF, or has no text
            layer (e.g. a scanned image, which would need OCR).
    """
    if isinstance(source, (str, Path)):
        source = Path(source)
        name = name or source.name
    name = name or "document"
    try:
        with pdfplumber.open(source) as pdf:
            pages = [page_text(page) for page in pdf.pages]
    except FileNotFoundError as exc:
        raise PdfTextError(f"file not found: {source}") from exc
    except Exception as exc:  # pdfminer raises many unrelated exception types
        raise PdfTextError(f"cannot read PDF {name}: {exc}") from exc

    text = "\n".join(pages)
    if not text.strip():
        raise PdfTextError(f"{name} has no text layer (scanned PDF? OCR is not supported)")
    return text


def page_text(page: Any) -> str:
    """Rebuild the reading order of one pdfplumber page from word coordinates."""
    # Rotated text (e.g. captions next to barcodes) is skipped: it never
    # carries invoice fields and would otherwise be spliced into other lines.
    words = [w for w in page.dedupe_chars().extract_words() if w["upright"]]
    return "\n".join(_join_line(line) for line in group_lines(words))


def group_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group words into lines, top to bottom, each line sorted left to right.

    A word joins the current line when its vertical centre lies within the
    band of the line's first word, which tolerates small baseline shifts
    between fonts while keeping consecutive lines apart.
    """
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        centre = (word["top"] + word["bottom"]) / 2
        if lines and lines[-1][0]["top"] <= centre <= lines[-1][0]["bottom"]:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _join_line(words: list[dict[str, Any]]) -> str:
    parts = [words[0]["text"]]
    for previous, word in pairwise(words):
        gap = word["x0"] - previous["x1"]
        parts.append(COLUMN_SEPARATOR if gap > COLUMN_GAP else " ")
        parts.append(word["text"])
    return "".join(parts)
