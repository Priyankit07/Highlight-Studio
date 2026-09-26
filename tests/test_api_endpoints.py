"""
Integration tests for the FastAPI application endpoints.
Tests health, schema, chunked upload, validation, security, renders, and media serving.
"""
from pathlib import Path
import json
import subprocess
import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api import db, storage


@pytest.fixture
def client():
    # Ensure fresh test DB
    db.init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def short_video(tmp_path: Path) -> Path:
    """Produce a small 3-second synthetic match video with audio."""
    v_path = tmp_path / "test_match.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=0x1a4314:s=320x240:r=25:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(v_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return v_path


def test_health_endpoint(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert "ffmpeg" in data
    assert "disk" in data
    assert "limits" in data
    assert ".mp4" in data["limits"]["allowed_extensions"]


def test_config_schema_endpoint(client: TestClient):
    res = client.get("/api/config/schema")
    assert res.status_code == 200
    fields = res.json()["fields"]
    names = [f["name"] for f in fields]
    assert "min_rise_db" in names
    assert "min_sustain_s" in names
    assert "target_duration" in names
    assert "pre_roll" in names
    assert "post_roll" in names

    rise_field = next(f for f in fields if f["name"] == "min_rise_db")
    assert rise_field["min"] == 1.0
    assert rise_field["max"] == 15.0
    assert rise_field["group"] == "basic"


def test_chunked_upload_flow(client: TestClient, short_video: Path):
    video_bytes = short_video.read_bytes()
    file_size = len(video_bytes)

    # 1. Initialize
    init_res = client.post("/api/uploads", json={"filename": "match.mp4", "size": file_size})
    assert init_res.status_code == 200
    upload_id = init_res.json()["upload_id"]

    # 2. Put chunk (single chunk for small file)
    chunk_res = client.put(f"/api/uploads/{upload_id}/chunks/0", content=video_bytes)
    assert chunk_res.status_code == 200

    # 3. Status check
    status_res = client.get(f"/api/uploads/{upload_id}")
    assert status_res.status_code == 200
    assert status_res.json()["received"] == [0]

    # 4. Complete
    complete_res = client.post(f"/api/uploads/{upload_id}/complete")
    assert complete_res.status_code == 200
    comp_data = complete_res.json()
    assert comp_data["ready"] is True
    assert comp_data["media"]["has_audio"] is True
    assert comp_data["media"]["has_video"] is True


def test_upload_rejects_unsupported_format(client: TestClient):
    res = client.post("/api/uploads", json={"filename": "malware.exe", "size": 1000})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_UPLOAD"


def test_upload_rejects_no_audio_video(client: TestClient, tmp_path: Path):
    # Create silent video without audio track
    no_audio_v = tmp_path / "silent.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=red:s=160x120:r=25:d=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(no_audio_v),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    v_bytes = no_audio_v.read_bytes()
    init_res = client.post("/api/uploads", json={"filename": "silent.mp4", "size": len(v_bytes)})
    upload_id = init_res.json()["upload_id"]
    client.put(f"/api/uploads/{upload_id}/chunks/0", content=v_bytes)

    comp_res = client.post(f"/api/uploads/{upload_id}/complete")
    assert comp_res.status_code == 400
    assert comp_res.json()["error"]["code"] == "NO_AUDIO_TRACK"


def test_create_and_query_job(client: TestClient, short_video: Path):
    v_bytes = short_video.read_bytes()
    init_res = client.post("/api/uploads", json={"filename": "match.mp4", "size": len(v_bytes)})
    upload_id = init_res.json()["upload_id"]
    client.put(f"/api/uploads/{upload_id}/chunks/0", content=v_bytes)
    client.post(f"/api/uploads/{upload_id}/complete")

    # Create job
    create_res = client.post("/api/jobs", json={
        "source": {"type": "upload", "upload_id": upload_id},
        "title": "Arsenal vs Chelsea",
        "config": {"min_rise_db": 5.0, "target_duration": 300.0}
    })
    assert create_res.status_code == 201
    job_id = create_res.json()["job_id"]
    assert create_res.json()["title"] == "Arsenal vs Chelsea"

    # Get job
    job_res = client.get(f"/api/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["id"] == job_id
    assert job_res.json()["config"]["min_rise_db"] == 5.0

    # List jobs
    list_res = client.get("/api/jobs")
    assert list_res.status_code == 200
    ids = [j["id"] for j in list_res.json()["jobs"]]
    assert job_id in ids


def test_path_traversal_and_whitelist_rejection(client: TestClient, tmp_path: Path):
    # Setup dummy job
    job_id = "test-job-sec"
    db.create_job(job_id, "Sec Test", "upload", "test.mp4", {})

    # Traversal attempts
    assert client.get(f"/api/jobs/{job_id}/media/../passwords.txt").status_code in (404, 400)
    assert client.get(f"/api/jobs/{job_id}/media/..%2f..%2fetc%2fpasswd").status_code in (404, 400)
    assert client.get(f"/api/jobs/{job_id}/media/%2e%2e/data").status_code in (404, 400)

    # Disallowed non-whitelisted file
    assert client.get(f"/api/jobs/{job_id}/media/source.mp4").status_code in (404, 400)
    assert client.get(f"/api/jobs/{job_id}/media/audio.wav").status_code in (404, 400)
    assert client.get(f"/api/jobs/{job_id}/media/random.txt").status_code in (404, 400)


def test_custom_render_validation_rejects_overlaps_and_short_clips(client: TestClient):
    job_id = "test-job-renders"
    db.create_job(job_id, "Render Test", "upload", "test.mp4", {})

    # 1. Overlapping windows
    res_overlap = client.post(f"/api/jobs/{job_id}/renders", json={
        "windows": [
            {"start": 10.0, "end": 20.0},
            {"start": 18.0, "end": 25.0},  # Overlap!
        ]
    })
    assert res_overlap.status_code == 422

    # 2. Clip duration shorter than 2.0s
    res_short = client.post(f"/api/jobs/{job_id}/renders", json={
        "windows": [
            {"start": 10.0, "end": 11.0},  # Only 1.0s long!
        ]
    })
    assert res_short.status_code == 422


def test_ssrf_prevention_on_url_import(client: TestClient):
    # Attempt import from localhost or private IP
    res_local = client.post("/api/jobs", json={
        "source": {"type": "url", "url": "http://127.0.0.1:8080/internal.mp4"}
    })
    assert res_local.status_code == 400
    assert res_local.json()["error"]["code"] == "INVALID_URL"

    res_priv = client.post("/api/jobs", json={
        "source": {"type": "url", "url": "http://192.168.1.10/match.mp4"}
    })
    assert res_priv.status_code == 400
    assert res_priv.json()["error"]["code"] == "INVALID_URL"
