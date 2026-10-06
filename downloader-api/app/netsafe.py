"""URL validation and SSRF-safe fetching.

The API fetches URLs on behalf of visitors, so every hop is checked to make
sure it points at the public internet and not at the server's own network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 6
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_BARE_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?$", re.IGNORECASE)
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet")


class UnsafeURLError(ValueError):
    """The URL is malformed or points somewhere the server must not reach."""


def normalize_input_url(raw: str) -> str:
    """Pull a usable http(s) URL out of whatever the visitor pasted.

    Share sheets often paste text like "Check this out! https://vm.tiktok.com/x/".
    """
    text = (raw or "").strip()
    if not text:
        raise UnsafeURLError("Paste a link first.")
    if len(text) > 4096:
        raise UnsafeURLError("That link is too long.")

    match = _URL_IN_TEXT.search(text)
    if match:
        url = match.group(0)
    elif _BARE_DOMAIN.match(text):
        url = "https://" + text
    else:
        raise UnsafeURLError("That doesn't look like a link. Paste a full URL, e.g. https://…")

    url = url.rstrip(".,;:!?)]}>'\"")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise UnsafeURLError("Only http and https links are supported.")
    if parts.username or parts.password:
        raise UnsafeURLError("Links with embedded credentials are not allowed.")
    if len(url) > 2048:
        raise UnsafeURLError("That link is too long.")
    return url


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def _check_literal_host(host: str) -> list[str] | None:
    """Validate a host that needs no DNS. Returns [] when fine, None when DNS is needed."""
    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(_BLOCKED_SUFFIXES) or "." not in lowered and ":" not in lowered:
        raise UnsafeURLError("Links to local or private addresses are not allowed.")
    try:
        ip = ipaddress.ip_address(lowered.strip("[]"))
    except ValueError:
        return None
    if not _ip_is_public(ip):
        raise UnsafeURLError("Links to local or private addresses are not allowed.")
    return []


def _check_resolved(addresses: Iterable[str]) -> None:
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            continue
        if not _ip_is_public(ip):
            raise UnsafeURLError("Links to local or private addresses are not allowed.")


def assert_public_url(url: str, allow_private: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise UnsafeURLError("Only http and https links are supported.")
    if allow_private:
        return
    if _check_literal_host(parts.hostname) is not None:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return  # Unresolvable here: the request itself will fail (or go via the proxy).
    _check_resolved(info[4][0] for info in infos)


async def assert_public_url_async(url: str, allow_private: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise UnsafeURLError("Only http and https links are supported.")
    if allow_private:
        return
    if _check_literal_host(parts.hostname) is not None:
        return
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(parts.hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    _check_resolved(info[4][0] for info in infos)


def _request_headers(headers: dict[str, str] | None) -> dict[str, str]:
    merged = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
    for key, value in (headers or {}).items():
        if key.lower() in {"host", "content-length", "accept-encoding", "connection"}:
            continue
        if isinstance(value, str):
            merged[key] = value
    merged["Accept-Encoding"] = "identity"
    return merged


async def open_stream(client: httpx.AsyncClient, url: str, headers: dict[str, str] | None,
                      allow_private: bool = False) -> httpx.Response:
    """GET a URL as a stream, validating every redirect hop."""
    req_headers = _request_headers(headers)
    for _ in range(MAX_REDIRECTS + 1):
        await assert_public_url_async(url, allow_private)
        request = client.build_request("GET", url, headers=req_headers)
        response = await client.send(request, stream=True, follow_redirects=False)
        if response.is_redirect and response.headers.get("location"):
            await response.aclose()
            url = urljoin(url, response.headers["location"])
            continue
        return response
    raise UnsafeURLError("Too many redirects.")


def open_stream_sync(client: httpx.Client, url: str, headers: dict[str, str] | None,
                     allow_private: bool = False) -> httpx.Response:
    req_headers = _request_headers(headers)
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(url, allow_private)
        request = client.build_request("GET", url, headers=req_headers)
        response = client.send(request, stream=True, follow_redirects=False)
        if response.is_redirect and response.headers.get("location"):
            response.close()
            url = urljoin(url, response.headers["location"])
            continue
        return response
    raise UnsafeURLError("Too many redirects.")


def client_kwargs(proxy: str | None) -> dict:
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)
    kwargs: dict = {"timeout": timeout, "follow_redirects": False}
    if proxy:
        kwargs["proxy"] = proxy
        kwargs["trust_env"] = False
    return kwargs
