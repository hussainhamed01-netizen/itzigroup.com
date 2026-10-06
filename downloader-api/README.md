# ItziGroup Downloader

Paste a link, get the media. Videos, reels, stories, photos, carousels and audio from
TikTok, Instagram, YouTube, X, Facebook, Snapchat, Threads, Pinterest, Reddit and 1,000+
other sites. Original quality, with no TikTok watermark.

```
downloader/        Web UI (static). Lives at itzigroup.com/downloader/ and is also served by the API.
downloader-api/    Python API that does the actual work (this folder).
```

GitHub Pages can only host static files, so the UI needs this API running on a real
server to work.

## How it works

| Engine | Used for |
| --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Videos and audio on 1,800+ sites: TikTok, YouTube, Instagram reels, X, Facebook, Vimeo… |
| [gallery-dl](https://github.com/mikf/gallery-dl) | Photos, carousels and stories: Instagram posts, Pinterest, Snapchat stories, TikTok photo slideshows… |
| Page metadata | Any other page with Open Graph media, plus direct file links |

The API tries the engines in the best order for each platform and falls back to the next
one when an engine finds nothing.

* **No watermark.** TikTok serves a clean copy of every video for in-app playback. yt-dlp
  labels the watermarked "download" copy, and the API skips it. If only a watermarked copy
  exists, the option is clearly marked.
* **Best quality.** Every resolution is listed, up to 4K60. When a site stores video and
  audio separately (YouTube, Instagram, Facebook), ffmpeg merges them into one MP4.
* **Fast path.** A ready-made file is streamed from the platform straight to the visitor,
  without touching the server's disk. Anything that needs merging, converting (MP3) or
  zipping runs as a background job with live progress.

## Run it

You need Docker. From the **repository root**:

```bash
cd downloader-api
docker compose up -d --build
```

Open http://localhost:8000. The image includes ffmpeg and Deno (yt-dlp uses Deno for
YouTube), and it updates yt-dlp and gallery-dl every time it starts.

Without Docker (Python 3.11+, with `ffmpeg` and ideally `deno` on the PATH):

```bash
cd downloader-api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

## Put it on itzigroup.com

The page at `https://itzigroup.com/downloader/` expects the API at
**`https://dl.itzigroup.com`**.

1. Run the Docker image on any server: a small VPS, Render, Railway, Fly.io, etc. Give it
   at least 1 GB RAM and a few GB of disk for merge jobs.
2. Point the `dl.itzigroup.com` DNS record at it and serve it over HTTPS. Most hosts do
   this for you. On a VPS, [Caddy](https://caddyserver.com) does it with one line:
   `dl.itzigroup.com { reverse_proxy localhost:8000 }`. Behind a proxy, set `TRUST_PROXY=1`.
3. Open `https://dl.itzigroup.com/api/health`. It should say `"status": "ok"`.

To use a different address, change it in `downloader/config.js` and in the
`connect-src` and `img-src` lists of `downloader/index.html`'s Content-Security-Policy,
then add your site to `ALLOWED_ORIGINS`.

`https://dl.itzigroup.com/` also serves the full UI by itself, so you can link people
straight there.

## Stories, private posts and "Sign in to confirm you're not a bot"

Some content needs a logged-in account: Instagram stories, private or age-restricted
posts, and sometimes all of Instagram or X. YouTube may also block busy server IPs. To
fix this, give the server a cookies file:

1. Log in to the site in a browser, preferably with a **secondary account**: platforms can
   ban accounts that download a lot.
2. Export the cookies in Netscape `cookies.txt` format, for example with the
   "Get cookies.txt LOCALLY" extension. You can put several sites in one file.
3. Mount the file into the container and set `COOKIES_FILE` (see `docker-compose.yml`).

Treat this file like a password. It is ignored by git (`cookies.txt`) and never sent to
visitors. If the server IP itself is blocked, set `OUTBOUND_PROXY` to route platform
traffic through a residential proxy.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | itzigroup.com + localhost | Sites whose pages may call the API (comma-separated, `*` for any) |
| `COOKIES_FILE` | — | Netscape cookies.txt for logged-in content |
| `OUTBOUND_PROXY` | — | Proxy for all platform traffic, e.g. `http://user:pass@host:port` |
| `TRUST_PROXY` | `0` | How many reverse proxies sit in front of the API: `1` behind Caddy, Nginx, Render or Railway; `2` with Cloudflare in front of one of those. Used to find the visitor's real IP for rate limits |
| `AUTO_UPDATE` | `1` (Docker) | Upgrade yt-dlp and gallery-dl on start |
| `MAX_FILESIZE_MB` | `2048` | Largest file the server will handle |
| `MAX_DURATION_MIN` | `240` | Longest media it will merge or convert |
| `MAX_ITEMS` | `30` | Most items read from a carousel, thread or playlist |
| `MAX_JOBS` | `3` | Merge/convert/ZIP jobs running at once |
| `MAX_EXTRACTIONS` | `4` | Links analyzed at once |
| `RATE_EXTRACT_PER_MIN` | `30` | Links one visitor may analyze per minute |
| `RATE_DOWNLOAD_PER_MIN` | `60` | Downloads one visitor may start per minute |
| `MEDIA_TTL` | `1800` | Seconds an analyzed link stays downloadable |
| `FILE_TTL` | `1200` | Seconds a finished job file is kept |
| `DATA_DIR` | `/data` (Docker) | Where job files are written |
| `JS_RUNTIMES` | auto | JavaScript runtimes yt-dlp may use (`deno,node,bun`) |
| `LOG_LEVEL` | `INFO` | Server log level |
| `ALLOW_PRIVATE_NETWORKS` | `0` | Testing only: allow links to local/private addresses |

Run **one** worker process: results and jobs are kept in memory.

## Privacy and safety

* Links are stripped from every server log line (they show up as `<url>`), and library
  request logging is turned off. Results expire after `MEDIA_TTL`, and job files are
  deleted after `FILE_TTL`.
* Pasted links that point at local or private addresses are refused. Files and previews
  the API streams itself are checked the same way at every redirect (SSRF protection).
  yt-dlp and gallery-dl make their own requests, so don't run the API on a network where
  internal services trust any caller.
* Only media content types are passed through to visitors, and per-IP rate limits stop
  abuse.

## API

| Method | Path | |
| --- | --- | --- |
| `GET` | `/api/health` | Engine versions, ffmpeg status, limits |
| `POST` | `/api/extract` | `{"url": "...", "fresh": false}` → title, items and download options |
| `GET` | `/api/media/{id}/file/{option}` | Stream a ready-made file (options with `mode: "direct"`) |
| `GET` | `/api/media/{id}/thumb/{index or "main"}` | Preview image |
| `POST` | `/api/media/{id}/jobs` | `{"option": "o3"}` or `{"option": "all"}` (ZIP) → job |
| `GET` | `/api/jobs/{id}` | Job progress |
| `GET` | `/api/jobs/{id}/file` | Finished file |
| `DELETE` | `/api/jobs/{id}` | Cancel |

Interactive docs: `/api/docs`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run offline. They cover format selection (watermark-free TikTok picks, YouTube
merges), URL safety, the full extract → download → ZIP flow against a local web server,
and rate limiting.

## Responsible use

Only download content you own, have permission to use, or that is licensed for reuse, and
respect each platform's terms. If you run a public instance, you are responsible for how
it is used.
