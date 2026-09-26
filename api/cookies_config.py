"""
Secure cookies configuration and storage manager.
Stores cookies.txt with chmod 0600 under data/cookies.txt.
Never logs or returns cookie contents over the API.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from api.storage import DATA_DIR

logger = logging.getLogger(__name__)

COOKIES_CONFIG_PATH = DATA_DIR / "cookies_config.json"
COOKIES_FILE_PATH = DATA_DIR / "cookies.txt"

SUPPORTED_BROWSERS = ["chrome", "safari", "firefox", "edge", "brave"]


def get_cookies_config() -> dict[str, Any]:
    """
    Get the current cookies configuration state.
    Returns:
        dict with keys: type ("none" | "browser" | "file"), browser (str | None), has_file (bool)
    """
    config = {"type": "none", "browser": None, "has_file": False}

    if COOKIES_CONFIG_PATH.exists():
        try:
            with open(COOKIES_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    config.update(saved)
        except Exception as e:
            logger.debug("Failed reading cookies config: %s", e)

    config["has_file"] = COOKIES_FILE_PATH.exists() and COOKIES_FILE_PATH.stat().st_size > 0
    config["source"] = config.get("type", "none")
    config["file_configured"] = config["has_file"]
    return config


def set_browser_cookies(browser: str) -> dict[str, Any]:
    """Set the active cookie source to a browser name."""
    clean = browser.strip().lower()
    if clean not in SUPPORTED_BROWSERS:
        raise ValueError(f"Unsupported browser '{browser}'. Supported: {', '.join(SUPPORTED_BROWSERS)}")

    data = {"type": "browser", "browser": clean}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(COOKIES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return get_cookies_config()


def save_cookies_file(content: bytes) -> dict[str, Any]:
    """Save raw cookies.txt content under data/cookies.txt with chmod 600."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE_PATH.write_bytes(content)
    try:
        os.chmod(COOKIES_FILE_PATH, 0o600)
    except OSError as e:
        logger.warning("Could not set 0600 permissions on cookies.txt: %s", e)

    data = {"type": "file", "browser": None}
    with open(COOKIES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return get_cookies_config()


def clear_cookies() -> dict[str, Any]:
    """Clear cookies configuration and remove cookies.txt."""
    if COOKIES_FILE_PATH.exists():
        try:
            COOKIES_FILE_PATH.unlink()
        except OSError:
            pass

    if COOKIES_CONFIG_PATH.exists():
        try:
            COOKIES_CONFIG_PATH.unlink()
        except OSError:
            pass

    return {"type": "none", "browser": None, "has_file": False}


def get_active_cookies_params() -> tuple[str | None, str | None]:
    """
    Return (cookies_from_browser, cookies_file_path) for yt-dlp.
    Respects environment variables YTDLP_COOKIES_BROWSER and YTDLP_COOKIES_FILE first,
    then active cookies_config.
    """
    env_browser = os.environ.get("YTDLP_COOKIES_BROWSER")
    env_file = os.environ.get("YTDLP_COOKIES_FILE")
    if env_browser or env_file:
        return env_browser, env_file

    cfg = get_cookies_config()
    ctype = cfg.get("type")
    if ctype == "browser" and cfg.get("browser"):
        return cfg["browser"], None
    elif ctype == "file" and cfg.get("has_file"):
        return None, str(COOKIES_FILE_PATH)

    return None, None
