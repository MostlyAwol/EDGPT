"""Rebuildable, on-demand session cache shared by HTTP and MCP."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import history_store as history
from session_summary import (SESSION_SCHEMA_VERSION, apply_event, close_session,
                             new_session, render_session, timestamp, utc_time)

SESSION_DB_PATH = Path(os.environ.get("EDGPT_DATA_DIR", "data")).expanduser() / "edgpt_sessions.db"
MAX_SESSIONS = 100


@contextmanager
def _connect():
    SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSION_DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        with conn:
            yield conn
    finally:
        conn.close()


def _save(conn, model):
    conn.execute(
        "INSERT INTO sessions(session_id,start,model_json) VALUES(?,?,?) "
        "ON CONFLICT(session_id) DO UPDATE SET start=excluded.start,model_json=excluded.model_json",
        (model["session_id"], model["start"], json.dumps(model, separators=(",", ":"))),
    )


def sync_sessions():
    history.sync_journals()
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                start TEXT,
                model_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start);
            CREATE TABLE IF NOT EXISTS session_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        # Serialize HTTP/MCP processes before reading either watermark or history.
        conn.execute("BEGIN IMMEDIATE")
        meta = {row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM session_meta")}
        cursor = meta.get("history_event_id", 0)
        if meta.get("schema_version") != SESSION_SCHEMA_VERSION:
            cursor = 0
        with history.session_event_stream(cursor, meta.get("history_generation", ""), meta.get("last_source")) as (generation, high, rebuild, rows):
            if rebuild or meta.get("schema_version") != SESSION_SCHEMA_VERSION:
                conn.execute("DELETE FROM sessions")
                conn.execute("DELETE FROM session_meta")
                meta = {}
            current = None
            if meta.get("open_session_id"):
                row = conn.execute("SELECT model_json FROM sessions WHERE session_id=?", (meta["open_session_id"],)).fetchone()
                if row:
                    current = json.loads(row[0])
            for row in rows:
                event = json.loads(row["raw_json"])
                source = [row["journal_file"], row["line_no"]]
                kind = event.get("event")
                # A fresh file part 1 can reveal a crash even before LoadGame arrives.
                if kind in ("FileHeader", "fileheader") and event.get("part") == 1:
                    meta.pop("pending_commander", None)
                    if current is not None:
                        close_session(current, "new_journal")
                        _save(conn, current)
                        current = None
                if kind == "LoadGame" and current is not None:
                    close_session(current, "new_load_game")
                    _save(conn, current)
                    current = None
                # Headers and Commander precede LoadGame, not independent sessions.
                if current is None and kind in ("FileHeader", "fileheader", "Commander", "Continued"):
                    if kind == "Commander":
                        meta["pending_commander"] = {"commander": event.get("Name"), "profile_id": event.get("FID")}
                    meta["last_source"] = source
                    continue
                if current is None:
                    current = new_session(event, source)
                    current.update(meta.pop("pending_commander", {}))
                    current["history_generation"] = generation
                apply_event(current, event, row["id"])
                if kind == "Shutdown":
                    close_session(current, "shutdown")
                    _save(conn, current)
                    current = None
                meta["last_source"] = source
            if current is not None:
                _save(conn, current)
            meta.update(schema_version=SESSION_SCHEMA_VERSION, history_event_id=high,
                        history_generation=generation,
                        open_session_id=current["session_id"] if current else None)
            conn.execute("DELETE FROM session_meta")
            for key, value in meta.items():
                conn.execute("INSERT INTO session_meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (key, json.dumps(value)))


def get_current_session_summary():
    """Latest session, including a completed session after shutdown; empty if none."""
    sync_sessions()
    with _connect() as conn:
        row = conn.execute("SELECT model_json FROM sessions ORDER BY sequence DESC LIMIT 1").fetchone()
    return render_session(json.loads(row[0])) if row else {}


def get_game_session(session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("id must be a nonempty session ID.")
    sync_sessions()
    with _connect() as conn:
        row = conn.execute("SELECT model_json FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    return render_session(json.loads(row[0])) if row else {}


def list_game_sessions(limit=20, before=0, start_time="", end_time=""):
    """Newest first; inclusive UTC filters on session start, exclusive sequence cursor."""
    try:
        limit, before = int(limit), int(before)
    except (ValueError, TypeError):
        raise ValueError("limit and before must be integers.") from None
    if not 1 <= limit <= MAX_SESSIONS or before < 0:
        raise ValueError("limit must be 1 to 100 and before must be nonnegative.")
    filters, params = [], []
    for name, value, op in (("start_time", start_time, ">="), ("end_time", end_time, "<=")):
        if value:
            normalized = timestamp(value)
            if normalized is None:
                raise ValueError(f"{name} must be an ISO 8601 timestamp with a timezone.")
            filters.append(f"start {op} ?")
            params.append(normalized)
    if start_time and end_time and utc_time(start_time) > utc_time(end_time):
        raise ValueError("start_time must not be after end_time.")
    if before:
        filters.append("sequence < ?")
        params.append(before)
    sync_sessions()
    where = " WHERE " + " AND ".join(filters) if filters else ""
    with _connect() as conn:
        rows = conn.execute("SELECT sequence,model_json FROM sessions" + where + " ORDER BY sequence DESC LIMIT ?",
                            [*params, limit + 1]).fetchall()
    return {"items": [render_session(json.loads(row["model_json"])) for row in rows[:limit]],
            "count": min(len(rows), limit),
            "next_before": rows[limit - 1]["sequence"] if len(rows) > limit else None}
