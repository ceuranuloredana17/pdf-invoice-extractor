"""API tests for the FastAPI app, using FastAPI's in-process TestClient."""

import pytest
from fastapi.testclient import TestClient

from invoice_extractor.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def upload(path):
    return ("files", (path.name, path.read_bytes(), "application/pdf"))


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "PDF Invoice Extractor" in response.text


def test_bundled_samples_are_listed_and_downloadable(client):
    names = client.get("/api/samples").json()
    assert names == ["acme_us.pdf", "nordlicht_eu.pdf", "pixelsoft_ro.pdf"]
    assert client.get(f"/static/samples/{names[0]}").content.startswith(b"%PDF")


def test_extract_multiple_files(client, sample_dir):
    files = [upload(sample_dir / "acme_us.pdf"), upload(sample_dir / "pixelsoft_ro.pdf")]
    response = client.post("/api/extract", files=files)

    assert response.status_code == 200
    data = response.json()
    assert [r["source"] for r in data] == ["acme_us.pdf", "pixelsoft_ro.pdf"]
    assert all(r["valid"] for r in data)
    assert data[0]["invoice"]["total"] == "3565.31"
    assert data[1]["invoice"]["currency"] == "RON"


def test_extract_as_csv(client, sample_dir):
    response = client.post(
        "/api/extract", params={"format": "csv"}, files=[upload(sample_dir / "acme_us.pdf")]
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "INV-2026-0042" in response.text


def test_corrupt_pdf_returns_result_with_error(client):
    response = client.post(
        "/api/extract", files=[("files", ("bad.pdf", b"not a pdf", "application/pdf"))]
    )
    assert response.status_code == 200
    [result] = response.json()
    assert result["valid"] is False
    assert "cannot read PDF bad.pdf" in result["error"]


def test_non_pdf_is_rejected(client):
    response = client.post("/api/extract", files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert response.status_code == 415


def test_missing_files_is_a_validation_error(client):
    assert client.post("/api/extract").status_code == 422


def test_unknown_format_is_rejected(client, sample_dir):
    response = client.post(
        "/api/extract", params={"format": "xml"}, files=[upload(sample_dir / "acme_us.pdf")]
    )
    assert response.status_code == 422


def test_file_size_limit(sample_dir):
    client = TestClient(create_app(max_file_bytes=100))
    response = client.post("/api/extract", files=[upload(sample_dir / "acme_us.pdf")])
    assert response.status_code == 413


def test_file_count_limit(sample_dir):
    client = TestClient(create_app(max_files=1))
    pdf = upload(sample_dir / "acme_us.pdf")
    assert client.post("/api/extract", files=[pdf, pdf]).status_code == 413
