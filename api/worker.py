"""
Worker manager: job scheduling, process isolation, background proxy/thumbnails, and cancelation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from api import db
from api.events import broker
from api.storage import get_job_dir
from api.runtime import ensure_js_runtime_on_path
from media_tools import extract_thumbnail, make_proxy

logger = logging.getLogger(__name__)

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", 1))

_running_processes: dict[str, subprocess.Popen] = {}
_running_lock = threading.Lock()


def get_active_count() -> int:
    with _running_lock:
        return len(_running_processes)


def is_job_running(job_id: str) -> bool:
    with _running_lock:
        proc = _running_processes.get(job_id)
        if not proc:
            return False
        if proc.poll() is not None:
            _running_processes.pop(job_id, None)
            return False
        job = db.get_job(job_id)
        if job and job["status"] in ("completed", "failed", "cancelled", "interrupted"):
            return False
        return True


def _generate_background_assets(job_id: str, job_dir: Path) -> None:
    """Generate proxy.mp4 and thumbs/NN.jpg in the background without blocking reel encoding."""
    try:
        candidates = list(job_dir.glob("source.*"))
        if not candidates:
            return
        source_video = candidates[0]

        # 1. Generate thumbnails at peak times
        analysis_json = job_dir / "analysis.json"
        if analysis_json.exists():
            with open(analysis_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            windows = data.get("windows", [])
            thumbs_dir = job_dir / "thumbs"
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            for idx, w in enumerate(windows):
                peak_t = float(w.get("peak_time", w.get("start", 0.0)))
                thumb_out = thumbs_dir / f"{idx}.jpg"
                try:
                    if not thumb_out.exists():
                        extract_thumbnail(source_video, peak_t, thumb_out, width=480)
                except Exception as e:
                    logger.debug("Failed thumb %d for job %s: %s", idx, job_id, e)

        # 2. Generate proxy MP4
        proxy_out = job_dir / "proxy.mp4"
        if not proxy_out.exists():
            try:
                make_proxy(source_video, proxy_out)
                logger.info("Proxy generated for job %s: %s", job_id, proxy_out.name)
            except Exception as e:
                logger.warning("Failed proxy generation for job %s: %s", job_id, e)

    except Exception as exc:
        logger.warning("Background asset generator encountered error for job %s: %s", job_id, exc)


def _monitor_child_process(job_id: str, proc: subprocess.Popen, job_dir: Path) -> None:
    log_file_path = job_dir / "job.log"
    job_dir.mkdir(parents=True, exist_ok=True)

    with open(log_file_path, "a", encoding="utf-8") as log_f:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line and proc.poll() is not None:
                break
            if not line:
                continue

            stripped = line.strip()
            # Try parse IPC JSON
            parsed = None
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed = json.loads(stripped)
                except Exception:
                    parsed = None

            if parsed and isinstance(parsed, dict) and "type" in parsed:
                mtype = parsed["type"]
                if mtype == "log":
                    msg = parsed.get("message", "")
                    log_f.write(msg + "\n")
                    log_f.flush()
                    broker.publish_nowait(job_id, "log", {"message": msg})

                elif mtype == "stage":
                    stage = parsed.get("stage", "")
                    fraction = parsed.get("fraction")
                    msg = parsed.get("message", "")
                    log_f.write(f"[{stage.upper()}] {msg} ({fraction})\n")
                    log_f.flush()
                    db.update_job(job_id, stage=stage, progress=fraction or 0.0)
                    broker.publish_nowait(job_id, "stage", {"stage": stage, "progress": fraction, "message": msg})

                elif mtype == "analysis_ready":
                    dur_s = parsed.get("duration_s", 0.0)
                    m_count = parsed.get("moment_count", 0)
                    db.update_job(job_id, status="analysis_ready", stage="analysis_ready", duration_s=dur_s, moment_count=m_count)
                    broker.publish_nowait(job_id, "analysis_ready", {
                        "duration_s": dur_s,
                        "moment_count": m_count,
                        "total_moments": parsed.get("total_moments", m_count),
                    })
                    # Spawn background asset generator thread
                    t = threading.Thread(target=_generate_background_assets, args=(job_id, job_dir), daemon=True)
                    t.start()

                elif mtype == "render_done":
                    rid = parsed.get("render_id", "default")
                    dur_s = parsed.get("duration_s", 0.0)
                    clip_c = parsed.get("clip_count", 0)
                    db.update_render(rid, status="completed", duration_s=dur_s)
                    db.update_job(job_id, active_render_id=rid)
                    broker.publish_nowait(job_id, "render_done", {
                        "render_id": rid,
                        "duration_s": dur_s,
                        "clip_count": clip_c,
                    })

                elif mtype == "completed":
                    db.update_job(job_id, status="completed", stage="completed", progress=1.0)
                    broker.publish_nowait(job_id, "completed", {})

                elif mtype == "error":
                    code = parsed.get("code", "PROCESS_FAILED")
                    msg = parsed.get("message", "An error occurred during processing")
                    db.update_job(job_id, status="failed", error_code=code, error_message=msg)
                    broker.publish_nowait(job_id, "error", {"code": code, "message": msg})
            else:
                # Raw stdout fallback
                log_f.write(stripped + "\n")
                log_f.flush()
                broker.publish_nowait(job_id, "log", {"message": stripped})

    proc.wait()
    retcode = proc.returncode

    with _running_lock:
        _running_processes.pop(job_id, None)

    # If exited with non-zero and not already cancelled or failed
    cur_job = db.get_job(job_id)
    if cur_job and cur_job["status"] not in ("completed", "cancelled", "failed", "interrupted"):
        if retcode != 0:
            db.update_job(job_id, status="failed", error_code="PROCESS_ERROR", error_message=f"Process exited with code {retcode}")
            broker.publish_nowait(job_id, "error", {"code": "PROCESS_ERROR", "message": f"Process exited with code {retcode}"})


def start_pipeline_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        return

    job_dir = get_job_dir(job_id)
    db.update_job(job_id, status="importing", stage="importing", progress=0.0)

    source_info = {"type": job["source_type"]}
    if job["source_type"] == "url":
        source_info["url"] = job["source_filename"]

    config_dict = job.get("config", {})

    cmd = [
        sys.executable,
        "-m", "api.runner",
        "--job-id", job_id,
        "--job-dir", str(job_dir),
        "--action", "initial_pipeline",
        "--source-json", json.dumps(source_info),
        "--config-json", json.dumps(config_dict),
    ]

    # start_new_session=True creates a new process group for clean killpg
    ensure_js_runtime_on_path()
    child_env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env=child_env,
    )

    with _running_lock:
        _running_processes[job_id] = proc

    # Register initial default render record
    db.create_render("default", job_id, [])

    t = threading.Thread(target=_monitor_child_process, args=(job_id, proc, job_dir), daemon=True)
    t.start()


def start_custom_render_job(job_id: str, render_id: str, render_spec: dict[str, Any]) -> None:
    job_dir = get_job_dir(job_id)
    db.update_job(job_id, status="rendering", stage="rendering", progress=0.0, active_render_id=render_id)
    db.create_render(render_id, job_id, render_spec.get("windows", []))

    cmd = [
        sys.executable,
        "-m", "api.runner",
        "--job-id", job_id,
        "--job-dir", str(job_dir),
        "--action", "custom_render",
        "--render-id", render_id,
        "--render-json", json.dumps(render_spec),
    ]

    ensure_js_runtime_on_path()
    child_env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env=child_env,
    )

    with _running_lock:
        _running_processes[job_id] = proc

    t = threading.Thread(target=_monitor_child_process, args=(job_id, proc, job_dir), daemon=True)
    t.start()


def cancel_job(job_id: str) -> bool:
    """
    Cancel running job by killing its entire process group.
    Ensures zero orphan FFmpeg processes.
    """
    with _running_lock:
        proc = _running_processes.get(job_id)

    if proc and proc.poll() is None:
        try:
            pgid = os.getpgid(proc.pid)
            logger.info("Killing process group %d for job %s", pgid, job_id)
            os.killpg(pgid, signal.SIGTERM)

            # Wait briefly for graceful shutdown
            for _ in range(25):  # up to 2.5s
                time.sleep(0.1)
                if proc.poll() is not None:
                    break
            else:
                # Force kill if still alive
                logger.warning("Force-killing process group %d for job %s", pgid, job_id)
                os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.warning("Error while killing process group for job %s: %s", job_id, e)

    with _running_lock:
        _running_processes.pop(job_id, None)

    # Clean up any leftover *.part and *.ytdl files
    try:
        job_dir = get_job_dir(job_id)
        if job_dir.exists():
            for p in list(job_dir.glob("*.part")) + list(job_dir.glob("*.ytdl")) + list(job_dir.glob("*.part-*")):
                try:
                    if p.is_file():
                        p.unlink()
                        logger.info("Cleaned up download part file on cancel: %s", p.name)
                except Exception as e:
                    logger.debug("Failed removing part file %s: %s", p, e)
    except Exception as e:
        logger.warning("Error cleaning up part files for job %s: %s", job_id, e)

    db.update_job(job_id, status="cancelled", stage="cancelled", error_code="JOB_CANCELLED", error_message="Job was cancelled by user")
    broker.publish_nowait(job_id, "stage", {"stage": "cancelled", "message": "Job cancelled"})
    broker.publish_nowait(job_id, "cancelled", {})
    return True


async def queue_manager_loop() -> None:
    """Background polling loop that picks up queued jobs if concurrency limit allows."""
    while True:
        try:
            active = get_active_count()
            if active < MAX_CONCURRENT_JOBS:
                jobs = db.list_jobs(limit=10)
                for j in jobs:
                    if j["status"] == "queued":
                        if get_active_count() < MAX_CONCURRENT_JOBS:
                            start_pipeline_job(j["id"])
        except Exception as e:
            logger.debug("Queue manager error: %s", e)
        await asyncio.sleep(1.0)
