"""
Standalone child process execution runner for isolated heavy jobs.
Ensures clean process-group isolation and outputs JSON lines on stdout for IPC.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add codebase and project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_DIR = PROJECT_ROOT / "codebase"
for p in (str(PROJECT_ROOT), str(CODEBASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import Config
from pipeline import download_video_from_url, process_single_video
from spike_detection import compute_envelope, detect_spikes, detect_subthreshold_suggestions
from spike_window import merge_spikes_into_windows, save_manifest
from clip_cutter import cut_highlight_clips
from plot import generate_debug_plot
from analysis_export import export_analysis
from media_tools import probe_media
from api.runtime import ensure_js_runtime_on_path
from api.error_taxonomy import (
    classify_url_error,
    CODE_SOURCE_BLOCKED,
    CODE_PRIVATE_VIDEO,
    CODE_LIVE_STREAM_UNSUPPORTED,
    CODE_TOO_LARGE,
    CODE_JS_RUNTIME_MISSING,
    CODE_EJS_MISSING,
)
from api.cookies_config import get_active_cookies_params

# Ensure JS runtime (deno or node) is on PATH
ensure_js_runtime_on_path()

logger = logging.getLogger(__name__)


def is_bot_check_error(err_str: str) -> bool:
    """Check if error message corresponds to a YouTube bot/robot challenge."""
    code, _, _ = classify_url_error(err_str)
    return code == CODE_SOURCE_BLOCKED


def classify_download_error(exc: Exception | str) -> tuple[str, str]:
    """Map exception to (error_code, user_friendly_message) without raw tracebacks."""
    code, msg, _ = classify_url_error(exc)
    return code, msg


def emit_ipc(msg_type: str, **kwargs) -> None:
    payload = {"type": msg_type, **kwargs}
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


class IPCLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            emit_ipc("log", message=msg)
        except Exception:
            pass


def setup_ipc_logging(verbose: bool = False) -> None:
    root_logger = logging.getLogger()
    level = logging.DEBUG if verbose else logging.INFO
    root_logger.setLevel(level)

    handler = IPCLoggingHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    root_logger.handlers = [handler]


def run_initial_pipeline(job_id: str, job_dir: Path, source_info: dict, config_overrides: dict) -> None:
    emit_ipc("stage", stage="queued", fraction=0.0, message="Starting job processing...")

    # Load Config with overrides
    cfg = Config(plot=True)
    for k, v in config_overrides.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    source_type = source_info.get("type")
    source_video: Path | None = None

    if source_type == "url":
        url = source_info.get("url")
        if not url:
            raise ValueError("Missing URL in source info")

        emit_ipc("stage", stage="importing", fraction=None, message=f"Downloading match video from {url}...")

        def ytdl_hook(d: dict) -> None:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                frac = round(downloaded / total, 3) if total > 0 else None
                speed_bytes_sec = d.get("speed") or 0
                speed_mb_s = round(speed_bytes_sec / (1024 * 1024), 2) if speed_bytes_sec else None
                eta_s = d.get("eta")
                downloaded_mb = round(downloaded / (1024 * 1024), 1)
                total_mb = round(total / (1024 * 1024), 1) if total > 0 else None

                parts = [f"{round(frac * 100)}%" if frac is not None else "Downloading"]
                if total_mb:
                    parts.append(f"({downloaded_mb}/{total_mb} MB)")
                else:
                    parts.append(f"({downloaded_mb} MB)")
                if speed_mb_s:
                    parts.append(f"{speed_mb_s} MB/s")
                if eta_s:
                    parts.append(f"ETA {eta_s}s")

                msg = " • ".join(parts)
                emit_ipc(
                    "stage",
                    stage="importing",
                    fraction=frac,
                    message=msg,
                    speed_mb_s=speed_mb_s,
                    eta_s=eta_s,
                    downloaded_mb=downloaded_mb,
                    total_mb=total_mb,
                )

        dest_dir = job_dir
        cookies_browser, cookies_file = get_active_cookies_params()
        quality = int(config_overrides.get("quality", 720))

        # Log yt-dlp and JS runtime versions for diagnostics (never log cookies)
        try:
            import yt_dlp
            from api.runtime import check_js_runtime
            js_info = check_js_runtime()
            js_ver = f"{js_info['runtime']} {js_info.get('version', '')}".strip() if js_info.get("installed") else "Not found"
            logger.info("yt-dlp version: %s | JS runtime: %s", getattr(yt_dlp.version, "__version__", "unknown"), js_ver)
        except Exception:
            pass

        proxy_url = os.environ.get("YTDLP_PROXY_URL")
        proxy_tried = False
        current_proxy = None

        max_network_retries = 2
        attempt = 0
        while True:
            try:
                source_video = download_video_from_url(
                    url=url,
                    output_dir=dest_dir,
                    filename_template="source.%(ext)s",
                    progress_hook=ytdl_hook,
                    cookies_from_browser=cookies_browser,
                    cookies_file=cookies_file,
                    quality=quality,
                    proxy=current_proxy,
                )
                break
            except Exception as exc:
                code, friendly_msg, hint = classify_url_error(exc)

                # If blocked and proxy is configured, retry once through proxy
                if code == CODE_SOURCE_BLOCKED and proxy_url and not proxy_tried:
                    proxy_tried = True
                    current_proxy = proxy_url
                    logger.warning("Source blocked on primary IP. Retrying once via YTDLP_PROXY_URL...")
                    emit_ipc("stage", stage="importing", fraction=None, message="Primary connection blocked; retrying via configured proxy...")
                    continue

                # Fail fast immediately on bot check, auth, live stream, or too large (never retry in a loop!)
                if code in (
                    CODE_SOURCE_BLOCKED,
                    CODE_PRIVATE_VIDEO,
                    CODE_LIVE_STREAM_UNSUPPORTED,
                    CODE_TOO_LARGE,
                    CODE_JS_RUNTIME_MISSING,
                    CODE_EJS_MISSING,
                ):
                    logger.error("Download permanently failed (%s): %s", code, friendly_msg)
                    emit_ipc("error", code=code, message=friendly_msg, hint=hint)
                    for p in dest_dir.glob("source.*.part"):
                        p.unlink(missing_ok=True)
                    for p in dest_dir.glob("source.*.ytdl"):
                        p.unlink(missing_ok=True)
                    sys.exit(1)

                # Retry only network timeouts
                is_timeout = "timeout" in str(exc).lower() or "timed out" in str(exc).lower() or "connection reset" in str(exc).lower()
                if is_timeout and attempt < max_network_retries:
                    attempt += 1
                    backoff = attempt * 1.5
                    logger.warning("Transient network timeout downloading %s; retry %d/%d in %.1fs...", url, attempt, max_network_retries, backoff)
                    emit_ipc("stage", stage="importing", fraction=None, message=f"Network timeout, retrying ({attempt}/{max_network_retries})...")
                    import time
                    time.sleep(backoff)
                    continue

                # Reached retry limit or non-retryable error
                logger.error("Download failed (%s): %s", code, friendly_msg)
                emit_ipc("error", code=code, message=friendly_msg, hint=hint)
                for p in dest_dir.glob("source.*.part"):
                    p.unlink(missing_ok=True)
                for p in dest_dir.glob("source.*.ytdl"):
                    p.unlink(missing_ok=True)
                sys.exit(1)
    elif source_type == "upload":
        # Video is already assembled as job_dir / f"source{ext}"
        candidates = list(job_dir.glob("source.*"))
        if not candidates:
            raise FileNotFoundError("Uploaded source video file not found in job directory")
        source_video = candidates[0]
    else:
        raise ValueError(f"Unknown source type: {source_type}")

    # Probe media
    meta = probe_media(source_video)
    if not meta.get("has_audio"):
        emit_ipc("error", code="NO_AUDIO_TRACK", message="Uploaded video file has no audio stream")
        sys.exit(1)
    if not meta.get("has_video"):
        emit_ipc("error", code="NO_VIDEO_TRACK", message="Uploaded file has no video stream")
        sys.exit(1)

    duration_s = meta.get("duration_s", 0.0)

    # Scoped paths
    audio_wav = job_dir / "audio.wav"
    manifest_target = job_dir / "windows.json"
    plot_target = job_dir / "debug.png"
    initial_render_dir = job_dir / "renders" / "default"
    initial_render_dir.mkdir(parents=True, exist_ok=True)

    def pipeline_progress_cb(stage: str, fraction: float | None, message: str) -> None:
        emit_ipc("stage", stage=stage, fraction=fraction, message=message)

    # Step 1: Extract audio
    pipeline_progress_cb("extracting_audio", 0.0, "Extracting match audio...")
    from audio_output import extract_audio_from_video
    extract_audio_from_video(source_video, audio_wav, config=cfg)
    pipeline_progress_cb("extracting_audio", 1.0, "Match audio extracted")

    # Step 2: Compute envelope & detect excitement spikes
    pipeline_progress_cb("detecting", 0.0, "Detecting excitement candidates from audio...")
    times, smoothed_db, baseline_db, rise_db, audio_dur = compute_envelope(audio_wav, config=cfg)
    spikes = detect_spikes(audio_wav, config=cfg, envelope=(times, smoothed_db, baseline_db, rise_db, audio_dur))
    pipeline_progress_cb("detecting", 1.0, f"Detected {len(spikes)} candidate spikes")

    # Step 3: Windows and analysis
    pipeline_progress_cb("selecting", 0.0, "Creating and selecting highlight windows...")
    windows = merge_spikes_into_windows(spikes, audio_duration=audio_dur, config=cfg)
    save_manifest(windows, manifest_target)

    # Sub-threshold candidate suggestions (min_rise_db - 1.5, min_sustain_s - 1.0)
    suggestions = detect_subthreshold_suggestions(
        audio_path=audio_wav,
        config=cfg,
        envelope=(times, smoothed_db, baseline_db, rise_db, audio_dur),
        primary_windows=windows,
    )

    # Export analysis JSONs
    export_analysis(
        output_dir=job_dir,
        times=times,
        smoothed_db=smoothed_db,
        baseline_db=baseline_db,
        rise_db=rise_db,
        total_duration_s=audio_dur,
        spikes=spikes,
        windows=windows,
        config=cfg,
        suggestions=suggestions,
    )

    # Generate debug plot
    if cfg.plot:
        try:
            generate_debug_plot(
                plot_path=plot_target,
                times=times,
                smoothed_db=smoothed_db,
                baseline_db=baseline_db,
                rise_db=rise_db,
                spikes=spikes,
                windows=windows,
                config=cfg,
                title=f"Match Audio Analysis: {source_video.name}",
            )
        except Exception as e:
            logging.warning("Could not generate debug plot: %s", e)

    moment_count = sum(1 for w in windows if w.selected)
    pipeline_progress_cb("selecting", 1.0, f"Selected {moment_count} highlight moments")

    # Emit analysis_ready event!
    emit_ipc(
        "analysis_ready",
        duration_s=round(audio_dur, 2),
        moment_count=moment_count,
        total_moments=len(windows),
    )

    # Step 4: Render initial reel
    pipeline_progress_cb("rendering", 0.0, f"Rendering initial highlight reel ({moment_count} clips)...")
    reel_path = cut_highlight_clips(
        video_path=source_video,
        windows=windows,
        output_folder=initial_render_dir,
        config=cfg,
        progress_cb=pipeline_progress_cb,
    )

    reel_dur = 0.0
    if isinstance(reel_path, Path) and reel_path.exists():
        try:
            reel_dur = float(probe_media(reel_path).get("duration_s", 0.0))
        except Exception:
            pass

    emit_ipc("render_done", render_id="default", duration_s=round(reel_dur, 2), clip_count=moment_count)
    emit_ipc("completed", duration_s=round(audio_dur, 2), moment_count=moment_count)


def run_custom_render(job_id: str, job_dir: Path, render_id: str, render_spec: dict) -> None:
    emit_ipc("stage", stage="rendering", fraction=0.0, message="Starting render...")

    candidates = list(job_dir.glob("source.*"))
    if not candidates:
        raise FileNotFoundError("Source video file not found in job directory")
    source_video = candidates[0]

    render_dir = job_dir / "renders" / render_id
    render_dir.mkdir(parents=True, exist_ok=True)

    windows_data = render_spec.get("windows", [])
    windows_tuples = [(float(w["start"]), float(w["end"])) for w in windows_data]

    cfg = Config()
    if render_spec.get("fade_duration_s") is not None:
        cfg.fade_duration_s = float(render_spec["fade_duration_s"])
    if render_spec.get("crf") is not None:
        cfg.crf = int(render_spec["crf"])
    if render_spec.get("preset") is not None:
        cfg.preset = str(render_spec["preset"])

    def render_progress_cb(stage: str, fraction: float | None, message: str) -> None:
        emit_ipc("stage", stage=stage, fraction=fraction, message=message)

    reel_path = cut_highlight_clips(
        video_path=source_video,
        windows=windows_tuples,
        output_folder=render_dir,
        config=cfg,
        progress_cb=render_progress_cb,
    )

    reel_dur = 0.0
    if isinstance(reel_path, Path) and reel_path.exists():
        try:
            reel_dur = float(probe_media(reel_path).get("duration_s", 0.0))
        except Exception:
            pass

    emit_ipc("render_done", render_id=render_id, duration_s=round(reel_dur, 2), clip_count=len(windows_tuples))
    emit_ipc("completed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--action", required=True, choices=["initial_pipeline", "custom_render"])
    parser.add_argument("--source-json", default="{}")
    parser.add_argument("--config-json", default="{}")
    parser.add_argument("--render-id", default="default")
    parser.add_argument("--render-json", default="{}")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    setup_ipc_logging(verbose=args.verbose)

    job_id = args.job_id
    job_dir = Path(args.job_dir).resolve()

    try:
        if args.action == "initial_pipeline":
            source_info = json.loads(args.source_json)
            config_overrides = json.loads(args.config_json)
            run_initial_pipeline(job_id, job_dir, source_info, config_overrides)
        elif args.action == "custom_render":
            render_spec = json.loads(args.render_json)
            run_custom_render(job_id, job_dir, args.render_id, render_spec)
    except Exception as exc:
        logging.exception("Runner failed: %s", exc)
        raw_msg = str(exc).strip()
        first_line = raw_msg.splitlines()[0] if raw_msg else "Process execution failed"
        if ": " in first_line:
            prefix, rest = first_line.split(": ", 1)
            if any(w in prefix for w in ("Error", "Exception", "Fault")):
                first_line = rest.strip()
        emit_ipc("error", code="PROCESS_FAILED", message=first_line)
        sys.exit(1)


if __name__ == "__main__":
    main()
