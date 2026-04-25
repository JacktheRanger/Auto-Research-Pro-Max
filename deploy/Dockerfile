# syntax=docker/dockerfile:1.6
#
# Multi-stage Dockerfile for Auto Research Pro Max.
# Stage 1 builds the Vite frontend bundle.
# Stage 2 installs the FastAPI backend and copies the bundle into place.
#
# Build:
#   docker build -t auto-research-pro-max -f deploy/Dockerfile .
# Run:
#   docker run --rm -p 8000:8000 -v "$(pwd)/backend/data:/app/backend/data" auto-research-pro-max

FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000
WORKDIR /app

# System packages: tesseract is optional; install it so OCR fallback works
# out of the box. Drop the apt-get block in your fork if you do not need OCR.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        tesseract-ocr \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY backend ./backend
COPY launcher.py ./

# Install the project as editable so backend.app is importable.
RUN pip install --upgrade pip && pip install -e ".[ocr]"

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:${PORT:-8000}/api/health || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
