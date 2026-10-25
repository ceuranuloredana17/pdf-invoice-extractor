"""Batch processing: PDF files in, :class:`ExtractionResult` objects out.

A failure on one file (corrupt PDF, scanned image, ...) is recorded in that
file's result and never aborts the rest of the batch.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from invoice_extractor.models import Invoice
from invoice_extractor.parser import InvoiceParser
from invoice_extractor.pdf_text import PdfTextError, extract_text
from invoice_extractor.validation import Issue, Severity, validate


@dataclass
class ExtractionResult:
    source: str
    invoice: Invoice | None = None
    issues: list[Issue] = field(default_factory=list)
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """True when extraction succeeded and no validation *errors* were found."""
        return self.invoice is not None and not any(
            issue.severity is Severity.ERROR for issue in self.issues
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "valid": self.is_valid,
            "error": self.error,
            "invoice": self.invoice.to_dict() if self.invoice else None,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def extract_file(path: str | Path, parser: InvoiceParser | None = None) -> ExtractionResult:
    path = Path(path)
    return _extract(path, str(path), parser)


def extract_bytes(
    data: bytes, name: str, parser: InvoiceParser | None = None
) -> ExtractionResult:
    """Extract from an in-memory PDF (e.g. an HTTP upload) without touching disk."""
    return _extract(io.BytesIO(data), name, parser)


def _extract(
    source: Path | IO[bytes], name: str, parser: InvoiceParser | None
) -> ExtractionResult:
    try:
        text = extract_text(source, name=Path(name).name)
    except PdfTextError as exc:
        return ExtractionResult(source=name, error=str(exc))

    invoice = (parser or InvoiceParser()).parse(text)
    return ExtractionResult(source=name, invoice=invoice, issues=validate(invoice))


def collect_pdfs(inputs: Iterable[str | Path]) -> list[Path]:
    """Expand directories (recursively) into a sorted, de-duplicated list of PDFs."""
    found: set[Path] = set()
    for item in map(Path, inputs):
        if item.is_dir():
            found.update(p for p in item.rglob("*") if p.suffix.lower() == ".pdf")
        else:
            found.add(item)
    return sorted(found)


def extract_many(paths: Iterable[str | Path], workers: int = 1) -> list[ExtractionResult]:
    """Extract every file, in input order.

    PDF parsing is CPU-bound, so ``workers > 1`` uses processes rather than
    threads to sidestep the GIL.
    """
    paths = list(paths)
    if workers <= 1 or len(paths) <= 1:
        return [extract_file(path) for path in paths]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(extract_file, paths))
