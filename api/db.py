"""
Database access module using Python's stdlib sqlite3.
Handles job metadata, state transitions, and render records.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables and reconcile interrupted jobs on startup."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                duration_s REAL DEFAULT 0.0,
                moment_count INTEGER DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                config_json TEXT NOT NULL,
                stage TEXT,
                progress REAL DEFAULT 0.0,
                active_render_id TEXT,
                labels_json TEXT DEFAULT '[]'
            );
        """)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN labels_json TEXT DEFAULT '[]';")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS renders (
                id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_s REAL DEFAULT 0.0,
                clip_count INTEGER DEFAULT 0,
                windows_json TEXT NOT NULL,
                error_message TEXT,
                PRIMARY KEY (job_id, id),
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            );
        """)
        conn.commit()

        # Startup reconciliation: mark any jobs left in running or queued state as 'interrupted'
        active_statuses = ("queued", "importing", "extracting_audio", "detecting", "rendering")
        placeholders = ",".join("?" for _ in active_statuses)
        cursor = conn.execute(f"SELECT id FROM jobs WHERE status IN ({placeholders})", active_statuses)
        interrupted_ids = [row["id"] for row in cursor.fetchall()]
        if interrupted_ids:
            now_iso = datetime.now(timezone.utc).isoformat()
            update_sql = f"UPDATE jobs SET status = 'interrupted', error_code = 'SERVER_RESTARTED', error_message = 'Process was interrupted by server restart', updated_at = ? WHERE id IN ({','.join('?' for _ in interrupted_ids)})"
            conn.execute(update_sql, [now_iso] + interrupted_ids)
            conn.commit()


def create_job(
    job_id: str,
    title: str,
    source_type: str,
    source_filename: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    config_json = json.dumps(config)
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs (
                id, title, status, created_at, updated_at,
                source_type, source_filename, config_json, stage, progress
            ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, 'queued', 0.0)
            """,
            (job_id, title, now_iso, now_iso, source_type, source_filename, config_json)
        )
        conn.commit()

    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Database error: Job record '{job_id}' could not be verified after commit.")
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["config"] = json.loads(d["config_json"])
        d["labels"] = json.loads(d.get("labels_json") or "[]")
        return d


def list_jobs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        jobs = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config_json"])
            d["labels"] = json.loads(d.get("labels_json") or "[]")
            jobs.append(d)
        return jobs


def update_job(
    job_id: str,
    title: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    progress: float | None = None,
    duration_s: float | None = None,
    moment_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    active_render_id: str | None = None,
    config: dict[str, Any] | None = None,
    labels: list[dict[str, Any]] | None = None,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    fields = ["updated_at = ?"]
    params: list[Any] = [now_iso]

    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if stage is not None:
        fields.append("stage = ?")
        params.append(stage)
    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if duration_s is not None:
        fields.append("duration_s = ?")
        params.append(duration_s)
    if moment_count is not None:
        fields.append("moment_count = ?")
        params.append(moment_count)
    if error_code is not None:
        fields.append("error_code = ?")
        params.append(error_code)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)
    if active_render_id is not None:
        fields.append("active_render_id = ?")
        params.append(active_render_id)
    if config is not None:
        fields.append("config_json = ?")
        params.append(json.dumps(config))
    if labels is not None:
        fields.append("labels_json = ?")
        params.append(json.dumps(labels))

    params.append(job_id)
    query = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
    with get_db_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def get_job_labels(job_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT labels_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row or not row["labels_json"]:
            return []
        try:
            return json.loads(row["labels_json"])
        except Exception:
            return []


def update_job_labels(job_id: str, labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    update_job(job_id, labels=labels)
    return get_job_labels(job_id)


def delete_job(job_id: str) -> bool:
    with get_db_connection() as conn:
        conn.execute("DELETE FROM renders WHERE job_id = ?", (job_id,))
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cur.rowcount > 0


def get_queue_position(job_id: str) -> int:
    """Return 1-indexed queue position if queued, or 0 if not queued."""
    with get_db_connection() as conn:
        job = conn.execute("SELECT created_at, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job or job["status"] != "queued":
            return 0
        res = conn.execute(
            "SELECT COUNT(*) as pos FROM jobs WHERE status = 'queued' AND created_at < ?",
            (job["created_at"],)
        ).fetchone()
        return (res["pos"] or 0) + 1


def create_render(
    render_id: str,
    job_id: str,
    windows: list[dict[str, Any]],
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    windows_json = json.dumps(windows)
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO renders (
                id, job_id, created_at, status, clip_count, windows_json
            ) VALUES (?, ?, ?, 'rendering', ?, ?)
            """,
            (render_id, job_id, now_iso, len(windows), windows_json)
        )
        conn.commit()
    return get_render(render_id, job_id)  # type: ignore


def update_render(
    render_id: str,
    status: str | None = None,
    duration_s: float | None = None,
    error_message: str | None = None,
    job_id: str | None = None,
) -> None:
    fields = []
    params: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if duration_s is not None:
        fields.append("duration_s = ?")
        params.append(duration_s)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)

    if not fields:
        return

    params.append(render_id)
    if job_id:
        params.append(job_id)
        query = f"UPDATE renders SET {', '.join(fields)} WHERE id = ? AND job_id = ?"
    else:
        query = f"UPDATE renders SET {', '.join(fields)} WHERE id = ?"

    with get_db_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def get_render(render_id: str, job_id: str | None = None) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        if job_id:
            row = conn.execute("SELECT * FROM renders WHERE id = ? AND job_id = ?", (render_id, job_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM renders WHERE id = ? LIMIT 1", (render_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["windows"] = json.loads(d["windows_json"])
        return d


def list_renders_for_job(job_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM renders WHERE job_id = ? ORDER BY created_at DESC",
            (job_id,)
        ).fetchall()
        renders = []
        for r in rows:
            d = dict(r)
            d["windows"] = json.loads(d["windows_json"])
            renders.append(d)
        return renders
