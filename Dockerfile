FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[web]"

# Run as an unprivileged user.
RUN useradd --create-home app
USER app

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["invoice-extractor-web"]
