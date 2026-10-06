"""Small helpers shared across the API: platforms, filenames, error text."""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from urllib.parse import quote, urlsplit

# key, display name, domain suffixes
PLATFORMS: list[tuple[str, str, tuple[str, ...]]] = [
    ("tiktok", "TikTok", ("tiktok.com", "tiktokv.com", "tiktokcdn.com", "douyin.com")),
    ("instagram", "Instagram", ("instagram.com", "instagr.am", "ig.me")),
    ("youtube", "YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com", "fb.gg")),
    ("x", "X (Twitter)", ("x.com", "twitter.com", "t.co", "fxtwitter.com", "vxtwitter.com")),
    ("snapchat", "Snapchat", ("snapchat.com",)),
    ("threads", "Threads", ("threads.net", "threads.com")),
    ("pinterest", "Pinterest", ("pinterest.com", "pin.it")),
    ("reddit", "Reddit", ("reddit.com", "redd.it")),
    ("linkedin", "LinkedIn", ("linkedin.com", "lnkd.in")),
    ("tumblr", "Tumblr", ("tumblr.com",)),
    ("bluesky", "Bluesky", ("bsky.app",)),
    ("vimeo", "Vimeo", ("vimeo.com",)),
    ("twitch", "Twitch", ("twitch.tv",)),
    ("kick", "Kick", ("kick.com",)),
    ("soundcloud", "SoundCloud", ("soundcloud.com", "snd.sc")),
    ("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly")),
    ("bilibili", "Bilibili", ("bilibili.com", "b23.tv", "bilibili.tv")),
    ("rumble", "Rumble", ("rumble.com",)),
    ("imgur", "Imgur", ("imgur.com",)),
    ("9gag", "9GAG", ("9gag.com",)),
    ("vk", "VK", ("vk.com", "vkvideo.ru", "vk.ru")),
    ("likee", "Likee", ("likee.video", "l.likee.video")),
    ("streamable", "Streamable", ("streamable.com",)),
]

# Pinterest also lives on country domains such as pinterest.co.uk or pinterest.de.
_PINTEREST_RE = re.compile(r"(^|\.)pinterest\.[a-z.]{2,6}$")

VIDEO_EXTS = {"mp4", "m4v", "mov", "webm", "mkv", "flv", "avi", "3gp", "ts", "m3u8"}
AUDIO_EXTS = {"mp3", "m4a", "aac", "opus", "ogg", "oga", "wav", "flac", "weba"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "avif", "heic", "bmp", "jfif"}


def detect_platform(url: str) -> tuple[str, str]:
    host = (urlsplit(url).hostname or "").lower()
    for key, name, domains in PLATFORMS:
        if any(host == d or host.endswith("." + d) for d in domains):
            return key, name
    if _PINTEREST_RE.search(host):
        return "pinterest", "Pinterest"
    bare = host[4:] if host.startswith("www.") else host
    return "web", bare or "Web"


_ILLEGAL = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*​-‏ -‮﻿]+')
_HASHTAGS = re.compile(r"(?:\s*#[^\s#]+)+\s*$")


def clean_title(text: str | None, limit: int = 140) -> str:
    """One-line, human title from a caption or description."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = text.splitlines()[0] if text.strip() else text
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def strip_hashtags(text: str) -> str:
    """Drop the trailing "#fyp #viral" block from a caption."""
    return _HASHTAGS.sub("", text).strip() or text


def safe_filename(stem: str | None, ext: str | None, limit: int = 100) -> str:
    stem = strip_hashtags(unicodedata.normalize("NFC", stem or ""))
    stem = _ILLEGAL.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .-_")
    if len(stem) > limit:
        stem = stem[:limit].rstrip(" .-_")
    stem = stem or "download"
    ext = (ext or "").lower().lstrip(".")
    return f"{stem}.{ext}" if ext else stem


def content_disposition(filename: str, inline: bool = False) -> str:
    kind = "inline" if inline else "attachment"
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r'[^A-Za-z0-9._ ()\[\]-]+', "_", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip() or "download"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def guess_ext(url: str, content_type: str | None = None, default: str = "") -> str:
    path = urlsplit(url).path
    match = re.search(r"\.([A-Za-z0-9]{2,5})$", path)
    if match:
        ext = match.group(1).lower()
        if ext in VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS:
            return "jpg" if ext in {"jpeg", "jfif"} else ext
    if content_type:
        ctype = content_type.split(";")[0].strip().lower()
        special = {"image/jpeg": "jpg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
                   "video/quicktime": "mov", "image/webp": "webp", "video/mp2t": "ts"}
        if ctype in special:
            return special[ctype]
        guessed = mimetypes.guess_extension(ctype)
        if guessed:
            return guessed.lstrip(".")
    return default


def kind_for_ext(ext: str) -> str:
    ext = (ext or "").lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "image"


def safe_media_type(content_type: str | None, ext: str) -> str:
    """Only pass through media types; anything else downloads as a binary."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype.startswith(("image/", "video/", "audio/")) and ctype != "image/svg+xml":
        return ctype
    guessed = mimetypes.guess_type(f"file.{ext}")[0] if ext else None
    if guessed and guessed.startswith(("image/", "video/", "audio/")) and guessed != "image/svg+xml":
        return guessed
    return "application/octet-stream"


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_URLS = re.compile(r"https?://\S+")


def redact(text: str) -> str:
    """Strip links from text bound for the server log."""
    return _URLS.sub("<url>", _ANSI.sub("", text or ""))[:500]

_ERRORS: list[tuple[str, tuple[str, ...], str]] = [
    ("blocked", ("not a bot", "confirm you", "captcha", "challenge"),
     "The platform asked this server to prove it isn't a bot. Try again later, or ask the "
     "server admin to add a cookies file."),
    ("login_required", ("login", "log in", "sign in", "logged-in", "cookies", "authenticat",
                        "requires an account", "account required", "--username"),
     "This content needs a signed-in account (stories, private or age-restricted posts). "
     "The server admin can enable it with a cookies file."),
    ("private", ("private",),
     "This post is private, so it can't be downloaded."),
    ("geo", ("geo", "your country", "not available in your region"),
     "This content is blocked in the server's region."),
    ("rate_limited", ("429", "too many requests", "rate limit", "rate-limit"),
     "The platform is rate-limiting requests right now. Wait a minute and try again."),
    ("not_found", ("404", "not found", "removed", "deleted", "does not exist", "no longer available",
                   "unavailable", "not available"),
     "This content was removed or doesn't exist. Check the link and try again."),
    ("unsupported", ("unsupported url", "no suitable extractor", "no extractor"),
     "This link isn't supported. Paste the direct link to a post, reel, story or video."),
    ("no_media", ("no video", "no media", "no formats", "there's no video", "nothing to download",
                  "no downloadable"),
     "No downloadable media was found at this link."),
    ("timeout", ("timed out", "timeout"),
     "The platform took too long to answer. Try again in a moment."),
]


_FAILED = "Couldn't fetch this link. Make sure the post is public and the link is complete."
FRIENDLY = {code: friendly for code, _, friendly in _ERRORS}


def friendly_for(code: str) -> str:
    return FRIENDLY.get(code, _FAILED)


def classify_error(message: str) -> tuple[str, str, str]:
    """Map an extractor error to (code, friendly message, short detail)."""
    detail = _ANSI.sub("", message or "").replace("ERROR: ", "").strip()
    detail = re.sub(r"\s+", " ", detail)[:300]
    lowered = detail.lower()
    for code, needles, friendly in _ERRORS:
        if any(needle in lowered for needle in needles):
            return code, friendly, detail
    return "failed", _FAILED, detail
