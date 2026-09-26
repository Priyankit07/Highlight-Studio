"""
Error taxonomy and mapping for video imports.
Converts backend, network, and yt-dlp exceptions into user-friendly error codes, messages, and hints.
Never exposes raw tracebacks to clients.
"""
from __future__ import annotations

import re

# Standard error taxonomy codes
CODE_SOURCE_BLOCKED = "SOURCE_BLOCKED"
CODE_JS_RUNTIME_MISSING = "JS_RUNTIME_MISSING"
CODE_EJS_MISSING = "EJS_MISSING"
CODE_UNSUPPORTED_URL = "UNSUPPORTED_URL"
CODE_PRIVATE_VIDEO = "PRIVATE_VIDEO"
CODE_GEO_BLOCKED = "GEO_BLOCKED"
CODE_LIVE_STREAM_UNSUPPORTED = "LIVE_STREAM_UNSUPPORTED"
CODE_TOO_LARGE = "TOO_LARGE"
CODE_DOWNLOAD_FAILED = "DOWNLOAD_FAILED"


def sanitize_error_text(err_str: str) -> str:
    """Extract a clean, concise single-line message stripped of traceback lines and prefixes."""
    lines = [line.strip() for line in err_str.splitlines() if line.strip()]
    clean = "Unknown download failure"
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            clean = line[len("ERROR:"):].strip()
            break
        elif "DownloadError:" in line:
            clean = line.split("DownloadError:", 1)[-1].strip()
            break
        elif "ExtractorError:" in line:
            clean = line.split("ExtractorError:", 1)[-1].strip()
            break
    else:
        if lines:
            clean = lines[-1]

    # Clean leading exception class names like "RuntimeError: "
    if ": " in clean:
        prefix, rest = clean.split(": ", 1)
        if any(w in prefix for w in ("Error", "Exception", "Fault")):
            clean = rest.strip()

    return clean


def classify_url_error(exc: Exception | str) -> tuple[str, str, str]:
    """
    Map an exception or error string to a structured (code, message, hint) tuple.

    Returns:
        tuple[code, message, hint]
    """
    err_str = str(exc).strip()
    lower = err_str.lower()

    # 1. Bot check / verification challenge
    bot_indicators = [
        "sign in to confirm you're not a bot",
        "sign in to confirm",
        "confirm you're not a bot",
        "bot check",
        "automated queries",
        "robot",
        "captcha",
    ]
    if any(b in lower for b in bot_indicators):
        return (
            CODE_SOURCE_BLOCKED,
            "YouTube blocked this download. Sign in or bot verification required.",
            "Configure browser cookies in Settings, or upload the video file instead.",
        )

    # 2. JavaScript runtime missing
    js_runtime_indicators = [
        "no supported javascript runtime",
        "javascript runtime could be found",
        "javascript runtime",
        "js runtime",
        "install a js runtime",
        "deno is required",
    ]
    if any(j in lower for j in js_runtime_indicators):
        return (
            CODE_JS_RUNTIME_MISSING,
            "JavaScript runtime missing.",
            "Install Deno >= 2.3 with: curl -fsSL https://deno.land/install.sh | sh (or Node.js >= 22).",
        )

    # 3. EJS solver missing
    if "yt-dlp-ejs" in lower or "ejs:npm" in lower or "ejs missing" in lower:
        return (
            CODE_EJS_MISSING,
            "yt-dlp JavaScript challenge solver package is missing.",
            'Run: uv add "yt-dlp[default]" in your terminal to install yt-dlp-ejs.',
        )

    # 4. Ongoing live stream
    live_indicators = [
        "is a live stream",
        "live stream is ongoing",
        "live stream recordings are not available",
        "live stream recording",
        "live event will begin",
        "premieres in",
        "ongoing live",
    ]
    if any(l in lower for l in live_indicators):
        return (
            CODE_LIVE_STREAM_UNSUPPORTED,
            "Ongoing live streams are not supported.",
            "Please wait until the live stream finishes and becomes a VOD.",
        )

    # 5. Private / Sign-in required video
    private_indicators = [
        "private video",
        "sign in if you've been granted access",
        "this video is private",
        "login required",
        "requires authentication",
        "members-only",
    ]
    if any(p in lower for p in private_indicators):
        return (
            CODE_PRIVATE_VIDEO,
            "This video is private or requires sign-in to view.",
            "Ensure the video is public, or configure browser cookies in Settings.",
        )

    # 6. Geo-blocked
    geo_indicators = [
        "not available in your country",
        "not available in your region",
        "geo restricted",
        "geographic region",
        "blocked in your country",
    ]
    if any(g in lower for g in geo_indicators):
        return (
            CODE_GEO_BLOCKED,
            "This video is not available in your region.",
            "Upload the video file directly or use an accessible video URL.",
        )

    # 7. Too large
    if "too large" in lower or "exceeds maximum" in lower or "file size limit" in lower or ("exceeds" in lower and "limit" in lower):
        return (
            CODE_TOO_LARGE,
            "Video exceeds file size limits.",
            "Choose a shorter video or select a lower quality setting.",
        )

    # 8. Unsupported URL / private address
    unsupported_indicators = [
        "unsupported url",
        "is not a valid url",
        "cannot import from private",
        "cannot import from local",
        "invalid url",
        "unknown url scheme",
    ]
    if any(u in lower for u in unsupported_indicators):
        return (
            CODE_UNSUPPORTED_URL,
            "Unsupported video URL or disallowed address.",
            "Please provide a valid public YouTube or direct video URL.",
        )

    # 9. Generic download failure
    clean_msg = sanitize_error_text(err_str)
    return (
        CODE_DOWNLOAD_FAILED,
        f"Failed to download video: {clean_msg}",
        "Check your internet connection, verify the link, or upload the video file directly.",
    )
