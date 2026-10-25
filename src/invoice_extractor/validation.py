"""Business-rule validation of an extracted invoice.

Extraction is heuristic, so every result is cross-checked: line items must
add up to the subtotal, subtotal + tax must equal the total, and so on. A
mismatch usually means a field was mis-read, which is exactly what a human
reviewer needs to be told about.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from invoice_extractor.models import CENT, Invoice

REQUIRED_FIELDS = ("invoice_number", "total")
RECOMMENDED_FIELDS = ("vendor", "customer", "invoice_date", "currency")


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    severity: Severity

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity.value}


def validate(invoice: Invoice, tolerance: Decimal = CENT) -> list[Issue]:
    """Return all problems found in ``invoice`` (empty list means it is consistent).

    ``tolerance`` absorbs rounding differences of a cent or so between the
    printed totals and the recomputed ones.
    """
    issues: list[Issue] = []

    for name in REQUIRED_FIELDS:
        if getattr(invoice, name) is None:
            issues.append(Issue(f"missing_{name}", f"Required field '{name}' not found",
                                Severity.ERROR))
    for name in RECOMMENDED_FIELDS:
        if getattr(invoice, name) is None:
            issues.append(Issue(f"missing_{name}", f"Field '{name}' not found",
                                Severity.WARNING))

    for index, item in enumerate(invoice.line_items, start=1):
        if abs(item.expected_amount - item.amount) > tolerance:
            issues.append(Issue(
                "line_item_mismatch",
                f"Line {index} ({item.description!r}): {item.quantity} x {item.unit_price} "
                f"= {item.expected_amount}, but amount is {item.amount}",
                Severity.WARNING,
            ))

    if invoice.line_items and invoice.subtotal is not None:
        items_sum = sum((item.amount for item in invoice.line_items), Decimal(0))
        if abs(items_sum - invoice.subtotal) > tolerance:
            issues.append(Issue(
                "subtotal_mismatch",
                f"Line items sum to {items_sum}, but subtotal is {invoice.subtotal}",
                Severity.ERROR,
            ))

    if None not in (invoice.subtotal, invoice.tax, invoice.total):
        expected_total = invoice.subtotal + invoice.tax
        formula = "Subtotal + tax"
        if invoice.previous_balance is not None:
            expected_total += invoice.previous_balance
            formula += " + previous balance"
        if abs(expected_total - invoice.total) > tolerance:
            issues.append(Issue(
                "total_mismatch",
                f"{formula} = {expected_total}, but total is {invoice.total}",
                Severity.ERROR,
            ))

    if None not in (invoice.subtotal, invoice.tax_rate, invoice.tax):
        expected_tax = (invoice.subtotal * invoice.tax_rate / 100).quantize(CENT)
        if abs(expected_tax - invoice.tax) > tolerance:
            issues.append(Issue(
                "tax_rate_mismatch",
                f"{invoice.tax_rate}% of {invoice.subtotal} = {expected_tax}, "
                f"but tax is {invoice.tax}",
                Severity.WARNING,
            ))

    if invoice.invoice_date and invoice.due_date and invoice.due_date < invoice.invoice_date:
        issues.append(Issue(
            "due_before_issue",
            f"Due date {invoice.due_date} is before invoice date {invoice.invoice_date}",
            Severity.WARNING,
        ))

    return issues
