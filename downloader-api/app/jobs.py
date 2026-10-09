"""Background jobs for downloads that need the server: merging, converting, zipping."""

from __future__ import annotations

import copy
import logging
import shutil
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .extract import file_stem, ytdl_params
from .models import Item, Job, Media, Option, TTLStore
from .netsafe import UnsafeURLError, client_kwargs, open_stream_sync
from .util import classify_error, redact, safe_filename

log = logging.getLogger("itzi.jobs")

_PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp", ".frag")


class JobCancelled(Exception):
    pass


class JobFailed(Exception):
    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


@dataclass
class Progress:
    """Reports progress for one file, optionally as a slice of a bigger job."""

    job: Job
    offset: float = 0.0
    scale: float = 1.0
    prefix: str = ""
    _last: float = 0.0

    def check(self) -> None:
        if self.job.cancel.is_set():
            raise JobCancelled()

    def stage(self, text: str, progress: float | None = None) -> None:
        self.check()
        self.job.stage = f"{self.prefix}{text}"
        if progress is not None:
            self.job.progress = self.offset + self.scale * progress
        elif self.scale >= 1.0:
            self.job.progress = None

    def bytes(self, downloaded: int, total: int | None, speed: float | None = None,
              eta: float | None = None, fraction: float | None = None, force: bool = False) -> None:
        self.check()
        now = time.monotonic()
        if not force and now - self._last < 0.25:
            return
        self._last = now
        self.job.downloaded = downloaded
        self.job.total = total
        self.job.speed = speed
        self.job.eta = int(eta) if eta is not None else None
        if fraction is None and total:
            fraction = downloaded / total
        if fraction is not None:
            self.job.progress = self.offset + self.scale * max(0.0, min(1.0, fraction))


def fetch_direct(url: str, headers: dict[str, str], dest: Path, progress: Progress,
                 settings: Settings) -> Path:
    progress.stage("Downloading", 0.0)
    started = time.monotonic()
    with httpx.Client(**client_kwargs(settings.proxy)) as client:
        try:
            response = open_stream_sync(client, url, headers, settings.allow_private_networks)
        except UnsafeURLError as exc:
            raise JobFailed(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise JobFailed(f"Network error: {exc}", "timeout") from exc
        try:
            if response.status_code >= 400:
                raise JobFailed(f"HTTP Error {response.status_code}: the media link was refused. "
                                "Analyze the link again to refresh it.",
                                "not_found" if response.status_code in (403, 404, 410) else "failed")
            length = response.headers.get("content-length")
            total = int(length) if length and length.isdigit() else None
            if total and total > settings.max_filesize:
                raise JobFailed("This file is larger than the server allows.", "too_large")
            downloaded = 0
            with open(dest, "wb") as handle:
                for chunk in response.iter_bytes(256 * 1024):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > settings.max_filesize:
                        raise JobFailed("This file is larger than the server allows.", "too_large")
                    elapsed = max(time.monotonic() - started, 0.001)
                    speed = downloaded / elapsed
                    eta = (total - downloaded) / speed if total and speed else None
                    progress.bytes(downloaded, total, speed, eta)
            progress.bytes(downloaded, total or downloaded, force=True, fraction=1.0)
        finally:
            response.close()
    return dest


def convert_audio(source: Path, codec: str, progress: Progress) -> Path:
    progress.stage("Converting to " + codec.upper())
    target = source.with_name(f"audio.{codec}")
    codec_args = {
        "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
        "m4a": ["-c:a", "aac", "-b:a", "192k"],
    }.get(codec, ["-b:a", "192k"])
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(source), "-vn", "-map_metadata", "-1", *codec_args, str(target)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    except FileNotFoundError as exc:
        raise JobFailed("Audio conversion is unavailable: ffmpeg is not installed.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace")[-300:] if exc.stderr else ""
        if "does not contain any stream" in detail or "matches no streams" in detail:
            raise JobFailed("This video has no sound to convert.", "no_media") from exc
        raise JobFailed(f"Audio conversion failed. {detail}".strip()) from exc
    except subprocess.TimeoutExpired as exc:
        raise JobFailed("Audio conversion took too long.", "timeout") from exc
    source.unlink(missing_ok=True)
    return target


def _find_output(workdir: Path) -> Path:
    files = [p for p in workdir.iterdir()
             if p.is_file() and not p.name.endswith(_PARTIAL_SUFFIXES) and ".part-" not in p.name
             and not p.name.endswith((".json", ".jpg", ".webp", ".png", ".vtt"))]
    if not files:
        raise JobFailed("The download finished without producing a file.")
    return max(files, key=lambda p: p.stat().st_size)


def ytdl_download(media: Media, option: Option, workdir: Path, progress: Progress,
                  settings: Settings) -> Path:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadCancelled, DownloadError

    source = option.source
    duration = (source.entry or {}).get("duration") or media.duration
    if duration and duration > settings.max_duration:
        raise JobFailed(f"This media is longer than the server's {settings.max_duration // 60}-minute "
                        "limit for converting or merging.", "too_large")

    def hook(status: dict[str, Any]) -> None:
        if progress.job.cancel.is_set():
            raise DownloadCancelled("Cancelled")
        if status.get("status") != "downloading":
            return
        info = status.get("info_dict") or {}
        has_video = (info.get("vcodec") or "") != "none"
        has_audio = (info.get("acodec") or "") != "none"
        what = "video" if has_video and not has_audio else "audio" if has_audio and not has_video else "media"
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        fraction = None
        if not total and status.get("fragment_count"):
            fraction = (status.get("fragment_index") or 0) / status["fragment_count"]
        progress.job.stage = f"{progress.prefix}Downloading {what}"
        progress.bytes(int(status.get("downloaded_bytes") or 0), int(total) if total else None,
                       status.get("speed"), status.get("eta"), fraction)

    def pp_hook(status: dict[str, Any]) -> None:
        if progress.job.cancel.is_set():
            raise DownloadCancelled("Cancelled")
        if status.get("status") != "started":
            return
        name = status.get("postprocessor") or ""
        label = {"Merger": "Merging video and audio", "FFmpegExtractAudio": "Converting to MP3",
                 "FixupM3u8": "Finishing up", "FFmpegFixupM3u8": "Finishing up",
                 "MoveFiles": "Finishing up"}.get(name, "Processing")
        progress.stage(label)

    def run(fmt: str, use_entry: bool) -> None:
        params = ytdl_params(
            settings, media.cookies,
            skip_download=False,
            format=fmt,
            outtmpl={"default": "media.%(ext)s"},
            paths={"home": str(workdir), "temp": str(workdir)},
            progress_hooks=[hook],
            postprocessor_hooks=[pp_hook],
            max_filesize=settings.max_filesize,
            concurrent_fragment_downloads=4,
            overwrites=True,
            ignore_no_formats_error=False,
            playlist_items="1",
        )
        if source.merge:
            params["merge_output_format"] = "mp4/mkv"
        if source.audio_codec:
            params["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                         "preferredcodec": source.audio_codec,
                                         "preferredquality": "192"}]
        with YoutubeDL(params) as ydl:
            if use_entry:
                ydl.process_ie_result(copy.deepcopy(source.entry), download=True)
            else:
                ydl.download([source.url or source.page_url])

    progress.stage("Starting download", 0.0)
    attempts: list[tuple[str, bool]] = []
    if source.entry is not None and not source.url:
        attempts.append((source.format or "b", True))
    if source.page_url or source.url:
        attempts.append((source.fallback_format or source.format or "b", False))
    last_error: Exception | None = None
    for fmt, use_entry in attempts:
        try:
            run(fmt, use_entry)
            return _find_output(workdir)
        except (DownloadCancelled, JobCancelled) as exc:
            raise JobCancelled() from exc
        except DownloadError as exc:
            if progress.job.cancel.is_set():
                raise JobCancelled() from exc
            if "File is larger than max-filesize" in str(exc):
                raise JobFailed("This file is larger than the server allows.", "too_large") from exc
            last_error = exc
            log.info("yt-dlp attempt failed (%s): %s", fmt, redact(str(exc)))
            for leftover in workdir.iterdir():
                if leftover.is_file():
                    leftover.unlink(missing_ok=True)
        except JobFailed as exc:
            last_error = exc
    if isinstance(last_error, JobFailed):
        raise last_error
    code, friendly, _ = classify_error(str(last_error or "Download failed"))
    raise JobFailed(friendly, code)


def run_option(media: Media, option: Option, workdir: Path, progress: Progress,
               settings: Settings) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    source = option.source
    if source.kind == "direct":
        ext = option.ext or "bin"
        path = fetch_direct(source.url or "", source.headers, workdir / f"media.{ext}", progress, settings)
        if source.audio_codec:
            path = convert_audio(path, source.audio_codec, progress)
        return path
    return ytdl_download(media, option, workdir, progress, settings)


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: TTLStore[Job] = TTLStore(ttl=6 * 3600, max_entries=2000)
        self.executor = ThreadPoolExecutor(max_workers=settings.max_jobs, thread_name_prefix="dl-job")

    def active_count(self) -> int:
        return sum(1 for job in self.jobs.values() if job.status in {"queued", "running"})

    def submit(self, media: Media, option_id: str) -> Job:
        job = Job(media_id=media.id, option_id=option_id)
        job.workdir = self.root / job.id
        self.jobs.put(job.id, job)
        self.executor.submit(self._run, job, media)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        job.cancel.set()
        if job.status == "queued":
            job.status = "cancelled"
            job.stage = "Cancelled"
        elif job.status == "done":
            self._discard(job)
            self.jobs.pop(job.id)
        return job

    def _run(self, job: Job, media: Media) -> None:
        if job.cancel.is_set():
            return
        job.status = "running"
        job.stage = "Starting"
        workdir = job.workdir or self.root / job.id
        try:
            ready = "Ready"
            if job.option_id == "all":
                path, filename, skipped = self._bundle(job, media, workdir)
                if skipped:
                    ready = f"Ready · {skipped} item(s) couldn't be included"
            else:
                found = media.option(job.option_id)
                if found is None:
                    raise JobFailed("That download option no longer exists.")
                _, option = found
                path = run_option(media, option, workdir, Progress(job), self.settings)
                stem = option.filename.rsplit(".", 1)[0]
                filename = safe_filename(stem, path.suffix.lstrip(".") or option.ext)
            job.path = path
            job.filename = filename
            job.size = path.stat().st_size
            job.downloaded = job.total = job.size
            job.speed = job.eta = None
            job.progress = 1.0
            job.stage = ready
            job.status = "done"
            self.jobs.touch(job.id, ttl=self.settings.file_ttl)
        except JobCancelled:
            job.status = "cancelled"
            job.stage = "Cancelled"
            shutil.rmtree(workdir, ignore_errors=True)
        except JobFailed as exc:
            job.status = "error"
            job.stage = "Failed"
            job.error = str(exc)
            job.error_code = exc.code
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception as exc:
            log.exception("job %s crashed", job.id)
            code, friendly, _ = classify_error(str(exc))
            job.status = "error"
            job.stage = "Failed"
            job.error = friendly
            job.error_code = code
            shutil.rmtree(workdir, ignore_errors=True)
        finally:
            job.finished = time.time()
            if job.status != "done":
                self.jobs.touch(job.id, ttl=300)

    def _bundle(self, job: Job, media: Media, workdir: Path) -> tuple[Path, str, int]:
        items: list[Item] = media.downloadable_items()
        if not items:
            raise JobFailed("Nothing to download.", "no_media")
        workdir.mkdir(parents=True, exist_ok=True)
        files: list[tuple[Path, str]] = []
        failures = 0
        count = len(items)
        for position, item in enumerate(items):
            option = item.options[0]
            progress = Progress(job, offset=position / count, scale=1 / count,
                                prefix=f"Item {position + 1} of {count} · ")
            try:
                path = run_option(media, option, workdir / f"item{position}", progress, self.settings)
            except JobFailed:
                failures += 1
                continue
            stem = option.filename.rsplit(".", 1)[0]
            files.append((path, safe_filename(stem, path.suffix.lstrip("."))))
        if not files:
            raise JobFailed("None of the items could be downloaded. Analyze the link again and retry.")
        Progress(job).stage("Creating ZIP")
        stem = file_stem(media)
        archive = workdir / "bundle.zip"
        used: set[str] = set()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for path, name in files:
                candidate, counter = name, 2
                while candidate in used:
                    base, _, ext = name.rpartition(".")
                    candidate = f"{base} ({counter}).{ext}"
                    counter += 1
                used.add(candidate)
                zf.write(path, arcname=candidate)
                path.unlink(missing_ok=True)
        return archive, safe_filename(stem, "zip"), failures

    def _discard(self, job: Job) -> None:
        if job.workdir:
            shutil.rmtree(job.workdir, ignore_errors=True)

    def cleanup(self) -> None:
        for job in self.jobs.purge():
            job.cancel.set()
            self._discard(job)
        # Folders left behind by a previous run of the server.
        live = {job.id for job in self.jobs.values()}
        cutoff = time.time() - max(self.settings.file_ttl, 600)
        for folder in self.root.iterdir():
            try:
                if folder.name not in live and folder.stat().st_mtime < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue

    def shutdown(self) -> None:
        for job in self.jobs.values():
            job.cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
