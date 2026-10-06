"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DEFAULT_UI_DIR = Path(__file__).resolve().parent.parent.parent / "downloader"


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return [part.strip() for part in raw.split(",") if part.strip()]


def _proxy_hops() -> int:
    raw = os.environ.get("TRUST_PROXY", "").strip().lower()
    if raw in {"true", "yes", "on"}:
        return 1
    return max(0, _int("TRUST_PROXY", 0))


@dataclass(frozen=True)
class Settings:
    # Origins allowed to call the API from a browser (CORS). "*" allows any.
    allowed_origins: list[str]
    # Netscape-format cookies.txt used for logged-in content (stories, private posts).
    cookies_file: Path | None
    # Optional outbound proxy for the extractors and media fetches.
    proxy: str | None
    # Where finished job files are written.
    data_dir: Path
    # Folder holding the web UI; served at "/" when present.
    ui_dir: Path | None
    # How long an analyzed link stays downloadable (seconds).
    media_ttl: int
    # How long a finished job's file is kept (seconds).
    file_ttl: int
    max_filesize: int
    # Longest media (seconds) the server will merge/convert.
    max_duration: int
    # Most entries read from a carousel, thread or playlist.
    max_items: int
    max_jobs: int
    max_extractions: int
    rate_extract: int
    rate_download: int
    # Number of reverse proxies in front of the API (0 = none). Each one appends the
    # address it saw to X-Forwarded-For, so the client is that many entries from the end.
    trust_proxy: int
    allow_private_networks: bool
    js_runtimes: list[str]

    @property
    def cookies_enabled(self) -> bool:
        return bool(self.cookies_file and self.cookies_file.is_file())

    def read_cookies(self) -> str:
        if not self.cookies_enabled:
            return ""
        try:
            return self.cookies_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    cookies = os.environ.get("COOKIES_FILE", "").strip()
    ui_raw = os.environ.get("UI_DIR")
    if ui_raw is None:
        ui_dir: Path | None = _DEFAULT_UI_DIR if _DEFAULT_UI_DIR.is_dir() else None
    else:
        ui_dir = Path(ui_raw) if ui_raw.strip() else None

    default_runtimes = [name for name in ("deno", "node", "bun") if shutil.which(name)]

    return Settings(
        allowed_origins=_list(
            "ALLOWED_ORIGINS",
            ["https://itzigroup.com", "https://www.itzigroup.com",
             "http://localhost:8000", "http://127.0.0.1:8000"],
        ),
        cookies_file=Path(cookies) if cookies else None,
        proxy=os.environ.get("OUTBOUND_PROXY", "").strip() or None,
        data_dir=Path(os.environ.get("DATA_DIR") or Path(tempfile.gettempdir()) / "itzi-downloader"),
        ui_dir=ui_dir,
        media_ttl=_int("MEDIA_TTL", 30 * 60),
        file_ttl=_int("FILE_TTL", 20 * 60),
        max_filesize=_int("MAX_FILESIZE_MB", 2048) * 1024 * 1024,
        max_duration=_int("MAX_DURATION_MIN", 240) * 60,
        max_items=max(1, _int("MAX_ITEMS", 30)),
        max_jobs=max(1, _int("MAX_JOBS", 3)),
        max_extractions=max(1, _int("MAX_EXTRACTIONS", 4)),
        rate_extract=_int("RATE_EXTRACT_PER_MIN", 30),
        rate_download=_int("RATE_DOWNLOAD_PER_MIN", 60),
        trust_proxy=_proxy_hops(),
        allow_private_networks=_bool("ALLOW_PRIVATE_NETWORKS"),
        js_runtimes=_list("JS_RUNTIMES", default_runtimes),
    )
