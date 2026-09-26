"""
Streaming HTTP downloader for direct media URLs (.mp4, .mkv, .mov, .webm, .ts).
Features:
- SSRF validation on every redirect
- Range header resume support
- Size cap enforcement
- Real-time download progress tracking (speed, ETA, bytes)
- Atomic rename and .part cleanup
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import time
import urllib.parse
from pathlib import Path
from typing import Callable
import httpx

from api.storage import MAX_UPLOAD_GB

logger = logging.getLogger(__name__)

DIRECT_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".ts", ".avi", ".m4v"}
MAX_SIZE_BYTES = int(MAX_UPLOAD_GB * 1024 * 1024 * 1024)


def is_direct_video_url(url_str: str) -> bool:
    """Return True if URL path points directly to a video container extension."""
    try:
        parsed = urllib.parse.urlparse(url_str)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in DIRECT_EXTENSIONS)
    except Exception:
        return False


def validate_url_host(url_str: str) -> None:
    """Validate that the URL is not pointing to localhost or private/internal networks."""
    parsed = urllib.parse.urlparse(url_str)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing host")

    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise ValueError("Cannot import from local addresses")

    direct_ip = None
    try:
        direct_ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass

    if direct_ip is not None:
        if direct_ip.is_private or direct_ip.is_loopback or direct_ip.is_reserved or direct_ip.is_link_local:
            raise ValueError("Cannot import from private or loopback IP ranges")
    else:
        try:
            resolved_ip = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved_ip)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                raise ValueError("Domain resolves to a private or loopback IP range")
        except socket.gaierror:
            pass


def download_direct_file(
    url: str,
    output_path: Path,
    progress_cb: Callable[[dict], None] | None = None,
    max_size_bytes: int = MAX_SIZE_BYTES,
    chunk_size: int = 256 * 1024,
) -> Path:
    """
    Stream download a direct media file with resume support and progress reporting.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = output_path.with_suffix(output_path.suffix + ".part")

    current_url = url
    redirect_count = 0
    max_redirects = 5

    # Check for existing partial file
    existing_bytes = part_path.stat().st_size if part_path.exists() else 0

    client = httpx.Client(timeout=30.0, follow_redirects=False)

    try:
        while redirect_count < max_redirects:
            validate_url_host(current_url)

            headers = {"User-Agent": "HighlightStudio/1.0"}
            if existing_bytes > 0:
                headers["Range"] = f"bytes={existing_bytes}-"

            req = client.build_request("GET", current_url, headers=headers)
            resp = client.send(req, stream=True)

            # Handle redirects manually to re-validate host
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise ValueError("Redirect received without Location header")
                current_url = urllib.parse.urljoin(current_url, location)
                redirect_count += 1
                resp.close()
                continue

            break
        else:
            raise ValueError("Too many redirects")

        if resp.status_code not in (200, 206):
            resp.close()
            raise ValueError(f"HTTP download failed with status {resp.status_code}")

        # Determine total size
        is_range = resp.status_code == 206
        content_length = int(resp.headers.get("content-length", 0))

        if is_range:
            total_bytes = existing_bytes + content_length
            file_mode = "ab"
            downloaded = existing_bytes
        else:
            total_bytes = content_length
            file_mode = "wb"
            downloaded = 0
            existing_bytes = 0

        if total_bytes > max_size_bytes:
            resp.close()
            if part_path.exists():
                part_path.unlink(missing_ok=True)
            raise ValueError(f"File size ({round(total_bytes / (1024**3), 2)} GB) exceeds maximum allowed {round(max_size_bytes / (1024**3), 1)} GB (too large)")

        start_time = time.time()
        last_progress_time = start_time
        bytes_since_last = 0

        with open(part_path, file_mode) as f:
            for chunk in resp.iter_bytes(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                bytes_since_last += len(chunk)

                if downloaded > max_size_bytes:
                    resp.close()
                    raise ValueError(f"Download exceeded maximum size cap ({round(max_size_bytes / (1024**3), 1)} GB) (too large)")

                now = time.time()
                if progress_cb and (now - last_progress_time >= 0.25 or (total_bytes > 0 and downloaded >= total_bytes)):
                    elapsed = now - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    eta = int((total_bytes - downloaded) / speed) if (speed > 0 and total_bytes > 0) else None
                    progress_cb({
                        "status": "downloading",
                        "downloaded_bytes": downloaded,
                        "total_bytes": total_bytes,
                        "speed": speed,
                        "eta": eta,
                    })
                    last_progress_time = now

        resp.close()
        # Atomic rename
        part_path.replace(output_path)
        logger.info("Direct download completed: %s (%d bytes)", output_path.name, downloaded)
        return output_path

    except Exception:
        # Clean up partial on error
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass
        raise
    finally:
        client.close()
