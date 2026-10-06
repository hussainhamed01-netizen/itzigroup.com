"""End-to-end API tests against a throwaway local web server (no internet needed)."""

import dataclasses
import functools
import http.server
import io
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2048 + b"\xff\xd9"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    (root / "a.jpg").write_bytes(JPEG)
    (root / "b.jpg").write_bytes(JPEG + b"b")
    (root / "post.html").write_text(
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="Two photos #nature">'
        '<meta property="og:image" content="/a.jpg">'
        '<meta property="og:image" content="/b.jpg">'
        "</head><body>hi</body></html>")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def make_client(tmp_path, **overrides):
    settings = dataclasses.replace(get_settings(), data_dir=tmp_path, ui_dir=None, **overrides)
    return TestClient(create_app(settings))


def wait_for(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in {"done", "error", "cancelled"}:
            return data
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_health(tmp_path):
    with make_client(tmp_path) as client:
        data = client.get("/api/health").json()
        assert data["status"] == "ok"
        assert data["engines"]["yt_dlp"]


def test_private_links_are_refused(tmp_path, site):
    with make_client(tmp_path, allow_private_networks=False) as client:
        response = client.post("/api/extract", json={"url": f"{site}/post.html"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_url"


def test_rate_limit(tmp_path):
    with make_client(tmp_path, rate_extract=2) as client:
        codes = [client.post("/api/extract", json={"url": "nope"}).status_code for _ in range(3)]
        assert codes == [400, 400, 429]


def test_full_flow_with_page_metadata(tmp_path, site):
    with make_client(tmp_path, allow_private_networks=True) as client:
        response = client.post("/api/extract", json={"url": f"Look {site}/post.html !"})
        assert response.status_code == 200, response.text
        media = response.json()
        assert media["source"] == "page"
        assert media["title"] == "Two photos #nature"
        assert [item["type"] for item in media["items"]] == ["image", "image"]
        assert media["bundle"] == {"id": "all", "count": 2}

        first = media["items"][0]["options"][0]
        assert first["mode"] == "direct"
        file_response = client.get(first["url"])
        assert file_response.status_code == 200
        assert file_response.content == JPEG
        assert file_response.headers["content-type"] == "image/jpeg"
        assert 'attachment; filename="Two photos (1).jpg"' in file_response.headers["content-disposition"]

        thumb = client.get(media["items"][1]["thumbnail"])
        assert thumb.status_code == 200 and thumb.content == JPEG + b"b"

        job = client.post(f"/api/media/{media['id']}/jobs", json={"option": "all"})
        assert job.status_code == 202
        done = wait_for(client, job.json()["id"])
        assert done["status"] == "done", done
        archive = client.get(done["url"])
        assert archive.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            assert sorted(zf.namelist()) == ["Two photos (1).jpg", "Two photos (2).jpg"]

        again = client.post("/api/extract", json={"url": f"{site}/post.html"}).json()
        assert again["cached"] is True and again["id"] == media["id"]


def test_unknown_option_and_expired_media(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/media/missing/file/o1").json()["error"]["code"] == "expired"
        assert client.post("/api/media/missing/jobs", json={"option": "o1"}).status_code == 404
        assert client.get("/api/jobs/missing").status_code == 404
        assert client.get("/api/whatever").status_code == 404
