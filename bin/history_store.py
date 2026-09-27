import glob
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DEFAULT_ELITE_DIR = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
ELITE_DIR = Path(os.environ.get("ELITE_JOURNAL_DIR", str(DEFAULT_ELITE_DIR))).expanduser()
DATA_DIR = Path(os.environ.get("EDGPT_DATA_DIR", "data")).expanduser()
DB_PATH = DATA_DIR / "edgpt_history.db"

SYSTEM_MAP_EVENT_TYPES = (
    "FSDJump",
    "DiscoveryScan",
    "FSSBodySignals",
    "FSSDiscoveryScan",
    "FSSSignalDiscovered",
    "FSSAllBodiesFound",
    "Scan",
    "SAAScanComplete",
    "SAASignalsFound",
    "ScanBaryCentre",
    "NavBeaconScan",
    "CodexEntry",
    "ScanOrganic",
)

HISTORY_SCHEMA_VERSION = 1

_LOCK = threading.RLock()


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with _LOCK, _connect() as conn:
        stored_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if stored_version not in (0, HISTORY_SCHEMA_VERSION):
            raise RuntimeError("Unsupported history schema; use a compatible EDGPT version or rebuild from journals.")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event TEXT,
                journal_file TEXT NOT NULL,
                line_no INTEGER NOT NULL,
                system TEXT,
                system_address INTEGER,
                body TEXT,
                station TEXT,
                ship TEXT,
                raw_json TEXT NOT NULL,
                UNIQUE(journal_file, line_no)
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
            CREATE INDEX IF NOT EXISTS idx_events_system ON events(system);
            CREATE INDEX IF NOT EXISTS idx_events_ship ON events(ship);

            CREATE TABLE IF NOT EXISTS history_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS journal_state (
                journal_file TEXT PRIMARY KEY,
                offset INTEGER NOT NULL DEFAULT 0,
                line_no INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                mtime REAL NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute("INSERT OR IGNORE INTO history_meta(key,value) VALUES('generation',?)", (uuid.uuid4().hex,))
        conn.execute(f"PRAGMA user_version={HISTORY_SCHEMA_VERSION}")


def _extract_fields(e: dict):
    system = e.get("StarSystem") or e.get("SystemName")
    system_address = e.get("SystemAddress")
    body = e.get("Body") or e.get("BodyName")
    station = e.get("StationName")
    ship = e.get("Ship") or e.get("ShipType")
    return system, system_address, body, station, ship


def sync_journals():
    """Index every Journal.*.log file and append only newly written lines."""
    init_db()
    files = sorted(glob.glob(str(ELITE_DIR / "Journal.*.log")))
    inserted = 0

    with _LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for filename in files:
            path = Path(filename)
            try:
                stat = path.stat()
            except OSError:
                continue

            row = conn.execute(
                "SELECT offset, line_no, size, mtime FROM journal_state WHERE journal_file=?",
                (path.name,),
            ).fetchone()

            offset = int(row["offset"]) if row else 0
            line_no = int(row["line_no"]) if row else 0
            old_size = int(row["size"]) if row else 0

            replaced = row and stat.st_size == old_size and stat.st_mtime != row["mtime"]
            if stat.st_size < old_size or offset > stat.st_size or replaced:
                conn.execute("DELETE FROM events WHERE journal_file=?", (path.name,))
                conn.execute("UPDATE history_meta SET value=? WHERE key='generation'", (uuid.uuid4().hex,))
                offset = 0
                line_no = 0

            if stat.st_size == old_size and row and not replaced and offset == stat.st_size:
                continue

            try:
                with path.open("rb") as f:
                    f.seek(offset)
                    while True:
                        line_start = f.tell()
                        raw_line = f.readline()
                        if not raw_line:
                            break
                        if not raw_line.endswith(b"\n"):
                            f.seek(line_start)
                            break
                        line_no += 1
                        try:
                            text = raw_line.decode("utf-8", errors="replace").strip()
                            if not text:
                                continue
                            e = json.loads(text)
                        except Exception:
                            continue

                        if not isinstance(e, dict):
                            continue
                        system, system_address, body, station, ship = _extract_fields(e)
                        cur = conn.execute(
                            """
                            INSERT OR IGNORE INTO events
                            (timestamp,event,journal_file,line_no,system,system_address,body,station,ship,raw_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                e.get("timestamp"),
                                e.get("event"),
                                path.name,
                                line_no,
                                system,
                                system_address,
                                body,
                                station,
                                ship,
                                json.dumps(e, ensure_ascii=False, separators=(",", ":")),
                            ),
                        )
                        if cur.rowcount:
                            inserted += 1

                    new_offset = f.tell()
            except OSError:
                continue

            conn.execute(
                """
                INSERT INTO journal_state(journal_file,offset,line_no,size,mtime)
                VALUES(?,?,?,?,?)
                ON CONFLICT(journal_file) DO UPDATE SET
                    offset=excluded.offset,
                    line_no=excluded.line_no,
                    size=excluded.size,
                    mtime=excluded.mtime
                """,
                (path.name, new_offset, line_no, stat.st_size, stat.st_mtime),
            )
        conn.commit()
    return inserted


def _row_to_event(row):
    try:
        return json.loads(row["raw_json"])
    except Exception:
        return {"event": row["event"], "timestamp": row["timestamp"]}


def recent_events(limit=200, *, sync=True):
    if sync:
        sync_journals()
    limit = max(1, min(int(limit), 5000))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT raw_json,event,timestamp FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_event(r) for r in reversed(rows)]


def latest_event(event_name: str, *, sync=True):
    if sync:
        sync_journals()
    with _connect() as conn:
        row = conn.execute(
            "SELECT raw_json,event,timestamp FROM events WHERE event=? ORDER BY id DESC LIMIT 1",
            (event_name,),
        ).fetchone()
    return _row_to_event(row) if row else None


def search_events(
    query: str = "",
    event: str = "",
    start_time: str = "",
    end_time: str = "",
    limit: int = 200,
    newest_first: bool = True,
):
    """Search raw historical events. `query` searches the serialized event JSON."""
    sync_journals()
    limit = max(1, min(int(limit), 5000))
    clauses = []
    params = []

    if event:
        clauses.append("event = ?")
        params.append(event)
    if start_time:
        clauses.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("timestamp <= ?")
        params.append(end_time)
    if query:
        clauses.append("raw_json LIKE ?")
        params.append(f"%{query}%")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order = "DESC" if newest_first else "ASC"
    sql = f"SELECT raw_json,event,timestamp FROM events{where} ORDER BY id {order} LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_event(r) for r in rows]


def history_summary(*, sync=True):
    if sync:
        sync_journals()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        journals = conn.execute("SELECT COUNT(*) FROM journal_state").fetchone()[0]
        first = conn.execute(
            "SELECT timestamp FROM events WHERE timestamp IS NOT NULL ORDER BY id ASC LIMIT 1"
        ).fetchone()
        last = conn.execute(
            "SELECT timestamp FROM events WHERE timestamp IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        event_rows = conn.execute(
            "SELECT event, COUNT(*) AS c FROM events GROUP BY event ORDER BY c DESC LIMIT 100"
        ).fetchall()
        systems = conn.execute(
            "SELECT COUNT(DISTINCT system) FROM events WHERE system IS NOT NULL AND system != ''"
        ).fetchone()[0]
        ships = conn.execute(
            "SELECT COUNT(DISTINCT ship) FROM events WHERE ship IS NOT NULL AND ship != ''"
        ).fetchone()[0]

    return {
        "database": str(DB_PATH),
        "journal_files_indexed": journals,
        "events_indexed": total,
        "first_event_time": first[0] if first else None,
        "last_event_time": last[0] if last else None,
        "distinct_systems_seen_in_events": systems,
        "distinct_ship_types_seen_in_events": ships,
        "event_counts": {r["event"]: r["c"] for r in event_rows if r["event"]},
    }


def get_event_page(before_id: Optional[int] = None, limit: int = 500):
    """Page through every raw journal event without losing data."""
    sync_journals()
    limit = max(1, min(int(limit), 5000))
    with _connect() as conn:
        if before_id is None:
            rows = conn.execute(
                "SELECT id, raw_json FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, raw_json FROM events WHERE id < ? ORDER BY id DESC LIMIT ?",
                (int(before_id), limit),
            ).fetchall()

    items = []
    for r in rows:
        try:
            event = json.loads(r["raw_json"])
        except Exception:
            event = {}
        items.append({"id": r["id"], "data": event})

    return {
        "items": items,
        "next_before_id": items[-1]["id"] if items else None,
        "count": len(items),
    }


def history_max_event_id(*, sync=True):
    """Return the current history watermark after indexing new journal lines."""
    if sync:
        sync_journals()
    with _connect() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
    return int(row[0])


def get_system_map_event_batch(after_id=0, through_id=None, limit=2000):
    """Read an ordered batch of events that can contribute to a system map."""
    after_id = max(0, int(after_id))
    limit = max(1, min(int(limit), 10000))
    placeholders = ",".join("?" for _ in SYSTEM_MAP_EVENT_TYPES)
    clauses = ["id > ?", f"event IN ({placeholders})"]
    params = [after_id, *SYSTEM_MAP_EVENT_TYPES]
    if through_id is not None:
        clauses.append("id <= ?")
        params.append(int(through_id))
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, raw_json FROM events WHERE {' AND '.join(clauses)} "
            "ORDER BY id ASC LIMIT ?",
            params,
        ).fetchall()

    items = []
    for row in rows:
        try:
            event = json.loads(row["raw_json"])
        except Exception:
            continue
        items.append({"id": int(row["id"]), "data": event})
    return items


def history_generation():
    """Identity changes on rebuild/replacement, even if event IDs have caught up."""
    with _connect() as conn:
        return conn.execute("SELECT value FROM history_meta WHERE key='generation'").fetchone()[0]


@contextmanager
def session_event_stream(after_id=0, generation="", last_source=None):
    """Consistent, bounded-memory replay in journal/line order (no ingestion).

    Late imports or edits to earlier journals require derived sessions to rebuild.
    The existing unique source index supplies replay order without a new schema.
    """
    with _connect() as conn:
        conn.execute("BEGIN")
        current_generation = conn.execute(
            "SELECT value FROM history_meta WHERE key='generation'"
        ).fetchone()[0]
        high = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        earliest = conn.execute(
            "SELECT journal_file,line_no FROM events WHERE id>? "
            "ORDER BY journal_file,line_no LIMIT 1", (after_id,)
        ).fetchone()
        rebuild = (generation != current_generation or after_id > high or
                   (earliest is not None and last_source is not None and
                    tuple(earliest) <= tuple(last_source)))
        rows = conn.execute(
            "SELECT id,journal_file,line_no,raw_json FROM events WHERE id>? "
            "ORDER BY journal_file,line_no", (0 if rebuild else after_id,)
        )
        yield current_generation, high, bool(rebuild), rows


def latest_state_events(event_types, *, sync=True):
    """Latest event of each reducer type, in source order, beyond recent windows."""
    if sync:
        sync_journals()
    with _connect() as conn:
        rows = []
        for event_type in event_types:
            row = conn.execute(
                "SELECT id,raw_json,event,timestamp FROM events WHERE event=? ORDER BY id DESC LIMIT 1",
                (event_type,),
            ).fetchone()
            if row is not None:
                rows.append(row)
        # Retain recent partial updates as well as older seed events.
        recent = conn.execute(
            "SELECT id,raw_json,event,timestamp FROM events ORDER BY id DESC LIMIT 250"
        ).fetchall()
    ordered = {row["id"]: row for row in rows + recent if row["event"] in event_types}
    return [_row_to_event(ordered[event_id]) for event_id in sorted(ordered)]
