"""
Health and diagnostics route.
Supports APP_ENV=local and APP_ENV=demo.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException, status
import imageio_ffmpeg

from api.storage import get_disk_stats, ALLOWED_EXTENSIONS, MAX_UPLOAD_GB, get_max_upload_gb, is_url_import_enabled
from api.runtime import check_js_runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


def _compute_diagnostics(mask_paths: bool = False) -> dict:
    app_env = os.environ.get("APP_ENV", "local")
    api_token = os.environ.get("API_TOKEN")

    # Check FFmpeg
    ffmpeg_ok = False
    ffmpeg_path = ""
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            ffmpeg_ok = True
            ffmpeg_path = "[bundled imageio-ffmpeg]" if mask_paths else exe
    except Exception:
        pass

    # Check yt-dlp version strictly from yt_dlp.version.__version__
    ytdlp_version = "Installed (version unknown)"
    ytdlp_ok = False
    try:
        import yt_dlp
        import yt_dlp.version
        ver = getattr(yt_dlp.version, "__version__", None)
        if ver:
            ytdlp_version = ver
            ytdlp_ok = True
        else:
            ytdlp_version = "Installed (version unknown)"
            ytdlp_ok = True
    except Exception:
        ytdlp_version = "Not installed"

    # Check JS runtime
    js_runtime = check_js_runtime()
    if mask_paths and "path" in js_runtime:
        js_runtime["path"] = Path(js_runtime["path"]).name if js_runtime["path"] else None

    from api.cookies_config import get_cookies_config
    cookies_cfg = get_cookies_config()
    disk = get_disk_stats()
    disk_ok = disk.get("free_gb", 0) >= 1.0

    url_import_ready = ytdlp_ok and js_runtime.get("available", False) and js_runtime.get("ejs_installed", False)

    # Worst status badge calculation:
    # HEALTHY: uploads and URL import both fine
    # UPLOADS OK, URL IMPORT LIMITED: only import pieces missing
    # ATTENTION NEEDED: ffmpeg or disk fails
    if not ffmpeg_ok or not disk_ok:
        overall_status = "ATTENTION NEEDED"
        badge_status = "degraded"
    elif not url_import_ready:
        overall_status = "UPLOADS OK, URL IMPORT LIMITED"
        badge_status = "degraded"
    else:
        overall_status = "HEALTHY"
        badge_status = "healthy"

    url_import_enabled = is_url_import_enabled()

    return {
        "ok": True,
        "status": badge_status,
        "overall_status": overall_status,
        "app_env": app_env,
        "auth_required": bool(api_token),
        "url_import_enabled": url_import_enabled,
        "ffmpeg": {
            "available": ffmpeg_ok,
            "path": ffmpeg_path,
        },
        "yt_dlp": {
            "version": ytdlp_version,
            "ejs_installed": js_runtime.get("ejs_installed", False),
        },
        "js_runtime": js_runtime,
        "cookies": cookies_cfg,
        "disk": disk,
        "limits": {
            "max_upload_gb": get_max_upload_gb(),
            "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        },
    }


@router.get("/health")
def health_check():
    app_env = os.environ.get("APP_ENV", "local")
    if app_env == "demo":
        # In demo mode, public /api/health returns only {ok: true, app_env: "demo", url_import_enabled, limits}
        return {
            "ok": True,
            "app_env": "demo",
            "url_import_enabled": is_url_import_enabled(),
            "limits": {
                "max_upload_gb": get_max_upload_gb(),
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            },
        }

    return _compute_diagnostics(mask_paths=False)


@router.get("/health/details")
def health_details(authorization: str | None = Header(default=None)):
    app_env = os.environ.get("APP_ENV", "local")
    api_token = os.environ.get("API_TOKEN")

    if app_env == "demo" and api_token:
        if not authorization or not authorization.startswith("Bearer ") or authorization[7:].strip() != api_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Protected diagnostics require valid API_TOKEN"},
            )

    return _compute_diagnostics(mask_paths=(app_env == "demo"))
