from datetime import date
from decimal import Decimal

import pytest

from invoice_extractor.normalize import detect_currency, parse_amount, parse_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", "1234.56"),
        ("$1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("€1.234,56", "1234.56"),
        ("1 234,56 RON", "1234.56"),
        ("1,234,567.89", "1234567.89"),
        ("1.234.567,89", "1234567.89"),
        ("85,00", "85.00"),
        ("1,000", "1000"),  # 3 digits after a lone separator -> thousands
        ("1.000", "1000"),
        ("12.5", "12.5"),
        ("-12.50", "-12.50"),
        ("42", "42"),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", "$", ".,"])
def test_parse_amount_rejects_non_numbers(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-03", date(2026, 10, 3)),
        ("03.10.2026", date(2026, 10, 3)),
        ("03/10/2026", date(2026, 10, 3)),  # day-first by default
        ("25/10/2026", date(2026, 10, 25)),
        ("10/25/2026", date(2026, 10, 25)),  # impossible day-first -> month-first fallback
        ("October 3, 2026", date(2026, 10, 3)),
        ("Oct 3, 2026", date(2026, 10, 3)),
        ("Oct. 3rd, 2026", date(2026, 10, 3)),
        ("3 October 2026", date(2026, 10, 3)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_month_first_preference():
    assert parse_date("03/10/2026", day_first=False) == date(2026, 3, 10)


@pytest.mark.parametrize("raw", ["", "yesterday", "32/13/2026"])
def test_parse_date_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_date(raw)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Total: $100.00", "USD"),
        ("Total: €100,00", "EUR"),
        ("Total: 100,00 RON", "RON"),
        ("Total: 100 lei", "RON"),
        ("Paid in EUR, fee $5, total EUR 200", "EUR"),
        ("no currency here", None),
    ],
)
def test_detect_currency(text, expected):
    assert detect_currency(text) == expected
