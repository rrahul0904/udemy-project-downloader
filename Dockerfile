FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DOWNLOAD_DIR=/downloads \
    DATA_DIR=/app/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg tesseract-ocr libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional CPU speech-to-text image for the transcriber profile only.
ARG INSTALL_LOCAL_ASR=0
COPY requirements-asr.txt .
RUN if [ "$INSTALL_LOCAL_ASR" = "1" ]; then pip install --no-cache-dir -r requirements-asr.txt; fi

COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 scripts ./scripts
RUN mkdir -p /downloads /app/data \
    && chown -R 10001:10001 /downloads /app/data /app

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=3).read()" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
