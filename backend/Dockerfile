# SkillShare API — container image for Cloud Run.
# Build context is backend/ (see .dockerignore); the app package is self-contained
# and does NOT bundle the CLI/MCP integration, which is excluded from the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (integration/, tests/, var/ etc. are excluded via .dockerignore).
COPY . .

# Cloud Run injects PORT (defaults to 8080). uvicorn binds it on all interfaces.
ENV PORT=8080
EXPOSE 8080
# --proxy-headers + trusting Cloud Run's forwarded headers makes request.url_for()
# emit https:// URLs (TLS terminates at Cloud Run's proxy). Without this, the
# /admin (SQLAdmin) page builds http:// asset URLs that the browser blocks as
# mixed content, so it renders unstyled.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
