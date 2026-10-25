# PDF Invoice Extractor

A Python tool that turns PDF invoices into **validated, structured data** (JSON / CSV):
invoice number, vendor, customer, issue and due dates, currency, subtotal, tax, total and
line items. It works across US, EU and Romanian invoice formats.

Extraction from free-form documents is never 100% reliable, so every result is
**cross-checked against accounting rules** (line items add up to the subtotal,
subtotal + tax = total, ...). Inconsistent invoices are flagged for human review
instead of being silently passed downstream.

```text
$ invoice-extractor samples/ -f csv
source,valid,invoice_number,vendor,invoice_date,currency,subtotal,tax,total,line_item_count,confidence,...
samples/acme_us.pdf,True,INV-2026-0042,Acme Design Studio LLC,2026-10-03,USD,3286.00,279.31,3565.31,3,1.0,...
samples/nordlicht_eu.pdf,True,NM/2026/317,Nordlicht Media GmbH,2026-08-28,EUR,1640.00,344.40,1984.40,2,1.0,...
samples/pixelsoft_ro.pdf,True,PXS-1187,SC Pixel Soft SRL,2026-09-15,RON,5350.00,1016.50,6366.50,2,1.0,...
Processed 3 file(s): 3 valid, 0 with errors, 0 unreadable.
```

## Features

- **Multi-locale number parsing**: `$1,234.56`, `1.234,56 RON`, `€85,00`, `1 234,56`.
  The decimal separator is inferred from the string itself.
- **Flexible date parsing**: ISO, `dd.mm.yyyy`, `dd/mm/yyyy`, `October 3, 2026`, `3rd Oct 2026`,
  with a configurable day-first/month-first preference and an automatic fallback.
- **Configurable labels**: English and Romanian out of the box. Adding a language or vendor
  layout means passing a different `Labels` object, with no regex changes.
- **Line item extraction** from invoice tables, with a consistency check
  (`qty × unit price = amount`) when no table header is present.
- **Validation layer** with error/warning severities and a per-invoice confidence score.
- **Batch processing** of whole directories, optionally in parallel (`--workers N`).
  A corrupt or scanned PDF is reported in its own result and never stops the batch.
- **Web app**: FastAPI REST API with OpenAPI docs, plus a drag-and-drop UI built in plain
  JavaScript. Files are processed in memory and never written to disk.
- **CLI + library API**, JSON and CSV export, `--strict` mode for CI/automation pipelines.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m invoice_extractor.sample_invoices samples   # generate 3 demo invoices
invoice-extractor samples/ -f json -o invoices.json
pytest --cov=invoice_extractor                       # 95 tests, ~96% coverage
```

### Web app

```bash
invoice-extractor-web          # then open http://127.0.0.1:8000
```

The UI accepts drag-and-drop uploads and includes a "Try the demo invoices" button.
Interactive API docs are served at `/docs`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/extract` | Multipart upload (`files`, up to 20 PDFs, 10 MB each). Returns JSON, or CSV with `?format=csv`. |
| `GET` | `/api/samples` | Names of the bundled demo invoices. |
| `GET` | `/api/health` | Liveness probe. |

```bash
curl -F "files=@invoice.pdf" http://127.0.0.1:8000/api/extract
```

Run it with Docker (the same image deploys to Render, Fly.io or Hugging Face Spaces):

```bash
docker build -t invoice-extractor .
docker run -p 8000:8000 invoice-extractor
```

### Library usage

```python
from invoice_extractor import extract_file

result = extract_file("invoice.pdf")
if result.is_valid:
    print(result.invoice.total, result.invoice.currency)
else:
    for issue in result.issues:
        print(issue.severity.value, issue.message)
```

## Architecture

```text
            ┌────────────┐   text   ┌──────────────┐  Invoice  ┌──────────────┐
 PDF ──────▶│ pdf_text   │────────▶│ parser        │─────────▶│ validation   │──▶ ExtractionResult
            │ (pdfplumber)│         │ (+ normalize) │          │ (rules)      │        │
            └────────────┘          └──────────────┘          └──────────────┘        ▼
                                                                                  exporters (JSON/CSV)
            pipeline.py: file discovery, error isolation, parallelism     cli.py: argument parsing
```

| Module | Responsibility |
|---|---|
| `models.py` | `Invoice` and `LineItem` dataclasses. Money is `Decimal`, never `float`. |
| `pdf_text.py` | The only module that touches PDFs. Wraps pdfplumber errors in a single `PdfTextError`. |
| `normalize.py` | Pure functions: `parse_amount`, `parse_date`, `detect_currency`. |
| `parser.py` | `InvoiceParser`: label-anchored regexes built from a `Labels` config. |
| `validation.py` | Business rules returning a list of `Issue(code, message, severity)`. |
| `pipeline.py` | `extract_file` / `extract_many`: orchestration, failure isolation, process pool. |
| `exporters.py` | JSON and CSV serialization. |
| `cli.py` | `argparse` front end. Exit codes are meaningful for scripting. |
| `web/app.py` | FastAPI app factory: upload validation (type, size, count), JSON/CSV responses. |
| `web/static/` | Single-page UI (HTML/CSS/JS, no build step) and the bundled demo PDFs. |

### Design decisions

- **Parsing is separated from I/O.** `InvoiceParser.parse()` takes a string, not a file. Most
  tests therefore run on plain text in milliseconds, and an OCR text source could be added
  later without touching the parser.
- **`Decimal` for money.** With `float`, `0.1 + 0.2 != 0.3`, which breaks the
  "subtotal + tax == total" check. Comparisons use a configurable tolerance of one cent
  to absorb rounding on the printed invoice.
- **Validate instead of trusting.** Heuristic extraction will sometimes be wrong. The
  arithmetic cross-checks turn silent mistakes into visible, explainable issues.
- **Processes, not threads, for parallelism.** PDF parsing is CPU-bound, so threads would be
  serialized by the GIL. Results are returned in input order regardless of worker count,
  and a test asserts that parallel and sequential output are identical.
- **The web layer stays thin.** The API reuses `extract_bytes` from the pipeline, so the CLI
  and HTTP paths share the same logic. The endpoint is a sync `def`, so CPU-bound parsing
  runs in FastAPI's thread pool instead of blocking the event loop. Upload limits are
  enforced while reading, so an oversized file is never fully loaded into memory.
- **Untrusted input is never rendered as HTML.** Extracted text and file names are inserted
  with `textContent`, so a crafted PDF cannot inject markup into the UI.
- **Layout is rebuilt from word coordinates.** Testing on a real utility bill showed that
  pdfplumber's default text order separated labels from their values, because they used
  different fonts with a 1.5 pt baseline shift. The bill also used "fake bold" (every glyph
  drawn twice) and two-column headers. `pdf_text.py` now de-duplicates glyphs, groups
  words into visual lines by vertical overlap, and marks wide gaps as column breaks.
  Each of these cases has a regression test.
- **Real-world totals are not always subtotal + tax.** Utility bills add the previous
  unpaid balance to the amount due, so validation accounts for `previous_balance`.
  Labels match with or without Romanian diacritics ("Factură" / "Factura").
- **Regex pitfalls are covered by tests.** For example, "Subtotal" must not match the "Total"
  label, "Due Date" must not match the generic "Date" label, and a description ending in a
  number ("Room 101 2 50.00 100.00") must still split correctly.

## Testing

```bash
pytest --cov=invoice_extractor --cov-report=term-missing
ruff check .
```

- **Unit tests** for normalization (parametrized edge cases), parsing and validation rules.
- **Integration tests** that generate real PDFs with reportlab at test time and run them
  through the full pipeline, exporters and CLI, including corrupt files and parallel mode.
- **API tests** with FastAPI's `TestClient`: uploads, CSV output, and rejection of wrong
  types, oversized files and too many files.
- **CI** runs lint and tests on Python 3.10–3.12, on Ubuntu and Windows (GitHub Actions).

## Limitations and roadmap

- Scanned PDFs without a text layer are detected and reported, but not processed. *Next:*
  add an OCR text source (Tesseract) behind the same interface as `pdf_text`.
- A customer name printed without any label (common on utility bills) is not detected.
  *Next:* locate the address block by position relative to the vendor block.
- Line items are recognized in the `description qty unit_price amount` layout only.
  Tables with extra VAT-rate and VAT-amount columns are skipped rather than mis-parsed.
- Rule-based extraction needs label configs for new layouts. *Next:* benchmark it against
  an ML/LLM-based extractor, keeping the validation layer as the safety net.

## License

MIT
