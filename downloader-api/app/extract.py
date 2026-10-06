"""Turn a pasted link into a list of downloadable items.

Three engines are tried in a platform-specific order:

* yt-dlp     — videos and audio from 1,800+ sites (TikTok, YouTube, Instagram reels…)
* gallery-dl — photos, carousels and stories (Instagram, Pinterest, X, Snapchat…)
* page meta  — Open Graph tags or a direct file link, for everything else
"""

from __future__ import annotations

import copy
import datetime as dt
import io
import logging
import re
import shutil
import threading
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from .config import Settings
from .models import Item, Media, Option, Source, Thumb
from .netsafe import client_kwargs, open_stream_sync
from .util import (AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, classify_error, clean_title,
                   detect_platform, friendly_for, guess_ext, kind_for_ext, redact,
                   safe_filename, strip_hashtags)

log = logging.getLogger("itzi.extract")

# Platforms whose own "save" button burns a watermark into the file.
WATERMARK_PLATFORMS = {"tiktok", "instagram", "snapchat", "likee", "threads", "facebook"}
# Platforms where a post is usually photos, so gallery-dl goes first.
GALLERY_FIRST = {"pinterest", "tumblr", "bluesky", "imgur", "threads", "9gag"}
# Platforms where an audio-only answer from yt-dlp probably means "photo slideshow".
PHOTO_CAPABLE = {"tiktok", "instagram", "x", "facebook", "threads", "pinterest", "reddit",
                 "snapchat", "bluesky", "tumblr", "vk"}

_DROP_INFO_KEYS = {"automatic_captions", "subtitles", "heatmap", "thumbnails", "chapters",
                   "requested_subtitles", "comments", "storyboards"}
_SKIP_GALLERY_TYPES = {"avatar", "subtitle", "background", "banner", "text", "profile"}
_SKIP_GALLERY_EXTS = {"json", "txt", "vtt", "srt", "ass", "html", "htm", "xml", "url"}

_ERROR_RANK = ["blocked", "login_required", "private", "geo", "rate_limited", "not_found",
               "timeout", "no_media", "failed", "unsupported"]


class ExtractionError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        found_code, friendly, detail = classify_error(message)
        self.code = code or found_code
        self.friendly = friendly_for(self.code) if code else friendly
        self.detail = detail


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


# --------------------------------------------------------------------------- yt-dlp

class _QuietLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)


_COOKIE_MAGIC = re.compile(r"#( Netscape)? HTTP Cookie File")


def cookie_stream(cookies: str) -> io.StringIO:
    """yt-dlp insists on the Netscape header line, even for an empty jar."""
    if not _COOKIE_MAGIC.match(cookies.lstrip()):
        cookies = "# Netscape HTTP Cookie File\n" + cookies
    return io.StringIO(cookies)


def ytdl_params(settings: Settings, cookies: str, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "logger": _QuietLogger(),
        "cookiefile": cookie_stream(cookies),
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 5,
        "extractor_retries": 2,
        "noplaylist": True,
        "playlistend": settings.max_items,
        "ignore_no_formats_error": True,
        "check_formats": False,
        "skip_download": True,
        "geo_bypass": True,
        "cachedir": str(settings.data_dir / "ytdl-cache"),
    }
    if settings.js_runtimes:
        params["js_runtimes"] = {name: {} for name in settings.js_runtimes}
    if settings.proxy:
        params["proxy"] = settings.proxy
    params.update(extra)
    return params


def _flags(fmt: dict[str, Any]) -> tuple[bool, bool]:
    """(has_video, has_audio) for a yt-dlp format, guessing when codecs are unknown."""
    ext = (fmt.get("ext") or "").lower()
    if ext == "mhtml" or (fmt.get("format_note") or "").lower() == "storyboard":
        return False, False
    vcodec = (fmt.get("vcodec") or "").lower()
    acodec = (fmt.get("acodec") or "").lower()
    if vcodec:
        has_video = vcodec != "none"
    else:
        has_video = ext not in AUDIO_EXTS and not (
            fmt.get("abr") and not fmt.get("height") and not fmt.get("vbr"))
    # Unknown audio codec: progressive files almost always carry sound. (yt-dlp marks
    # audio_ext "none" in that case, so it can't be trusted here.)
    has_audio = acodec != "none" if acodec else True
    return has_video, has_audio


def _is_watermarked(fmt: dict[str, Any]) -> bool:
    text = f"{fmt.get('format_note') or ''} {fmt.get('format') or ''}".lower()
    return "watermark" in text


def _is_direct(fmt: dict[str, Any]) -> bool:
    return (
        (fmt.get("protocol") or "https") in {"http", "https"}
        and not fmt.get("downloader_options")
        and not fmt.get("fragments")
        and not fmt.get("impersonate")
        and bool(fmt.get("url"))
    )


def _size(fmt: dict[str, Any] | None) -> tuple[int | None, bool]:
    if not fmt:
        return None, False
    if fmt.get("filesize"):
        return int(fmt["filesize"]), False
    if fmt.get("filesize_approx"):
        return int(fmt["filesize_approx"]), True
    return None, False


def _res(fmt: dict[str, Any]) -> int:
    width, height = fmt.get("width"), fmt.get("height")
    if width and height:
        return int(min(width, height))  # vertical 1080x1920 is "1080p"
    return int(height or 0)


def _quality_label(res: int, fps: float | None) -> tuple[str, str]:
    if not res:
        return "Best quality", ""
    label = f"{res}p"
    if fps and fps > 32:
        label += f"{round(fps)}"
    if res >= 2160:
        tier = "4K"
    elif res >= 1440:
        tier = "2K"
    elif res >= 1080:
        tier = "Full HD"
    elif res >= 720:
        tier = "HD"
    else:
        tier = ""
    return label, tier


def _codec_rank(fmt: dict[str, Any]) -> int:
    vcodec = (fmt.get("vcodec") or "").lower()
    if vcodec.startswith(("avc", "h264")):
        return 3
    if vcodec.startswith(("vp9", "vp09", "av01")):
        return 2
    if not vcodec:
        return 2
    return 1  # hevc / h265 / bytevc1 play in fewer places


def _direct_source(fmt: dict[str, Any], cookie_header: Callable[[str], str | None]) -> Source:
    headers = {k: v for k, v in (fmt.get("http_headers") or {}).items() if isinstance(v, str)}
    cookie = cookie_header(fmt["url"])
    if cookie:
        headers["Cookie"] = cookie
    return Source(kind="direct", url=fmt["url"], headers=headers)


def _trim_entry(entry: dict[str, Any]) -> dict[str, Any]:
    from yt_dlp import YoutubeDL

    trimmed = {k: v for k, v in entry.items() if k not in _DROP_INFO_KEYS}
    return YoutubeDL.sanitize_info(trimmed, remove_private_keys=True)


def _ytdl_item_options(entry: dict[str, Any], cookie_header: Callable[[str], str | None],
                       can_ffmpeg: bool, page_url: str) -> list[Option]:
    formats = [f for f in (entry.get("formats") or []) if f.get("url") and not f.get("has_drm")]
    if not formats and entry.get("url"):
        formats = [entry]
    if not formats:
        return []

    stored = _trim_entry(entry)
    videos, audios = [], []
    for fmt in formats:
        has_video, has_audio = _flags(fmt)
        if has_video:
            videos.append((fmt, has_audio))
        elif has_audio:
            audios.append(fmt)

    def audio_score(fmt: dict[str, Any]) -> tuple:
        return (_is_direct(fmt), (fmt.get("ext") == "m4a"), fmt.get("abr") or fmt.get("tbr") or 0)

    best_audio = max(audios, key=audio_score) if audios else None

    clean = [(f, a) for f, a in videos if not _is_watermarked(f)]
    pool = clean or videos
    only_watermarked = bool(videos) and not clean

    def video_score(fmt: dict[str, Any]) -> tuple:
        return (_is_direct(fmt), _codec_rank(fmt), fmt.get("ext") == "mp4",
                fmt.get("fps") or 0, fmt.get("tbr") or 0, _size(fmt)[0] or 0,
                fmt.get("quality") or 0, fmt.get("preference") or 0)

    by_res: dict[int, list[tuple[dict[str, Any], bool]]] = {}
    for fmt, has_audio in pool:
        by_res.setdefault(_res(fmt), []).append((fmt, has_audio))

    options: list[Option] = []
    for res in sorted(by_res, reverse=True):
        candidates = by_res[res]
        with_audio = [f for f, a in candidates if a]
        size, approx = None, False
        note_bits: list[str] = []
        limit = f"[height<={res}]" if res else ""
        if with_audio:
            fmt = max(with_audio, key=video_score)
            size, approx = _size(fmt)
            if _is_direct(fmt):
                source = _direct_source(fmt, cookie_header)
            else:
                source = Source(kind="ytdl", format=fmt["format_id"], entry=stored,
                                fallback_format=f"b{limit}/bv*{limit}+ba/b", page_url=page_url,
                                merge=can_ffmpeg)
            ext = fmt.get("ext") or "mp4"
            if source.kind == "ytdl" and (fmt.get("protocol") or "").startswith("m3u8"):
                ext = "mp4"
        elif best_audio is not None and can_ffmpeg:
            fmt = max((f for f, _ in candidates),
                      key=lambda f: (f.get("ext") == "mp4",) + video_score(f))
            vsize, vapprox = _size(fmt)
            asize, aapprox = _size(best_audio)
            if vsize and asize:
                size, approx = vsize + asize, vapprox or aapprox
            source = Source(kind="ytdl", format=f"{fmt['format_id']}+{best_audio['format_id']}",
                            fallback_format=f"bv*{limit}+ba/b{limit}/b", entry=stored,
                            page_url=page_url, merge=True)
            ext = "mp4"
        else:
            fmt = max((f for f, _ in candidates), key=video_score)
            size, approx = _size(fmt)
            source = (_direct_source(fmt, cookie_header) if _is_direct(fmt) else
                      Source(kind="ytdl", format=fmt["format_id"], entry=stored, page_url=page_url,
                             fallback_format=f"bv*{limit}/b{limit}/b"))
            ext = fmt.get("ext") or "mp4"
            note_bits.append("No sound")

        label, tier = _quality_label(res, fmt.get("fps"))
        if tier:
            note_bits.insert(0, tier)
        vcodec = (fmt.get("vcodec") or "").lower()
        if vcodec.startswith(("hevc", "h265", "bytevc1")):
            note_bits.append("H.265")
        if only_watermarked:
            note_bits.append("Watermarked — no clean copy available")
        options.append(Option(
            id="", kind="video", label=label, ext=ext, filename="", source=source,
            note=" · ".join(note_bits), size=size, size_approx=approx, height=res or None,
            watermark=only_watermarked,
        ))
        if len(options) >= 8:
            break

    has_any_audio = best_audio is not None or any(a for _, a in videos)
    if has_any_audio and can_ffmpeg:
        options.append(Option(
            id="", kind="audio", label="MP3", ext="mp3", filename="", note="192 kbps · converted",
            source=Source(kind="ytdl", format="ba/b", fallback_format="ba/b", audio_codec="mp3",
                          entry=stored, page_url=page_url),
        ))
    if best_audio is not None:
        size, approx = _size(best_audio)
        ext = best_audio.get("ext") or "m4a"
        bitrate = best_audio.get("abr") or best_audio.get("tbr")
        note = f"{round(bitrate)} kbps · original" if bitrate else "Original audio"
        if _is_direct(best_audio):
            source = _direct_source(best_audio, cookie_header)
        else:
            source = Source(kind="ytdl", format=best_audio["format_id"], fallback_format="ba/b",
                            entry=stored, page_url=page_url)
            if (best_audio.get("protocol") or "").startswith("m3u8"):
                ext = "m4a" if ext in {"mp4", "m4a"} else ext
        options.append(Option(id="", kind="audio", label=ext.upper(), ext=ext, filename="",
                              note=note, size=size, size_approx=approx, source=source))
    return options


def _flatten_entries(info: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if info.get("_type") in {"playlist", "multi_video"}:
        out: list[dict[str, Any]] = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            out.extend(_flatten_entries(entry, limit - len(out)))
            if len(out) >= limit:
                break
        return out[:limit]
    return [info]


def _ytdl_thumb(entry: dict[str, Any], page_url: str) -> Thumb | None:
    url = entry.get("thumbnail")
    if not url:
        thumbs = [t for t in entry.get("thumbnails") or [] if t.get("url")]
        if thumbs:
            url = thumbs[-1]["url"]
    if not url or not url.startswith(("http://", "https://")):
        return None
    parts = urlsplit(entry.get("webpage_url") or page_url)
    return Thumb(url=url, headers={"Referer": f"{parts.scheme}://{parts.netloc}/"})


def _format_date(raw: str | None) -> str | None:
    if raw and len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def from_ytdlp(url: str, settings: Settings, cookies: str) -> Media:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError, ExtractorError

    key, name = detect_platform(url)
    can_ffmpeg = ffmpeg_available()
    params = ytdl_params(settings, cookies)
    try:
        with YoutubeDL(params) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ExtractionError("No media found", "no_media")
            entries = _flatten_entries(info, settings.max_items)
            jar = io.StringIO()
            ydl.cookiejar.save(jar)

            def cookie_header(target: str) -> str | None:
                try:
                    return ydl.cookiejar.get_cookie_header(target)
                except Exception:
                    return None

            items: list[Item] = []
            for index, entry in enumerate(entries):
                page = entry.get("webpage_url") or url
                options = _ytdl_item_options(entry, cookie_header, can_ffmpeg, page)
                kinds = {opt.kind for opt in options}
                items.append(Item(
                    index=index,
                    type="video" if "video" in kinds else "audio" if kinds else "video",
                    title=clean_title(entry.get("title")),
                    thumb=_ytdl_thumb(entry, url),
                    duration=entry.get("duration"),
                    width=entry.get("width"),
                    height=entry.get("height"),
                    options=options,
                ))
    except (DownloadError, ExtractorError) as exc:
        raise ExtractionError(str(exc)) from exc

    first = entries[0] if entries else info
    title = info.get("title") if info.get("_type") in {"playlist", "multi_video"} else None
    title = title or first.get("title") or first.get("description") or ""
    extractor_key = (first.get("extractor_key") or "").lower()
    if key == "web" and extractor_key not in {"", "generic"}:
        name = first.get("extractor_key") or name

    media = Media(
        url=url, platform=key, platform_name=name, source="yt-dlp",
        title=clean_title(title),
        uploader=first.get("uploader") or first.get("channel") or first.get("creator")
        or first.get("uploader_id") or "",
        uploader_url=first.get("uploader_url") or first.get("channel_url"),
        description=clean_title(first.get("description"), 400),
        duration=first.get("duration") if len(entries) == 1 else None,
        upload_date=_format_date(first.get("upload_date")),
        views=first.get("view_count"), likes=first.get("like_count"),
        comments=first.get("comment_count"),
        thumb=_ytdl_thumb(first, url) or _ytdl_thumb(info, url),
        items=items,
        truncated=info.get("_type") in {"playlist", "multi_video"} and len(entries) >= settings.max_items,
        cookies=jar.getvalue(),
    )
    return media


# ----------------------------------------------------------------------- gallery-dl

_gdl_lock = threading.Lock()
_gdl_configured = False


def _configure_gallery_dl(settings: Settings) -> None:
    global _gdl_configured
    with _gdl_lock:
        if _gdl_configured:
            return
        from gallery_dl import config

        config.clear()
        config.set(("extractor",), "cookies-update", False)
        if settings.cookies_enabled:
            config.set(("extractor",), "cookies", str(settings.cookies_file))
        if settings.proxy:
            config.set(("extractor",), "proxy", settings.proxy)
        config.set(("extractor",), "timeout", 25.0)
        config.set(("extractor",), "retries", 2)
        config.set(("extractor",), "image-range", f"1-{settings.max_items}")
        config.set(("output",), "private", True)
        config.set(("output",), "mode", "null")
        for name in ("gallery-dl", "extractor", "downloader", "job", "postprocessor"):
            logging.getLogger(name).setLevel(logging.ERROR)
        _gdl_configured = True


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _name_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("username", "nick", "name", "handle", "screen_name", "full_name", "display_name"):
            if isinstance(value.get(key), str) and value[key]:
                return value[key]
    return ""


def _gdl_uploader(data: dict[str, Any]) -> str:
    for key in ("username", "author", "user", "owner", "uploader", "creator", "fullname",
                "account", "blog", "board", "subreddit"):
        name = _name_of(data.get(key))
        if name:
            return name
    return ""


def _gdl_thumb(data: dict[str, Any], headers: dict[str, str]) -> Thumb | None:
    for key in ("thumbnail", "display_url", "preview", "cover", "poster", "image", "thumbnail_url"):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get("url")
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return Thumb(url=value, headers=headers)
    return None


def from_gallery_dl(url: str, settings: Settings, cookies: str) -> Media:
    _configure_gallery_dl(settings)
    from gallery_dl import exception as gdl_exc
    from gallery_dl import extractor as gdl_extractor
    from gallery_dl import job as gdl_job
    from gallery_dl.extractor.message import Message

    try:
        extr = gdl_extractor.find(url)
    except Exception as exc:  # malformed URLs can raise inside pattern code
        raise ExtractionError(str(exc), "unsupported") from exc
    if extr is None:
        raise ExtractionError("No suitable extractor", "unsupported")

    data_job = gdl_job.DataJob(extr, file=None, resolve=1)
    data_job.run()
    exc = data_job.exception
    urls = [(msg[1], msg[2]) for msg in data_job.data if msg and msg[0] == Message.Url]
    if not urls:
        if exc is not None:
            if isinstance(exc, (gdl_exc.AuthenticationError, gdl_exc.AuthorizationError)):
                raise ExtractionError(str(exc) or "login required", "login_required")
            if isinstance(exc, gdl_exc.NotFoundError):
                raise ExtractionError(str(exc) or "not found", "not_found")
            raise ExtractionError(f"{exc.__class__.__name__}: {exc}")
        raise ExtractionError("No media found", "no_media")

    session_headers = {k: v for k, v in dict(getattr(extr, "session").headers).items()
                       if k.lower() in {"user-agent", "referer", "accept-language"} and isinstance(v, str)}
    jar = getattr(extr, "cookies", None)

    def cookie_header(target: str) -> str | None:
        if not jar:
            return None
        try:
            import requests

            prepared = requests.Request("GET", target).prepare()
            return requests.cookies.get_cookie_header(jar, prepared)
        except Exception:
            return None

    can_ffmpeg = ffmpeg_available()
    key, name = detect_platform(url)
    items: list[Item] = []
    post_meta = data_job.data_post[0] if data_job.data_post else {}
    for file_url, meta in urls:
        if len(items) >= settings.max_items:
            break
        meta = meta or {}
        if str(meta.get("type") or "").lower() in _SKIP_GALLERY_TYPES:
            continue
        index = len(items)
        title = clean_title(_first_text(meta, "description", "content", "title", "caption", "text"))
        if file_url.startswith("ytdl:"):
            target = file_url[5:]
            items.append(Item(index=index, type="video", title=title,
                              thumb=_gdl_thumb(meta, session_headers), options=[
                Option(id="", kind="video", label="Best quality", ext="mp4", filename="",
                       note="Original", source=Source(kind="ytdl", page_url=target, url=target,
                                                      format="bv*+ba/b" if can_ffmpeg else "b",
                                                      merge=can_ffmpeg)),
            ] + ([Option(id="", kind="audio", label="MP3", ext="mp3", filename="",
                         note="192 kbps · converted",
                         source=Source(kind="ytdl", page_url=target, url=target, format="ba/b",
                                       audio_codec="mp3"))] if can_ffmpeg else [])))
            continue

        ext = str(meta.get("extension") or guess_ext(file_url) or "jpg").lower()
        if ext in _SKIP_GALLERY_EXTS:
            continue
        ext = "jpg" if ext == "jpeg" else ext
        kind = kind_for_ext(ext)
        headers = dict(session_headers)
        extra = meta.get("_http_headers")
        if isinstance(extra, dict):
            headers.update({k: v for k, v in extra.items() if isinstance(v, str)})
        cookie = cookie_header(file_url)
        if cookie:
            headers["Cookie"] = cookie

        width, height = meta.get("width"), meta.get("height")
        label = "Original"
        if kind == "image" and isinstance(width, int) and isinstance(height, int) and width and height:
            label = f"Original · {width}×{height}"
        elif kind == "video" and isinstance(width, int) and isinstance(height, int) and width and height:
            label = f"{min(width, height)}p"
        options = [Option(id="", kind=kind, label=label, ext=ext, filename="",
                          note="Full resolution" if kind == "image" else "Original file",
                          source=Source(kind="direct", url=file_url, headers=headers),
                          size=meta.get("filesize") if isinstance(meta.get("filesize"), int) else None)]
        if kind == "video" and can_ffmpeg:
            options.append(Option(id="", kind="audio", label="MP3", ext="mp3", filename="",
                                  note="192 kbps · converted", needs_processing=True,
                                  source=Source(kind="direct", url=file_url, headers=headers,
                                                audio_codec="mp3")))
        thumb = Thumb(url=file_url, headers=headers) if kind == "image" else _gdl_thumb(meta, headers)
        items.append(Item(index=index, type=kind, title=title, thumb=thumb,
                          width=width if isinstance(width, int) else None,
                          height=height if isinstance(height, int) else None,
                          duration=meta.get("duration") if isinstance(meta.get("duration"), (int, float)) else None,
                          options=options))

    if not items:
        raise ExtractionError("No media found", "no_media")

    first_meta = urls[0][1] or {}
    merged = {**post_meta, **first_meta}
    date = merged.get("date")
    likes = merged.get("likes") or merged.get("like_count") or merged.get("favorite_count")
    return Media(
        url=url, platform=key, platform_name=name if key != "web" else extr.category.title(),
        source="gallery-dl",
        title=clean_title(_first_text(merged, "description", "content", "title", "caption", "text")),
        uploader=_gdl_uploader(merged),
        upload_date=date.strftime("%Y-%m-%d") if isinstance(date, (dt.date, dt.datetime)) else None,
        likes=likes if isinstance(likes, int) else None,
        thumb=next((item.thumb for item in items if item.thumb), None),
        items=items,
        truncated=len(urls) > settings.max_items,
        cookies=cookies,
    )


# ------------------------------------------------------------------- page metadata

class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[tuple[str, str]] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            data = {k.lower(): (v or "") for k, v in attrs}
            key = (data.get("property") or data.get("name") or data.get("itemprop") or "").lower()
            if key and data.get("content"):
                self.meta.append((key, data["content"].strip()))
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self.title) < 300:
            self.title += data


def from_page(url: str, settings: Settings, cookies: str) -> Media:
    key, name = detect_platform(url)
    headers = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
    try:
        with httpx.Client(**client_kwargs(settings.proxy)) as client:
            response = open_stream_sync(client, url, headers, settings.allow_private_networks)
            try:
                if response.status_code >= 400:
                    raise ExtractionError(f"HTTP Error {response.status_code}")
                final_url = str(response.url)
                ctype = response.headers.get("content-type", "").lower()
                if ctype.startswith(("image/", "video/", "audio/")):
                    ext = guess_ext(final_url, ctype, "bin")
                    kind = kind_for_ext(ext) if ext in VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS else ctype.split("/")[0]
                    size = response.headers.get("content-length")
                    filename = urlsplit(final_url).path.rsplit("/", 1)[-1]
                    return _single_file_media(url, final_url, kind, ext, int(size) if size and size.isdigit() else None,
                                              filename, key, name, cookies)
                if "html" not in ctype and "xml" not in ctype:
                    raise ExtractionError("No media found", "no_media")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_500_000:
                        break
            finally:
                response.close()
    except httpx.HTTPError as exc:
        raise ExtractionError(f"{exc.__class__.__name__}: {exc}") from exc

    parser = _MetaParser()
    try:
        parser.feed(body.decode(response.encoding or "utf-8", errors="replace"))
    except Exception:
        pass
    meta: dict[str, list[str]] = {}
    for k, v in parser.meta:
        meta.setdefault(k, []).append(v)

    def first(*keys: str) -> str:
        for k in keys:
            if meta.get(k):
                return meta[k][0]
        return ""

    referer = {"Referer": final_url}
    items: list[Item] = []
    for key_name in ("og:video:secure_url", "og:video:url", "og:video", "twitter:player:stream"):
        for video_url in meta.get(key_name, []):
            video_url = urljoin(final_url, video_url)
            ext = guess_ext(video_url, first("og:video:type"))
            if ext in VIDEO_EXTS and ext != "m3u8" and not any(o.source.url == video_url
                                                               for i in items for o in i.options):
                items.append(_file_item(len(items), "video", video_url, ext, referer, "Original video"))
    seen: set[str] = set()
    for key_name in ("og:image:secure_url", "og:image:url", "og:image", "twitter:image", "twitter:image:src"):
        for image_url in meta.get(key_name, []):
            image_url = urljoin(final_url, image_url)
            if image_url in seen or not image_url.startswith(("http://", "https://")):
                continue
            seen.add(image_url)
            ext = guess_ext(image_url, first("og:image:type"), "jpg")
            if ext not in IMAGE_EXTS:
                ext = "jpg"
            items.append(_file_item(len(items), "image", image_url, ext, referer, "Preview image"))
        if seen:
            break
    if not items:
        raise ExtractionError("No media found", "no_media")

    title = first("og:title", "twitter:title") or parser.title
    return Media(
        url=url, platform=key, platform_name=name if key != "web" else (first("og:site_name") or name),
        source="page", title=clean_title(title), uploader=first("og:site_name", "author"),
        description=clean_title(first("og:description", "description"), 400),
        thumb=next((i.thumb for i in items if i.thumb), None), items=items, cookies=cookies,
    )


def _file_item(index: int, kind: str, file_url: str, ext: str, headers: dict[str, str], note: str) -> Item:
    options = [Option(id="", kind=kind, label="Original", ext=ext, filename="", note=note,
                      source=Source(kind="direct", url=file_url, headers=headers))]
    if kind == "video" and ffmpeg_available():
        options.append(Option(id="", kind="audio", label="MP3", ext="mp3", filename="",
                              note="192 kbps · converted", needs_processing=True,
                              source=Source(kind="direct", url=file_url, headers=headers, audio_codec="mp3")))
    return Item(index=index, type=kind, thumb=Thumb(file_url, headers) if kind == "image" else None,
                options=options)


def _single_file_media(url: str, final_url: str, kind: str, ext: str, size: int | None,
                       filename: str, key: str, name: str, cookies: str) -> Media:
    item = _file_item(0, kind, final_url, ext, {}, "Direct file")
    item.options[0].size = size
    stem = filename.rsplit(".", 1)[0] if filename else ""
    return Media(url=url, platform=key, platform_name=name, source="direct",
                 title=clean_title(stem) or "Direct file", items=[item],
                 thumb=item.thumb, cookies=cookies)


# --------------------------------------------------------------------------- driver

ENGINES: dict[str, Callable[[str, Settings, str], Media]] = {
    "yt-dlp": from_ytdlp,
    "gallery-dl": from_gallery_dl,
    "page": from_page,
}


def engine_order(platform: str, url: str) -> list[str]:
    path = urlsplit(url).path.lower()
    if platform == "instagram":
        if any(part in path for part in ("/reel", "/tv/", "/stories/")):
            return ["yt-dlp", "gallery-dl", "page"]
        return ["gallery-dl", "yt-dlp", "page"]
    if platform == "snapchat" and ("/story" in path or "/highlight" in path or path.startswith("/add/")):
        return ["gallery-dl", "yt-dlp", "page"]
    if platform in GALLERY_FIRST:
        return ["gallery-dl", "yt-dlp", "page"]
    return ["yt-dlp", "gallery-dl", "page"]


def _only_audio(media: Media) -> bool:
    items = media.downloadable_items()
    return bool(items) and all(item.type == "audio" for item in items)


def _merge_slideshow(audio_media: Media, photo_media: Media) -> Media:
    photos = [item for item in photo_media.downloadable_items() if item.type != "audio"]
    audio = audio_media.downloadable_items()
    merged = copy.copy(audio_media)
    merged.items = photos + audio
    for index, item in enumerate(merged.items):
        item.index = index
        if item.type == "audio" and not item.title:
            item.title = "Sound"
    merged.thumb = photo_media.thumb or audio_media.thumb
    merged.title = audio_media.title or photo_media.title
    merged.source = "yt-dlp + gallery-dl"
    return merged


def file_stem(media: Media) -> str:
    stem = strip_hashtags(media.title or "") or f"{media.platform_name} media"
    if media.uploader and media.uploader.lower() not in stem.lower():
        stem = f"{media.uploader} - {stem}"
    return stem


def _finalize(media: Media) -> Media:
    stem = file_stem(media)
    counter = 0
    items = media.downloadable_items()
    for item in items:
        item_stem = stem if len(items) == 1 else f"{stem} ({item.index + 1})"
        for opt in item.options:
            counter += 1
            opt.id = f"o{counter}"
            opt.filename = safe_filename(item_stem, opt.ext)
    if media.platform in WATERMARK_PLATFORMS:
        visual = [opt for item in items for opt in item.options if opt.kind in {"video", "image"}]
        media.watermark_free = bool(visual) and not any(opt.watermark for opt in visual)
    if media.duration is None and len(items) == 1:
        media.duration = items[0].duration
    return media


def extract(url: str, settings: Settings) -> tuple[Media, str | None]:
    """Return (media, notice). Raises ExtractionError when nothing usable was found."""
    platform, _ = detect_platform(url)
    cookies = settings.read_cookies()
    errors: list[ExtractionError] = []
    result: Media | None = None
    for engine in engine_order(platform, url):
        try:
            media = ENGINES[engine](url, settings, cookies)
        except ExtractionError as exc:
            log.info("%s failed (%s): %s", engine, platform, redact(exc.detail))
            errors.append(exc)
            continue
        except Exception as exc:  # an engine bug must not hide the other engines
            log.exception("%s crashed (%s)", engine, platform)
            errors.append(ExtractionError(f"{exc.__class__.__name__}: {exc}"))
            continue
        if not media.downloadable_items():
            errors.append(ExtractionError("No media found", "no_media"))
            continue
        if engine == "yt-dlp" and platform in PHOTO_CAPABLE and _only_audio(media):
            try:
                photos = from_gallery_dl(url, settings, cookies)
                if any(item.type == "image" for item in photos.downloadable_items()):
                    media = _merge_slideshow(media, photos)
            except Exception as exc:
                log.info("slideshow lookup failed (%s): %s", platform, redact(str(exc)))
        result = media
        break

    if result is None:
        raise _best_error(errors)

    notice = None
    if result.source == "page" and platform != "web" and errors:
        best = _best_error(errors)
        notice = f"Only the preview could be saved. {best.friendly}"
    return _finalize(result), notice


def _best_error(errors: list[ExtractionError]) -> ExtractionError:
    if not errors:
        return ExtractionError("No media found", "no_media")
    return min(errors, key=lambda e: _ERROR_RANK.index(e.code) if e.code in _ERROR_RANK else len(_ERROR_RANK))
