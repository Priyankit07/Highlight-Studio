"""
Storage layout, chunked upload assembly, disk space validation, and media path security.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".ts", ".webm", ".m4v"}
APP_ENV = os.environ.get("APP_ENV", "local")


def get_max_upload_gb() -> float:
    env_val = os.environ.get("MAX_UPLOAD_GB")
    if env_val is not None and env_val.strip() != "":
        try:
            return float(env_val.strip())
        except ValueError:
            pass
    app_env = os.environ.get("APP_ENV", "local")
    return 1.0 if app_env == "demo" else 10.0


def get_retention_days() -> int:
    env_val = os.environ.get("RETENTION_DAYS")
    if env_val is not None and env_val.strip() != "":
        try:
            return int(env_val.strip())
        except ValueError:
            pass
    app_env = os.environ.get("APP_ENV", "local")
    return 1 if app_env == "demo" else 14


def is_url_import_enabled() -> bool:
    env_val = os.environ.get("ENABLE_URL_IMPORT")
    if env_val is not None and env_val.strip() != "":
        return env_val.strip().lower() in ("1", "true", "yes")
    app_env = os.environ.get("APP_ENV", "local")
    return False if app_env == "demo" else True


MAX_UPLOAD_GB = get_max_upload_gb()
RETENTION_DAYS = get_retention_days()


def ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_disk_stats() -> dict[str, Any]:
    ensure_dirs()
    usage = shutil.disk_usage(DATA_DIR)
    return {
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "total_gb": round(usage.total / (1024 ** 3), 2),
    }


def check_disk_space_for_upload(file_size_bytes: int) -> bool:
    """Refuse upload if free disk space is under 2x the file size."""
    stats = get_disk_stats()
    return stats["free_bytes"] >= (2 * file_size_bytes)


def validate_safe_id(identifier: str) -> None:
    if not identifier or not re.match(r"^[a-zA-Z0-9_-]+$", identifier):
        raise ValueError(f"Invalid identifier '{identifier}': contains illegal or traversal characters")


def get_job_dir(job_id: str) -> Path:
    validate_safe_id(job_id)
    ensure_dirs()
    return JOBS_DIR / job_id


def get_upload_dir(upload_id: str) -> Path:
    validate_safe_id(upload_id)
    ensure_dirs()
    return UPLOADS_DIR / upload_id


# Chunked upload management

def init_upload(upload_id: str, filename: str, total_size: int) -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported video format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    limit_gb = get_max_upload_gb()
    if total_size > (limit_gb * 1024 * 1024 * 1024):
        raise ValueError(f"File size exceeds maximum upload limit of {limit_gb} GB")

    if not check_disk_space_for_upload(total_size):
        raise RuntimeError("Insufficient disk space on server (requires at least 2x file size free)")

    up_dir = get_upload_dir(upload_id)
    up_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = up_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "chunk_size": CHUNK_SIZE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(up_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


def get_upload_meta(upload_id: str) -> dict[str, Any] | None:
    up_dir = get_upload_dir(upload_id)
    meta_file = up_dir / "meta.json"
    if not meta_file.exists():
        return None
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_received_chunks(upload_id: str) -> list[int]:
    up_dir = get_upload_dir(upload_id)
    chunks_dir = up_dir / "chunks"
    if not chunks_dir.exists():
        return []
    received = []
    for f in chunks_dir.iterdir():
        if f.is_file() and f.name.isdigit():
            received.append(int(f.name))
    return sorted(received)


def save_chunk(upload_id: str, chunk_index: int, chunk_data: bytes) -> None:
    up_dir = get_upload_dir(upload_id)
    if not (up_dir / "meta.json").exists():
        raise FileNotFoundError(f"Upload session not found: {upload_id}")
    chunks_dir = up_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunks_dir / str(chunk_index)
    with open(chunk_path, "wb") as f:
        f.write(chunk_data)


def assemble_upload(upload_id: str, dest_path: Path) -> Path:
    meta = get_upload_meta(upload_id)
    if not meta:
        raise FileNotFoundError(f"Upload session not found: {upload_id}")

    up_dir = get_upload_dir(upload_id)
    chunks_dir = up_dir / "chunks"
    total_size = meta["total_size"]
    chunk_size = meta["chunk_size"]
    expected_chunks = (total_size + chunk_size - 1) // chunk_size

    received = get_received_chunks(upload_id)
    if len(received) < expected_chunks:
        missing = set(range(expected_chunks)) - set(received)
        raise ValueError(f"Upload incomplete: missing chunks {sorted(missing)}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as out_f:
        for i in range(expected_chunks):
            chunk_file = chunks_dir / str(i)
            if not chunk_file.exists():
                raise ValueError(f"Missing chunk {i}")
            with open(chunk_file, "rb") as in_f:
                shutil.copyfileobj(in_f, out_f)

    # Verify size
    if dest_path.stat().st_size != total_size:
        raise ValueError(f"Assembled file size mismatch: expected {total_size}, got {dest_path.stat().st_size}")

    # Clean up chunk files
    try:
        shutil.rmtree(chunks_dir)
    except Exception as e:
        logger.warning("Could not clean up chunks dir %s: %s", chunks_dir, e)

    return dest_path


# Whitelist media path validation

MEDIA_WHITELIST_REGEX = re.compile(
    r"^(proxy\.mp4|debug\.png|windows\.json|windows\.csv|thumbs/\d+\.jpg|renders/[a-zA-Z0-9_-]+/highlights\.mp4)$"
)


def resolve_media_path(job_id: str, relative_path: str) -> Path:
    """
    Validate that relative_path is strictly within whitelist and cannot escape data/jobs/<job_id>/.
    Raises ValueError on traversal attempt or disallowed file.
    """
    # Reject URL encoding tricks (%2e%2e) or backslashes
    if ".." in relative_path or "%2e" in relative_path.lower() or "\\" in relative_path:
        raise ValueError("Invalid path: traversal characters detected")

    clean_path = relative_path.strip().lstrip("/")
    if not MEDIA_WHITELIST_REGEX.match(clean_path):
        raise ValueError(f"Requested media file '{clean_path}' is not in allowed media whitelist")

    job_dir = get_job_dir(job_id).resolve()
    target = (job_dir / clean_path).resolve()

    # Strict containment check
    if not str(target).startswith(str(job_dir)):
        raise ValueError("Path traversal attempt detected")

    return target


def run_retention_cleanup() -> int:
    """
    Remove jobs and uploads older than RETENTION_DAYS (if RETENTION_DAYS > 0).
    Returns count of deleted directories.
    """
    if RETENTION_DAYS <= 0:
        return 0

    ensure_dirs()
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    deleted_count = 0

    for item in JOBS_DIR.iterdir():
        if item.is_dir():
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                try:
                    shutil.rmtree(item)
                    deleted_count += 1
                except Exception as e:
                    logger.warning("Failed to delete expired job dir %s: %s", item, e)

    for item in UPLOADS_DIR.iterdir():
        if item.is_dir():
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                try:
                    shutil.rmtree(item)
                    deleted_count += 1
                except Exception as e:
                    logger.warning("Failed to delete expired upload dir %s: %s", item, e)

    return deleted_count
