from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .stages import PIPELINE_STAGES, rollback_target_index, stage_catalog

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SANDBOX_DIR = DATA_DIR / "sandboxes"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "app.db"

_LOCK = threading.Lock()
_JSON_DEFAULTS: dict[str, Any] = {
    "authors_json": [],
    "metadata_json": {},
    "contract_json": {},
    "artifact_schema_json": [],
    "artifact_json": {},
    "content_json": {},
    "embedding_json": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _decode_json_value(key: str, value: Any) -> Any:
    if key not in _JSON_DEFAULTS:
        return value
    if value in (None, ""):
        default = _JSON_DEFAULTS[key]
        return default.copy() if isinstance(default, (dict, list)) else default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        default = _JSON_DEFAULTS[key]
        return default.copy() if isinstance(default, (dict, list)) else default


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key in list(payload.keys()):
        payload[key] = _decode_json_value(key, payload[key])
    return payload


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _media_url(path: str | None) -> str:
    if not path:
        return ""
    try:
        relative = Path(path).resolve().relative_to(DATA_DIR.resolve())
    except (OSError, ValueError):
        return ""
    return f"/media/{quote(relative.as_posix(), safe='/')}"


def media_url_for_path(path: str | None) -> str:
    return _media_url(path)


def _paper_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    payload = _to_dict(row)
    if payload is None:
        return None
    payload["stored_file_url"] = _media_url(payload.get("stored_path"))
    payload["preview_image_url"] = _media_url(payload.get("preview_image_path"))
    payload["preview_thumbnail_url"] = _media_url(payload.get("preview_thumbnail_path"))
    payload["chunk_count"] = int(payload.get("chunk_count") or 0)
    payload["retrieval_ready"] = payload["chunk_count"] > 0
    return payload


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_schema(conn: sqlite3.Connection) -> None:
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
            abstract TEXT NOT NULL DEFAULT '',
            doi TEXT NOT NULL DEFAULT '',
            venue TEXT NOT NULL DEFAULT '',
            year INTEGER NOT NULL DEFAULT 0,
            authors_json TEXT NOT NULL DEFAULT '[]',
            source_provider TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '',
            canonical_key TEXT NOT NULL DEFAULT '',
            citation_key TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            extracted_text TEXT NOT NULL DEFAULT '',
            preview_image_path TEXT NOT NULL DEFAULT '',
            preview_thumbnail_path TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS paper_chunks (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_estimate INTEGER NOT NULL DEFAULT 0,
            embedding_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE (paper_id, chunk_index),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paper_chunks_project ON paper_chunks(project_id);
        CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper ON paper_chunks(paper_id);

        CREATE TABLE IF NOT EXISTS plans (
            project_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            plan_markdown TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
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
            pending_gate_index INTEGER NOT NULL DEFAULT 0,
            pending_gate_key TEXT NOT NULL DEFAULT '',
            pending_gate_state TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
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
            contract_json TEXT NOT NULL DEFAULT '{}',
            artifact_schema_json TEXT NOT NULL DEFAULT '[]',
            artifact_json TEXT NOT NULL DEFAULT '{}',
            gate_status TEXT NOT NULL DEFAULT '',
            approval_required INTEGER NOT NULL DEFAULT 0,
            approval_label TEXT NOT NULL DEFAULT '',
            rollback_target_index INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, stage_index),
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """
    )

    for name, definition in (
        ("abstract", "TEXT NOT NULL DEFAULT ''"),
        ("doi", "TEXT NOT NULL DEFAULT ''"),
        ("venue", "TEXT NOT NULL DEFAULT ''"),
        ("year", "INTEGER NOT NULL DEFAULT 0"),
        ("authors_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("source_provider", "TEXT NOT NULL DEFAULT ''"),
        ("external_id", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_key", "TEXT NOT NULL DEFAULT ''"),
        ("citation_key", "TEXT NOT NULL DEFAULT ''"),
        ("content_hash", "TEXT NOT NULL DEFAULT ''"),
        ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("preview_image_path", "TEXT NOT NULL DEFAULT ''"),
        ("preview_thumbnail_path", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
    ):
        _ensure_column(conn, "papers", name, definition)

    _ensure_column(conn, "plans", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")

    for name, definition in (
        ("pending_gate_index", "INTEGER NOT NULL DEFAULT 0"),
        ("pending_gate_key", "TEXT NOT NULL DEFAULT ''"),
        ("pending_gate_state", "TEXT NOT NULL DEFAULT ''"),
        ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        _ensure_column(conn, "runs", name, definition)

    for name, definition in (
        ("contract_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("artifact_schema_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("artifact_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("gate_status", "TEXT NOT NULL DEFAULT ''"),
        ("approval_required", "INTEGER NOT NULL DEFAULT 0"),
        ("approval_label", "TEXT NOT NULL DEFAULT ''"),
        ("rollback_target_index", "INTEGER NOT NULL DEFAULT 0"),
        ("error", "TEXT NOT NULL DEFAULT ''"),
        ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        _ensure_column(conn, "run_stages", name, definition)


def _seed_settings(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO settings (
                id, api_key, base_url, research_model, code_model, embedding_model, notes, updated_at
            ) VALUES (1, '', 'https://api.openai.com/v1', 'gpt-5.4', 'gpt-5.4', '', '', ?)
            """,
            (utc_now(),),
        )
        return

    current = conn.execute("SELECT research_model, code_model FROM settings WHERE id = 1").fetchone()
    if current is None:
        return
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
        conn.execute(f"UPDATE settings SET {', '.join(updates)} WHERE id = ?", tuple(params))


def init_db() -> None:
    with _LOCK, _connect() as conn:
        _ensure_schema(conn)
        _seed_settings(conn)
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
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [_to_dict(row) for row in rows if row is not None]


def get_project(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _to_dict(row)


def update_project_status(project_id: str, status: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), project_id),
        )
        conn.commit()


def add_paper_source(payload: dict[str, Any]) -> dict[str, Any]:
    paper_id = f"paper_{uuid.uuid4().hex[:10]}"
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO papers (
                id, project_id, source_type, title, url, file_name, stored_path, notes, abstract,
                doi, venue, year, authors_json, source_provider, external_id, canonical_key, citation_key,
                content_hash, extracted_text, preview_image_path, preview_thumbnail_path, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload.get("abstract", ""),
                payload.get("doi", ""),
                payload.get("venue", ""),
                int(payload.get("year") or 0),
                _json_dump(payload.get("authors_json", [])),
                payload.get("source_provider", ""),
                payload.get("external_id", ""),
                payload.get("canonical_key", ""),
                payload.get("citation_key", ""),
                payload.get("content_hash", ""),
                payload.get("extracted_text", ""),
                payload.get("preview_image_path", ""),
                payload.get("preview_thumbnail_path", ""),
                _json_dump(payload.get("metadata_json", {})),
                now,
                payload.get("updated_at", now),
            ),
        )
        conn.commit()
    return get_paper(paper_id)


def update_paper_source(paper_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE papers
            SET source_type = ?,
                title = ?,
                url = ?,
                file_name = ?,
                stored_path = ?,
                notes = ?,
                abstract = ?,
                doi = ?,
                venue = ?,
                year = ?,
                authors_json = ?,
                source_provider = ?,
                external_id = ?,
                canonical_key = ?,
                citation_key = ?,
                content_hash = ?,
                extracted_text = ?,
                preview_image_path = ?,
                preview_thumbnail_path = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payload["source_type"],
                payload["title"],
                payload.get("url", ""),
                payload.get("file_name", ""),
                payload.get("stored_path", ""),
                payload.get("notes", ""),
                payload.get("abstract", ""),
                payload.get("doi", ""),
                payload.get("venue", ""),
                int(payload.get("year") or 0),
                _json_dump(payload.get("authors_json", [])),
                payload.get("source_provider", ""),
                payload.get("external_id", ""),
                payload.get("canonical_key", ""),
                payload.get("citation_key", ""),
                payload.get("content_hash", ""),
                payload.get("extracted_text", ""),
                payload.get("preview_image_path", ""),
                payload.get("preview_thumbnail_path", ""),
                _json_dump(payload.get("metadata_json", {})),
                payload.get("updated_at", now),
                paper_id,
            ),
        )
        conn.commit()
    return get_paper(paper_id)


def list_papers(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT papers.*,
                   COALESCE(chunk_stats.chunk_count, 0) AS chunk_count
            FROM papers
            LEFT JOIN (
                SELECT paper_id, COUNT(*) AS chunk_count
                FROM paper_chunks
                GROUP BY paper_id
            ) AS chunk_stats
                ON chunk_stats.paper_id = papers.id
            WHERE papers.project_id = ?
            ORDER BY papers.created_at ASC
            """,
            (project_id,),
        ).fetchall()
    return [_paper_to_dict(row) for row in rows if row is not None]


def get_paper(paper_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT papers.*,
                   COALESCE(chunk_stats.chunk_count, 0) AS chunk_count
            FROM papers
            LEFT JOIN (
                SELECT paper_id, COUNT(*) AS chunk_count
                FROM paper_chunks
                GROUP BY paper_id
            ) AS chunk_stats
                ON chunk_stats.paper_id = papers.id
            WHERE papers.id = ?
            """,
            (paper_id,),
        ).fetchone()
    return _paper_to_dict(row)


def find_duplicate_paper(
    project_id: str,
    *,
    doi: str = "",
    canonical_key: str = "",
    external_id: str = "",
    source_provider: str = "",
    content_hash: str = "",
) -> dict[str, Any] | None:
    checks = [
        ("SELECT id FROM papers WHERE project_id = ? AND doi = ? AND doi != '' LIMIT 1", (project_id, doi.strip())),
        (
            "SELECT id FROM papers WHERE project_id = ? AND content_hash = ? AND content_hash != '' LIMIT 1",
            (project_id, content_hash.strip()),
        ),
        (
            """
            SELECT id FROM papers
            WHERE project_id = ? AND external_id = ? AND external_id != '' AND source_provider = ?
            LIMIT 1
            """,
            (project_id, external_id.strip(), source_provider.strip()),
        ),
        (
            "SELECT id FROM papers WHERE project_id = ? AND canonical_key = ? AND canonical_key != '' LIMIT 1",
            (project_id, canonical_key.strip()),
        ),
    ]
    with _connect() as conn:
        for query, params in checks:
            if not any(params[1:]):
                continue
            row = conn.execute(query, params).fetchone()
            if row is not None:
                return get_paper(row["id"])
    return None


def paper_exists_with_citation_key(project_id: str, citation_key: str, exclude_paper_id: str = "") -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM papers
            WHERE project_id = ? AND citation_key = ? AND id != ?
            LIMIT 1
            """,
            (project_id, citation_key, exclude_paper_id),
        ).fetchone()
    return row is not None


def replace_paper_chunks(paper_id: str, project_id: str, chunks: list[dict[str, Any]]) -> None:
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (paper_id,))
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO paper_chunks (
                    id, paper_id, project_id, chunk_index, content, token_estimate,
                    embedding_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.get("id") or f"chunk_{uuid.uuid4().hex[:12]}",
                    paper_id,
                    project_id,
                    int(chunk.get("chunk_index") or 0),
                    chunk.get("content") or "",
                    int(chunk.get("token_estimate") or 0),
                    _json_dump(chunk.get("embedding_json", [])),
                    _json_dump(chunk.get("metadata_json", {})),
                    chunk.get("created_at") or now,
                ),
            )
        conn.commit()


def list_project_paper_chunks(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                paper_chunks.*,
                papers.title AS paper_title,
                papers.source_type AS paper_source_type,
                papers.source_provider AS paper_source_provider,
                papers.citation_key AS paper_citation_key,
                papers.doi AS paper_doi,
                papers.venue AS paper_venue,
                papers.year AS paper_year,
                papers.url AS paper_url,
                papers.preview_thumbnail_path AS paper_preview_thumbnail_path
            FROM paper_chunks
            INNER JOIN papers ON papers.id = paper_chunks.paper_id
            WHERE paper_chunks.project_id = ?
            ORDER BY paper_chunks.paper_id ASC, paper_chunks.chunk_index ASC
            """,
            (project_id,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = _to_dict(row)
        if payload is None:
            continue
        payload["paper_preview_thumbnail_url"] = _media_url(payload.get("paper_preview_thumbnail_path"))
        items.append(payload)
    return items


def list_paper_chunks(paper_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_chunks WHERE paper_id = ? ORDER BY chunk_index ASC",
            (paper_id,),
        ).fetchall()
    return [_to_dict(row) for row in rows if row is not None]


def update_chunk_embeddings(chunks: list[dict[str, Any]]) -> None:
    if not chunks:
        return
    with _LOCK, _connect() as conn:
        for chunk in chunks:
            conn.execute(
                "UPDATE paper_chunks SET embedding_json = ?, metadata_json = ? WHERE id = ?",
                (
                    _json_dump(chunk.get("embedding_json", [])),
                    _json_dump(chunk.get("metadata_json", {})),
                    chunk["id"],
                ),
            )
        conn.commit()


def save_plan(
    project_id: str,
    plan_markdown: str,
    status: str,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    metadata = metadata_json or {}
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO plans (project_id, status, plan_markdown, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                status = excluded.status,
                plan_markdown = excluded.plan_markdown,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (project_id, status, plan_markdown, _json_dump(metadata), now, now),
        )
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("plan_ready" if status == "ready" else status, now, project_id),
        )
        conn.commit()
    return get_plan(project_id)


def approve_plan(project_id: str) -> dict[str, Any] | None:
    now = utc_now()
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE plans SET status = ?, updated_at = ? WHERE project_id = ?",
            ("approved", now, project_id),
        )
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("approved", now, project_id),
        )
        conn.commit()
    return get_plan(project_id)


def get_plan(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM plans WHERE project_id = ?", (project_id,)).fetchone()
    return _to_dict(row)


def _catalog_for_run() -> list[dict[str, Any]]:
    return stage_catalog()


def create_run(project_id: str) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    catalog = _catalog_for_run()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO runs (
                id, project_id, status, current_stage_index, total_stages, pending_gate_index, pending_gate_key,
                pending_gate_state, started_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                "queued",
                0,
                len(catalog),
                0,
                "",
                "",
                now,
                now,
                _json_dump({"events": []}),
            ),
        )
        for stage in PIPELINE_STAGES:
            conn.execute(
                """
                INSERT INTO run_stages (
                    run_id, stage_index, stage_key, stage_label, status, contract_json, artifact_schema_json,
                    approval_required, approval_label, rollback_target_index, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stage.index,
                    stage.key,
                    stage.label,
                    "pending",
                    _json_dump(_catalog_for_run()[stage.index - 1]["contract"]),
                    _json_dump(_catalog_for_run()[stage.index - 1]["artifact_schema"]),
                    1 if stage.approval_gate else 0,
                    stage.approval_gate.label if stage.approval_gate else "",
                    rollback_target_index(stage) or 0,
                    _json_dump({"prompt_focus": stage.prompt_focus}),
                ),
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


def get_run_stage(run_id: str, stage_index: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM run_stages WHERE run_id = ? AND stage_index = ?",
            (run_id, stage_index),
        ).fetchone()
    return _to_dict(row)


def list_run_stages(run_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM run_stages WHERE run_id = ? ORDER BY stage_index ASC",
            (run_id,),
        ).fetchall()
    return [_to_dict(row) for row in rows if row is not None]


def update_run(
    run_id: str,
    *,
    status: str | None = None,
    current_stage_index: int | None = None,
    pending_gate_index: int | None = None,
    pending_gate_key: str | None = None,
    pending_gate_state: str | None = None,
    error: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    finished: bool | None = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [utc_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if current_stage_index is not None:
        fields.append("current_stage_index = ?")
        values.append(current_stage_index)
    if pending_gate_index is not None:
        fields.append("pending_gate_index = ?")
        values.append(pending_gate_index)
    if pending_gate_key is not None:
        fields.append("pending_gate_key = ?")
        values.append(pending_gate_key)
    if pending_gate_state is not None:
        fields.append("pending_gate_state = ?")
        values.append(pending_gate_state)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if metadata_json is not None:
        fields.append("metadata_json = ?")
        values.append(_json_dump(metadata_json))
    if finished is True:
        fields.append("finished_at = ?")
        values.append(utc_now())
    elif finished is False:
        fields.append("finished_at = ?")
        values.append("")
    values.append(run_id)
    with _LOCK, _connect() as conn:
        conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()


def update_run_status(run_id: str, status: str, current_stage_index: int, error: str = "") -> None:
    update_run(
        run_id,
        status=status,
        current_stage_index=current_stage_index,
        error=error,
        finished=status in {"completed", "failed"},
    )


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
    status: str | None = None,
    notes: str | None = None,
    content_md: str | None = None,
    contract_json: dict[str, Any] | None = None,
    artifact_schema_json: list[dict[str, Any]] | None = None,
    artifact_json: dict[str, Any] | None = None,
    gate_status: str | None = None,
    error: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    started: bool = False,
    completed: bool = False,
    reset_timestamps: bool = False,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)
    if content_md is not None:
        fields.append("content_md = ?")
        values.append(content_md)
    if contract_json is not None:
        fields.append("contract_json = ?")
        values.append(_json_dump(contract_json))
    if artifact_schema_json is not None:
        fields.append("artifact_schema_json = ?")
        values.append(_json_dump(artifact_schema_json))
    if artifact_json is not None:
        fields.append("artifact_json = ?")
        values.append(_json_dump(artifact_json))
    if gate_status is not None:
        fields.append("gate_status = ?")
        values.append(gate_status)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if metadata_json is not None:
        fields.append("metadata_json = ?")
        values.append(_json_dump(metadata_json))
    if started:
        fields.append("started_at = ?")
        values.append(utc_now())
    if completed:
        fields.append("completed_at = ?")
        values.append(utc_now())
    if reset_timestamps:
        fields.append("started_at = ?")
        values.append("")
        fields.append("completed_at = ?")
        values.append("")
    if not fields:
        return
    values.extend([run_id, stage_index])
    with _LOCK, _connect() as conn:
        conn.execute(
            f"UPDATE run_stages SET {', '.join(fields)} WHERE run_id = ? AND stage_index = ?",
            tuple(values),
        )
        conn.commit()


def reset_run_from_stage(run_id: str, from_stage_index: int) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE run_stages
            SET status = 'pending',
                notes = '',
                content_md = '',
                started_at = '',
                completed_at = '',
                artifact_json = '{}',
                gate_status = '',
                error = '',
                metadata_json = '{}'
            WHERE run_id = ? AND stage_index >= ?
            """,
            (run_id, from_stage_index),
        )
        conn.commit()


def append_run_event(run_id: str, event: dict[str, Any]) -> None:
    run = get_run(run_id)
    if run is None:
        return
    metadata = run.get("metadata_json") or {}
    events = metadata.get("events")
    if not isinstance(events, list):
        events = []
    events.append(event)
    metadata["events"] = events[-40:]
    update_run(run_id, metadata_json=metadata)
