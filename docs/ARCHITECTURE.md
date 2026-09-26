# System Architecture & Lifecycle

Football Highlight Studio combines an audio spike detection backend with an asynchronous job manager and a desktop-first React frontend.

---

## 1. High-Level Architecture

```
[ Browser / Frontend (React + Vite + d3-scale) ]
                    |
      HTTP REST / SSE Events / Range Streaming
                    v
[ FastAPI Web Layer (api/main.py, api/routes/*) ]
      |                      |                    |
[ Upload Assembler ]   [ SQLite DB ]    [ Job Worker & Concurrency ]
(api/storage.py)      (api/db.py)      (api/worker.py)
                                                  |
                                                  | Subprocess Isolation (PGID)
                                                  v
                                      [ Job Runner (api/runner.py) ]
                                                  |
                        +-------------------------+-------------------------+
                        |                                                   |
             [ Audio Pipeline ]                                   [ FFmpeg Render ]
             - Audio Extraction (22.05kHz mono)                   - Fast Proxy (480p)
             - RMS dB Envelope (10Hz)                             - Peak Thumbnails
             - Rolling-Median Baseline (90s)                      - Clip Cutting
             - Adaptive Spike Detection                           - Fade Transitions
             - Greedy Window Merging                              - Concat Demuxer
```

---

## 2. Job Lifecycle State Machine

```
               [ User Upload / URL ]
                         |
                         v
                    ( queued )
                         | (Worker pick)
                         v
                    ( importing )
                         |
                         v
                ( extracting_audio )
                         |
                         v
                    ( detecting )
                         |
                         v
              +---> [ analysis_ready ]  <-- Studio UI reveals here!
              |          |
 (Background) |          v
 (Thumbnails  |     ( rendering )
  & Proxy)    |          |
              +          v
                    ( completed )

Failure / Interruption paths:
any state --(error)---------> ( failed )
any state --(user cancel)----> ( cancelled )  [os.killpg terminates FFmpeg <3s]
running   --(server restart)-> ( interrupted ) [Offers instant retry]
```

---

## 3. Directory Layout & Media Storage

All persistent artifacts reside under `data/jobs/<job_id>/`:

```
data/
└── jobs/
    └── <job_id>/
        ├── source.mp4           # Assembled raw video
        ├── audio.wav            # 22.05 kHz mono WAV for fast analysis
        ├── envelope.json        # Downsampled dB envelope (<= 3000 points)
        ├── analysis.json        # Spikes, detected windows, and config
        ├── windows.json         # Highlight manifest for export
        ├── windows.csv          # CSV export
        ├── debug.png            # Matplotlib detection graph
        ├── proxy.mp4            # Fast 480p scrubbable source preview
        ├── thumbs/              # JPEGs captured at peak excitement
        │   ├── 01.jpg
        │   └── 02.jpg
        ├── job.log              # Stdout/stderr log stream
        └── renders/             # Generated highlight reels
            ├── default/
            │   └── highlights.mp4
            └── r_a9f1b20c/
                └── highlights.mp4
```

---

## 4. Key Design Patterns

### Process-Group Isolation & Safe Cancellation
Video encoding operations with FFmpeg spawn external native processes inside Python thread pools that cannot be safely interrupted using Python threads alone.

To guarantee zero lingering processes upon job cancellation:
1. `api/runner.py` is invoked as a separate Python process with `start_new_session=True` (creating its own OS process group).
2. When the user cancels or the job times out, `api/worker.py` issues `os.killpg(pgid, signal.SIGTERM)`, followed by `SIGKILL` if still alive after 2 seconds.
3. Every FFmpeg child process is terminated immediately.

### Fast Re-tuning ($\le 3$ Seconds)
When adjusting sensitivity thresholds (`min_rise_db`, `min_sustain_s`, `target_duration`), the server executes detection and window merging directly in memory against the pre-extracted `audio.wav`. It bypasses audio extraction and video encoding completely, delivering new moments in under 3 seconds even on full-length matches.

### Range-Supported Video Streaming
Browsers playing `<video>` elements require HTTP `206 Partial Content` with `Accept-Ranges: bytes` headers to support scrubbing and random seeking. `api/routes/media.py` includes a streaming response handler that calculates chunk offsets, byte boundaries, and content lengths.
