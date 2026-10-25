"""Generate realistic sample invoice PDFs for demos and integration tests.

Requires the ``dev`` extra (reportlab). Usage::

    python -m invoice_extractor.sample_invoices samples/
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SampleInvoice:
    title: str
    header: tuple[str, ...]
    columns: tuple[str, str, str, str]
    rows: tuple[tuple[str, str, str, str], ...]
    totals: tuple[str, ...]


SAMPLES: dict[str, SampleInvoice] = {
    # US layout: "$1,234.56", month-name dates.
    "acme_us.pdf": SampleInvoice(
        title="INVOICE",
        header=(
            "From: Acme Design Studio LLC",
            "Invoice Number: INV-2026-0042",
            "Invoice Date: October 3, 2026",
            "Due Date: November 2, 2026",
            "Bill To: Globex Corporation",
        ),
        columns=("Description", "Qty", "Unit Price", "Amount"),
        rows=(
            ("Website redesign", "1", "$2,400.00", "$2,400.00"),
            ("Logo design", "2", "$350.00", "$700.00"),
            ("Hosting (12 months)", "12", "$15.50", "$186.00"),
        ),
        totals=("Subtotal: $3,286.00", "Tax (8.5%): $279.31", "Total Due: $3,565.31"),
    ),
    # Romanian layout: "1.234,56 RON", dd.mm.yyyy dates.
    "pixelsoft_ro.pdf": SampleInvoice(
        title="FACTURA",
        header=(
            "Furnizor: SC Pixel Soft SRL",
            "Factura nr. PXS-1187",
            "Data emiterii: 15.09.2026",
            "Termen de plata: 15.10.2026",
            "Client: Andromeda Tech SRL",
        ),
        columns=("Descriere", "Cant.", "Pret unitar", "Valoare"),
        rows=(
            ("Licenta software anuala", "3", "1.250,00", "3.750,00"),
            ("Instruire utilizatori", "8", "200,00", "1.600,00"),
        ),
        totals=("Subtotal: 5.350,00 RON", "TVA (19%): 1.016,50 RON",
                "Total de plata: 6.366,50 RON"),
    ),
    # EU layout: "€1.234,56", dd/mm/yyyy dates.
    "nordlicht_eu.pdf": SampleInvoice(
        title="INVOICE",
        header=(
            "Vendor: Nordlicht Media GmbH",
            "Invoice No: NM/2026/317",
            "Date: 28/08/2026",
            "Payment Due: 27/09/2026",
            "Customer: Blue Harbor B.V.",
        ),
        columns=("Description", "Qty", "Unit Price", "Amount"),
        rows=(
            ("Video editing (hours)", "14", "€85,00", "€1.190,00"),
            ("Color grading", "1", "€450,00", "€450,00"),
        ),
        totals=("Subtotal: €1.640,00", "VAT 21%: €344,40", "Grand Total: €1.984,40"),
    ),
}

_COLUMN_X = (50, 300, 370, 470)


def render(sample: SampleInvoice, path: str | Path) -> Path:
    """Draw ``sample`` as a one-page A4 PDF at ``path``."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = Path(path)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 60

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, sample.title)
    y -= 35

    pdf.setFont("Helvetica", 11)
    for line in sample.header:
        pdf.drawString(50, y, line)
        y -= 18
    y -= 20

    pdf.setFont("Helvetica-Bold", 11)
    for x, heading in zip(_COLUMN_X, sample.columns, strict=True):
        pdf.drawString(x, y, heading)
    y -= 6
    pdf.line(50, y, 545, y)
    y -= 16

    pdf.setFont("Helvetica", 11)
    for row in sample.rows:
        for x, cell in zip(_COLUMN_X, row, strict=True):
            pdf.drawString(x, y, cell)
        y -= 18
    y -= 10
    pdf.line(50, y + 8, 545, y + 8)

    for line in sample.totals:
        pdf.drawRightString(545, y - 6, line)
        y -= 18

    pdf.save()
    return path


def generate_all(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return [render(sample, directory / name) for name, sample in SAMPLES.items()]


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "samples"
    for generated in generate_all(out_dir):
        print(generated)
