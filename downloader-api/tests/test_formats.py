"""Format selection: watermark-free TikTok picks, YouTube merges, audio options."""

from app.extract import _finalize, _ytdl_item_options, engine_order
from app.models import Item, Media


def no_cookies(_url):
    return None


def tiktok_entry():
    common = {"http_headers": {"Referer": "https://www.tiktok.com/", "User-Agent": "UA"}}
    return {
        "id": "7300000000000000000",
        "title": "dance #fyp",
        "duration": 15,
        "webpage_url": "https://www.tiktok.com/@user/video/7300000000000000000",
        "formats": [
            {**common, "format_id": "download", "url": "https://v16.tiktokcdn.com/wm.mp4",
             "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 576, "height": 1024,
             "format_note": "watermarked", "protocol": "https", "preference": -2},
            {**common, "format_id": "bytevc1_1080p_1500000-0", "url": "https://v16.tiktokcdn.com/hevc.mp4",
             "ext": "mp4", "vcodec": "h265", "acodec": "aac", "width": 1080, "height": 1920,
             "tbr": 1500, "protocol": "https"},
            {**common, "format_id": "h264_1080p_2000000-0", "url": "https://v16.tiktokcdn.com/avc.mp4",
             "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 1080, "height": 1920,
             "tbr": 2000, "filesize": 4_000_000, "protocol": "https"},
            {**common, "format_id": "h264_540p_800000-0", "url": "https://v16.tiktokcdn.com/avc540.mp4",
             "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 576, "height": 1024,
             "tbr": 800, "protocol": "https"},
            {**common, "format_id": "audio", "url": "https://sf16.tiktokcdn.com/music.mp3",
             "ext": "mp3", "vcodec": "none", "acodec": "mp3", "abr": 128, "protocol": "https"},
        ],
    }


def test_tiktok_prefers_clean_h264_and_skips_watermark():
    options = _ytdl_item_options(tiktok_entry(), no_cookies, True, "https://www.tiktok.com/x")
    videos = [o for o in options if o.kind == "video"]
    assert [o.label for o in videos] == ["1080p", "576p"]
    best = videos[0]
    assert best.source.kind == "direct"
    assert best.source.url == "https://v16.tiktokcdn.com/avc.mp4"
    assert best.source.headers["Referer"] == "https://www.tiktok.com/"
    assert best.size == 4_000_000
    assert not any(o.watermark for o in videos)
    assert all("wm.mp4" not in (o.source.url or "") for o in options)


def test_tiktok_audio_options_and_finalize_flags():
    options = _ytdl_item_options(tiktok_entry(), no_cookies, True, "https://www.tiktok.com/x")
    audio = [o for o in options if o.kind == "audio"]
    assert [o.label for o in audio] == ["MP3", "MP3"]
    assert audio[0].mode == "process" and audio[0].source.audio_codec == "mp3"
    assert audio[1].mode == "direct"  # the original sound file

    media = Media(url="https://www.tiktok.com/x", platform="tiktok", platform_name="TikTok",
                  source="yt-dlp", title="dance #fyp", uploader="user",
                  items=[Item(index=0, type="video", options=options)])
    _finalize(media)
    assert media.watermark_free is True
    assert [o.id for o in options] == [f"o{i}" for i in range(1, len(options) + 1)]
    assert options[0].filename == "user - dance.mp4"


def test_only_watermarked_copy_is_flagged():
    entry = tiktok_entry()
    entry["formats"] = [f for f in entry["formats"] if f["format_id"] in {"download", "audio"}]
    options = _ytdl_item_options(entry, no_cookies, True, "https://www.tiktok.com/x")
    video = next(o for o in options if o.kind == "video")
    assert video.watermark is True
    assert "Watermarked" in video.note


def youtube_entry():
    def fmt(fid, **kw):
        base = {"format_id": fid, "url": f"https://rr.googlevideo.com/{fid}", "protocol": "https",
                "downloader_options": {"http_chunk_size": 10485760}}
        base.update(kw)
        return base

    return {
        "id": "abc", "title": "Video", "duration": 212, "webpage_url": "https://www.youtube.com/watch?v=abc",
        "formats": [
            fmt("sb0", ext="mhtml", vcodec="none", acodec="none", format_note="storyboard", protocol="mhtml"),
            fmt("140", ext="m4a", vcodec="none", acodec="mp4a.40.2", abr=129, filesize=3_000_000),
            fmt("251", ext="webm", vcodec="none", acodec="opus", abr=140),
            fmt("18", ext="mp4", vcodec="avc1.42001E", acodec="mp4a.40.2", width=640, height=360, tbr=500),
            fmt("137", ext="mp4", vcodec="avc1.640028", acodec="none", width=1920, height=1080, tbr=4000,
                filesize=50_000_000),
            fmt("248", ext="webm", vcodec="vp9", acodec="none", width=1920, height=1080, tbr=3000),
            fmt("313", ext="webm", vcodec="vp9", acodec="none", width=3840, height=2160, tbr=16000, fps=60),
        ],
    }


def test_youtube_merges_dash_and_keeps_progressive():
    options = _ytdl_item_options(youtube_entry(), no_cookies, True, "https://www.youtube.com/watch?v=abc")
    videos = [o for o in options if o.kind == "video"]
    assert [o.label for o in videos] == ["2160p60", "1080p", "360p"]
    uhd, fhd, sd = videos
    assert uhd.source.format == "313+140" and uhd.source.merge and uhd.note.startswith("4K")
    assert fhd.source.format == "137+140"  # H.264 beats VP9 for compatibility
    assert fhd.size == 53_000_000
    assert sd.source.format == "18" and sd.mode == "process"  # chunked download handled by yt-dlp
    audio = [o for o in options if o.kind == "audio"]
    assert [o.label for o in audio] == ["MP3", "M4A"]
    assert audio[1].source.format == "140"


def test_no_ffmpeg_hides_merges_and_conversion():
    options = _ytdl_item_options(youtube_entry(), no_cookies, False, "https://www.youtube.com/watch?v=abc")
    assert not any(o.source.merge or o.source.audio_codec for o in options)
    videos = {o.label: o for o in options if o.kind == "video"}
    assert "No sound" in videos["1080p"].note
    assert "No sound" not in videos["360p"].note


def test_engine_order_per_platform():
    assert engine_order("instagram", "https://www.instagram.com/p/abc/")[0] == "gallery-dl"
    assert engine_order("instagram", "https://www.instagram.com/reel/abc/")[0] == "yt-dlp"
    assert engine_order("instagram", "https://www.instagram.com/stories/user/123/")[0] == "yt-dlp"
    assert engine_order("pinterest", "https://pin.it/abc")[0] == "gallery-dl"
    assert engine_order("snapchat", "https://www.snapchat.com/add/user")[0] == "gallery-dl"
    assert engine_order("tiktok", "https://www.tiktok.com/@u/video/1")[0] == "yt-dlp"
    assert engine_order("web", "https://example.com/")[-1] == "page"
