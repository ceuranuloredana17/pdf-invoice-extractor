"""Rule-based parser that turns invoice *text* into an :class:`Invoice`.

The parser never touches files: it receives plain text. PDF reading lives in
:mod:`invoice_extractor.pdf_text`. Keeping the two apart means the parsing
logic can be unit-tested with plain strings, and another text source (OCR,
DOCX, e-mail body) can be plugged in without changing the parser.

Labels are configurable through :class:`Labels`, so supporting a new language
or a vendor-specific layout means passing a different label set, not editing
the regular expressions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from invoice_extractor.models import Invoice, LineItem
from invoice_extractor.normalize import detect_currency, parse_amount, parse_date

# Horizontal whitespace only, so a value is never taken from the next line.
H = r"[^\S\r\n]"
AMOUNT = r"-?(?:[$€£]" + H + r"?)?\d(?:[\d.,]*\d)?"
CURRENCY_PREFIX = rf"(?:(?:[$€£]|[A-Z]{{3}}){H}?)?"
DATE = (
    r"\d{1,4}[./-]\d{1,2}[./-]\d{2,4}"
    rf"|[A-Za-z]{{3,9}}\.?{H}+\d{{1,2}}(?:st|nd|rd|th)?,?{H}+\d{{4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?{H}+[A-Za-z]{{3,9}}\.?,?{H}+\d{{4}}"
)
LINE_ITEM = re.compile(
    rf"^(?P<description>.+?){H}+(?P<quantity>\d+(?:[.,]\d+)?){H}+"
    rf"(?P<unit_price>{AMOUNT}){H}+(?P<amount>{AMOUNT})(?:{H}+[A-Z]{{3}})?{H}*$"
)
# Invoice ids such as "INV-2026-0042" or a series + number like "FDB25 / 61461216".
INVOICE_ID = (
    r"[A-Z0-9][A-Z0-9\-/]*\d[A-Z0-9\-/]*"
    rf"(?:{H}?/{H}?[A-Z0-9][A-Z0-9\-]*)*"
)
# pdf_text marks a wide gap between words (i.e. a new column) with 3+ spaces.
COLUMN_BREAK = re.compile(rf"{H}{{3,}}")

# Labels are written without diacritics and match both spellings, so
# "factura" also matches "Factură" and "data scadentei" matches "Data scadenței".
_DIACRITIC_VARIANTS = {"a": "aăâ", "i": "iî", "s": "sșş", "t": "tțţ"}


@dataclass(frozen=True)
class Labels:
    """Label synonyms (case- and diacritic-insensitive) recognized for each field."""

    invoice_number: tuple[str, ...] = (
        "invoice number", "invoice no", "invoice #", "invoice",
        "factura seria si nr", "factura seria", "factura nr", "numar factura", "factura",
    )
    invoice_date: tuple[str, ...] = (
        "invoice date", "date of issue", "issue date", "date",
        "data emiterii", "data facturii", "data",
    )
    due_date: tuple[str, ...] = (
        "due date", "payment due", "date due",
        "termen de plata", "data scadentei", "data scadenta", "scadenta", "ultima zi de plata",
    )
    vendor: tuple[str, ...] = ("from", "vendor", "seller", "supplier", "furnizor")
    customer: tuple[str, ...] = ("bill to", "billed to", "customer", "client", "cumparator")
    subtotal: tuple[str, ...] = ("subtotal", "sub-total", "net amount", "total fara tva")
    tax: tuple[str, ...] = ("vat", "tax", "sales tax", "tva")
    total: tuple[str, ...] = (
        "total due", "amount due", "balance due", "grand total",
        "total de plata", "total de achitat", "total factura", "total",
    )
    # A row with three amounts "net  tax  gross", e.g. "Factura curenta: 38,66 8,12 46,78".
    summary_row: tuple[str, ...] = ("factura curenta", "total factura", "totaluri", "total")
    previous_balance: tuple[str, ...] = (
        "previous balance", "balance forward", "sold precedent", "valoare sold precedent",
    )
    table_header: tuple[str, ...] = ("description", "descriere", "item", "service", "details")


def _label_regex(label: str) -> str:
    parts = []
    for char in label:
        if char == " ":
            parts.append(H + "+")
        elif char.lower() in _DIACRITIC_VARIANTS:
            parts.append(f"[{_DIACRITIC_VARIANTS[char.lower()]}]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def _alternation(labels: Iterable[str]) -> str:
    """Build ``(?:a|b|c)`` with the longest label first, so that e.g.
    "invoice number" wins over its prefix "invoice"."""
    ordered = sorted(labels, key=len, reverse=True)
    return "(?:" + "|".join(_label_regex(label) for label in ordered) + ")"


class InvoiceParser:
    """Extracts invoice fields from text using label-anchored regular expressions."""

    def __init__(self, labels: Labels | None = None, *, day_first: bool = True) -> None:
        self.labels = labels or Labels()
        self.day_first = day_first
        flags = re.IGNORECASE | re.MULTILINE
        lb = self.labels

        self._number_re = re.compile(
            rf"(?<!\w){_alternation(lb.invoice_number)}{H}*[:#.]*{H}*(?P<value>{INVOICE_ID})",
            flags,
        )
        # "(?<!due )" stops the generic "date" label from matching "Due Date".
        self._invoice_date_re = re.compile(
            rf"(?<!\w)(?<!due ){_alternation(lb.invoice_date)}{H}*[:\-]?{H}*(?P<value>{DATE})",
            flags,
        )
        self._due_date_re = re.compile(
            rf"(?<!\w){_alternation(lb.due_date)}{H}*[:\-]?{H}*(?P<value>{DATE})", flags
        )
        self._subtotal_re = self._amount_pattern(lb.subtotal)
        self._tax_re = self._amount_pattern(lb.tax)
        self._total_re = self._amount_pattern(lb.total)
        self._previous_balance_re = self._amount_pattern(lb.previous_balance)
        self._summary_row_re = re.compile(
            rf"(?<!\w){_alternation(lb.summary_row)}{H}*:?{H}*"
            rf"(?P<net>{AMOUNT}){H}+(?P<tax>{AMOUNT}){H}+(?P<gross>{AMOUNT}){H}*$",
            flags,
        )
        self._vendor_re = self._party_pattern(lb.vendor)
        self._customer_re = self._party_pattern(lb.customer)
        self._header_re = re.compile(rf"(?<!\w){_alternation(lb.table_header)}(?!\w)", flags)
        self._totals_start_re = re.compile(
            rf"^{H}*{_alternation(lb.subtotal + lb.total + lb.tax)}(?!\w)", flags
        )

    @staticmethod
    def _amount_pattern(labels: Iterable[str]) -> re.Pattern[str]:
        # Optional rate such as "(19%)" or "19%" between label and amount.
        return re.compile(
            rf"(?<!\w){_alternation(labels)}{H}*"
            rf"(?:\(?{H}*(?P<rate>\d+(?:[.,]\d+)?){H}*%{H}*\)?)?{H}*[:\-]?{H}*"
            rf"{CURRENCY_PREFIX}(?P<value>{AMOUNT})",
            re.IGNORECASE | re.MULTILINE,
        )

    @staticmethod
    def _party_pattern(labels: Iterable[str]) -> re.Pattern[str]:
        return re.compile(
            rf"^{H}*{_alternation(labels)}{H}*:{H}*(?P<value>.*)$",
            re.IGNORECASE | re.MULTILINE,
        )

    # ------------------------------------------------------------------ public

    def parse(self, text: str) -> Invoice:
        tax_match = self._tax_re.search(text)
        subtotal = self._find_amount(self._subtotal_re, text)
        tax = _safe_amount(tax_match.group("value")) if tax_match else None
        if subtotal is None and tax is None:
            subtotal, tax = self._find_summary_row(text)

        return Invoice(
            invoice_number=self._first_group(self._number_re, text),
            vendor=self._find_party(self._vendor_re, text) or self._fallback_vendor(text),
            customer=self._find_party(self._customer_re, text),
            invoice_date=self._find_date(self._invoice_date_re, text),
            due_date=self._find_date(self._due_date_re, text),
            currency=detect_currency(text),
            subtotal=subtotal,
            tax_rate=_safe_amount(tax_match.group("rate")) if tax_match else None,
            tax=tax,
            previous_balance=self._find_amount(self._previous_balance_re, text),
            total=self._find_amount(self._total_re, text),
            line_items=self.parse_line_items(text),
        )

    def _find_summary_row(self, text: str) -> tuple[Decimal | None, Decimal | None]:
        """Fallback for layouts that print net, tax and gross on one row.

        A row is accepted only if net + tax == gross, so an unrelated line with
        three numbers is not mistaken for the totals.
        """
        for match in self._summary_row_re.finditer(text):
            net, tax, gross = (_safe_amount(match[name]) for name in ("net", "tax", "gross"))
            if None not in (net, tax, gross) and net + tax == gross:
                return net, tax
        return None, None

    def parse_line_items(self, text: str) -> list[LineItem]:
        """Parse table rows of the form ``description qty unit_price amount``.

        If a table header (e.g. "Description ...") is found, only rows between
        it and the totals block are considered. Without a header every line is
        a candidate, but a row is accepted only when qty x price == amount, to
        avoid picking up unrelated lines that happen to end in numbers.
        """
        lines = text.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if self._header_re.search(line)), None)
        candidates = lines[start:] if start is not None else lines
        require_consistency = start is None

        items: list[LineItem] = []
        for line in candidates:
            if start is not None and self._totals_start_re.search(line):
                break
            item = self._parse_line_item(line)
            if item is None:
                continue
            if require_consistency and item.expected_amount != item.amount:
                continue
            items.append(item)
        return items

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _parse_line_item(line: str) -> LineItem | None:
        match = LINE_ITEM.match(line.strip())
        if not match:
            return None
        try:
            return LineItem(
                description=match["description"].strip(),
                quantity=parse_amount(match["quantity"]),
                unit_price=parse_amount(match["unit_price"]),
                amount=parse_amount(match["amount"]),
            )
        except ValueError:
            return None

    @staticmethod
    def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        return match.group("value").strip() if match else None

    def _find_date(self, pattern: re.Pattern[str], text: str) -> date | None:
        for match in pattern.finditer(text):
            try:
                return parse_date(match.group("value"), day_first=self.day_first)
            except ValueError:
                continue
        return None

    @staticmethod
    def _find_amount(pattern: re.Pattern[str], text: str) -> Decimal | None:
        for match in pattern.finditer(text):
            value = _safe_amount(match.group("value"))
            if value is not None:
                return value
        return None

    @staticmethod
    def _find_party(pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        if not match:
            return None
        if value := _first_column(match.group("value")):
            return value
        # Label on its own line: the name is on the next non-empty line.
        following = text[match.end():].splitlines()
        return next((_first_column(line) for line in following if line.strip()), None)

    @staticmethod
    def _fallback_vendor(text: str) -> str | None:
        """Most invoices start with the issuer's name; skip a bare title line."""
        for line in text.splitlines():
            first = _first_column(line)
            if first and first.lower() not in {"invoice", "factura", "tax invoice"}:
                return first
        return None


def _first_column(line: str) -> str:
    """Text before the first column break: "Acme Ltd   Client ID: 7" -> "Acme Ltd"."""
    return COLUMN_BREAK.split(line.strip(), maxsplit=1)[0]


def _safe_amount(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return parse_amount(raw)
    except ValueError:
        return None
