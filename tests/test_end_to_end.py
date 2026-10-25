"""Integration tests: real PDFs -> pipeline -> exporters -> CLI."""

import csv
import io
import json
from decimal import Decimal

import pytest

from invoice_extractor.cli import main
from invoice_extractor.exporters import to_csv, to_json
from invoice_extractor.pdf_text import PdfTextError, extract_text
from invoice_extractor.pipeline import collect_pdfs, extract_file, extract_many

EXPECTED_TOTALS = {
    "acme_us.pdf": ("INV-2026-0042", "USD", Decimal("3565.31")),
    "nordlicht_eu.pdf": ("NM/2026/317", "EUR", Decimal("1984.40")),
    "pixelsoft_ro.pdf": ("PXS-1187", "RON", Decimal("6366.50")),
}


@pytest.mark.parametrize("name", sorted(EXPECTED_TOTALS))
def test_sample_pdfs_are_fully_extracted(sample_dir, name):
    result = extract_file(sample_dir / name)

    number, currency, total = EXPECTED_TOTALS[name]
    assert result.error is None
    assert result.invoice.invoice_number == number
    assert result.invoice.currency == currency
    assert result.invoice.total == total
    assert result.invoice.confidence == 1.0
    assert result.issues == []
    assert result.is_valid


def test_corrupt_pdf_is_reported_not_raised(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")

    result = extract_file(broken)

    assert result.invoice is None
    assert "cannot read PDF" in result.error
    assert not result.is_valid


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(PdfTextError, match="not found"):
        extract_text(tmp_path / "nope.pdf")


def test_batch_continues_after_a_failure(sample_dir, tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-garbage")
    paths = [*collect_pdfs([sample_dir]), broken]

    results = extract_many(paths)

    assert [r.is_valid for r in results] == [True, True, True, False]


def test_parallel_and_sequential_results_match(sample_dir):
    paths = collect_pdfs([sample_dir])
    sequential = [r.to_dict() for r in extract_many(paths, workers=1)]
    parallel = [r.to_dict() for r in extract_many(paths, workers=2)]
    assert sequential == parallel


def test_json_export_round_trips(sample_dir):
    data = json.loads(to_json(extract_many(collect_pdfs([sample_dir]))))
    assert len(data) == 3
    assert data[0]["invoice"]["total"] == "3565.31"
    assert len(data[0]["invoice"]["line_items"]) == 3


def test_csv_export_has_one_row_per_invoice(sample_dir):
    rows = list(csv.DictReader(io.StringIO(to_csv(extract_many(collect_pdfs([sample_dir]))))))
    assert [row["invoice_number"] for row in rows] == ["INV-2026-0042", "NM/2026/317", "PXS-1187"]
    assert rows[2]["line_item_count"] == "2"


def test_cli_writes_output_file(sample_dir, tmp_path, capsys):
    out = tmp_path / "out.csv"
    exit_code = main([str(sample_dir), "-f", "csv", "-o", str(out), "--strict"])

    assert exit_code == 0
    assert out.read_text(encoding="utf-8").count("\n") == 4  # header + 3 rows
    assert "3 valid" in capsys.readouterr().err


def test_cli_strict_mode_fails_on_bad_input(tmp_path, capsys):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    assert main([str(broken), "--strict"]) == 1
    assert main([str(broken)]) == 0


def test_cli_reports_when_no_pdfs_found(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "No PDF files found" in capsys.readouterr().err
