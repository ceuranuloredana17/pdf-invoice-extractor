from pathlib import Path

import pytest

from invoice_extractor.sample_invoices import generate_all


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory) -> Path:
    """Directory with freshly generated sample invoice PDFs."""
    directory = tmp_path_factory.mktemp("samples")
    generate_all(directory)
    return directory
