import pytest

from app.netsafe import UnsafeURLError, assert_public_url, normalize_input_url
from app.util import classify_error, content_disposition, detect_platform, safe_filename


@pytest.mark.parametrize("url,key", [
    ("https://vm.tiktok.com/ZMabc/", "tiktok"),
    ("https://www.instagram.com/reel/C123/", "instagram"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ("https://x.com/user/status/1", "x"),
    ("https://twitter.com/user/status/1", "x"),
    ("https://fb.watch/abc/", "facebook"),
    ("https://www.pinterest.co.uk/pin/123/", "pinterest"),
    ("https://www.threads.net/@user/post/abc", "threads"),
    ("https://story.snapchat.com/s/abc", "snapchat"),
    ("https://example.com/video", "web"),
])
def test_detect_platform(url, key):
    assert detect_platform(url)[0] == key


def test_normalize_pulls_link_out_of_shared_text():
    text = "Check this out!! https://vm.tiktok.com/ZMabc/ #fyp"
    assert normalize_input_url(text) == "https://vm.tiktok.com/ZMabc/"
    assert normalize_input_url("www.instagram.com/p/abc/") == "https://www.instagram.com/p/abc/"
    assert normalize_input_url("(https://youtu.be/abc).") == "https://youtu.be/abc"


@pytest.mark.parametrize("bad", ["", "hello", "ftp://x.com/a", "javascript:alert(1)",
                                 "https://user:pass@example.com/"])
def test_normalize_rejects(bad):
    with pytest.raises(UnsafeURLError):
        normalize_input_url(bad)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost:8000/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://100.64.0.1/",
    "http://printer.local/", "http://intranet/", "http://[::ffff:127.0.0.1]/",
])
def test_private_addresses_blocked(url):
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)
    assert_public_url(url, allow_private=True)


def test_public_ip_allowed():
    assert_public_url("https://1.1.1.1/")


def test_safe_filename():
    assert safe_filename('a/b\\c:d*?"<>|e #fyp #viral', "mp4") == "a b c d e.mp4"
    assert safe_filename("", "jpg") == "download.jpg"
    assert len(safe_filename("x" * 500, "mp4")) <= 104
    assert safe_filename("ドラゴン 🐉", "mp4") == "ドラゴン 🐉.mp4"


def test_content_disposition_unicode():
    header = content_disposition("ドラゴン.mp4")
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''%E3%83%89" in header


@pytest.mark.parametrize("message,code", [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "blocked"),
    ("ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or login required", "login_required"),
    ("ERROR: [TikTok] 1: Video not available, status code 10204", "not_found"),
    ("ERROR: Unsupported URL: https://example.com", "unsupported"),
    ("ERROR: [twitter] 1: No video could be found in this tweet", "no_media"),
    ("ERROR: This video is private", "private"),
    ("something odd", "failed"),
])
def test_classify_error(message, code):
    assert classify_error(message)[0] == code
