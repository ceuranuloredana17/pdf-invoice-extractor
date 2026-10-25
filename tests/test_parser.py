from datetime import date
from decimal import Decimal

import pytest

from invoice_extractor.parser import InvoiceParser, Labels

US_INVOICE = """\
INVOICE
From: Acme Design Studio LLC
Invoice Number: INV-2026-0042
Invoice Date: October 3, 2026
Due Date: November 2, 2026
Bill To: Globex Corporation
Description Qty Unit Price Amount
Website redesign 1 $2,400.00 $2,400.00
Logo design 2 $350.00 $700.00
Subtotal: $3,286.00
Tax (8.5%): $279.31
Total Due: $3,565.31
"""

RO_INVOICE = """\
FACTURA
Furnizor: SC Pixel Soft SRL
Factura nr. PXS-1187
Data emiterii: 15.09.2026
Termen de plata: 15.10.2026
Client: Andromeda Tech SRL
Descriere Cant. Pret unitar Valoare
Licenta software anuala 3 1.250,00 3.750,00
Subtotal: 3.750,00 RON
TVA (19%): 712,50 RON
Total de plata: 4.462,50 RON
"""


# Layout of a real Romanian utility bill (as rebuilt by pdf_text), anonymized:
# diacritics in labels, "series / number" ids, no "Client:" label, a net/tax/gross
# summary row, and a total that includes the previous unpaid balance.
UTILITY_BILL = """\
Telecom Exemplu S.A.   Cod client: 1234567
Str. Exemplului nr. 1,   C.I.F.:
Factură seria și nr.: ABC25 / 98765432
Data:   06.08.2025
Perioada facturată: 01.08.2025 - 31.08.2025
Ultima zi de plată: 31.08.2025
Produse si servicii   Cant.   (lei) TVA (%)   (lei)   (lei)
1.1   Abonament internet   1   16,81   21   3,53   20,34
Factura curenta:   16,81   3,53   20,34
Sold precedent   Valoare sold precedent:   46,00
Total   Total de achitat:   66,34
Factura transmisa electronic conform acord din data de 02.08.2019
"""


@pytest.fixture
def parser():
    return InvoiceParser()


def test_parses_us_invoice(parser):
    invoice = parser.parse(US_INVOICE)

    assert invoice.invoice_number == "INV-2026-0042"
    assert invoice.vendor == "Acme Design Studio LLC"
    assert invoice.customer == "Globex Corporation"
    assert invoice.invoice_date == date(2026, 10, 3)
    assert invoice.due_date == date(2026, 11, 2)
    assert invoice.currency == "USD"
    assert invoice.subtotal == Decimal("3286.00")
    assert invoice.tax_rate == Decimal("8.5")
    assert invoice.tax == Decimal("279.31")
    assert invoice.total == Decimal("3565.31")
    assert [item.description for item in invoice.line_items] == ["Website redesign", "Logo design"]
    assert invoice.confidence == 1.0


def test_parses_romanian_invoice(parser):
    invoice = parser.parse(RO_INVOICE)

    assert invoice.invoice_number == "PXS-1187"
    assert invoice.vendor == "SC Pixel Soft SRL"
    assert invoice.customer == "Andromeda Tech SRL"
    assert invoice.invoice_date == date(2026, 9, 15)
    assert invoice.due_date == date(2026, 10, 15)
    assert invoice.currency == "RON"
    assert invoice.tax_rate == Decimal("19")
    assert invoice.total == Decimal("4462.50")
    assert invoice.line_items[0].quantity == Decimal("3")
    assert invoice.line_items[0].amount == Decimal("3750.00")


def test_parses_utility_bill_layout(parser):
    invoice = parser.parse(UTILITY_BILL)

    assert invoice.invoice_number == "ABC25 / 98765432"
    assert invoice.vendor == "Telecom Exemplu S.A."  # right-hand column cut off
    assert invoice.invoice_date == date(2025, 8, 6)  # not the contract date at the bottom
    assert invoice.due_date == date(2025, 8, 31)
    assert invoice.currency == "RON"
    assert invoice.subtotal == Decimal("16.81")
    assert invoice.tax == Decimal("3.53")
    assert invoice.previous_balance == Decimal("46.00")
    assert invoice.total == Decimal("66.34")


@pytest.mark.parametrize("label", ["Factură nr.", "FACTURĂ NR.", "Factura nr."])
def test_labels_match_with_or_without_diacritics(parser, label):
    assert parser.parse(f"{label} X-1").invoice_number == "X-1"


def test_summary_row_requires_consistent_math(parser):
    invoice = parser.parse("Total:   10,00   2,00   99,00")
    assert invoice.subtotal is None
    assert invoice.tax is None


def test_explicit_subtotal_takes_precedence_over_summary_row(parser):
    invoice = parser.parse("Subtotal: 50.00\nTax: 5.00\nTotal:   10,00   2,00   12,00")
    assert (invoice.subtotal, invoice.tax) == (Decimal("50.00"), Decimal("5.00"))


def test_subtotal_is_not_mistaken_for_total(parser):
    invoice = parser.parse("Subtotal: 100.00\nTotal: 119.00")
    assert invoice.subtotal == Decimal("100.00")
    assert invoice.total == Decimal("119.00")


def test_due_date_is_not_mistaken_for_invoice_date(parser):
    invoice = parser.parse("Due Date: 2026-11-02\nDate: 2026-10-03")
    assert invoice.invoice_date == date(2026, 10, 3)
    assert invoice.due_date == date(2026, 11, 2)


def test_title_line_is_not_an_invoice_number(parser):
    assert parser.parse("INVOICE\nInvoice #: A-17").invoice_number == "A-17"


def test_party_name_on_line_after_label(parser):
    invoice = parser.parse("Bill To:\n\n  Initech Inc.\n  1 Main St")
    assert invoice.customer == "Initech Inc."


def test_vendor_falls_back_to_first_line(parser):
    assert parser.parse("INVOICE\nUmbrella Ltd\nInvoice #: 9").vendor == "Umbrella Ltd"


def test_line_items_without_header_require_consistent_math(parser):
    text = "Widget 2 5.00 10.00\nOrder ref 2026 10 15 99\nGadget 3 1.50 4.50"
    items = parser.parse_line_items(text)
    assert [item.description for item in items] == ["Widget", "Gadget"]


def test_line_items_stop_at_totals_block(parser):
    text = "Description Qty Price Amount\nA 1 1.00 1.00\nTotal 1 1.00 1.00\nB 1 2.00 2.00"
    assert [item.description for item in parser.parse_line_items(text)] == ["A"]


def test_description_may_end_with_a_number(parser):
    items = parser.parse_line_items("Description\nRoom 101 2 50.00 100.00")
    assert items[0].description == "Room 101"
    assert items[0].quantity == Decimal("2")


def test_empty_text_gives_empty_invoice(parser):
    invoice = parser.parse("")
    assert invoice.invoice_number is None
    assert invoice.total is None
    assert invoice.line_items == []
    assert invoice.confidence == 0.0


def test_custom_labels_extend_the_parser():
    labels = Labels(invoice_number=("rechnungsnummer",), total=("gesamtbetrag",))
    invoice = InvoiceParser(labels).parse("Rechnungsnummer: RE-55\nGesamtbetrag: 1.190,00 EUR")
    assert invoice.invoice_number == "RE-55"
    assert invoice.total == Decimal("1190.00")
