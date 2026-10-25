"""Web front end: a FastAPI REST API plus a single-page UI."""

from invoice_extractor.web.app import app, create_app

__all__ = ["app", "create_app"]
