"""Layout reconstruction, tested on hand-made word boxes and on real PDFs."""

from reportlab.pdfgen import canvas

from invoice_extractor.pdf_text import COLUMN_SEPARATOR, extract_text, group_lines, page_text


def word(text, x0, top, size=10):
    return {"text": text, "x0": x0, "x1": x0 + 6 * len(text), "top": top,
            "bottom": top + size, "upright": True}


def texts(lines):
    return [[w["text"] for w in line] for line in lines]


def test_words_with_slightly_different_baselines_share_a_line():
    words = [word("Data:", 20, 173.6), word("06.08.2025", 97, 174.7), word("Next", 20, 184.4)]
    assert texts(group_lines(words)) == [["Data:", "06.08.2025"], ["Next"]]


def test_words_are_ordered_left_to_right_within_a_line():
    words = [word("B", 200, 100.5), word("A", 10, 100)]
    assert texts(group_lines(words)) == [["A", "B"]]


def test_wide_gap_becomes_column_separator(tmp_path):
    path = tmp_path / "columns.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(50, 700, "Acme Ltd")
    pdf.drawString(350, 700, "Client ID: 7")
    pdf.save()

    assert extract_text(path) == f"Acme Ltd{COLUMN_SEPARATOR}Client ID: 7"


def test_label_and_value_in_different_fonts_are_joined(tmp_path):
    """Regression test for a real utility bill: bold value, 1.5 pt lower baseline."""
    path = tmp_path / "fonts.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(20, 700, "Invoice No:")
    pdf.drawString(20, 689, "Date:")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(80, 698.5, "AB-123")
    pdf.drawString(80, 687.5, "06.08.2025")
    pdf.save()

    lines = [line.split() for line in extract_text(path).splitlines()]
    assert lines == [["Invoice", "No:", "AB-123"], ["Date:", "06.08.2025"]]


def test_fake_bold_duplicate_glyphs_are_removed(tmp_path):
    """Some generators fake bold by drawing the same text twice, slightly offset."""
    path = tmp_path / "fake_bold.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(50, 700, "Invoice No: AB-123")
    pdf.drawString(50.3, 700, "Invoice No: AB-123")
    pdf.save()

    assert extract_text(path) == "Invoice No: AB-123"


def test_rotated_text_is_ignored():
    rotated = {**word("Scan me", 500, 100), "upright": False}

    class FakePage:
        def dedupe_chars(self):
            return self

        def extract_words(self):
            return [word("Total:", 10, 100), rotated]

    assert page_text(FakePage()) == "Total:"
