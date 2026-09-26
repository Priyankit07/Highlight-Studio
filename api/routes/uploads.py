"""
Chunked, resumable file upload routes.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.models import UploadInitRequest, UploadInitResponse, UploadStatusResponse
from api.storage import (
    init_upload,
    get_upload_meta,
    get_received_chunks,
    save_chunk,
    assemble_upload,
    get_upload_dir,
)
from media_tools import probe_media

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("", response_model=UploadInitResponse)
def initialize_upload(payload: UploadInitRequest):
    upload_id = str(uuid.uuid4())
    try:
        res = init_upload(upload_id=upload_id, filename=payload.filename, total_size=payload.size)
        return res
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_UPLOAD", "message": str(e)},
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail={"code": "DISK_FULL", "message": str(e)},
        )


@router.put("/{upload_id}/chunks/{chunk_index}")
async def upload_chunk(upload_id: str, chunk_index: int, request: Request):
    meta = get_upload_meta(upload_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload session '{upload_id}' does not exist"},
        )

    # Read body stream
    chunk_data = await request.body()
    if not chunk_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_CHUNK", "message": "Chunk data cannot be empty"},
        )

    try:
        save_chunk(upload_id, chunk_index, chunk_data)
        return {"status": "ok", "chunk_index": chunk_index}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CHUNK_SAVE_FAILED", "message": str(e)},
        )


@router.get("/{upload_id}", response_model=UploadStatusResponse)
def get_upload_status(upload_id: str):
    meta = get_upload_meta(upload_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload session '{upload_id}' does not exist"},
        )

    received = get_received_chunks(upload_id)
    return {
        "upload_id": upload_id,
        "received": received,
    }


@router.post("/{upload_id}/complete")
def complete_upload(upload_id: str):
    meta = get_upload_meta(upload_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload session '{upload_id}' does not exist"},
        )

    orig_filename = meta["filename"]
    ext = Path(orig_filename).suffix.lower()
    up_dir = get_upload_dir(upload_id)
    assembled_path = up_dir / f"assembled{ext}"

    try:
        assemble_upload(upload_id, assembled_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ASSEMBLY_FAILED", "message": str(e)},
        )

    # Probe media and validate audio & video streams
    try:
        media_info = probe_media(assembled_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PROBE_FAILED", "message": f"Failed to probe media: {e}"},
        )

    if not media_info.get("has_audio"):
        # Explicit user-friendly NO_AUDIO_TRACK rejection
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_AUDIO_TRACK",
                "message": "The uploaded video has no audio track. Excitement detection requires match commentary or crowd audio.",
            },
        )

    if not media_info.get("has_video"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_VIDEO_TRACK",
                "message": "The uploaded file does not contain a valid video track.",
            },
        )

    return {
        "upload_id": upload_id,
        "filename": orig_filename,
        "duration_s": media_info.get("duration_s", 0.0),
        "media": media_info,
        "ready": True,
    }
