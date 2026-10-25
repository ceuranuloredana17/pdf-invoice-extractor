"""Domain models for extracted invoice data.

Monetary values use ``Decimal`` rather than ``float`` so that totals can be
compared exactly (0.1 + 0.2 == 0.3 holds for Decimal, not for float).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from decimal import Decimal
from typing import Any

CENT = Decimal("0.01")


@dataclass(frozen=True)
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal

    @property
    def expected_amount(self) -> Decimal:
        """Amount implied by quantity x unit price, rounded to cents."""
        return (self.quantity * self.unit_price).quantize(CENT)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: _serialize(getattr(self, f.name)) for f in fields(self)}


@dataclass
class Invoice:
    invoice_number: str | None = None
    vendor: str | None = None
    customer: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_rate: Decimal | None = None
    tax: Decimal | None = None
    # Unpaid amount from earlier invoices, included in ``total`` (utility bills).
    previous_balance: Decimal | None = None
    total: Decimal | None = None
    line_items: list[LineItem] = field(default_factory=list)

    # Fields used to compute the extraction confidence score.
    KEY_FIELDS = (
        "invoice_number",
        "vendor",
        "customer",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    )

    @property
    def confidence(self) -> float:
        """Share of key fields (plus line items) that were found, in [0, 1]."""
        found = sum(getattr(self, name) is not None for name in self.KEY_FIELDS)
        found += bool(self.line_items)
        return round(found / (len(self.KEY_FIELDS) + 1), 2)

    def to_dict(self) -> dict[str, Any]:
        data = {
            f.name: _serialize(getattr(self, f.name))
            for f in fields(self)
            if f.name != "line_items"
        }
        data["line_items"] = [item.to_dict() for item in self.line_items]
        data["confidence"] = self.confidence
        return data


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
