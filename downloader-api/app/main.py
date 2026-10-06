"""HTTP API (and optional web UI host) for the ItziGroup Downloader."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, get_settings
from .extract import ExtractionError, extract, ffmpeg_available
from .jobs import JobManager
from .models import Media, TTLStore
from .netsafe import UnsafeURLError, assert_public_url_async, client_kwargs, normalize_input_url, open_stream
from .ratelimit import RateLimiter
from .util import content_disposition, redact, safe_media_type

class _RedactLinks(logging.Filter):
    """Log lines must never carry the links people paste."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_RedactLinks())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(logging.WARNING)  # library chatter (gallery-dl, httpx…) stays quiet
    app_log = logging.getLogger("itzi")
    if not app_log.handlers:
        app_log.addHandler(handler)
        app_log.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
        app_log.propagate = False
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return app_log


log = _setup_logging()

EXTRACT_TIMEOUT = 150


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: str | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers or {}


class ExtractRequest(BaseModel):
    url: str = Field(..., max_length=4096)
    fresh: bool = False


class JobRequest(BaseModel):
    option: str = Field(..., max_length=32)


class State:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.media: TTLStore[Media] = TTLStore(ttl=settings.media_ttl, max_entries=500)
        self.recent: TTLStore[str] = TTLStore(ttl=min(600, settings.media_ttl), max_entries=2000)
        self.jobs = JobManager(settings)
        self.limiter = RateLimiter()
        self.extract_slots = asyncio.Semaphore(settings.max_extractions)
        self.http: httpx.AsyncClient | None = None


def _ytdl_version() -> str | None:
    try:
        from yt_dlp.version import __version__ as version
        return version
    except Exception:
        return None


def _gdl_version() -> str | None:
    try:
        from gallery_dl.version import __version__ as version
        return version
    except Exception:
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    state = State(settings)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.http = httpx.AsyncClient(**client_kwargs(settings.proxy),
                                       limits=httpx.Limits(max_connections=200, max_keepalive_connections=40))
        sweeper = asyncio.create_task(_sweep_forever(state))
        log.info("Downloader API %s ready (yt-dlp %s, gallery-dl %s, ffmpeg %s, cookies %s)",
                 __version__, _ytdl_version(), _gdl_version(),
                 "yes" if ffmpeg_available() else "NO", "yes" if settings.cookies_enabled else "no")
        try:
            yield
        finally:
            sweeper.cancel()
            state.jobs.shutdown()
            await state.http.aclose()

    app = FastAPI(title="ItziGroup Downloader API", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.state.downloader = state

    origins = settings.allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if "*" in origins else origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "Content-Length", "Retry-After"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.detail:
            body["detail"] = exc.detail
        return JSONResponse({"error": body}, status_code=exc.status, headers=exc.headers)

    def client_ip(request: Request) -> str:
        if settings.trust_proxy:
            for header in ("cf-connecting-ip", "x-real-ip"):
                if request.headers.get(header):
                    return request.headers[header].strip()
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def limit(request: Request, bucket: str, per_minute: int) -> None:
        wait = state.limiter.hit(f"{bucket}:{client_ip(request)}", per_minute)
        if wait is not None:
            raise ApiError(429, "rate_limited", "You're going a little fast. Try again in a moment.",
                           headers={"Retry-After": str(int(wait))})

    def get_media(media_id: str) -> Media:
        media = state.media.get(media_id)
        if media is None:
            raise ApiError(404, "expired", "This result expired. Analyze the link again.")
        return media

    # ------------------------------------------------------------------ routes

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "engines": {"yt_dlp": _ytdl_version(), "gallery_dl": _gdl_version()},
            "ffmpeg": ffmpeg_available(),
            "js_runtimes": [name for name in settings.js_runtimes if shutil.which(name)],
            "cookies": settings.cookies_enabled,
            "limits": {
                "max_filesize_mb": settings.max_filesize // (1024 * 1024),
                "max_duration_min": settings.max_duration // 60,
                "max_items": settings.max_items,
            },
            "active_jobs": state.jobs.active_count(),
        }

    @app.post("/api/extract")
    async def extract_route(body: ExtractRequest, request: Request) -> dict[str, Any]:
        limit(request, "extract", settings.rate_extract)
        try:
            url = normalize_input_url(body.url)
            await assert_public_url_async(url, settings.allow_private_networks)
        except UnsafeURLError as exc:
            raise ApiError(400, "invalid_url", str(exc)) from exc

        if not body.fresh:
            cached_id = state.recent.get(url)
            cached = state.media.get(cached_id) if cached_id else None
            if cached is not None:
                return {**cached.public(), "cached": True}

        try:
            async with state.extract_slots:
                media, notice = await asyncio.wait_for(
                    asyncio.to_thread(extract, url, settings), timeout=EXTRACT_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise ApiError(504, "timeout", "The platform took too long to answer. Try again.") from exc
        except ExtractionError as exc:
            status = 404 if exc.code in {"not_found", "no_media", "unsupported", "private"} else 422
            raise ApiError(status, exc.code, exc.friendly, exc.detail) from exc

        media.notice = notice
        state.media.put(media.id, media)
        state.recent.put(url, media.id)
        return {**media.public(), "cached": False}

    @app.get("/api/media/{media_id}")
    async def media_route(media_id: str) -> dict[str, Any]:
        return get_media(media_id).public()

    @app.get("/api/media/{media_id}/thumb/{key}")
    async def thumb_route(media_id: str, key: str, request: Request) -> Response:
        media = get_media(media_id)
        thumb = media.thumb
        if key != "main":
            try:
                index = int(key)
            except ValueError as exc:
                raise ApiError(404, "not_found", "No such image.") from exc
            item = next((i for i in media.items if i.index == index), None)
            thumb = item.thumb if item else None
        if thumb is None:
            raise ApiError(404, "not_found", "No preview for this item.")
        assert state.http is not None
        try:
            upstream = await open_stream(state.http, thumb.url, thumb.headers, settings.allow_private_networks)
        except (UnsafeURLError, httpx.HTTPError) as exc:
            raise ApiError(502, "upstream", "Couldn't load the preview.") from exc
        ctype = upstream.headers.get("content-type", "").split(";")[0].strip().lower()
        if upstream.status_code >= 400 or not ctype.startswith("image/") or ctype == "image/svg+xml":
            await upstream.aclose()
            raise ApiError(502, "upstream", "Couldn't load the preview.")
        length = upstream.headers.get("content-length")
        if length and length.isdigit() and int(length) > 25 * 1024 * 1024:
            await upstream.aclose()
            raise ApiError(413, "too_large", "Preview is too large.")
        headers = {"Cache-Control": "private, max-age=900",
                   "Content-Security-Policy": "default-src 'none'",
                   "Cross-Origin-Resource-Policy": "cross-origin"}
        if length and length.isdigit():
            headers["Content-Length"] = length
        return StreamingResponse(_relay(upstream), media_type=ctype, headers=headers)

    @app.get("/api/media/{media_id}/file/{option_id}")
    async def file_route(media_id: str, option_id: str, request: Request) -> Response:
        limit(request, "download", settings.rate_download)
        media = get_media(media_id)
        found = media.option(option_id)
        if found is None:
            raise ApiError(404, "not_found", "That download option doesn't exist.")
        _, option = found
        if option.mode != "direct" or not option.source.url:
            raise ApiError(409, "needs_job", "This format is prepared on the server. Start a job instead.")
        assert state.http is not None
        try:
            upstream = await open_stream(state.http, option.source.url, option.source.headers,
                                         settings.allow_private_networks)
        except UnsafeURLError as exc:
            raise ApiError(400, "invalid_url", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "upstream", "Couldn't reach the platform. Try again.") from exc
        if upstream.status_code >= 400:
            status = upstream.status_code
            await upstream.aclose()
            raise ApiError(502, "upstream_refused",
                           f"The platform refused the download (HTTP {status}). Analyze the link again.")
        length = upstream.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_filesize:
            await upstream.aclose()
            raise ApiError(413, "too_large", "This file is larger than the server allows.")
        headers = {
            "Content-Disposition": content_disposition(option.filename),
            "Content-Security-Policy": "default-src 'none'",
            "Cache-Control": "no-store",
        }
        if length and length.isdigit():
            headers["Content-Length"] = length
        media_type = safe_media_type(upstream.headers.get("content-type"), option.ext)
        return StreamingResponse(_relay(upstream, settings.max_filesize), media_type=media_type,
                                 headers=headers)

    @app.post("/api/media/{media_id}/jobs", status_code=202)
    async def create_job(media_id: str, body: JobRequest, request: Request) -> dict[str, Any]:
        limit(request, "download", settings.rate_download)
        media = get_media(media_id)
        if body.option != "all" and media.option(body.option) is None:
            raise ApiError(404, "not_found", "That download option doesn't exist.")
        if body.option == "all" and len(media.downloadable_items()) < 1:
            raise ApiError(404, "not_found", "Nothing to download.")
        if state.jobs.active_count() >= settings.max_jobs * 10:
            raise ApiError(503, "busy", "The server is busy right now. Try again in a minute.",
                           headers={"Retry-After": "30"})
        state.media.touch(media.id)
        job = state.jobs.submit(media, body.option)
        return job.public()

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str) -> dict[str, Any]:
        job = state.jobs.get(job_id)
        if job is None:
            raise ApiError(404, "expired", "This download expired. Start it again.")
        return job.public()

    @app.delete("/api/jobs/{job_id}")
    async def job_cancel(job_id: str) -> dict[str, Any]:
        job = state.jobs.cancel(job_id)
        if job is None:
            raise ApiError(404, "expired", "This download expired.")
        return job.public()

    @app.get("/api/jobs/{job_id}/file")
    async def job_file(job_id: str) -> Response:
        job = state.jobs.get(job_id)
        if job is None or job.status != "done" or job.path is None or not Path(job.path).is_file():
            raise ApiError(404, "expired", "This file is no longer available. Start the download again.")
        filename = job.filename or job.path.name
        media_type = safe_media_type(None, Path(filename).suffix.lstrip("."))
        if filename.endswith(".zip"):
            media_type = "application/zip"
        return FileResponse(job.path, media_type=media_type, headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Security-Policy": "default-src 'none'",
        })

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "DELETE"], include_in_schema=False)
    async def api_not_found(rest: str) -> Response:
        raise ApiError(404, "not_found", "Unknown API endpoint.")

    assets_dir = settings.ui_dir.parent / "assets" if settings.ui_dir else None
    if assets_dir and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if settings.ui_dir and settings.ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.ui_dir, html=True), name="ui")

    return app


async def _relay(upstream: httpx.Response, max_bytes: int | None = None) -> AsyncIterator[bytes]:
    sent = 0
    try:
        async for chunk in upstream.aiter_bytes(256 * 1024):
            sent += len(chunk)
            if max_bytes is not None and sent > max_bytes:
                break
            yield chunk
    finally:
        await upstream.aclose()


async def _sweep_forever(state: State) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            state.media.purge()
            state.recent.purge()
            await asyncio.to_thread(state.jobs.cleanup)
            state.limiter.sweep()
        except Exception:
            log.exception("cleanup failed")


app = create_app()
