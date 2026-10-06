# ItziGroup Downloader: API + web UI in one image.
# Build from the repository root (the UI and site assets live outside this folder):
#   docker build -f downloader-api/Dockerfile -t itzi-downloader .

FROM denoland/deno:bin AS deno

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    UI_DIR=/srv/downloader \
    DATA_DIR=/data \
    AUTO_UPDATE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno runs YouTube's player JavaScript for yt-dlp.
COPY --from=deno /deno /usr/local/bin/deno

RUN useradd --create-home --uid 10001 app \
    && python -m venv /opt/venv \
    && mkdir -p /data \
    && chown -R app:app /opt/venv /data

COPY downloader-api/requirements.txt /srv/api/requirements.txt
RUN pip install --no-cache-dir -r /srv/api/requirements.txt && chown -R app:app /opt/venv

COPY downloader-api/app /srv/api/app
COPY downloader-api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY downloader /srv/downloader
COPY assets/fonts /srv/assets/fonts
COPY assets/logo.png assets/favicon.png /srv/assets/

USER app
WORKDIR /srv/api
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
