FROM python:3.11-slim

# docling / pymupdf need these for PDF/DOCX parsing at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Fix: Debian Bookworm ships OpenSSL 3.x with SECLEVEL=2 by default.
# MongoDB Atlas TLS handshake fails with TLSV1_ALERT_INTERNAL_ERROR because
# SECLEVEL=2 disallows certain cipher suites the Atlas cluster negotiates.
# Lowering to SECLEVEL=1 (still TLS 1.2+, just more permissive ciphers) fixes this.
RUN sed -i 's/^\(CipherString\s*=\s*DEFAULT\).*/\1@SECLEVEL=1/' /etc/ssl/openssl.cnf || true && \
    grep -q 'SECLEVEL' /etc/ssl/openssl.cnf || \
    sed -i '/^\[system_default_sect\]/a CipherString = DEFAULT@SECLEVEL=1' /etc/ssl/openssl.cnf || true

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
