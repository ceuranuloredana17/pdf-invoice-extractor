"""Normalization of raw strings (amounts, dates, currencies) into typed values.

These functions are pure (no I/O) so they are trivial to unit test.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
ISO_CURRENCIES = ("USD", "EUR", "GBP", "RON", "CHF")

_ISO_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")
_DAY_FIRST_FORMATS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y")
_MONTH_FIRST_FORMATS = ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y")
_TEXT_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y")


def parse_amount(raw: str) -> Decimal:
    """Parse a monetary amount written in US or European style.

    Examples: ``"$1,234.56"``, ``"1.234,56 RON"``, ``"€85,00"``, ``"-12.50"``.

    The decimal separator is inferred from the string itself:
      * if both ``,`` and ``.`` appear, the right-most one is the decimal separator;
      * if only one kind appears once and is followed by exactly 3 digits, it is
        treated as a thousands separator (invoices use 2 decimals for money);
      * a separator that appears several times is always a thousands separator.

    Raises:
        ValueError: if the string contains no parseable number.
    """
    cleaned = re.sub(r"[^\d,.\-]", "", raw)
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-").strip(".,")
    if not re.search(r"\d", cleaned):
        raise ValueError(f"no amount found in {raw!r}")

    decimal_sep = _infer_decimal_separator(cleaned)
    if decimal_sep is None:
        digits = cleaned.replace(",", "").replace(".", "")
    else:
        thousands_sep = "." if decimal_sep == "," else ","
        digits = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")

    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount {raw!r}") from exc
    return -value if negative else value


def _infer_decimal_separator(number: str) -> str | None:
    last_comma, last_dot = number.rfind(","), number.rfind(".")
    if last_comma != -1 and last_dot != -1:
        return "," if last_comma > last_dot else "."
    for sep, position in ((",", last_comma), (".", last_dot)):
        if position == -1:
            continue
        digits_after = len(number) - position - 1
        if number.count(sep) == 1 and digits_after != 3:
            return sep
        return None
    return None


def parse_date(raw: str, *, day_first: bool = True) -> date:
    """Parse a date in one of the common invoice formats.

    ``day_first`` resolves ambiguous numeric dates such as ``03/04/2026``
    (3 April vs. March 4). If the preferred interpretation is impossible
    (e.g. ``10/25/2026`` with day_first=True), the other one is tried.

    Raises:
        ValueError: if no known format matches.
    """
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).replace(" ,", ",")
    text = re.sub(r"^([A-Za-z]{3})\.", r"\1", text)  # "Oct. 3, 2026" -> "Oct 3, 2026"

    numeric = (
        _DAY_FIRST_FORMATS + _MONTH_FIRST_FORMATS
        if day_first
        else _MONTH_FIRST_FORMATS + _DAY_FIRST_FORMATS
    )
    for fmt in _ISO_FORMATS + numeric + _TEXT_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {raw!r}")


def detect_currency(text: str) -> str | None:
    """Return the most frequently mentioned currency in ``text`` (ISO 4217 code)."""
    counts: Counter[str] = Counter()
    for code in re.findall(rf"\b({'|'.join(ISO_CURRENCIES)})\b", text):
        counts[code] += 1
    for symbol, code in CURRENCY_SYMBOLS.items():
        counts[code] += text.count(symbol)
    counts["RON"] += len(re.findall(r"\blei\b", text, flags=re.IGNORECASE))

    if not counts or counts.most_common(1)[0][1] == 0:
        return None
    return counts.most_common(1)[0][0]
