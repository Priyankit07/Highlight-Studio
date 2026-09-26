"""
Safe media streaming and download route with HTTP Range support for video seeking.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from api import db
from api.storage import resolve_media_path

router = APIRouter(prefix="/jobs", tags=["Media"])


def send_range_file(file_path: Path, range_header: str, content_type: str, filename: str | None = None) -> Response:
    file_size = file_path.stat().st_size
    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        # Invalid range syntax, return full file
        return FileResponse(file_path, media_type=content_type)

    start = int(range_match.group(1))
    end_str = range_match.group(2)
    end = int(end_str) if end_str else file_size - 1

    if start >= file_size or end >= file_size or start > end:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_length = end - start + 1

    def stream_chunk():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_length
            while remaining > 0:
                chunk_read = min(remaining, 64 * 1024)
                data = f.read(chunk_read)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_length),
        "Content-Type": content_type,
    }
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return StreamingResponse(
        stream_chunk(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers,
    )


@router.get("/{job_id}/media/{name:path}")
def get_job_media(
    job_id: str,
    name: str,
    range: str | None = Header(default=None),
    download: bool = Query(default=False),
):
    """
    Serve whitelisted media assets for a job.
    Supports HTTP Range requests for scrubbable video playback.
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    try:
        file_path = resolve_media_path(job_id, name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PATH", "message": "Disallowed media file or path traversal detected"},
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": f"Media file '{name}' does not exist"},
        )

    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or "application/octet-stream"

    # Compute download filename if requested
    dl_filename = None
    if download:
        title_slug = re.sub(r"[^\w\-]", "_", job.get("title", "highlights")).strip("_")
        stem = Path(name).stem
        ext = file_path.suffix
        dl_filename = f"{title_slug}_{stem}{ext}"

    # Handle Range header for video seeking
    if range and (content_type.startswith("video/") or content_type.startswith("audio/")):
        return send_range_file(file_path, range, content_type, dl_filename)

    headers = {"Accept-Ranges": "bytes"}
    if dl_filename:
        headers["Content-Disposition"] = f'attachment; filename="{dl_filename}"'

    return FileResponse(file_path, media_type=content_type, headers=headers)
