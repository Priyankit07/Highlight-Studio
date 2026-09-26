#!/usr/bin/env python3
"""
Seed pre-processed demo match into data/demo/ and data/jobs/demo-match/
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root and codebase to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "codebase"))

import imageio_ffmpeg
from codebase.pipeline import run_pipeline
from codebase.media_tools import extract_thumbnail, make_proxy, probe_media
from api import db
from api.models import ConfigModel

DEMO_DIR = PROJECT_ROOT / "data" / "demo"
JOBS_DIR = PROJECT_ROOT / "data" / "jobs"
DEMO_JOB_ID = "demo-match"
RAW_SYNTHETIC = PROJECT_ROOT / "raw videos" / "synthetic_match.mp4"


def setup_demo_job(target_override: Path | str | None = None):
    print("⚽ Setting up pre-processed demo match for judges...")
    if target_override:
        target_dir = Path(target_override)
        target_dir.mkdir(parents=True, exist_ok=True)
        demo_dest = target_dir
        job_dest = target_dir
    else:
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        target_job_dir = JOBS_DIR / DEMO_JOB_ID
        target_job_dir.mkdir(parents=True, exist_ok=True)
        demo_dest = DEMO_DIR
        job_dest = target_job_dir

    # Check for build-time demo assets
    demo_assets = Path("/app/demo_assets")
    if not demo_assets.exists():
        demo_assets = PROJECT_ROOT / "demo_assets"

    # Seed data/demo from /app/demo_assets if data/demo is missing/incomplete
    if not target_override and demo_assets.exists():
        for item in demo_assets.iterdir():
            dest = DEMO_DIR / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

    # If demo_dest already has windows.json, we can copy into job_dest if different
    if (demo_dest / "windows.json").exists() and (demo_dest / "source.mp4").exists():
        if job_dest != demo_dest:
            for item in demo_dest.iterdir():
                dest = job_dest / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
        if not target_override:
            _register_demo_job_in_db(job_dest)
        print("✅ Demo match successfully initialized from pre-built assets.")
        return

    # Look for source video candidate
    cand_sources = [
        demo_dest / "source.mp4",
        demo_dest / "synthetic_match.mp4",
        demo_assets / "source.mp4",
        demo_assets / "synthetic_match.mp4",
        RAW_SYNTHETIC,
    ]
    found_source = None
    for cand in cand_sources:
        if cand.exists() and cand.is_file():
            found_source = cand
            break

    demo_source = job_dest / "source.mp4"
    if not demo_source.exists():
        if found_source:
            shutil.copy2(found_source, demo_source)
        else:
            print("Generating synthetic match broadcast (120s)...")
            from tools.make_synthetic_match import make_synthetic_match
            make_synthetic_match(
                output_wav=job_dest / "synthetic_match.wav",
                output_mp4=demo_source,
                events_json=job_dest / "synthetic_events.json",
                events_csv=job_dest / "synthetic_events.csv",
                duration_s=120.0,
            )

    # Run pipeline to generate windows, analysis, envelope, highlights
    run_pipeline(
        video_path=demo_source,
        clips_output_dir=job_dest,
    )

    # Generate proxy and thumbnails
    proxy_mp4 = job_dest / "proxy.mp4"
    if not proxy_mp4.exists():
        print("Creating proxy video...")
        try:
            make_proxy(demo_source, proxy_mp4)
        except Exception as e:
            print(f"Proxy generation fallback: {e}")
            shutil.copy2(demo_source, proxy_mp4)

    # Generate thumbnails
    thumbs_dir = job_dest / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    windows_file = job_dest / "windows.json"
    if windows_file.exists():
        with open(windows_file, "r") as f:
            windows = json.load(f)
        for i, w in enumerate(windows):
            thumb_path = thumbs_dir / f"{i:02d}.jpg"
            if not thumb_path.exists():
                peak_time = w.get("peak_time", w.get("start", 0))
                try:
                    extract_thumbnail(demo_source, peak_time, thumb_path)
                except Exception:
                    pass

    # Ensure renders/default/highlights.mp4 exists
    renders_default = job_dest / "renders" / "default"
    renders_default.mkdir(parents=True, exist_ok=True)
    top_reel = job_dest / "highlights.mp4"
    if top_reel.exists() and not (renders_default / "highlights.mp4").exists():
        shutil.copy2(top_reel, renders_default / "highlights.mp4")

    # Mirror all generated artifacts to demo_dest as template if different
    if demo_dest != job_dest:
        for item in job_dest.iterdir():
            dest = demo_dest / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    if not target_override:
        _register_demo_job_in_db(job_dest)
        print("✅ Pre-processed demo job successfully initialized at data/jobs/demo-match/")
    else:
        print(f"✅ Pre-processed demo assets successfully generated at {target_override}")


def _register_demo_job_in_db(job_dir: Path):
    try:
        db.init_db()
        renders_default = job_dir / "renders" / "default"
        reel_file = renders_default / "highlights.mp4"
        reel_dur = 30.0
        if reel_file.exists():
            try:
                meta = probe_media(reel_file)
                reel_dur = float(meta.get("duration_s", 30.0))
            except Exception:
                pass

        existing = db.get_job(DEMO_JOB_ID)
        if not existing:
            db.create_job(
                job_id=DEMO_JOB_ID,
                title="Synthetic Match (Demo)",
                source_type="upload",
                source_filename="synthetic_match.mp4",
                config=ConfigModel().model_dump(),
            )

        duration_s = 120.0
        source_file = job_dir / "source.mp4"
        if source_file.exists():
            try:
                meta = probe_media(source_file)
                duration_s = float(meta.get("duration_s", 120.0))
            except Exception:
                pass

        moment_count = 1
        wf = job_dir / "windows.json"
        if wf.exists():
            try:
                with open(wf, "r") as f:
                    moment_count = len(json.load(f))
            except Exception:
                pass

        db.update_job(
            DEMO_JOB_ID,
            status="completed",
            stage="completed",
            progress=1.0,
            duration_s=round(duration_s, 2),
            moment_count=moment_count,
            active_render_id="default",
        )
        db.create_render(
            render_id="default",
            job_id=DEMO_JOB_ID,
            windows=[{"start": 10, "end": 35}],
        )
        db.update_render(
            render_id="default",
            job_id=DEMO_JOB_ID,
            status="completed",
            duration_s=round(reel_dur, 2),
        )
    except Exception as e:
        print(f"Notice: database registration skipped or deferred: {e}")


if __name__ == "__main__":
    setup_demo_job()
