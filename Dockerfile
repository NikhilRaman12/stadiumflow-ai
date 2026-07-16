# ── StadiumIQ — Production Dockerfile ─────────────────────────────
# Multi-stage build: deps → runtime
# Image: nikhilraman12/stadiumiq:latest
# ──────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

# Install into isolated prefix
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="StadiumIQ GenAI Platform"
LABEL org.opencontainers.image.description="FIFA World Cup 2026 — LangGraph · MCP · A2A · GraphRAG · Gemini"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.source="https://github.com/NikhilRaman12/stadiumflow-ai"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy backend source
COPY backend/ ./

# Copy frontend to be served by FastAPI
COPY frontend/ ./frontend/

# Create required dirs
RUN mkdir -p graph_rag/index db && \
    # ensure UTF-8 locale on container
    apt-get update && apt-get install -y --no-install-recommends locales && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && locale-gen && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV PYTHONIOENCODING=utf-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0
ENV LOG_LEVEL=INFO
ENV DEBUG=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Use main.py as entrypoint (production app)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
