"""
Highlight generator pipeline and CLI entry point.
Orchestrates audio extraction, excitement spike detection, window merging & selection,
manifest generation, debug plotting, and video highlight reel cutting.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import urllib.parse
from pathlib import Path

from typing import Callable, Any

from audio_output import extract_audio_from_video
from clip_cutter import cut_highlight_clips
from config import Config
from plot import generate_debug_plot
from spike_detection import compute_envelope, detect_spikes, detect_subthreshold_suggestions
from spike_window import merge_spikes_into_windows, save_manifest
from analysis_export import export_analysis

logger = logging.getLogger("highlight_generator")


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging output."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, force=True)


def _parse_browser_cookies_spec(val: str | tuple) -> tuple:
    """Parse a browser cookie string spec into yt-dlp's expected tuple format."""
    if isinstance(val, tuple):
        return val
    # Format: BROWSER[+KEYRING][:PROFILE][::CONTAINER]
    m = re.fullmatch(
        r"(?P<name>[^+:]+)(?:\s*\+\s*(?P<keyring>[^:]+))?(?:\s*:\s*(?!:)(?P<profile>.+?))?(?:\s*::\s*(?P<container>.+))?",
        val.strip(),
    )
    if m:
        browser_name, keyring, profile, container = m.group("name", "keyring", "profile", "container")
        return (browser_name.lower(), profile, keyring.upper() if keyring else None, container)
    return (val.strip().lower(), None, None, None)


def download_video_from_url(
    url: str,
    output_dir: Path,
    filename_template: str | None = None,
    progress_hook: Callable[[dict], None] | None = None,
    cookies_from_browser: str | tuple | None = None,
    cookies_file: str | Path | None = None,
    quality: int = 720,
    proxy: str | None = None,
) -> Path:
    """
    Download a video using streaming HTTP (for direct links) or yt-dlp into output_dir.

    Args:
        url: Video URL to download.
        output_dir: Destination directory ('raw videos/').
        filename_template: Optional output filename template (default "%(id)s.%(ext)s").
        progress_hook: Optional yt-dlp progress hook.
        cookies_from_browser: Optional browser name/spec to load cookies from (e.g. 'chrome', 'firefox').
        cookies_file: Optional path to Netscape cookies.txt file.
        quality: Video height limit (default 720, e.g. 480, 720, 1080).
        proxy: Optional HTTP/HTTPS/SOCKS proxy URL for yt-dlp.

    Returns:
        Path to downloaded video file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    template = filename_template or "%(id)s.%(ext)s"

    # 1. Direct video URL streaming check
    try:
        from api.direct_downloader import is_direct_video_url, download_direct_file
        if is_direct_video_url(url):
            logger.info("Direct media file URL detected, downloading via streaming HTTP: %s", url)
            parsed_name = Path(urllib.parse.urlparse(url).path).name or "source.mp4"
            dest_name = template.replace("%(title)s", Path(parsed_name).stem).replace("%(id)s", Path(parsed_name).stem).replace("%(ext)s", Path(parsed_name).suffix.lstrip("."))
            out_file = output_dir / dest_name
            return download_direct_file(url, out_file, progress_cb=progress_hook)
    except Exception as e:
        logger.debug("Direct download check skipped/failed: %s", e)

    # 2. Web / YouTube download via yt-dlp
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError("yt-dlp is required for --url downloads. Install it with: uv pip install yt-dlp") from e

    # Ensure JS runtime (deno or node) is discoverable on PATH for yt-dlp
    js_cfg = {}
    try:
        from api.runtime import ensure_js_runtime_on_path, get_js_runtime_config
        ensure_js_runtime_on_path()
        js_cfg = get_js_runtime_config()
    except Exception:
        local_bin = str(Path.home() / ".local" / "bin")
        if local_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

    out_template = str(output_dir / template)
    q = quality if quality in (480, 720, 1080) else 720
    format_str = f"bestvideo[height<={q}]+bestaudio/best[height<={q}]/best"

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    ydl_opts: dict[str, Any] = {
        "outtmpl": out_template,
        "format": format_str,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe,
        "remote_components": ["ejs:npm", "ejs:github"],
        "quiet": False,
        "no_warnings": False,
    }
    if js_cfg:
        ydl_opts["js_runtimes"] = js_cfg
    if proxy:
        ydl_opts["proxy"] = proxy
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = _parse_browser_cookies_spec(cookies_from_browser)
    if cookies_file:
        ydl_opts["cookiefile"] = str(cookies_file)
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    logger.info("Downloading match video from URL: %s (quality: <=%dp)", url, q)
    import typing
    with yt_dlp.YoutubeDL(typing.cast(Any, ydl_opts)) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # Check if merged to mp4
        final_path = Path(filename)
        if not final_path.exists():
            mp4_cand = final_path.with_suffix(".mp4")
            if mp4_cand.exists():
                final_path = mp4_cand

    logger.info("Downloaded video: %s (%.2f MB)", final_path.name, final_path.stat().st_size / (1024 * 1024))
    return final_path


def process_single_video(
    video_path: Path,
    config: Config,
    audio_output_path: Path | None = None,
    spike_window_output_path: Path | None = None,
    clips_output_dir: Path | None = None,
    progress_cb: Callable[[str, float | None, str], None] | None = None,
) -> Path | None:
    """
    Execute highlight generation for a single video file.

    Returns:
        Path to generated highlights.mp4, or None if dry-run or no clips.
    """
    stem = video_path.stem
    logger.info("=" * 60)
    logger.info("Processing match video: %s", video_path.name)
    logger.info("=" * 60)

    # Scoped output paths
    audio_wav = audio_output_path or (config.audio_dir / f"{stem}.wav")
    match_out_dir = clips_output_dir or (config.out_dir / stem)
    manifest_target = spike_window_output_path or (match_out_dir / "windows.json")
    plot_target = match_out_dir / "debug.png"

    match_out_dir.mkdir(parents=True, exist_ok=True)
    audio_wav.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Audio extraction (or reuse if requested and valid)
    should_extract = True
    if config.reuse_audio and audio_wav.exists() and audio_wav.stat().st_size > 0:
        if audio_wav.stat().st_mtime >= video_path.stat().st_mtime:
            logger.info("Reusing existing WAV audio (newer than video): %s", audio_wav)
            should_extract = False

    if should_extract:
        if progress_cb:
            progress_cb("extracting_audio", 0.0, "Extracting match audio...")
        logger.info("[Step 1/4] Extracting match audio...")
        extract_audio_from_video(video_path, audio_wav, config=config)
        if progress_cb:
            progress_cb("extracting_audio", 1.0, "Match audio extracted")
    else:
        if progress_cb:
            progress_cb("extracting_audio", 1.0, "Reused existing audio")

    # Step 2: Compute envelope and detect excitement spikes
    if progress_cb:
        progress_cb("detecting", 0.0, "Detecting excitement candidates from audio...")
    logger.info("[Step 2/4] Detecting excitement candidates from audio...")

    # Compute envelope once
    times, smoothed_db, baseline_db, rise_db, audio_duration = compute_envelope(audio_wav, config=config)
    spikes = detect_spikes(audio_wav, config=config, envelope=(times, smoothed_db, baseline_db, rise_db, audio_duration))

    if progress_cb:
        progress_cb("detecting", 1.0, f"Detected {len(spikes)} candidate spikes")

    # Step 3: Create, merge, rank, and select windows
    if progress_cb:
        progress_cb("selecting", 0.0, "Creating and selecting highlight windows...")
    logger.info("[Step 3/4] Creating and selecting highlight windows...")
    windows = merge_spikes_into_windows(spikes, audio_duration=audio_duration, config=config)

    # Save manifest (JSON + CSV)
    save_manifest(windows, manifest_target)

    # Sub-threshold candidate suggestions (min_rise_db - 1.5, min_sustain_s - 1.0)
    suggestions = detect_subthreshold_suggestions(
        audio_path=audio_wav,
        config=config,
        envelope=(times, smoothed_db, baseline_db, rise_db, audio_duration),
        primary_windows=windows,
    )

    # Export analysis JSONs (envelope.json and analysis.json)
    export_analysis(
        output_dir=match_out_dir,
        times=times,
        smoothed_db=smoothed_db,
        baseline_db=baseline_db,
        rise_db=rise_db,
        total_duration_s=audio_duration,
        spikes=spikes,
        windows=windows,
        config=config,
        suggestions=suggestions,
    )

    selected_count = sum(1 for w in windows if w.selected)
    if progress_cb:
        progress_cb("selecting", 1.0, f"Selected {selected_count} highlight moments")

    # Optional debug plot
    if config.plot:
        logger.info("Generating debug visualization plot...")
        generate_debug_plot(
            plot_path=plot_target,
            times=times,
            smoothed_db=smoothed_db,
            baseline_db=baseline_db,
            rise_db=rise_db,
            spikes=spikes,
            windows=windows,
            config=config,
            title=f"Match Audio Analysis: {video_path.name}",
        )

    # Dry-run check
    if config.dry_run:
        logger.info("Dry-run requested: skipping video clip cutting.")
        return None

    # Step 4: Cut highlight clips and combine
    logger.info("[Step 4/4] Cutting and assembling highlight reel...")
    reel_path = cut_highlight_clips(
        video_path=video_path,
        windows=windows,
        output_folder=match_out_dir,
        config=config,
        progress_cb=progress_cb,
    )

    if reel_path:
        logger.info("=" * 60)
        logger.info("Highlights reel complete: %s", reel_path)
        logger.info("=" * 60)
    else:
        logger.warning("No highlights reel was produced (0 windows selected).")

    return reel_path if isinstance(reel_path, Path) else None


def run_pipeline(
    video_path: str | Path,
    audio_output_path: str | Path | None = None,
    spike_window_output_path: str | Path | None = None,
    clips_output_dir: str | Path | None = None,
    config: Config | None = None,
    progress_cb: Callable[[str, float | None, str], None] | None = None,
) -> Path | None:
    """
    Public entry point for running the pipeline programmatically.

    Args:
        video_path: Path to video file or directory containing video files.
        audio_output_path: Optional explicit WAV output path.
        spike_window_output_path: Optional explicit manifest path.
        clips_output_dir: Optional explicit output directory.
        config: Optional Config instance.
        progress_cb: Optional progress callback.

    Returns:
        Path to generated highlights reel (or None).
    """
    cfg = config or Config()
    v_path = Path(video_path).resolve()

    if not v_path.exists():
        raise FileNotFoundError(f"Input path not found: {v_path}")

    setup_logging(verbose=cfg.verbose)

    if v_path.is_dir():
        # Process every video file in directory
        video_extensions = {".mp4", ".mkv", ".mov", ".avi", ".ts", ".webm", ".m4v"}
        video_files = [f for f in sorted(v_path.iterdir()) if f.is_file() and f.suffix.lower() in video_extensions]

        if not video_files:
            logger.warning("No video files found in directory: %s", v_path)
            return None

        logger.info("Found %d video file(s) in %s", len(video_files), v_path)
        last_reel = None
        for vf in video_files:
            last_reel = process_single_video(vf, cfg, progress_cb=progress_cb)
        return last_reel

    return process_single_video(
        v_path,
        cfg,
        audio_output_path=Path(audio_output_path).resolve() if audio_output_path else None,
        spike_window_output_path=Path(spike_window_output_path).resolve() if spike_window_output_path else None,
        clips_output_dir=Path(clips_output_dir).resolve() if clips_output_dir else None,
        progress_cb=progress_cb,
    )


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, Config]:
    """Parse command-line arguments and load configuration."""
    parser = argparse.ArgumentParser(
        description="Football (Soccer) Highlight Generator - Turn broadcast match video into excitement highlights reel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", nargs="?", default=None, help="Path to input match video file or directory of videos")
    parser.add_argument("--url", type=str, default=None, help="URL of match video to download via yt-dlp")
    parser.add_argument("--quality", type=int, default=720, choices=[480, 720, 1080], help="Maximum video resolution height (480, 720, 1080)")
    parser.add_argument("--cookies-from-browser", type=str, default=None, help="Load cookies from browser (e.g. chrome, firefox, safari)")
    parser.add_argument("--cookies-file", type=str, default=None, help="Path to Netscape cookies.txt file")
    parser.add_argument("--config", type=str, default=None, help="Path to optional TOML config file")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory for generated highlights")
    parser.add_argument("--target-duration", type=float, default=None, help="Target reel duration in seconds (0 = keep all)")
    parser.add_argument("--pre-roll", type=float, default=None, help="Lead-in seconds before excitement spike")
    parser.add_argument("--post-roll", type=float, default=None, help="Reaction seconds after excitement spike")
    parser.add_argument("--min-rise-db", type=float, default=None, help="Minimum rise in dB above rolling baseline")
    parser.add_argument("--min-sustain", type=float, default=None, help="Minimum sustain duration in seconds")
    parser.add_argument("--skip-start", type=float, default=None, help="Seconds to skip at start (intro jingles)")
    parser.add_argument("--top-k", type=int, default=None, help="Max number of highlight moments to select")
    parser.add_argument("--keep-clips", action="store_true", default=None, help="Keep intermediate clip segments")
    parser.add_argument("--reuse-audio", action="store_true", default=None, help="Skip extraction if WAV is newer than video")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Fast tuning mode: extract/detect/manifest/plot without video cutting")
    parser.add_argument("--plot", action="store_true", default=None, help="Generate debug envelope visualization plot")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Enable verbose debug logging")

    args = parser.parse_args(argv)

    # Initialize Config: start with defaults or TOML
    if args.config:
        cfg = Config.from_toml(args.config)
    else:
        cfg = Config()

    # Apply CLI overrides if explicitly passed
    if args.out_dir is not None:
        cfg.out_dir = Path(args.out_dir)
    if args.target_duration is not None:
        cfg.target_duration = args.target_duration
    if args.pre_roll is not None:
        cfg.pre_roll = args.pre_roll
    if args.post_roll is not None:
        cfg.post_roll = args.post_roll
    if args.min_rise_db is not None:
        cfg.min_rise_db = args.min_rise_db
    if args.min_sustain is not None:
        cfg.min_sustain_s = args.min_sustain
    if args.skip_start is not None:
        cfg.skip_start_s = args.skip_start
    if args.top_k is not None:
        cfg.top_k = args.top_k
    if args.keep_clips is not None:
        cfg.keep_clips = args.keep_clips
    if args.reuse_audio is not None:
        cfg.reuse_audio = args.reuse_audio
    if args.dry_run is not None:
        cfg.dry_run = args.dry_run
    if args.plot is not None:
        cfg.plot = args.plot
    if args.verbose:
        cfg.verbose = True

    return args, cfg


def main(argv: list[str] | None = None) -> int:
    args, cfg = parse_args(argv)
    setup_logging(verbose=cfg.verbose)

    input_path = args.input

    if args.url:
        project_root = Path(__file__).resolve().parent.parent
        raw_videos_dir = project_root / "raw videos"
        input_path = download_video_from_url(
            args.url,
            raw_videos_dir,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file,
        )

    if not input_path:
        logger.error("No input video or --url provided. Run with --help for usage instructions.")
        return 1

    try:
        run_pipeline(input_path, config=cfg)
        return 0
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=cfg.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())