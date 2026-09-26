# Football Highlight Studio - REST API Reference

The backend exposes a standard REST API with JSON payloads, Server-Sent Events (SSE) for real-time progress updates, and HTTP Range streaming for media files.

All error responses adhere to a consistent error envelope:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation",
    "detail": {}
  }
}
```

---

## 1. System & Health

### `GET /api/health`
Public health status check.
- **Local mode:** Returns full system diagnostics, available runtimes, disk space, and limits.
- **Demo mode (`APP_ENV=demo`):** Returns only `{ "ok": true, "app_env": "demo", "url_import_enabled": false, "limits": { "max_upload_gb": 1.0 } }` without filesystem paths.

### `GET /api/health/details`
Detailed diagnostics endpoint. Protected by Bearer `API_TOKEN` if enabled.

### `POST /api/demo/auth`
Authenticate against the optional `DEMO_PASSWORD` gate.
- **Body:** `{ "password": "string" }`
- **Response:** Sets HttpOnly cookie `demo_session` on success.

### `GET /api/sample/clip`
Download the bundled 60-second synthetic match clip (<= 3 MB) for test runs.

---

## 2. Configuration & Tuning

### `GET /api/config/schema`
Returns all customizable hyperparameters, default values, min/max ranges, step intervals, and UI grouping (`basic` vs `advanced`).

---

## 3. Chunked Uploads

Streaming chunked upload protocol for large match video files. Chunks are 8 MB each and streamed directly to disk without loading whole files into memory.

### `POST /api/uploads`
Initialize a chunked upload session.
- **Body:** `{ "filename": "match.mp4", "size": 104857600 }`
- **Response:** `{ "upload_id": "...", "chunk_size": 8388608 }`
- **Errors:** `DISK_FULL` (HTTP 507 if free disk < 2x file size), `INVALID_UPLOAD` (HTTP 400).

### `PUT /api/uploads/{upload_id}/chunks/{chunk_index}`
Stream raw binary data for a specific chunk.
- **Headers:** `Content-Type: application/octet-stream`
- **Body:** Raw binary slice of the file.

### `GET /api/uploads/{upload_id}`
Query received chunks to support network resumption.
- **Response:** `{ "upload_id": "...", "received": [0, 1, 2] }`

### `POST /api/uploads/{upload_id}/complete`
Assemble received chunks, verify file size integrity, and validate media streams.
- **Response:** `{ "upload_id": "...", "ready": true, "duration_s": 720.0, "media": { ... } }`
- **Errors:** `NO_AUDIO_TRACK`, `NO_VIDEO_TRACK`, `ASSEMBLY_FAILED`.

---

## 4. URL Import

### `POST /api/import/check`
Preflight inspection of a web or video URL before download.
- **Body:** `{ "url": "https://..." }`
- **Response (Success):** `{ "ok": true, "title": "...", "duration_s": 720, "thumbnail": "...", "is_live": false, "est_size_mb": 250 }`
- **Response (Blocked/Error):** `{ "ok": false, "error_code": "SOURCE_BLOCKED", "message": "...", "hint": "..." }`

---

## 5. Jobs & Processing Pipeline

### `POST /api/jobs`
Enqueue a highlight generation job.
- **Body:**
  ```json
  {
    "source": {
      "type": "upload",
      "upload_id": "uuid"
    },
    "title": "Match Title",
    "config": {
      "target_duration": 180,
      "sensitivity": 3
    }
  }
  ```
- **Response:** `{ "job_id": "...", "title": "...", "status": "queued", "queue_position": 0 }`

### `GET /api/jobs`
List recent jobs in reverse chronological order.

### `GET /api/jobs/{job_id}`
Retrieve complete job details, current processing stage, active render, duration, and labels.

### `GET /api/jobs/{job_id}/events`
Server-Sent Events (SSE) stream for real-time progress updates, stage transitions, and log lines.

### `POST /api/jobs/{job_id}/cancel`
Immediately terminate the job process group and all child FFmpeg subprocesses.

### `POST /api/jobs/{job_id}/retry`
Retry an interrupted or failed job without re-uploading source video.

---

## 6. Studio & Editorial Controls

### `GET /api/jobs/{job_id}/analysis`
Fetch complete detection analysis: downsampled audio envelope (<= 2000 points), baseline curve, detected moments, suggested candidate spikes (`analysis.suggestions`), and sensitivity settings.

### `POST /api/jobs/{job_id}/retune`
Re-run detection algorithm with new parameters without re-extracting audio (completes in under 3 seconds).
- **Body:** `{ "config": { "min_rise_db": 5.0, "min_sustain_s": 3.5 } }`

### `PUT /api/jobs/{job_id}/windows`
Persist manual moment additions, removals, and trim edits.
- **Body:** `[ { "start": 12.0, "end": 35.0, "source": "manual" } ]`

### `POST /api/jobs/{job_id}/renders`
Encode a new highlight reel version with specified windows.
- **Body:**
  ```json
  {
    "windows": [ { "start": 12.0, "end": 35.0 } ],
    "fade_duration_s": 0.25,
    "crf": 22
  }
  ```

### `GET /api/jobs/{job_id}/renders`
List all rendered versions for comparison and download.

### `POST /api/jobs/{job_id}/labels`
Save known ground-truth event timestamps. Evaluates recall and caught/missed status.

### `POST /api/jobs/{job_id}/find-settings`
Run an automated hyperparameter sweep against user labels to propose optimal sensitivity settings.

---

## 7. Media Serving

### `GET /api/jobs/{job_id}/media/{name}`
Stream or download whitelisted job media assets.
- **Whitelisted assets:** `proxy.mp4`, `debug.png`, `windows.json`, `windows.csv`, `thumbs/NN.jpg`, `renders/{rid}/highlights.mp4`.
- **Features:** Supports HTTP `Range` requests for scrubbing and seeking.
- **Security:** Path traversal attempts (`..`, `%2e%2e`, odd job IDs) return HTTP 400.
