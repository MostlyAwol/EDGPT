# Shared state and test foundation

Roadmap item 4 is implemented in `bin/current_state.py`. Both HTTP `/state`
and MCP `get_elite_state` call its builder. Journal ingestion stays in
`history_store.py`; `reduce_state()` is a pure function of ordered journal
events and live snapshots; HTTP query parsing and MCP tool registration stay
in their transport modules. System-map reduction and text rendering remain
in `system_map.py`.

## State contract

- A composite state request calls journal synchronization once. Internal
  queries skip ingestion explicitly; standalone queries still refresh data.
- Latest events for each reducer type seed the bounded 250-event replay.
  Indexed history IDs define source order, including ties/missing timestamps.
  A newer jump or undock is not overridden by an older location or docking
  event outside that window.
- Live status overrides journal coordinates and fuel. The shared status
  decoder retains raw flags and adds decoded names.
- HTTP defaults and all four independent raw-field options are preserved.
  Recent output selection does not affect normalized state.
- MCP retains `location_event`, `loadout`, `status`, `navroute`,
  `history_summary`, `recent_events`, `live_json_files`, and `system_map`.
  It adds normalized fields and `generated_at`. Its location event now uses
  the newest location-like event rather than preferring the `Location` type.
- Server imports start no listener or worker and create no runtime directory.
  Environment variables select journal/data paths before import; tests can
  inject module paths or call the reducer directly.

This is additive for MCP and preserves HTTP response selection. Clients should
allow additional MCP keys. The current-state model is not persisted. Separate
queries and live sidecars are not an atomic snapshot of a running game.

## Persistence versions and recovery

| Model | Version | Migration/rebuild behavior |
| --- | --- | --- |
| History index | `HISTORY_SCHEMA_VERSION = 1`, SQLite `user_version` | Existing unversioned EDGPT tables are adopted in place, retaining event IDs/cursors and adding generation metadata. Unsupported nonzero versions fail explicitly without deleting data. |
| System maps | `MAP_SCHEMA_VERSION`, `map_meta.schema_version` | Model-version mismatch, history-generation mismatch, or a watermark beyond history clears the derived cache and replays raw history. |

History receives a persistent generation identifier on initial schema adoption.
It changes when a journal is truncated or replaced at the same size. A rebuilt
history database receives a new identifier even if its event IDs catch up to
the old watermark. Maps compare that identity before incremental replay.

Ingestion is serialized with a SQLite write transaction across processes.
Repeated sync does not duplicate a source `(journal_file, line_no)`. Identical
payloads on different source lines remain distinct raw events. Truncation
removes old rows for that file before reindexing. Malformed complete lines and
non-object JSON are skipped; an incomplete final line is retried on append.
Same-size replacement is detected through modification time. Replacements
that preserve both size and modification time, or grow an existing file while
rewriting earlier bytes, are not detected as replacements.

For a manual rebuild, stop all EDGPT helpers, back up the data directory, and
move the affected database and any matching `-wal` / `-shm` files out of that
directory. Restart EDGPT with the original journals available. History is
reindexed if absent; maps regenerate if absent or invalidated. Do not delete
journals: the cache cannot reconstruct source data no longer available locally.
For an unsupported history version, use the matching application version or
perform this backed-up rebuild; EDGPT does not guess a destructive migration.

## Automated verification

Install `requirements.txt` in the project's virtual environment, then run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use generated data and committed synthetic fixtures in `tests/fixtures`.
Persistence tests use temporary journal/database directories. HTTP/MCP smoke
tests use loopback and temporary ports. The suite covers append, a new-process
restart, idempotence, duplicate payloads, truncation, malformed/partial lines,
legacy optional fields, multiple files, history search/pagination, schema
adoption and rejection, map rebuilding, pure reduction, HTTP contracts, shared
transport state, single synchronization, safe imports, MCP registration and
an actual MCP client initialize/list/call exchange.

Add a sanitized regression fixture whenever a real journal pattern exposes a
bug. Packaged executable and launcher UI checks remain release checks; these
tests exercise the Python runtime and require no live commander data.
