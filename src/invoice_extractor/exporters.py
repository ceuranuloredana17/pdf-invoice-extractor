"""Serialize extraction results to JSON or CSV."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence

from invoice_extractor.pipeline import ExtractionResult

CSV_COLUMNS = (
    "source", "valid", "error", "invoice_number", "vendor", "customer", "invoice_date",
    "due_date", "currency", "subtotal", "tax_rate", "tax", "previous_balance", "total",
    "line_item_count",
    "confidence", "issues",
)


def to_json(results: Sequence[ExtractionResult]) -> str:
    return json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)


def to_csv(results: Sequence[ExtractionResult]) -> str:
    """One row per invoice; line items are summarized as a count."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for result in results:
        invoice = result.invoice.to_dict() if result.invoice else {}
        row = {column: invoice.get(column) for column in CSV_COLUMNS}
        row.update(
            source=result.source,
            valid=result.is_valid,
            error=result.error,
            line_item_count=len(invoice.get("line_items", [])),
            issues="; ".join(issue.code for issue in result.issues),
        )
        writer.writerow(row)
    return buffer.getvalue()


EXPORTERS = {"json": to_json, "csv": to_csv}
