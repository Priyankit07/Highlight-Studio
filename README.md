# ⚽ Highlight Studio

> **Automated Football Match Highlight Reel Generator powered by Adaptive Audio Excitement Detection.**
> Transform full 90-minute football match recordings into curated, high-energy highlight reels in seconds — with zero black-box machine learning and no expensive GPUs required.

Built with **FastAPI** + **React / TypeScript / Vite** wrapped around a verifiable Python signal-processing pipeline (**FFmpeg + SciPy**).

---

## ⚡ 60-Second Overview

Broadcasters, content creators, and fans spend hours scrubbing through full match footage to extract key moments. **Highlight Studio** automates this entire workflow:

1. **Drop a Match Video** (or click **Instant Demo** to explore a pre-processed match immediately).
2. **Adaptive Excitement Detection** calculates a rolling acoustic baseline, detects sustained crowd roars and commentator volume spikes, and isolates key match moments in seconds.
3. **Interactive Studio:** Inspect moments on a scrubbable, zoomable timeline, preview video clips, adjust lead-in buffers, restore cropped spans, add missed moments with a single click, or retune sensitivity in real time (< 3 seconds).
4. **Export Clean Reels & Data:** Render high-definition reels with smooth 0.25s fade transitions, and download timestamped manifests (`windows.json`, `windows.csv`) and acoustic debug plots (`debug.png`).

---

## 🏗️ Architecture Diagram

```
┌──────────────────────────────┐
│ Match Video (Upload / URL)   │
└──────────────┬───────────────┘
               │  (8MB Chunks / SSRF-Safe Ingestion)
               ▼
┌──────────────────────────────┐       ┌──────────────────────────────┐
│  FastAPI Backend (Port 8000) │ <===> │  Interactive Studio (Vite)   │
│  - Async Worker & SQLite     │  SSE  │  - Waveform & Moment Cards   │
│  - Chunk Assembler & Media   │  REST │  - Retuning & Manual Marking │
└──────────────┬───────────────┘       └──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Python Signal Processing Engine (codebase/)                         │
│                                                                     │
│  1. FFmpeg Direct Extract   ──> 22.05 kHz Mono PCM WAV              │
│  2. RMS Energy Envelope     ──> 10 Hz Logarithmic Decibels (dB)     │
│  3. 90s Rolling Baseline    ──> scipy.ndimage.median_filter         │
│  4. Rise & Sustain Detect   ──> min_rise_db, min_sustain_s          │
│  5. Expand-First Windowing  ──> [onset - 12s, offset + 6s]          │
│  6. Merge & Budget Assembly ──> Greedy ranking + Fade Crossfades    │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Output Deliverables: Final Reel (.mp4) + Manifests (JSON/CSV) + Plot│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 How Excitement Detection Works (Plain Language)

Instead of slow, brittle computer vision models that require massive GPU clusters, Highlight Studio uses transparent acoustic signal processing:

1. **Audio Extraction:** Direct FFmpeg extraction extracts match audio to 22.05 kHz mono 32-bit float PCM WAV, avoiding 16-bit integer squaring overflow bugs.
2. **Logarithmic Energy Envelope:** Computes Root Mean Square (RMS) energy at 10 Hz (10 samples per second) converted to decibels (dB).
3. **Adaptive 90-Second Rolling Baseline:** A rolling median filter tracks ambient stadium noise. This automatically adapts to loud derbies, quiet neutral grounds, or broadcast mixer changes without global distortion.
4. **Excitement Rise & Sustain Filtering:** Candidate excitement events must rise above the ambient baseline by `min_rise_db` (default: `4.0 dB`) and remain elevated for at least `min_sustain_s` (default: `3.0 s`). Sudden short transients (referee whistles, microphone thumps, ball kicks) are automatically rejected.
5. **Expand-First Windowing:** Each spike is expanded with build-up lead-in (`pre_roll`, default: `12 s`) and celebration aftermath (`post_roll`, default: `6 s`) *before* merging overlapping intervals, guaranteeing zero duplicate frames and zero overlapping cuts.
6. **Budget Assembly & Seamless Joins:** Moments are greedily ranked by acoustic energy area or peak rise up to the target length cap, and joined using seamless 0.25-second video and audio fade transitions.

---

## ✨ Key Features

- **Adaptive Rolling Baseline:** No global-maximum distortion; normalizes against local ambient sound.
- **Transient Rejection:** Eliminates referee whistles, mic thumps, and ball kicks with sustain thresholds.
- **Expand-First Windowing:** Guarantees zero repeated footage and zero overlapping clips.
- **Interactive Timeline & Studio:** Scrub, zoom, pan, split, preview clips, and inspect intensity bars.
- **Sub-3-Second Retuning:** Re-run spike detection on cached acoustic envelopes without re-extracting audio.
- **Missed Moments Recovery:**
  - One-click manual moment adding (`+ Add Moment` or double-click timeline).
  - Sub-threshold **Possible Moments** suggestions (dashed outlines on timeline).
  - **Restore Full Span** button when a window is cropped around a peak.
  - Automated parameter sweep optimizer to maximize recall against labeled goals.
- **Dual Manifest Export:** Download timestamped `windows.json` and `windows.csv` with start, end, peak, and score metadata.
- **Resumable Chunked Uploads:** 8 MB chunks with parallel uploading, disk-space preflight checks, and pause/resume.
- **URL Video Import:** Best-effort stream downloading via `yt-dlp` with SSRF protection and friendly error taxonomy mapping.
- **Instant Demo Mode:** Pre-loaded 12-minute synthetic broadcast match to test all studio features immediately.

---

## 🚀 Quickstart

### Prerequisites
- **Python:** >= 3.12 (recommended with [`uv`](https://github.com/astral-sh/uv))
- **Node.js:** >= 20
- **FFmpeg:** installed and available on system `PATH`

### 1. Local Development (Backend + Frontend)

```bash
# Clone repository
git clone https://github.com/Priyankit07/Highlight-Studio.git
cd Highlight-Studio

# 1. Install backend dependencies
uv sync

# 2. Seed pre-processed demo match
uv run python tools/seed_demo_job.py

# 3. Start FastAPI backend (port 8000)
uv run uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# 4. In a second terminal: Start React frontend (port 5173)
cd frontend
npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

### 2. Single-Container Docker Compose

```bash
# Copy sample configuration
cp .env.example .env

# Build and start container (port 8000)
docker compose up -d --build
```

Access the studio at **`http://localhost:8000`**.

---

### 3. Direct CLI Pipeline

You can also run the underlying pipeline directly from the command line:

```bash
# Generate highlights reel from a match video
uv run python codebase/pipeline.py "raw videos/synthetic_match.mp4"

# Fast dry-run: compute envelope and generate debug.png without video rendering
uv run python codebase/pipeline.py "raw videos/synthetic_match.mp4" --dry-run --plot
```

---

## 📁 Repository Structure

```
Highlight-Studio/
├── api/                   # FastAPI backend application
│   ├── main.py            # API entrypoint, CORS, rate limits, static mounts
│   ├── routes/            # Endpoints: jobs, uploads, imports, media, health
│   ├── storage.py         # Chunk assembly, disk checks, path validation
│   ├── runner.py          # Background pipeline execution & progress callbacks
│   ├── worker.py          # Process group management, cancel & cleanup
│   └── error_taxonomy.py  # User-friendly error mapping & troubleshooting copy
├── codebase/              # Core signal processing & video editing engine
│   ├── pipeline.py        # End-to-end highlight generation orchestrator
│   ├── spike_detection.py # RMS envelope, rolling baseline, peak detection
│   ├── spike_window.py    # Expand-first windowing, overlap merge, ranking
│   ├── clip_cutter.py     # FFmpeg clip extraction with fade transitions
│   ├── media_tools.py     # Fast metadata probe, proxy video, thumbnail extract
│   ├── analysis_export.py # Waveform downsampling for fast web visualization
│   └── evaluate.py        # Precision, recall, and hyperparameter grid sweep
├── frontend/              # React 18 + TypeScript + Vite + TailwindCSS UI
│   ├── src/pages/         # JobStudioPage, LibraryPage, NewJobPage, SettingsPage
│   ├── src/components/    # Timeline, VideoPlayer, MomentList, TuningDrawer
│   └── e2e/               # Playwright end-to-end integration tests
├── docs/                  # Technical documentation
│   ├── API.md             # REST API endpoint reference and schemas
│   ├── ARCHITECTURE.md    # In-depth architectural design decisions
│   └── DEMO.md            # 2-minute demonstration script for judges
├── scripts/               # Developer automation scripts (dev, build, smoke test)
├── tools/                 # Synthetic match generator & demo seeders
└── tests/                 # Comprehensive pytest test suite (61 tests)
```

---

## 🧪 Testing & Verification

The repository includes a comprehensive test suite covering audio processing, window algorithms, API endpoints, upload handling, and end-to-end execution:

```bash
# Run backend pytest suite (61 tests)
uv run pytest

# Run frontend unit tests (16 tests)
cd frontend && npm test

# Run Playwright E2E browser tests across all job states (12 tests)
npx playwright test

# Run deployment smoke test against live instance
./scripts/smoke_test.sh http://127.0.0.1:8000
```

---

## ⚠️ Honest Limitations

> [!NOTE]
> 1. **Acoustic Energy vs Event Semantics:** The detector identifies acoustic energy peaks from crowd volume and commentator voice modulation. It does not classify whether a moment was a goal, a near-miss hitting the post, a controversial penalty, a red card altercation, or an away-fan cheer.
> 2. **Missed Moments Recovery:** In matches where crowd audio is heavily compressed or commentary builds up very gradually, certain moments may fall below thresholds. Highlight Studio includes dedicated **"Add Moment"** tools, sub-threshold **"Possible Moments"** suggestions, and real-time retuning so you retain full editorial control.
> 3. **URL Import:** Web video import (via `yt-dlp`) is provided as a best-effort convenience for self-hosted installations. Cloud environments frequently face automated bot-checks from video streaming providers; direct file upload is always recommended for cloud deployments.
> 4. **Broadcast Rights:** Ensure you hold the appropriate licensing and broadcast permissions for any video footage processed and exported.

---

## 📄 License

This project is licensed under the MIT License.
