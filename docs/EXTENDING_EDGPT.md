# Extending EDGPT

This is the implementation playbook to use after reading
`PROGRAM_DESIGN.md`. It converts the architecture into repeatable feature-work
decisions.

## Start with the data path

Classify a requested feature before editing:

| Feature kind | Primary module | Usually also inspect |
| --- | --- | --- |
| New raw journal query | `bin/history_store.py` | `bin/mcp_server.py`, `bin/server.py` |
| New system-map event/field | `bin/system_map.py` | `bin/system_map_store.py`, map tests |
| New derived current-state field | `bin/server.py` | `bin/mcp_server.py`, relay behavior |
| New MCP capability | `bin/mcp_server.py` | history/live-file source and README tool list |
| New local HTTP endpoint | `bin/server.py` | consumers, privacy/CORS implications |
| New setting or credential | `launcher.py` | helper environment/config loader, release scan |
| New long-running integration | new helper + `launcher.py` | process lifecycle, logs, packaging |
| GitHub publication change | `bin/uploader.py` | privacy, rate/commit volume, manifest format |
| Installer/release change | build scripts and `.iss` | `.gitignore`, security scan, release docs |

A useful design question is: **What is the authoritative raw source, what is
derived, and which interfaces should expose it?** Keeping that distinction
prevents current-state convenience logic from becoming the only way to recover
valuable game data.

## General feature checklist

### 1. Define the contract

Write down:

- input source (journal event, live file, config, or remote service);
- output shape and null/missing behavior;
- freshness requirement;
- volume and pagination limits;
- whether the data is sensitive; and
- which modes need it: HTTP, MCP, GitHub, UI, or some combination.

Prefer additive output changes. Existing AI clients may rely on current field
names and MCP tool behavior even though there is no formal versioned API yet.

### 2. Put logic at the lowest reusable layer

- Raw history storage/search belongs in `history_store.py`.
- Transport-neutral derived state should ideally be a reusable function/module,
  even though current code still derives HTTP and MCP state separately.
- Protocol adaptation belongs in `server.py` or `mcp_server.py`.
- UI code should supervise/configure; it should not become the sole owner of
  data-processing logic.

If both HTTP and MCP need substantial new state logic, consider extracting a
side-effect-free shared state module rather than duplicating the rules. Do not
import `server.py` from elsewhere while it starts `serve_forever()` at import.

### 3. Preserve raw data

When adding a specialized parser or summary, retain access to the original
journal event or live file. Elite can add fields before EDGPT knows about them,
and raw preservation lets AI clients use those fields immediately.

### 4. Bound expensive operations

History is unbounded. New history APIs should use indexed filters and capped
limits or cursor pagination. Avoid loading every event or every journal into
memory. If adding a frequently filtered field, extract it during ingestion and
add an SQLite index with a migration-safe `CREATE INDEX IF NOT EXISTS`.

Be mindful that every query helper currently synchronizes journals. A new
composite operation should not accidentally multiply full directory scans.

### 5. Make failure semantics explicit

Decide whether a failure should:

- return empty/missing optional data;
- surface a structured client error;
- log and retry; or
- stop startup because a core invariant is broken.

Never include tokens in logs or exception messages. Treat journal contents,
paths, commander identity, and location history as private user data.

### 6. Cover process and packaging behavior

If a new helper is added, update all of these:

- development command selection;
- packaged executable selection;
- environment contract;
- start order and readiness behavior;
- stop/close behavior;
- UI status and diagnostics;
- PyInstaller build/staging;
- installer inclusion; and
- public-release forbidden-file scan if it creates secrets/runtime artifacts.

### 7. Update user-visible discovery

For a new MCP tool, update its docstring and the tool list in `README.md`.
For setup changes, update `QUICKSTART.md`. For privacy/security changes, update
`SECURITY.md`. For release validation, update `RELEASE_CHECKLIST.md`.

## Recipes

### Add a journal-backed MCP tool

1. Check whether `search_events`, `latest_event`, or `get_event_page` already
   provides the needed result.
2. If not, add a bounded query helper to `history_store.py` and use parameters,
   not string interpolation, for values.
3. Add an `@mcp.tool()` function with useful type hints and a description that
   explains when an AI should call it.
4. Return predictable empty values (`{}` or `[]`) when no result is normal.
5. Add the tool to `README.md` and test it through an MCP client, not only as a
   Python function.

Example shape:

```python
@mcp.tool()
def get_example_history(limit: int = 100) -> list:
    """Explain the user question this tool answers."""
    return example_query(max(1, min(limit, 5000)))
```

### Add a normalized current-state field

1. Identify the relevant event(s) and live file(s).
2. Establish precedence: startup snapshot, recent event replay, then live
   sidecar override is the existing pattern.
3. Add a stable default to the state dictionary so the key exists even when
   Elite is not emitting that data.
4. Update replay rules without removing the raw event.
5. Decide whether `mcp_server.build_current_state()` should expose the same
   convenience field.
6. Confirm relay hashing ignores only genuinely volatile fields.
7. Test “never observed,” normal update, and conflicting old/new source cases.

### Add information to system maps

1. Add the journal event type to `SYSTEM_MAP_EVENT_TYPES` in
   `history_store.py` so historical and new instances enter the map stream.
2. Decide whether the event belongs to a body (`BodyID`), the system, or the
   system-signal collection.
3. Merge it in `system_map.apply_event()` without discarding fields already
   learned on an earlier visit.
4. If persisted model semantics change, increment `MAP_SCHEMA_VERSION`; the
   cache will rebuild from raw journals.
5. Keep the simple renderer limited to names, types, distances, and hierarchy
   unless product requirements explicitly expand it.
6. Put complete retained event data in the full renderer.
7. Add tests for missing prerequisites, repeated visits, hierarchy, ordering,
   and historical backfill.

### Add a setting

1. Add a default under the appropriate `DEFAULT_CONFIG` section.
2. Add a Tkinter variable/control in `open_settings()`.
3. Normalize and save it in `save_close()`.
4. Pass it to helpers through config or a clearly named environment variable.
5. Keep credentials out of JSON. Use a dedicated DPAPI-protected file for a
   secret and add its filename to build/release exclusions.
6. State whether changes require bridge restart; current settings do.

### Add a live JSON feature

First consider whether the generic MCP pair
`list_elite_live_files`/`get_elite_live_file` already makes the data available.
Add a dedicated tool only when it improves discoverability, gives a stable
shape, or performs meaningful derivation. Use `Path(filename).name` for any
caller-controlled filename.

### Add a remote integration

Prefer an isolated helper process when it has a long-running loop or external
failure modes. Give it bounded timeouts, backoff/rate awareness, change
detection, and restart-safe behavior. Make it opt-in. Document exactly what
private data leaves the PC and make core local MCP work without it.

## Verification strategy

There is no committed test suite yet, so feature work should add targeted tests
where practical and still perform integration smoke checks.

The repository expects a local Windows virtual environment at `.venv`. If its
interpreter path is stale after moving machines or removing Python, recreate
the environment and install `requirements.txt` before running checks.

Minimum checks for ordinary changes:

```powershell
.\.venv\Scripts\python.exe -m py_compile launcher.py bin\history_store.py bin\system_map.py bin\system_map_store.py bin\server.py bin\mcp_server.py bin\uploader.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Recommended journal-store tests should use temporary directories selected via
`ELITE_JOURNAL_DIR` and `EDGPT_DATA_DIR`, then cover:

- initial multi-file import;
- appending to a journal;
- duplicate sync idempotence;
- malformed lines;
- file truncation;
- exact-event, time-range, and text search; and
- pagination without duplicates or gaps.

Representative runtime smoke checks:

- start through the launcher and verify the UI remains responsive;
- check `http://127.0.0.1:8080/state` and history endpoints;
- invoke changed MCP tools from an MCP client;
- stop/restart and verify incremental indexing;
- if relay changed, use a private test repository; and
- if packaging changed, test the staged app without the source `.venv`.

Do not use a real user's journal folder for destructive/truncation tests.

## A sensible first testing refactor

If upcoming work becomes substantial, the highest-leverage preparation is:

1. move server startup behind `if __name__ == "__main__"`;
2. extract shared, side-effect-free state construction;
3. make source/data paths injectable; and
4. add temporary-directory tests for history and state derivation.

That change would improve confidence without changing the public architecture.

## Version-change checklist

The current version is repeated rather than centrally generated. Search for the
old version and update at least:

- `launcher.py` (`APP_VERSION`);
- `README.md` headings/download filenames;
- `QUICKSTART.md` installer filename;
- `installer/EDGPT-standalone.iss` version and output filename;
- `build-standalone.ps1` expected installer filename;
- `build-release.ps1` expected installer filename;
- `CHANGELOG.md`; and
- release/checklist text where applicable.

Then build using `build-release.ps1` and confirm the safety scan and checksums.

## Definition of done for a feature

A feature is complete when:

- raw and derived data responsibilities are clear;
- behavior is bounded for large histories;
- local/MCP/relay exposure matches the intended modes;
- errors and missing data behave predictably;
- secrets/private data remain protected;
- development and packaged execution paths still work;
- relevant automated and smoke checks pass; and
- architecture and user-facing documentation reflect the new contract.
