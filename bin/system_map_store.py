import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from history_store import (
    get_system_map_event_batch,
    history_max_event_id,
    history_generation,
)
from system_map import (
    MAP_SCHEMA_VERSION,
    apply_event,
    map_metadata,
    new_system_map,
    render_full_map,
    render_simple_map,
)


DATA_DIR = Path(os.environ.get("EDGPT_DATA_DIR", "data")).expanduser()
MAP_DB_PATH = DATA_DIR / "edgpt_system_maps.db"

_LOCK = threading.RLock()


@contextmanager
def _connect():
    MAP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(MAP_DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
    finally:
        conn.close()


def init_db():
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_maps (
                system_address INTEGER PRIMARY KEY,
                system_name TEXT NOT NULL,
                first_seen TEXT,
                last_updated TEXT,
                body_count INTEGER,
                known_complete INTEGER NOT NULL DEFAULT 0,
                visits INTEGER NOT NULL DEFAULT 0,
                map_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_system_maps_name
                ON system_maps(system_name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_system_maps_updated
                ON system_maps(last_updated);
            CREATE TABLE IF NOT EXISTS map_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()


def _meta(conn, key, default=""):
    row = conn.execute("SELECT value FROM map_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO map_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _load_model(conn, system_address, system_name=""):
    row = conn.execute(
        "SELECT map_json FROM system_maps WHERE system_address=?", (int(system_address),)
    ).fetchone()
    if row:
        try:
            return json.loads(row["map_json"])
        except Exception:
            pass
    return new_system_map(system_address, system_name)


def _save_model(conn, model):
    metadata = map_metadata(model)
    conn.execute(
        """
        INSERT INTO system_maps(
            system_address,system_name,first_seen,last_updated,body_count,
            known_complete,visits,map_json
        ) VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(system_address) DO UPDATE SET
            system_name=excluded.system_name,
            first_seen=excluded.first_seen,
            last_updated=excluded.last_updated,
            body_count=excluded.body_count,
            known_complete=excluded.known_complete,
            visits=excluded.visits,
            map_json=excluded.map_json
        """,
        (
            metadata["system_address"],
            metadata["system_name"],
            metadata["first_seen"],
            metadata["last_updated"],
            metadata["body_count"],
            int(metadata["known_complete"]),
            metadata["visits"],
            json.dumps(model, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def sync_system_maps(*, sync_history=True):
    """Backfill and incrementally update saved maps from indexed journals."""
    init_db()
    high_watermark = history_max_event_id(sync=sync_history)
    generation = history_generation()
    processed = 0

    with _LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        stored_version = int(_meta(conn, "schema_version", "0") or 0)
        cursor = int(_meta(conn, "history_event_id", "0") or 0)
        if (stored_version != MAP_SCHEMA_VERSION or cursor > high_watermark
                or _meta(conn, "history_generation") != generation):
            conn.execute("DELETE FROM system_maps")
            conn.execute("DELETE FROM map_meta")
            cursor = 0
            _set_meta(conn, "schema_version", MAP_SCHEMA_VERSION)
            _set_meta(conn, "history_event_id", 0)

        while cursor < high_watermark:
            batch = get_system_map_event_batch(cursor, high_watermark, 2000)
            if not batch:
                cursor = high_watermark
                break

            models = {}
            for item in batch:
                event = item["data"]
                try:
                    address = int(event.get("SystemAddress"))
                except (TypeError, ValueError):
                    cursor = max(cursor, int(item["id"]))
                    continue
                if address not in models:
                    name = event.get("SystemName") or event.get("StarSystem") or ""
                    models[address] = _load_model(conn, address, name)
                apply_event(models[address], event, item["id"])
                if event.get("event") == "FSDJump":
                    _set_meta(conn, "current_system_address", address)
                cursor = max(cursor, int(item["id"]))
                processed += 1

            for model in models.values():
                _save_model(conn, model)
            _set_meta(conn, "history_event_id", cursor)

        _set_meta(conn, "history_generation", generation)
        _set_meta(conn, "history_event_id", high_watermark)
        _set_meta(conn, "schema_version", MAP_SCHEMA_VERSION)
        conn.commit()
    return processed


def _result(model, include_full=False, *, include_model=False):
    if not model:
        return None
    result = map_metadata(model)
    result["simple_text"] = render_simple_map(model)
    if include_full:
        result["full_text"] = render_full_map(model)
    if include_model:
        result["model"] = model
    return result


def get_system_map(identifier, include_full=False, *, include_model=False):
    sync_system_maps()
    with _connect() as conn:
        row = None
        try:
            address = int(str(identifier).strip())
            row = conn.execute(
                "SELECT map_json FROM system_maps WHERE system_address=?", (address,)
            ).fetchone()
        except (TypeError, ValueError):
            name = str(identifier or "").strip()
            if name:
                row = conn.execute(
                    "SELECT map_json FROM system_maps WHERE system_name=? COLLATE NOCASE "
                    "ORDER BY last_updated DESC LIMIT 1",
                    (name,),
                ).fetchone()
        if not row:
            return None
        try:
            model = json.loads(row["map_json"])
        except Exception:
            return None
    return _result(model, include_full, include_model=include_model)


def get_current_system_map(include_full=False, *, sync_history=True, include_model=False):
    sync_system_maps(sync_history=sync_history)
    with _connect() as conn:
        address = _meta(conn, "current_system_address", "")
        if not address:
            return None
        row = conn.execute(
            "SELECT map_json FROM system_maps WHERE system_address=?", (int(address),)
        ).fetchone()
        if not row:
            return None
        try:
            model = json.loads(row["map_json"])
        except Exception:
            return None
    return _result(model, include_full, include_model=include_model)


def list_system_maps(query="", limit=100):
    sync_system_maps()
    limit = max(1, min(int(limit), 1000))
    query = str(query or "").strip()
    with _connect() as conn:
        if query:
            rows = conn.execute(
                "SELECT system_address,system_name,first_seen,last_updated,body_count,"
                "known_complete,visits FROM system_maps "
                "WHERE system_name LIKE ? COLLATE NOCASE "
                "ORDER BY last_updated DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT system_address,system_name,first_seen,last_updated,body_count,"
                "known_complete,visits FROM system_maps "
                "ORDER BY last_updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [
        {
            "system_address": row["system_address"],
            "system_name": row["system_name"],
            "first_seen": row["first_seen"],
            "last_updated": row["last_updated"],
            "body_count": row["body_count"],
            "known_complete": bool(row["known_complete"]),
            "visits": row["visits"],
        }
        for row in rows
    ]
