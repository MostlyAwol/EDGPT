# EDGPT Program Design Notes

This document is the durable mental model for EDGPT. It is written for two
audiences:

- a developer returning later who needs to become productive quickly; and
- a reader learning how the existing program is put together.

It describes the current source tree, not an idealized future architecture.

## One-minute mental model

EDGPT is a Windows desktop process supervisor around three data services.
Elite Dangerous writes newline-delimited journal logs and live JSON files to a
folder. EDGPT indexes the logs into SQLite, derives a convenient current-state
view, and exposes the data through local HTTP and MCP. An optional helper copies
the same information to GitHub. An optional third-party tunnel can make local
MCP reachable by supported OpenAI clients.

```text
Elite journal directory
  |-- Journal.*.log ------------------------+
  |-- Status.json, NavRoute.json, ...       |
  |                                         v
  |                              bin/history_store.py
  |                                   | SQLite
  |                                   v
  +--------------------------> bin/server.py :8080
  |                                   |
  |                                   +--> /state and history HTTP endpoints
  |                                   |
  |                                   +--> bin/uploader.py --> GitHub (optional)
  |
  +--------------------------> bin/mcp_server.py :8000/mcp
                                      |
                                      +--> AI client directly
                                      +--> tunnel-client.exe (optional)

launcher.py starts, stops, configures, and monitors the helper processes.
```

There is no AI chat UI in this repository. EDGPT is a bridge that gives an
external AI client access to game data.

## Source map

| Path | Responsibility | Runs as |
| --- | --- | --- |
| `launcher.py` | Tkinter UI, config, DPAPI secrets, child-process lifecycle, diagnostics | Main desktop process |
| `bin/history_store.py` | Incremental journal ingestion and SQLite query API | Imported library |
| `bin/system_map.py` | Pure event-to-map merging, hierarchy inference, and text rendering | Imported library |
| `bin/system_map_store.py` | Historical backfill and persistent per-system map cache | Imported library |
| `bin/server.py` | Derived state model, history HTTP API, small local dashboard | Child process on `127.0.0.1:8080` |
| `bin/mcp_server.py` | MCP tools over raw/live/current Elite data | Child process on `127.0.0.1:8000/mcp` |
| `bin/uploader.py` | Optional state and raw-file mirror using GitHub Contents API | Child process |
| `build-standalone.ps1` | PyInstaller builds, staging, optional installer compilation | Developer build script |
| `build-release.ps1` | Public-release safety scan, ZIP, hashes | Release build script |
| `installer/EDGPT-standalone.iss` | Per-user Inno Setup installer | Installer definition |

`README.md`, `QUICKSTART.md`, `SECURITY.md`, and `RELEASE_CHECKLIST.md` are
operator/release documentation. This file is the internal design reference.

## Runtime topology

### Development versus packaged mode

`launcher.py` detects PyInstaller with `sys.frozen`.

- In development, it runs `.venv/Scripts/python.exe` with the Python helpers.
- In a packaged build, it runs `bin/edgpt-state.exe`, `bin/edgpt-mcp.exe`, and
  `bin/edgpt-uploader.exe`.
- The runtime root is the source directory in development and the directory
  containing `EDGPT.exe` in a packaged build.

The helpers are separate processes on purpose. A blocking HTTP server, MCP
server, and long-running uploader do not block Tkinter's UI loop, and each can
be packaged independently.

### Startup sequence

When auto-start is enabled, or the user clicks **START BRIDGE**:

1. The launcher checks that the Python/runtime helpers and journal directory
   exist.
2. It starts the state server.
3. It polls `http://127.0.0.1:8080/state` for up to 12 seconds.
4. It starts the MCP server.
5. It conditionally starts the GitHub relay if enabled and fully configured.
6. It conditionally initializes and runs the OpenAI tunnel if enabled.
7. Separate daemon threads copy each child's combined stdout/stderr into the
   UI log without blocking Tkinter.

The launcher owns only processes it started. Process health is inferred from
`Popen.poll()`, except the state-server readiness check, which performs HTTP.
Closing the window asks before terminating running children.

## Configuration, secrets, and runtime files

The launcher creates `data/` beside the application and stores:

| File | Contents |
| --- | --- |
| `data/config.json` | Non-secret Elite path and feature settings |
| `data/github_secret.bin` | GitHub token encrypted with Windows DPAPI |
| `data/openai_secret.bin` | Tunnel API key encrypted with Windows DPAPI |
| `data/edgpt_history.db` | Indexed journal events and ingestion cursors |
| `data/edgpt_system_maps.db` | Persistent maps keyed by Elite `SystemAddress` |

The default config has four sections:

- `elite.journal_path`: source directory for logs and live JSON files;
- `github`: enabled flag, `owner/repository`, branch, and state filename;
- `openai`: enabled flag, local tunnel profile, and tunnel ID; and
- `app.auto_start`: whether the launcher starts the core bridge on open.

Loading deep-merges saved settings over defaults, so adding a new default key
does not invalidate older configs. A malformed config silently falls back to
defaults in memory. Saving rewrites the complete merged config.

Secrets are not placed in `config.json` or child command lines. The launcher
encrypts them with Windows `CryptProtectData`; the relay decrypts its token with
`CryptUnprotectData`. The tunnel key is passed to the tunnel child in the
`CONTROL_PLANE_API_KEY` environment variable.

The launcher supplies the following contract to helper processes:

| Environment variable | Meaning |
| --- | --- |
| `ELITE_JOURNAL_DIR` | Directory containing journals and live JSON |
| `EDGPT_DATA_DIR` | Directory containing the SQLite history database |
| `EDGPT_CONFIG_FILE` | Config path used by the GitHub relay |
| `EDGPT_GITHUB_SECRET_FILE` | Encrypted GitHub token path |
| `EDGPT_STATE_PORT` | Optional state-server port override; defaults to `8080` |
| `PYTHONUTF8`, `PYTHONIOENCODING` | Force UTF-8 helper output |

These environment variables are important seams for tests and future alternate
launchers.

## Historical journal index

Elite journals are newline-delimited JSON files named `Journal.*.log`.
`bin/history_store.py` preserves every valid event's original JSON while also
extracting a few frequently searched fields.

### Database schema

`events` stores:

- an internal autoincrement `id` used for ordering/pagination;
- timestamp and event type;
- source journal filename and one-based line number;
- extracted system, system address, body, station, and ship; and
- compact `raw_json`, which remains the authoritative event representation.

The unique `(journal_file, line_no)` constraint makes repeat indexing
idempotent. Indexes exist on timestamp, event, system, and ship.

`journal_state` stores one ingestion cursor per filename: byte offset, line
number, observed size, and modification time.

SQLite uses WAL mode and `synchronous=NORMAL`. A process-local reentrant lock
serializes ingestion work. Each database operation opens and closes its own
connection; the lock does not coordinate separate OS processes, so SQLite's WAL
and busy timeout provide the cross-process coordination.

### Incremental ingestion algorithm

`sync_journals()` performs this sequence:

1. Create the schema if needed.
2. Sort all matching journal files.
3. Load each file's saved byte offset and line number.
4. If a file shrank, reset its cursor to the beginning.
5. Skip an unchanged-size file.
6. Seek to the cursor and parse newly appended lines only.
7. Insert valid JSON with `INSERT OR IGNORE`.
8. Save the new cursor.

Malformed/partial lines and transient file errors are skipped rather than
stopping the bridge. A consequence is that a malformed line skipped after the
cursor advances is not retried unless the file later shrinks or the database is
rebuilt.

All public query helpers call `sync_journals()` before reading. This keeps data
fresh without a dedicated file-watcher, at the cost of repeated filesystem and
database checks during composite requests.

### Query API

- `recent_events(limit)` returns oldest-to-newest within the selected recent
  window.
- `latest_event(event_name)` returns the newest exact event type.
- `search_events(...)` filters exact event type, ISO-like timestamp bounds, and
  a substring of serialized JSON; results default to newest first.
- `history_summary()` returns counts, time bounds, and top event statistics.
- `get_event_page(before_id, limit)` pages newest-first using stable database
  IDs, with a maximum page size of 5,000.

Timestamps are compared as text. This works for the journal's consistently
formatted UTC timestamps, but would not be safe for arbitrary timestamp
formats.

## Current-state derivation

The state HTTP server's `build_state()` is the richest normalized view. It:

1. synchronizes journals;
2. loads every valid top-level `*.json` live file;
3. gets 250 recent raw events plus the newest `Loadout`, location-like,
   `LoadGame`, `Docked`, and `Undocked` events;
4. replays relevant fields into a stable state dictionary; and
5. lets `Status.json` override rapidly changing coordinates, heading, altitude,
   and fuel values.

Location falls back from `Location` to `FSDJump` to `CarrierJump`. Ship identity
comes from `LoadGame`/`Loadout`. Docking state is reconstructed from location
and dock/undock events. Fuel is derived from loadout capacity, jump/scoop
events, and current status.

The default output contains convenient normalized fields while omitting the
large raw `loadout`, `live_files`, `recent_events`, and `history_summary`
fields. Callers can independently opt into each raw field. Internally, state
derivation still uses the loadout, live status/route, and at least 250 recent
events. This keeps the default LLM context small without making normalized
state less accurate or discarding access to upstream data.

The MCP server has a smaller `build_current_state()` rather than importing the
HTTP server because importing `server.py` would immediately start its blocking
server. The two representations overlap but are not identical:

- HTTP `/state` returns normalized fields with independently selectable raw
  history, loadout, and live-file context.
- MCP `get_elite_state` returns the latest location event, loadout, status,
  route, history summary, recent events, and live filenames.

When changing the meaning of “current state,” explicitly decide whether both
representations need the change.

## Persistent system maps

System maps are a second event-sourced state model. `system_map_store.py`
backfills all relevant events from the history database, then stores one merged
map per `SystemAddress` in `data/edgpt_system_maps.db`. A history-event watermark
makes later updates incremental. If the history database is rebuilt or the map
schema version changes, the map cache is safely regenerated from journals.

The initial event set includes `FSDJump`, `DiscoveryScan`, `FSSDiscoveryScan`,
`FSSSignalDiscovered`, `FSSBodySignals`, `Scan`, `ScanBaryCentre`,
`FSSAllBodiesFound`, `SAAScanComplete`, `SAASignalsFound`, `NavBeaconScan`,
`CodexEntry`, and `ScanOrganic`.

Unlike a per-visit transient state, a map is not cleared on a later jump into
the same system. New events merge into the saved model. This preserves the
first visit's scan data when Elite does not emit it again, while allowing later
FSS, SAA, organic, and signal data to enrich the map.

Parentage comes from the ordered `Parents` list on `Scan` events. The first
entry is the immediate parent. Nonzero `Null` parents represent barycentres;
the remainder of the chain is used to infer where an otherwise parentless
`ScanBaryCentre` belongs. Named ring events are matched to ring definitions in
their parent body's `Scan` data. Siblings are sorted by
`DistanceFromArrivalLS`; a barycentre without its own distance uses its nearest
descendant for ordering.

Two text renderings serve different LLM contexts:

- the simple tree contains system/scan status, body names, body types, arrival
  distances, and hierarchy; and
- the full tree adds retained raw system, scan, surface-scan, organic, and
  signal event data.

The aggregate current-state responses include the simple map only, preventing
the full representation from inflating every request. Dedicated HTTP endpoints
and MCP tools retrieve full or historical maps on demand.

## Local HTTP interface

`bin/server.py` uses the standard-library single-threaded `HTTPServer` bound to
loopback only.

| Endpoint | Result |
| --- | --- |
| `GET /` | Dashboard that refreshes `/state` every five seconds |
| `GET /state` | Compact normalized state; accepts independent `history_summary`, `recent_events`, `loadout`, and `live_files` options |
| `GET /history/summary` | Database/history statistics |
| `GET /history/recent?count=250` | Recent raw events |
| `GET /history/search?q=&event=&start=&end=&limit=` | Filtered raw events |
| `GET /system-map/simple` | Current compact system-map tree |
| `GET /system-map/full` | Current full system-map tree and retained event data |
| `GET /system-maps?q=&limit=` | List/filter saved historical maps |
| `GET /system-maps/get?system=&detail=` | Get a saved map by exact name/address |

JSON responses disable caching and currently allow any CORS origin. Unknown
paths return 404. Most read/parse errors intentionally degrade to empty or null
data rather than producing an error response.

## MCP interface

`bin/mcp_server.py` uses `FastMCP` in stateless HTTP/JSON mode. The launcher and
documentation assume the library's configured/default listener produces
`http://127.0.0.1:8000/mcp`.

| Tool | Source and purpose |
| --- | --- |
| `get_elite_state` | Compact current context bundle |
| `get_full_loadout` | Latest raw `Loadout`, including engineering/modules |
| `get_navroute` | Current `NavRoute.json` |
| `get_status` | Current `Status.json` |
| `list_elite_live_files` | Names of available live JSON sidecars |
| `get_elite_live_file` | Safely reads one basename from the Elite directory |
| `get_recent_events` | Up to 5,000 recent raw events |
| `search_journal` | Search all indexed historical/current journals |
| `get_latest_journal_event` | Latest raw event for an exact type |
| `get_history_summary` | Index statistics |
| `get_raw_history_page` | Stable newest-first raw pagination |
| `get_current_system_map_simple` | Compact tree for the current system |
| `get_current_system_map_full` | Full tree for the current system |
| `list_saved_system_maps` | Find current and historical saved maps |
| `get_saved_system_map_simple` | Compact saved tree by name/address |
| `get_saved_system_map_full` | Full saved tree by name/address |

The basename normalization in `get_elite_live_file` prevents path traversal.
MCP descriptions are part of the product: they tell AI clients when a tool is
useful, so feature work should update descriptions deliberately.

## GitHub relay

The optional relay exists for AI clients that can read GitHub but cannot reach
local MCP.

Every two seconds it fetches local `/state`, recursively removes volatile
timestamp keys, hashes the stable value, and remembers changes. It pushes at
most once every ten seconds. Every five minutes it also scans journals and live
JSON files and mirrors changed files by SHA-256.

The relay opts into all four optional `/state` fields to retain its existing
Full Context behavior even though ordinary `/state` requests are compact.

It writes:

- the configured state file (normally `elite_state.json`);
- `edgpt_manifest.json` describing mirrored files;
- journals under `edgpt_raw/journals/`; and
- live JSON under `edgpt_raw/live/`.

GitHub's Contents API is used directly through `urllib`; no Git client is
involved. Existing blob SHAs are fetched before updates. Individual raw files
over 90 MiB are skipped and recorded in the manifest. The relay catches most
errors, prints them, sleeps, and retries indefinitely.

Privacy implication: the relay can publish detailed location and activity
history. A private repository is the expected configuration.

## Build and release design

`build-standalone.ps1` installs/updates build dependencies into the developer
virtual environment and creates:

- a windowed, one-directory `EDGPT.exe` application;
- one-file console executables for state, MCP, and uploader helpers; and
- optionally, an Inno Setup installer.

The launcher distribution and helpers are staged into `release/EDGPT`.
Third-party tunnel binaries are included only when the developer explicitly
uses `-IncludeThirdParty`; this path is for local testing, not the public build.

`build-release.ps1` calls the standalone builder, rejects runtime data,
credentials, databases, and tunnel binaries in the public stage, then creates a
portable ZIP and SHA-256 checksums. This safety scan is a release invariant and
should remain stricter than ordinary `.gitignore` rules.

The Inno installer is per-user (`PrivilegesRequired=lowest`) and installs under
`LocalAppData/Programs/EDGPT`.

## Error-handling philosophy

The current program favors continued availability and visible log messages:

- unreadable live JSON returns `None`;
- bad journal lines are skipped;
- GitHub failures retry forever;
- optional helpers failing do not stop core state/MCP startup; and
- config parse failures fall back to defaults.

This is friendly for a live companion app, but it can hide root causes. When
adding features, distinguish optional/stale data from a broken invariant. Log
enough context to diagnose the latter without logging secrets or private raw
data unnecessarily.

## Known constraints and design debts

These are facts to account for, not necessarily bugs that must all be fixed:

- The project currently has no automated test suite.
- Current-state logic is duplicated/uneven between HTTP and MCP.
- Location fallback prefers the newest `Location` event whenever any exists,
  then `FSDJump`, then `CarrierJump`; it does not directly compare timestamps
  across those event types. Recent-event replay often corrects this, but only
  when the newer movement event is still in the 250-event window.
- Composite state requests call journal synchronization repeatedly through
  nested query helpers.
- The state HTTP server is single-threaded; a slow state build blocks other
  HTTP requests.
- Process status mostly means “the child has not exited,” not “the endpoint is
  healthy.” MCP diagnostics do not perform an MCP request.
- Ports and URLs are constants rather than configuration.
- Most malformed-input errors become missing data, with limited observability.
- GitHub mirroring creates one commit per changed file and keeps only in-memory
  hashes, so restarting can cause remote checks/uploads again.
- Raw files are decoded as UTF-8 text before GitHub upload; this is correct for
  expected Elite files, not a general binary mirror.
- DPAPI and `ctypes.windll` make the launcher and relay Windows-specific by
  design.
- Version strings and release filenames appear in several files and must be
  updated together.

## Fast re-entry checklist

When returning to the repository later:

1. Read this file, `docs/EXTENDING_EDGPT.md`, and `docs/ROADMAP.md`.
2. Run `git status --short` before editing; preserve user changes.
3. Read the relevant module from the source map, plus its direct data producer
   and consumer.
4. Check `data/config.json` structure only if needed; never expose or commit
   `data/`, secret `.bin` files, or the database.
5. Remember the two public views: HTTP state and MCP tools.
6. Decide whether an addition affects local-only mode, GitHub relay mode, or
   both.
7. Validate development and frozen-path assumptions.
8. Run syntax/tests and perform a representative endpoint/tool smoke test.
9. For a release change, use the release checklist and public safety build.

## Glossary

- **Journal event**: one JSON object on one line of `Journal.*.log`.
- **Live file / sidecar**: a current JSON snapshot such as `Status.json`.
- **Normalized state**: stable convenience fields synthesized from raw inputs.
- **Full Context**: access to current data plus raw recent and historical data.
- **MCP**: the protocol through which an AI client invokes EDGPT tools.
- **Relay**: optional publication of EDGPT state/raw files to GitHub.
- **Frozen mode**: execution from PyInstaller-built binaries.
