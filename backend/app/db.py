from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stages import V1_STAGES

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key in ("metadata_json", "content_json"):
        if key in payload and payload[key]:
            payload[key] = json.loads(payload[key])
    return payload


def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
                research_model TEXT NOT NULL DEFAULT 'gpt-5.4',
                code_model TEXT NOT NULL DEFAULT 'gpt-5.4',
                embedding_model TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                idea TEXT NOT NULL,
                background TEXT NOT NULL,
                direction TEXT NOT NULL,
                goals TEXT NOT NULL,
                constraints_text TEXT NOT NULL,
                compute_budget TEXT NOT NULL,
                api_budget TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                file_name TEXT NOT NULL DEFAULT '',
                stored_path TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS plans (
                project_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                plan_markdown TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                current_stage_index INTEGER NOT NULL DEFAULT 0,
                total_stages INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS run_stages (
                run_id TEXT NOT NULL,
                stage_index INTEGER NOT NULL,
                stage_key TEXT NOT NULL,
                stage_label TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                content_md TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (run_id, stage_index),
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            """
        )
        settings_row = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if settings_row is None:
            conn.execute(
                """
                INSERT INTO settings (
                    id, api_key, base_url, research_model, code_model, embedding_model, notes, updated_at
                ) VALUES (1, '', 'https://api.openai.com/v1', 'gpt-5.4', 'gpt-5.4', '', '', ?)
                """,
                (utc_now(),),
            )
        else:
            current = conn.execute(
                "SELECT research_model, code_model FROM settings WHERE id = 1"
            ).fetchone()
            if current is not None:
                updates: list[str] = []
                params: list[Any] = []
                if current["research_model"] == "gpt-4.1-mini":
                    updates.append("research_model = ?")
                    params.append("gpt-5.4")
                if current["code_model"] == "gpt-4.1-mini":
                    updates.append("code_model = ?")
                    params.append("gpt-5.4")
                if updates:
                    updates.append("updated_at = ?")
                    params.append(utc_now())
                    params.append(1)
                    conn.execute(
                        f"UPDATE settings SET {', '.join(updates)} WHERE id = ?",
                        tuple(params),
                    )
        conn.commit()


def get_settings() -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return _to_dict(row) or {}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE settings
            SET api_key = ?, base_url = ?, research_model = ?, code_model = ?, embedding_model = ?, notes = ?, updated_at = ?
            WHERE id = 1
            """,
            (
                payload["api_key"],
                payload["base_url"],
                payload["research_model"],
                payload["code_model"],
                payload["embedding_model"],
                payload["notes"],
                now,
            ),
        )
        conn.commit()
    return get_settings()


def create_project(payload: dict[str, str]) -> dict[str, Any]:
    project_id = f"proj_{uuid.uuid4().hex[:10]}"
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, title, idea, background, direction, goals, constraints_text,
                compute_budget, api_budget, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                payload["title"],
                payload["idea"],
                payload["background"],
                payload["direction"],
                payload["goals"],
                payload["constraints_text"],
                payload["compute_budget"],
                payload["api_budget"],
                "draft",
                now,
                now,
            ),
        )
        conn.commit()
    return get_project(project_id)


def list_projects() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
    return [_to_dict(row) for row in rows if row is not None]


def get_project(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return _to_dict(row)


def update_project_status(project_id: str, status: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), project_id),
        )
        conn.commit()


def add_paper_source(payload: dict[str, str]) -> dict[str, Any]:
    paper_id = f"paper_{uuid.uuid4().hex[:10]}"
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO papers (
                id, project_id, source_type, title, url, file_name, stored_path, notes, extracted_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                payload["project_id"],
                payload["source_type"],
                payload["title"],
                payload.get("url", ""),
                payload.get("file_name", ""),
                payload.get("stored_path", ""),
                payload.get("notes", ""),
                payload.get("extracted_text", ""),
                now,
            ),
        )
        conn.commit()
    return get_paper(paper_id)


def list_papers(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
    return [_to_dict(row) for row in rows if row is not None]


def get_paper(paper_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _to_dict(row)


def save_plan(project_id: str, plan_markdown: str, status: str) -> dict[str, Any]:
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO plans (project_id, status, plan_markdown, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                status = excluded.status,
                plan_markdown = excluded.plan_markdown,
                updated_at = excluded.updated_at
            """,
            (project_id, status, plan_markdown, now, now),
        )
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("plan_ready" if status == "ready" else status, now, project_id),
        )
        conn.commit()
    return get_plan(project_id)


def approve_plan(project_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE plans SET status = ?, updated_at = ? WHERE project_id = ?",
            ("approved", utc_now(), project_id),
        )
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("approved", utc_now(), project_id),
        )
        conn.commit()
    return get_plan(project_id)


def get_plan(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM plans WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return _to_dict(row)


def create_run(project_id: str) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO runs (
                id, project_id, status, current_stage_index, total_stages, started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, project_id, "queued", 0, len(V1_STAGES), now, now),
        )
        for stage in V1_STAGES:
            conn.execute(
                """
                INSERT INTO run_stages (
                    run_id, stage_index, stage_key, stage_label, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, stage.index, stage.key, stage.label, "pending"),
            )
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("running", now, project_id),
        )
        conn.commit()
    return get_run(run_id)


def get_latest_run(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return _to_dict(row)


def get_run(run_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _to_dict(row)


def list_run_stages(run_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, stage_index, stage_key, stage_label, status, notes, content_md, started_at, completed_at
            FROM run_stages WHERE run_id = ? ORDER BY stage_index ASC
            """,
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_run_status(run_id: str, status: str, current_stage_index: int, error: str = "") -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?, current_stage_index = ?, updated_at = ?, error = ?,
                finished_at = CASE WHEN ? IN ('completed', 'failed') THEN ? ELSE finished_at END
            WHERE id = ?
            """,
            (status, current_stage_index, utc_now(), error, status, utc_now(), run_id),
        )
        conn.commit()


def set_project_run_complete(project_id: str, status: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), project_id),
        )
        conn.commit()


def update_stage(
    run_id: str,
    stage_index: int,
    *,
    status: str,
    notes: str = "",
    content_md: str | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    fields = ["status = ?", "notes = ?"]
    values: list[Any] = [status, notes]
    if content_md is not None:
        fields.append("content_md = ?")
        values.append(content_md)
    if started:
        fields.append("started_at = ?")
        values.append(utc_now())
    if completed:
        fields.append("completed_at = ?")
        values.append(utc_now())
    values.extend([run_id, stage_index])

    with _LOCK, _connect() as conn:
        conn.execute(
            f"UPDATE run_stages SET {', '.join(fields)} WHERE run_id = ? AND stage_index = ?",
            tuple(values),
        )
        conn.commit()
