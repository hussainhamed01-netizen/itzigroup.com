"""In-memory data model for analyzed links and download jobs."""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar


def new_id(nbytes: int = 12) -> str:
    return secrets.token_urlsafe(nbytes)


@dataclass
class Source:
    """How to obtain an option's file. Never sent to the browser."""

    kind: str  # "direct" (stream a URL) | "ytdl" (let yt-dlp download/merge/convert)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # yt-dlp settings
    format: str | None = None
    fallback_format: str | None = None
    audio_codec: str | None = None  # e.g. "mp3" to convert
    merge: bool = False
    entry: dict[str, Any] | None = None  # yt-dlp info dict for the item
    page_url: str | None = None  # re-extract from here when the cached info is stale


@dataclass
class Option:
    id: str
    kind: str  # video | audio | image
    label: str
    ext: str
    filename: str
    source: Source
    note: str = ""
    size: int | None = None
    size_approx: bool = False
    height: int | None = None
    watermark: bool = False
    needs_processing: bool = False

    @property
    def mode(self) -> str:
        return "process" if self.needs_processing or self.source.kind != "direct" else "direct"

    def public(self, media_id: str) -> dict[str, Any]:
        data = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "ext": self.ext,
            "filename": self.filename,
            "note": self.note,
            "size": self.size,
            "size_approx": self.size_approx,
            "watermark": self.watermark,
            "mode": self.mode,
        }
        if self.mode == "direct":
            data["url"] = f"/api/media/{media_id}/file/{self.id}"
        return data


@dataclass
class Thumb:
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Item:
    index: int
    type: str  # video | image | audio
    title: str = ""
    thumb: Thumb | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    options: list[Option] = field(default_factory=list)

    def public(self, media_id: str) -> dict[str, Any]:
        return {
            "index": self.index,
            "type": self.type,
            "title": self.title,
            "thumbnail": f"/api/media/{media_id}/thumb/{self.index}" if self.thumb else None,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "options": [opt.public(media_id) for opt in self.options],
        }


@dataclass
class Media:
    url: str
    platform: str
    platform_name: str
    source: str  # which extractor produced it
    id: str = field(default_factory=new_id)
    title: str = ""
    uploader: str = ""
    uploader_url: str | None = None
    description: str = ""
    duration: float | None = None
    upload_date: str | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    thumb: Thumb | None = None
    items: list[Item] = field(default_factory=list)
    truncated: bool = False
    watermark_free: bool = False
    notice: str | None = None
    cookies: str = ""  # Netscape cookie jar captured during extraction

    def option(self, option_id: str) -> tuple[Item, Option] | None:
        for item in self.items:
            for opt in item.options:
                if opt.id == option_id:
                    return item, opt
        return None

    def downloadable_items(self) -> list[Item]:
        return [item for item in self.items if item.options]

    def public(self) -> dict[str, Any]:
        items = self.downloadable_items()
        return {
            "id": self.id,
            "url": self.url,
            "platform": {"key": self.platform, "name": self.platform_name},
            "source": self.source,
            "title": self.title,
            "uploader": self.uploader,
            "uploader_url": self.uploader_url,
            "description": self.description,
            "duration": self.duration,
            "upload_date": self.upload_date,
            "stats": {"views": self.views, "likes": self.likes, "comments": self.comments},
            "thumbnail": f"/api/media/{self.id}/thumb/main" if self.thumb else None,
            "watermark_free": self.watermark_free,
            "truncated": self.truncated,
            "notice": self.notice,
            "items": [item.public(self.id) for item in items],
            "bundle": {"id": "all", "count": len(items)} if len(items) > 1 else None,
        }


@dataclass
class Job:
    media_id: str
    option_id: str
    id: str = field(default_factory=new_id)
    status: str = "queued"  # queued | running | done | error | cancelled
    stage: str = "Waiting in queue"
    progress: float | None = None
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: int | None = None
    filename: str | None = None
    path: Path | None = None
    workdir: Path | None = None
    size: int | None = None
    error: str | None = None
    error_code: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": None if self.progress is None else round(max(0.0, min(1.0, self.progress)), 4),
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "eta": self.eta,
            "filename": self.filename,
            "size": self.size,
            "error": self.error,
            "error_code": self.error_code,
        }
        if self.status == "done":
            data["url"] = f"/api/jobs/{self.id}/file"
        return data


T = TypeVar("T")


class TTLStore(Generic[T]):
    """Thread-safe dict whose entries expire, capped to a maximum size."""

    def __init__(self, ttl: float, max_entries: int = 5000):
        self.ttl = ttl
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, key: str, value: T, ttl: float | None = None) -> list[T]:
        evicted: list[T] = []
        with self._lock:
            self._data[key] = (time.time() + (ttl if ttl is not None else self.ttl), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                evicted.append(self._data.popitem(last=False)[1][1])
        return evicted

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry[0] < time.time():
                del self._data[key]
                return None
            return entry[1]

    def touch(self, key: str, ttl: float | None = None) -> None:
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                self._data[key] = (time.time() + (ttl if ttl is not None else self.ttl), entry[1])

    def pop(self, key: str) -> T | None:
        with self._lock:
            entry = self._data.pop(key, None)
            return entry[1] if entry else None

    def purge(self) -> list[T]:
        now = time.time()
        with self._lock:
            expired = [key for key, (expires, _) in self._data.items() if expires < now]
            return [self._data.pop(key)[1] for key in expired]

    def values(self) -> list[T]:
        with self._lock:
            return [value for _, value in self._data.values()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
