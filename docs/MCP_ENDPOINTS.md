# MCP endpoint and tools

EDGPT exposes one Streamable HTTP MCP endpoint:
`http://127.0.0.1:8000/mcp`. Set `EDGPT_MCP_PORT` before startup to change the
port. The server name is `Elite Dangerous Full Context`; it binds to
`127.0.0.1` and configures FastMCP with `stateless_http=True` and
`json_response=True`. Implementation: [mcp_server.py](../bin/mcp_server.py).

Configure an MCP-compatible client with that URL. Tools are invoked through
the MCP protocol (`tools/list` and `tools/call`), not individual REST paths.
A hosted client needs a transport that can reach the local endpoint. The server
does not configure application authentication. Returned state/history can
contain private commander information and local database paths.

The tables describe tool return values; the MCP SDK wraps these in protocol
results. Arguments with defaults are optional; other arguments are required.
The complete tool list is also exposed by `get_edgpt_capabilities`. For plain HTTP requests, see
[State Engine endpoints](STATE_ENGINE_ENDPOINTS.md).

## State and live files

| Tool | Arguments | Return value |
| --- | --- | --- |
| `get_elite_state` | None | Normalized current state plus raw context described below. |
| `get_full_loadout` | None | Latest complete `Loadout` event, including modules/engineering; `{}` if unavailable. |
| `get_navroute` | None | Live `NavRoute.json`; `{}` if unavailable. |
| `get_status` | None | Live `Status.json` with decoded flags; `{}` if unavailable. |
| `list_elite_live_files` | None | Sorted list of current `*.json` filenames in the journal directory. |
| `get_elite_live_file` | `filename: str` | `{filename, data}`; `data` is `null` if unreadable/missing/invalid JSON. |

`get_elite_state` uses the same reducer as HTTP `/state` and returns all of
its default normalized fields. It additionally includes `history_summary`,
the latest 250 `recent_events`, `loadout`, `location_event` (latest `Location`,
`FSDJump`, or `CarrierJump` event), and `live_json_files` (filenames).
It does **not** include the complete `live_files` collection and accepts no
output-selection arguments. Missing loadout/location events are `null`.
Recent events are returned oldest to newest within the selected latest events.

Status responses retain raw numeric `Flags`, `Flags2`, and `GuiFocus` and add
decoded names (`FlagsDecoded`, `Flags2Decoded`, `GuiFocusDecoded`) where
applicable. Unknown active bits appear in `FlagsUnknownBits` and
`Flags2UnknownBits`; missing raw fields stay absent. This applies to status
inside state and to `get_elite_live_file("Status.json")` as well.

`get_elite_live_file` appends `.json` if needed and uses the basename of the
supplied filename. Use a name from `list_elite_live_files`; discovery does not
guarantee the file can be parsed at the moment it is read.

## Journal history

| Tool | Arguments | Return value |
| --- | --- | --- |
| `get_recent_events` | `count: int = 250` | Latest raw events, in ascending indexed ID order. |
| `search_journal` | `query: str = ""`, `event: str = ""`, `start_time: str = ""`, `end_time: str = ""`, `limit: int = 200` | Matching raw events, newest indexed ID first. |
| `get_latest_journal_event` | `event: str` | Newest event of the exact event type; `{}` if unavailable. |
| `get_history_summary` | None | Index statistics, including database path, event/file counts, time bounds, distinct system/ship counts, and event-type counts. |
| `get_raw_history_page` | `before_id: int = 0`, `limit: int = 500` | `{items: [{id, data}], next_before_id, count}`, newest indexed ID first. |

Counts/limits are clamped to 1–5,000. Search scans all indexed journals;
`query` uses SQL `LIKE` over serialized JSON, with `%` and `_` wildcard behavior.
`event` is an exact type. Time bounds are inclusive string comparisons, without
timezone normalization or timestamp validation; use journal-style UTC values
such as `2026-01-01T00:00:00Z`. Raw events retain original journal fields.

For complete history, call `get_raw_history_page` with `before_id=0` (any
nonpositive value starts at the newest event). Pass each `next_before_id` as
the next `before_id`; the cursor is exclusive. Every nonempty page returns a
cursor, even the last nonempty page. Stop when `items` is empty and
`next_before_id` is `null`. IDs belong to the current history index; restart
pagination after a rebuild. Search and recent-event tools have no cursor.

## Sessions

| Tool | Arguments | Return value |
| --- | --- | --- |
| `get_current_session_summary` | None | Latest observed session, including after shutdown; `{}` if unavailable. |
| `list_game_sessions` | `limit: int = 20`, `before: int = 0`, `start_time: str = ""`, `end_time: str = ""` | `{items, count, next_before}` in newest source-journal order. |
| `get_game_session` | `session_id: str` | Saved session summary; `{}` if a valid ID is unknown. |

Session limits are strictly 1–100, not clamped. Use `next_before` as the next
`before`; `null` marks the end. Optional inclusive time filters apply to session
start times and require ISO 8601 timestamps with timezones. Invalid limits,
cursors, IDs, times, or reversed ranges produce tool errors. See
[SESSIONS.md](SESSIONS.md) for fields, activities, boundaries, and warnings.

## System maps

| Tool | Arguments | Return value |
| --- | --- | --- |
| `get_current_system_map_simple` | None | Compact body-tree text. |
| `get_current_system_map_full` | None | Detailed tree text with all retained scan/signal data. |
| `list_saved_system_maps` | `query: str = ""`, `limit: int = 100` | Metadata list, most recently updated first; optional system-name filter. |
| `get_saved_system_map_simple` | `system: str` | Compact saved-map text by exact case-insensitive name or numeric SystemAddress. |
| `get_saved_system_map_full` | `system: str` | Detailed saved-map text by the same lookup. |

Map tools return **strings**, except `list_saved_system_maps`, which returns
metadata objects with `system_address`, `system_name`, `first_seen`,
`last_updated`, `body_count`, `known_complete`, and `visits`. List limits are
clamped to 1–1,000. Maps merge recorded historical visits; they do not supply
unobserved game data.

Unavailable current maps return `No saved current-system map is available.`
Unknown saved maps return `No saved system map found for: <system>`.
These are successful text results, not tool errors. HTTP map endpoints instead
return JSON objects containing metadata and rendered text.

## Diagnostics

Compact overviews are available through `get_current_system_summary()` and
`get_saved_system_summary(system: str)` (name or SystemAddress). They return
the same structured overview as HTTP, including `summary_text`, or `{}` until
`FSSAllBodiesFound` is recorded. Reads refresh and persist derived curiosities.
See [SYSTEM_SUMMARIES.md](SYSTEM_SUMMARIES.md).

| Tool | Arguments | Return value |
| --- | --- | --- |
| `get_edgpt_health` | None | Readiness, indexing, freshness, component checks, and retained errors. |
| `get_edgpt_capabilities` | None | Application/schema versions, endpoints, tool names, models, profiles, limits, and integration flags. |

See [HEALTH.md](HEALTH.md) for the contract. There is no separate MCP version
tool; versions are included in these results. Inspect the health `status`
(`ready`, `stale`, `indexing`, `degraded`, or `error`) rather than treating a
successful tool call as proof of readiness.

## Example tool calls

These are `tools/call` parameter objects for an initialized MCP client, not
standalone HTTP request bodies:

```json
{"name":"get_elite_state","arguments":{}}
```

```json
{"name":"search_journal","arguments":{"event":"FSDJump","limit":20}}
```

```json
{"name":"get_elite_live_file","arguments":{"filename":"Cargo.json"}}
```

```json
{"name":"get_raw_history_page","arguments":{"before_id":0,"limit":500}}
```

Use targeted tools when only one piece of context is needed. Requests may
synchronize journals or rebuild derived caches, so initial calls can take
longer. State generation time does not guarantee fresh game data; consult
health/source timestamps. See [STATE_FOUNDATION.md](STATE_FOUNDATION.md) for
shared-state behavior and persistence recovery.
