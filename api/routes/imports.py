"""
URL Import preflight check endpoint.
Fast metadata extraction, direct file validation, SSRF checks, and friendly error taxonomy mapping.
"""
from __future__ import annotations

import concurrent.futures
import logging
import urllib.parse
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
import imageio_ffmpeg
import typing

from api.cookies_config import get_active_cookies_params
from api.direct_downloader import is_direct_video_url, validate_url_host
from api.error_taxonomy import (
    classify_url_error,
    CODE_EJS_MISSING,
    CODE_JS_RUNTIME_MISSING,
    CODE_LIVE_STREAM_UNSUPPORTED,
    CODE_TOO_LARGE,
    CODE_UNSUPPORTED_URL,
)
from api.runtime import ensure_js_runtime_on_path, get_js_runtime_config, is_ejs_installed
from api.storage import MAX_UPLOAD_GB
from pipeline import _parse_browser_cookies_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["Import"])


class ImportCheckRequest(BaseModel):
    url: str


def _extract_info_worker(url: str, ydl_opts: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp
    with yt_dlp.YoutubeDL(typing.cast(Any, ydl_opts)) as ydl:
        return ydl.extract_info(url, download=False)


@router.post("/check")
def check_import_url(payload: ImportCheckRequest) -> dict[str, Any]:
    url = payload.url.strip()
    if not url:
        return {
            "ok": False,
            "error_code": CODE_UNSUPPORTED_URL,
            "message": "Missing URL parameter.",
            "hint": "Please paste a video URL or direct video file link.",
        }

    # 0. Check if URL import is enabled
    from api.storage import is_url_import_enabled
    if not is_url_import_enabled():
        return {
            "ok": False,
            "error_code": "URL_IMPORT_DISABLED",
            "message": "URL video import is disabled on this server instance.",
            "hint": "Please upload video files directly.",
        }

    # 1. SSRF and protocol check
    try:
        validate_url_host(url)
    except ValueError as e:
        return {
            "ok": False,
            "error_code": CODE_UNSUPPORTED_URL,
            "message": str(e),
            "hint": "Please provide a publicly accessible video URL.",
        }

    # 2. Check if direct video file link (.mp4, .mkv, .mov, etc.)
    if is_direct_video_url(url):
        try:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                resp = client.head(url, headers={"User-Agent": "HighlightStudio/1.0"})
                if resp.status_code not in (200, 206, 302, 301):
                    # Try byte-range GET if HEAD unsupported
                    resp = client.get(url, headers={"User-Agent": "HighlightStudio/1.0", "Range": "bytes=0-1024"})

                if resp.status_code in (200, 206):
                    content_length = int(resp.headers.get("content-length", 0))
                    filename = Path(urllib.parse.urlparse(url).path).name or "Direct Video"

                    if content_length > MAX_UPLOAD_GB * 1024 * 1024 * 1024:
                        return {
                            "ok": False,
                            "error_code": CODE_TOO_LARGE,
                            "message": f"File exceeds maximum allowed size ({MAX_UPLOAD_GB} GB).",
                            "hint": "Choose a smaller video file or upload directly.",
                        }

                    return {
                        "ok": True,
                        "title": filename,
                        "duration_s": None,
                        "thumbnail": None,
                        "is_live": False,
                        "est_size_mb": round(content_length / (1024 * 1024), 1) if content_length > 0 else None,
                    }
        except Exception as e:
            logger.debug("Direct URL head check failed: %s", e)

    # 3. Web page / YouTube URL extraction via yt-dlp
    is_yt = "youtube.com" in url.lower() or "youtu.be" in url.lower()
    rt_name, rt_path, _ = ensure_js_runtime_on_path()
    ejs_ok = is_ejs_installed()

    if is_yt:
        if not rt_name:
            return {
                "ok": False,
                "error_code": CODE_JS_RUNTIME_MISSING,
                "message": "JavaScript runtime missing.",
                "hint": "Install Deno >= 2.3 with: curl -fsSL https://deno.land/install.sh | sh (or Node.js >= 22).",
            }
        if not ejs_ok:
            return {
                "ok": False,
                "error_code": CODE_EJS_MISSING,
                "message": "yt-dlp JavaScript challenge solver package is missing.",
                "hint": 'Run: uv add "yt-dlp[default]" in your terminal to install yt-dlp-ejs.',
            }

    cookies_browser, cookies_file = get_active_cookies_params()
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ffmpeg_location": ffmpeg_exe,
        "remote_components": ["ejs:npm", "ejs:github"],
    }
    js_cfg = get_js_runtime_config()
    if js_cfg:
        ydl_opts["js_runtimes"] = js_cfg
    if cookies_browser:
        ydl_opts["cookiesfrombrowser"] = _parse_browser_cookies_spec(cookies_browser)
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_extract_info_worker, url, ydl_opts)
            info = future.result(timeout=15.0)
    except concurrent.futures.TimeoutError:
        return {
            "ok": False,
            "error_code": "DOWNLOAD_FAILED",
            "message": "Video preflight check timed out after 15 seconds.",
            "hint": "The video platform is responding slowly. Check the URL or upload the video file directly.",
        }
    except Exception as exc:
        code, msg, hint = classify_url_error(exc)
        return {
            "ok": False,
            "error_code": code,
            "message": msg,
            "hint": hint,
        }

    # Inspect extracted metadata
    is_live = bool(info.get("is_live") or info.get("live_status") == "is_live")
    if is_live:
        return {
            "ok": False,
            "error_code": CODE_LIVE_STREAM_UNSUPPORTED,
            "message": "Ongoing live streams are not supported.",
            "hint": "Please wait until the live stream finishes and becomes a VOD.",
        }

    filesize = info.get("filesize") or info.get("filesize_approx") or 0
    if filesize > MAX_UPLOAD_GB * 1024 * 1024 * 1024:
        return {
            "ok": False,
            "error_code": CODE_TOO_LARGE,
            "message": f"Video exceeds maximum allowed size ({MAX_UPLOAD_GB} GB).",
            "hint": "Choose a shorter video or select a lower quality setting.",
        }

    # Pick thumbnail URL
    thumbnail = info.get("thumbnail")
    if not thumbnail and info.get("thumbnails"):
        thumbnail = info["thumbnails"][-1].get("url")

    return {
        "ok": True,
        "title": info.get("title", "Match Video"),
        "duration_s": info.get("duration"),
        "thumbnail": thumbnail,
        "is_live": False,
        "est_size_mb": round(filesize / (1024 * 1024), 1) if filesize > 0 else None,
    }
