"""PDF Invoice Extractor: turn PDF invoices into validated, structured data."""

from invoice_extractor.models import Invoice, LineItem
from invoice_extractor.parser import InvoiceParser
from invoice_extractor.pipeline import ExtractionResult, extract_file, extract_many
from invoice_extractor.validation import Issue, Severity, validate

__all__ = [
    "ExtractionResult",
    "Invoice",
    "InvoiceParser",
    "Issue",
    "LineItem",
    "Severity",
    "extract_file",
    "extract_many",
    "validate",
]

__version__ = "1.0.0"
