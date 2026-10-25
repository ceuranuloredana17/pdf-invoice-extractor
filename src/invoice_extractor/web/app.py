"""FastAPI application exposing the extractor over HTTP.

Endpoints:
    GET  /                 single-page UI (static/index.html)
    GET  /api/health       liveness probe
    GET  /api/samples      names of the bundled demo invoices
    POST /api/extract      upload one or more PDFs -> JSON (or CSV with ?format=csv)

Run locally with ``invoice-extractor-web`` and open http://127.0.0.1:8000.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from invoice_extractor import __version__
from invoice_extractor.exporters import to_csv
from invoice_extractor.pipeline import ExtractionResult, extract_bytes

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = STATIC_DIR / "samples"

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 20


def create_app(
    max_file_bytes: int = MAX_FILE_BYTES, max_files: int = MAX_FILES
) -> FastAPI:
    """Application factory; limits are parameters so tests can lower them."""
    app = FastAPI(
        title="PDF Invoice Extractor",
        version=__version__,
        description="Extract and validate structured data from PDF invoices.",
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/samples")
    def samples() -> list[str]:
        return sorted(p.name for p in SAMPLES_DIR.glob("*.pdf"))

    # Declared with plain ``def``: PDF parsing is CPU-bound and blocking, so
    # FastAPI runs it in its thread pool instead of stalling the event loop.
    @app.post("/api/extract", response_model=None)
    def extract(
        files: Annotated[list[UploadFile], File(description="PDF invoices")],
        format: Annotated[Literal["json", "csv"], Query()] = "json",
    ) -> list[dict] | PlainTextResponse:
        if len(files) > max_files:
            raise HTTPException(413, f"Too many files (max {max_files} per request)")

        results: list[ExtractionResult] = []
        for upload in files:
            name = upload.filename or "upload.pdf"
            if not name.lower().endswith(".pdf"):
                raise HTTPException(415, f"{name}: only .pdf files are accepted")
            # Read one byte past the limit to detect oversize files without
            # loading arbitrarily large uploads into memory.
            data = upload.file.read(max_file_bytes + 1)
            if len(data) > max_file_bytes:
                raise HTTPException(
                    413, f"{name}: file larger than {max_file_bytes // (1024 * 1024)} MB"
                )
            results.append(extract_bytes(data, name))

        if format == "csv":
            return PlainTextResponse(
                to_csv(results),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="invoices.csv"'},
            )
        return [result.to_dict() for result in results]

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


def run() -> None:
    """Entry point for ``invoice-extractor-web``."""
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("invoice_extractor.web.app:app", host=host, port=port)
