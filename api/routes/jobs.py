"""
Job management, SSE event streaming, analysis, retuning, and custom render routes.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import shutil
import socket
import urllib.parse
import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api import db, worker
from api.events import broker
from api.models import (
    ConfigModel,
    CreateJobRequest,
    CreateRenderRequest,
    RetuneRequest,
    LabelItem,
    UpdateWindowsRequest,
)
from api.storage import get_job_dir, get_upload_dir
from config import Config
from spike_detection import compute_envelope, detect_spikes, detect_subthreshold_suggestions
from spike_window import merge_spikes_into_windows, save_manifest
from analysis_export import export_analysis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _validate_remote_url(url_str: str) -> None:
    parsed = urllib.parse.urlparse(url_str)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing host")

    # Reject localhost and local names
    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
        raise ValueError("Cannot import from local addresses")

    # Check if direct IP address
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


def _calculate_reel_offsets(windows: list[dict[str, Any]], job_id: str) -> list[dict[str, Any]]:
    cum_offset = 0.0
    for idx, w in enumerate(windows):
        w["thumb_url"] = f"/api/jobs/{job_id}/media/thumbs/{idx}.jpg"
        if w.get("selected"):
            w["reel_offset"] = round(cum_offset, 2)
            dur = float(w.get("duration", max(0.0, w.get("end", 0.0) - w.get("start", 0.0))))
            cum_offset += dur
        else:
            w["reel_offset"] = None
    return windows


@router.post("", status_code=status.HTTP_201_CREATED)
def create_job(payload: CreateJobRequest):
    source = payload.source
    job_id = str(uuid.uuid4())
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    config_dict = payload.config or {}
    if config_dict:
        # Validate overrides against ConfigModel
        try:
            validated = ConfigModel(**config_dict)
            config_dict = validated.model_dump(exclude_unset=True)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_CONFIG", "message": str(e)},
            )

    source_type = source.type
    source_filename = ""
    default_title = "Highlight Reel"

    if source_type == "upload":
        upload_id = source.upload_id
        if not upload_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_UPLOAD_ID", "message": "upload_id is required for source type 'upload'"},
            )

        up_dir = get_upload_dir(upload_id)
        candidates = list(up_dir.glob("assembled.*"))
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "UPLOAD_NOT_ASSEMBLED", "message": "Upload has not been completed or assembled"},
            )

        assembled_video = candidates[0]
        ext = assembled_video.suffix
        dest_source = job_dir / f"source{ext}"
        shutil.move(str(assembled_video), str(dest_source))

        # Read meta
        meta_file = up_dir / "meta.json"
        if meta_file.exists():
            with open(meta_file, "r") as f:
                up_meta = json.load(f)
                source_filename = up_meta.get("filename", assembled_video.name)
                default_title = Path(source_filename).stem
        else:
            source_filename = assembled_video.name
            default_title = Path(source_filename).stem

    elif source_type == "url":
        from api.storage import is_url_import_enabled
        if not is_url_import_enabled():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "URL_IMPORT_DISABLED", "message": "URL video import is disabled on this server instance"},
            )
        url = source.url
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_URL", "message": "url is required for source type 'url'"},
            )
        try:
            _validate_remote_url(url)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_URL", "message": str(e)},
            )
        import urllib.parse
        domain = urllib.parse.urlparse(url).netloc.replace("www.", "") or "web"
        default_title = f"{domain} import"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SOURCE", "message": f"Unsupported source type: {source_type}"},
        )

    title = payload.title or default_title
    try:
        job_record = db.create_job(
            job_id=job_id,
            title=title,
            source_type=source_type,
            source_filename=source_filename,
            config=config_dict,
        )
    except Exception as e:
        logger.error("Failed to persist job record %s: %s", job_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "JOB_CREATION_FAILED", "message": f"Failed to persist job record: {str(e)}"},
        )

    if not job_record or not job_record.get("id"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "JOB_CREATION_FAILED", "message": "Failed to create and verify job record in database"},
        )

    # Ensure the transaction is finalized and the record is queryable
    verified_job = db.get_job(job_id)
    if not verified_job:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "JOB_PERSISTENCE_ERROR", "message": f"Job '{job_id}' committed but cannot be retrieved"},
        )

    # Trigger job worker if concurrency allows
    try:
        if worker.get_active_count() < worker.MAX_CONCURRENT_JOBS:
            worker.start_pipeline_job(job_id)
    except Exception as e:
        logger.error("Failed to start pipeline worker for job %s: %s", job_id, e, exc_info=True)

    return {
        "job_id": job_id,
        "title": title,
        "status": verified_job.get("status", "queued"),
        "queue_position": db.get_queue_position(job_id),
    }


@router.get("")
def list_jobs(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    raw_jobs = db.list_jobs(limit=limit, offset=offset)
    jobs = []
    for j in raw_jobs:
        job_id = j["id"]
        pos = db.get_queue_position(job_id)
        # Compute reel duration from active render
        active_rid = j.get("active_render_id") or "default"
        render_rec = db.get_render(active_rid)
        reel_len = render_rec.get("duration_s", 0.0) if render_rec else 0.0

        # Thumbnail URL if available
        thumb_url = f"/api/jobs/{job_id}/media/thumbs/0.jpg"
        thumb_path = get_job_dir(job_id) / "thumbs" / "0.jpg"
        if not thumb_path.exists():
            thumb_url = None

        jobs.append({
            "id": job_id,
            "title": j["title"],
            "status": j["status"],
            "created_at": j["created_at"],
            "updated_at": j["updated_at"],
            "duration_s": j.get("duration_s", 0.0),
            "moment_count": j.get("moment_count", 0),
            "reel_length": reel_len,
            "queue_position": pos,
            "thumbnail_url": thumb_url,
            "error": {"code": j.get("error_code"), "message": j.get("error_message")} if j.get("error_code") else None,
        })

    return {"jobs": jobs}


@router.get("/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    pos = db.get_queue_position(job_id)
    renders = db.list_renders_for_job(job_id)

    # Check if proxy video is ready
    proxy_ready = (get_job_dir(job_id) / "proxy.mp4").exists()

    return {
        "id": job["id"],
        "title": job["title"],
        "status": job["status"],
        "stage": job.get("stage"),
        "progress": job.get("progress", 0.0),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "duration_s": job.get("duration_s", 0.0),
        "moment_count": job.get("moment_count", 0),
        "config": job.get("config", {}),
        "active_render_id": job.get("active_render_id"),
        "queue_position": pos,
        "proxy_ready": proxy_ready,
        "renders": renders,
        "labels": job.get("labels", []),
        "error": {"code": job.get("error_code"), "message": job.get("error_message")} if job.get("error_code") else None,
    }


@router.patch("/{job_id}")
def update_job(job_id: str, payload: dict[str, Any]):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found"})
    if "title" in payload:
        db.update_job(job_id, title=str(payload["title"]).strip())
    return {"status": "ok"}


@router.get("/{job_id}/events")
async def stream_job_events(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    return StreamingResponse(
        broker.event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/cancel")
def cancel_job_endpoint(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    worker.cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id}


@router.post("/{job_id}/retry")
def retry_job_endpoint(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    if job["status"] in ("running", "detecting", "rendering", "extracting_audio"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOB_ALREADY_RUNNING", "message": "Job is currently active"},
        )

    db.update_job(
        job_id,
        status="queued",
        stage=None,
        progress=0.0,
        error_code=None,
        error_message=None,
    )
    if worker.get_active_count() < worker.MAX_CONCURRENT_JOBS:
        worker.start_pipeline_job(job_id)
    return {"status": "queued", "job_id": job_id}


@router.delete("/{job_id}")
def delete_job_endpoint(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    worker.cancel_job(job_id)
    db.delete_job(job_id)

    job_dir = get_job_dir(job_id)
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except Exception as e:
            logger.warning("Error deleting job dir %s: %s", job_dir, e)

    return {"status": "deleted", "job_id": job_id}


@router.get("/{job_id}/analysis")
def get_job_analysis(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    job_dir = get_job_dir(job_id)
    envelope_file = job_dir / "envelope.json"
    analysis_file = job_dir / "analysis.json"

    if not envelope_file.exists() or not analysis_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ANALYSIS_NOT_READY", "message": "Analysis is not ready yet"},
        )

    with open(envelope_file, "r", encoding="utf-8") as f:
        envelope = json.load(f)

    with open(analysis_file, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    windows = analysis.get("windows", [])
    windows_with_meta = _calculate_reel_offsets(windows, job_id)
    suggestions = analysis.get("suggestions", [])
    if not suggestions:
        audio_wav = job_dir / "audio.wav"
        if audio_wav.exists() and envelope and "t" in envelope and len(envelope["t"]) > 0:
            try:
                import numpy as np
                times_arr = np.array(envelope["t"], dtype=np.float32)
                db_arr = np.array(envelope["db"], dtype=np.float32)
                base_arr = np.array(envelope["baseline"], dtype=np.float32)
                rise_arr = np.array(envelope["rise"], dtype=np.float32)
                total_dur = float(analysis.get("duration_s", 0.0))
                cfg = Config()
                cfg_dict = analysis.get("config", {})
                for k, v in cfg_dict.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                suggestions = detect_subthreshold_suggestions(
                    audio_wav,
                    config=cfg,
                    envelope=(times_arr, db_arr, base_arr, rise_arr, total_dur),
                    primary_windows=windows,
                )
            except Exception as e:
                logger.debug("Failed computing on-the-fly suggestions: %s", e)

    return {
        "duration_s": analysis.get("duration_s", 0.0),
        "envelope": envelope,
        "spikes": analysis.get("spikes", []),
        "windows": windows_with_meta,
        "suggestions": suggestions,
        "config": analysis.get("config", {}),
    }


@router.post("/{job_id}/retune")
def retune_job(job_id: str, payload: RetuneRequest):
    """
    Fast parameter retuning without re-extracting audio or cutting video.
    Re-runs excitement detection and window selection in place (< 3s target).
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    job_dir = get_job_dir(job_id)
    audio_wav = job_dir / "audio.wav"
    if not audio_wav.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUDIO_NOT_FOUND", "message": "Audio WAV file not found for retune"},
        )

    # Validate config
    current_cfg_dict = job.get("config", {})
    current_cfg_dict.update(payload.config)
    try:
        validated = ConfigModel(**current_cfg_dict)
        effective_cfg = validated.model_dump()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CONFIG", "message": str(e)},
        )

    cfg = Config()
    for k, v in effective_cfg.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    # Re-compute envelope and detection
    times, smoothed_db, baseline_db, rise_db, audio_duration = compute_envelope(audio_wav, config=cfg)
    spikes = detect_spikes(audio_wav, config=cfg, envelope=(times, smoothed_db, baseline_db, rise_db, audio_duration))
    windows = merge_spikes_into_windows(spikes, audio_duration=audio_duration, config=cfg)

    # Update manifest on disk
    save_manifest(windows, job_dir / "windows.json")

    # Sub-threshold candidate suggestions (min_rise_db - 1.5, min_sustain_s - 1.0)
    suggestions = detect_subthreshold_suggestions(
        audio_path=audio_wav,
        config=cfg,
        envelope=(times, smoothed_db, baseline_db, rise_db, audio_duration),
        primary_windows=windows,
    )

    # Export updated analysis JSONs
    export_analysis(
        output_dir=job_dir,
        times=times,
        smoothed_db=smoothed_db,
        baseline_db=baseline_db,
        rise_db=rise_db,
        total_duration_s=audio_duration,
        spikes=spikes,
        windows=windows,
        config=cfg,
        suggestions=suggestions,
    )

    moment_count = sum(1 for w in windows if w.selected)
    db.update_job(job_id, moment_count=moment_count, config=effective_cfg)

    # Read back envelope and analysis for response
    with open(job_dir / "envelope.json", "r", encoding="utf-8") as f:
        envelope_data = json.load(f)

    windows_dicts = [w.to_dict() for w in windows]
    windows_with_meta = _calculate_reel_offsets(windows_dicts, job_id)

    broker.publish_nowait(job_id, "analysis_ready", {
        "duration_s": round(audio_duration, 2),
        "moment_count": moment_count,
        "total_moments": len(windows),
    })

    return {
        "duration_s": round(audio_duration, 2),
        "envelope": envelope_data,
        "spikes": [
            {
                "onset": s.onset,
                "offset": s.offset,
                "peak_time": s.peak_time,
                "peak_rise_db": s.peak_rise_db,
                "score": s.score,
                "duration": s.duration,
            }
            for s in spikes
        ],
        "windows": windows_with_meta,
        "suggestions": suggestions,
        "config": effective_cfg,
    }


@router.put("/{job_id}/windows")
def update_job_windows(job_id: str, payload: UpdateWindowsRequest):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )
    job_dir = get_job_dir(job_id)
    analysis_file = job_dir / "analysis.json"
    windows_file = job_dir / "windows.json"

    windows_data = [w.model_dump() for w in payload.windows]
    windows_data.sort(key=lambda w: w["start"])

    # Update windows.json
    with open(windows_file, "w", encoding="utf-8") as f:
        json.dump(windows_data, f, indent=2)

    # Update analysis.json
    if analysis_file.exists():
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        analysis_data["windows"] = windows_data
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis_data, f, indent=2)

    moment_count = sum(1 for w in windows_data if w.get("selected"))
    db.update_job(job_id, moment_count=moment_count)

    windows_with_meta = _calculate_reel_offsets(windows_data, job_id)
    return {"windows": windows_with_meta, "moment_count": moment_count}


def _evaluate_labels_for_job(job_id: str, labels: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    job_dir = get_job_dir(job_id)
    windows_file = job_dir / "windows.json"
    windows: list[dict[str, Any]] = []
    if windows_file.exists():
        try:
            with open(windows_file, "r", encoding="utf-8") as f:
                windows = json.load(f)
        except Exception:
            pass

    selected_windows = [w for w in windows if w.get("selected", True)]
    tolerance_s = 3.0

    evaluated: list[dict[str, Any]] = []
    for lbl in labels:
        t = float(lbl.get("time", 0.0))
        is_caught = any(
            (w.get("start", 0.0) - tolerance_s) <= t <= (w.get("end", 0.0) + tolerance_s)
            for w in selected_windows
        )
        evaluated.append({**lbl, "caught": is_caught})

    total = len(labels)
    caught_count = sum(1 for l in evaluated if l.get("caught"))
    missed_count = total - caught_count
    recall = round(caught_count / total, 3) if total > 0 else 0.0

    summary = {
        "total": total,
        "caught": caught_count,
        "missed": missed_count,
        "recall": recall,
    }
    return evaluated, summary


@router.get("/{job_id}/labels")
def get_job_labels_endpoint(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )
    labels = db.get_job_labels(job_id)
    evaluated, summary = _evaluate_labels_for_job(job_id, labels)
    return {"labels": evaluated, "summary": summary}


@router.post("/{job_id}/labels")
def add_or_update_label(job_id: str, payload: LabelItem):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )
    labels = db.get_job_labels(job_id)
    label_id = payload.id or str(uuid.uuid4())[:8]
    new_label = {"id": label_id, "time": round(payload.time, 2), "label": payload.label.strip()}
    updated = [l for l in labels if l.get("id") != label_id]
    updated.append(new_label)
    updated.sort(key=lambda l: l["time"])
    db.update_job_labels(job_id, updated)

    job_dir = get_job_dir(job_id)
    with open(job_dir / "labels.json", "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)

    evaluated, summary = _evaluate_labels_for_job(job_id, updated)
    return {"labels": evaluated, "summary": summary, "added": new_label}


@router.delete("/{job_id}/labels/{label_id}")
def delete_job_label(job_id: str, label_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )
    labels = db.get_job_labels(job_id)
    updated = [l for l in labels if l.get("id") != label_id]
    db.update_job_labels(job_id, updated)

    job_dir = get_job_dir(job_id)
    with open(job_dir / "labels.json", "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)

    evaluated, summary = _evaluate_labels_for_job(job_id, updated)
    return {"labels": evaluated, "summary": summary, "deleted": label_id}


@router.post("/{job_id}/find-settings")
def find_better_settings(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )
    labels = db.get_job_labels(job_id)
    if not labels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_LABELS", "message": "No event labels entered for this match. Add at least one label first."},
        )
    job_dir = get_job_dir(job_id)
    audio_wav = job_dir / "audio.wav"
    if not audio_wav.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AUDIO_NOT_FOUND", "message": "Audio WAV file not found for setting sweep."},
        )
    from evaluate import run_parameter_sweep
    results = run_parameter_sweep(audio_wav, labels)
    return {"results": results[:10]}


@router.post("/{job_id}/renders", status_code=status.HTTP_202_ACCEPTED)
def create_render_endpoint(job_id: str, payload: CreateRenderRequest):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    # Reject if already actively rendering
    if worker.is_job_running(job_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOB_BUSY", "message": "Job is currently rendering or processing. Please wait or cancel first."},
        )

    render_id = str(uuid.uuid4())
    render_spec = {
        "windows": [w.model_dump() for w in payload.windows],
        "fade_duration_s": payload.fade_duration_s,
        "crf": payload.crf,
        "preset": payload.preset,
    }

    worker.start_custom_render_job(job_id, render_id, render_spec)
    return {
        "render_id": render_id,
        "status": "rendering",
        "clip_count": len(payload.windows),
    }


@router.get("/{job_id}/renders/{rid}")
def get_render_endpoint(job_id: str, rid: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found"},
        )

    render = db.get_render(rid)
    if not render or render.get("job_id") != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RENDER_NOT_FOUND", "message": f"Render '{rid}' not found"},
        )

    return render
