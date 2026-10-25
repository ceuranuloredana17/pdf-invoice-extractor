from datetime import date
from decimal import Decimal

import pytest

from invoice_extractor.models import Invoice, LineItem
from invoice_extractor.validation import Severity, validate


def make_invoice(**overrides) -> Invoice:
    fields = dict(
        invoice_number="INV-1",
        vendor="Acme",
        customer="Globex",
        invoice_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        currency="USD",
        subtotal=Decimal("150.00"),
        tax_rate=Decimal("10"),
        tax=Decimal("15.00"),
        total=Decimal("165.00"),
        line_items=[
            LineItem("A", Decimal("1"), Decimal("100.00"), Decimal("100.00")),
            LineItem("B", Decimal("2"), Decimal("25.00"), Decimal("50.00")),
        ],
    )
    fields.update(overrides)
    return Invoice(**fields)


def codes(issues):
    return {issue.code for issue in issues}


def test_consistent_invoice_has_no_issues():
    assert validate(make_invoice()) == []


def test_missing_required_fields_are_errors():
    issues = validate(make_invoice(invoice_number=None, total=None))
    assert {"missing_invoice_number", "missing_total"} <= codes(issues)
    assert all(i.severity is Severity.ERROR for i in issues if i.code.startswith("missing_"))


def test_missing_recommended_field_is_warning():
    [issue] = validate(make_invoice(vendor=None))
    assert issue.code == "missing_vendor"
    assert issue.severity is Severity.WARNING


def test_total_mismatch():
    assert "total_mismatch" in codes(validate(make_invoice(total=Decimal("170.00"))))


def test_previous_balance_is_part_of_the_total():
    invoice = make_invoice(previous_balance=Decimal("46.00"), total=Decimal("211.00"))
    assert validate(invoice) == []


def test_total_mismatch_mentions_previous_balance():
    invoice = make_invoice(previous_balance=Decimal("46.00"), total=Decimal("165.00"))
    [issue] = validate(invoice)
    assert issue.code == "total_mismatch"
    assert "previous balance" in issue.message


def test_subtotal_mismatch():
    assert "subtotal_mismatch" in codes(validate(make_invoice(subtotal=Decimal("140.00"))))


def test_line_item_mismatch():
    bad = [LineItem("A", Decimal("3"), Decimal("10.00"), Decimal("35.00"))]
    issues = validate(make_invoice(line_items=bad, subtotal=Decimal("35.00"),
                                   tax=Decimal("3.50"), total=Decimal("38.50")))
    assert codes(issues) == {"line_item_mismatch"}


def test_tax_rate_mismatch():
    assert "tax_rate_mismatch" in codes(validate(make_invoice(tax_rate=Decimal("20"))))


def test_due_date_before_issue_date():
    assert "due_before_issue" in codes(validate(make_invoice(due_date=date(2026, 9, 1))))


@pytest.mark.parametrize("delta", ["0.01", "-0.01"])
def test_rounding_within_tolerance_is_accepted(delta):
    assert validate(make_invoice(total=Decimal("165.00") + Decimal(delta))) == []
