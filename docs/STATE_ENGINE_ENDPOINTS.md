# State Engine HTTP endpoints

The State Engine serves local game state, indexed journal history, session
summaries, and saved system maps. The default base URL is
`http://127.0.0.1:8080`; set `EDGPT_STATE_PORT` before startup to change the port.
The listener binds to `127.0.0.1`. Implementation: [server.py](../bin/server.py).
For the separate MCP interface, see [MCP endpoints](MCP_ENDPOINTS.md).

All routes below use **GET**. JSON responses use
`application/json; charset=utf-8`, disable caching, and include
`Access-Control-Allow-Origin: *`. `/` and `/map` return HTML. The server has no
application authentication; responses can contain private commander data.

## Route reference

| Path | Query parameters (defaults shown) | Response |
| --- | --- | --- |
| `/` | None | Dashboard showing `/state`, refreshed every five seconds. |
| `/state` | See below | Normalized current state with optional raw context. |
| `/health` | None | Diagnostic object; inspect `status`, even when HTTP is 200. |
| `/capabilities` | None | Versions, HTTP paths, MCP tools, models, profiles, limits, and enabled integrations. |
| `/version` | None | `application`, `version`, `api_schema_version`, `health_schema_version`, `capabilities_schema_version`. |
| `/history/summary` | None | History index statistics. |
| `/history/recent` | `count=250` | Raw events, oldest to newest within the selected latest events. |
| `/history/search` | `q=""`, `event=""`, `start=""`, `end=""`, `limit=200` | Matching raw events, newest indexed ID first. |
| `/sessions` | `limit=20`, `before=0`, `start=""`, `end=""` | `{items, count, next_before}`. |
| `/sessions/current` | None | Latest observed session, including after shutdown; `{}` if unavailable. |
| `/sessions/get` | `id` (required) | Saved session; 404 if unknown. |
| `/system-map/simple` | None | Current map metadata and `simple_text`; `{}` if unavailable. |
| `/system-map/full` | None | Current map metadata, `simple_text`, and `full_text`; `{}` if unavailable. |
| `/system-maps` | `q=""`, `limit=100` | Saved map metadata, latest update first; `q` filters system names. |
| `/system-maps/get` | `system` (name or numeric SystemAddress), `detail=simple` | Saved map; `detail=full` adds `full_text`; 404 if not found. |
| `/map` | Optional `system` (numeric SystemAddress only) | HTML system map, refreshed every five seconds; omit `system` to follow location. |

`/map` is implemented but is currently absent from the `/capabilities`
`http_endpoints` list. See [HEALTH.md](HEALTH.md) for the diagnostic schemas
and readiness semantics.

## Current state

`GET /state` returns these fields by default. Unavailable scalar values are
generally `null`; `docked` defaults to `false` before a docking state is known.

| Fields | Meaning |
| --- | --- |
| `system`, `system_address`, `star_position` | System name, numeric address, and journal `StarPos`. |
| `body`, `body_type`, `station`, `docked` | Last reduced body and docking information. |
| `ship`, `ship_name`, `ship_ident`, `jump_range` | Ship type, custom name, identifier, and loadout `MaxJumpRange`. |
| `fuel` | Object containing `main`, `reservoir`, and `capacity`. |
| `location` | Object containing `latitude`, `longitude`, `altitude`, and `heading`. |
| `status`, `navroute` | Live `Status.json` and `NavRoute.json` contents, or `null`. |
| `system_map` | Compact map object with metadata and `simple_text`, or `null`. |
| `generated_at` | Response generation time in Unix seconds; not the source event time. |

The following options independently add fields; omitted options omit their
corresponding fields entirely:

| Query option | Default | Added field |
| --- | --- | --- |
| `history_summary` | `false` | `history_summary`: index statistics. |
| `recent_events` | Omitted | `recent_events`: latest 0–5,000 raw events in ascending indexed order; `0` returns `[]`. |
| `loadout` | `false` | `loadout`: latest complete `Loadout` event, or `null`. |
| `live_files` | `false` | `live_files`: filename-to-JSON-value object for readable live JSON files. |

Boolean values accept `true/false`, `1/0`, `yes/no`, and `on/off`, ignoring
case and surrounding whitespace. Invalid or repeated recognized options
return 400 with `{"error":"..."}`. Unknown `/state` parameters are ignored.

Normalized state is derived independently of output selection. Live status
coordinates and fuel take precedence over journal values. Status preserves
numeric `Flags`, `Flags2`, and `GuiFocus`, adding decoded names for available
values and unknown active bit positions. Missing raw fields remain absent.
Separate queries and live files do not form an atomic game snapshot. See
[STATE_FOUNDATION.md](STATE_FOUNDATION.md) for reduction and recovery details.

## History, sessions, and maps

History counts and search limits are clamped to 1–5,000. Noninteger HTTP
`count`/`limit` values fall back to the route default. Search `event` is an
exact event type; `q` searches serialized event JSON using SQL `LIKE`
(including `%` and `_` wildcards). Time bounds are inclusive string comparisons
against journal timestamps. Use journal-style UTC timestamps such as
`2026-01-01T00:00:00Z`; history search does not validate or normalize timezones.
Ordering uses indexed IDs, not timestamp sorting.

History summary returns `database` (a local path), `journal_files_indexed`,
`events_indexed`, `first_event_time`, `last_event_time`,
`distinct_systems_seen_in_events`, `distinct_ship_types_seen_in_events`, and
`event_counts` (up to 100 event types). Raw history cursor pagination is
available through MCP's `get_raw_history_page`, not an HTTP route.

Session limits are strictly 1–100. Pass `next_before` back as `before` until
it is `null`. Session time filters apply to session **start times**, inclusively,
and require ISO 8601 timestamps with timezones. Invalid filters, limits, cursors,
or unknown/repeated session parameters return 400. Missing/invalid IDs return
400; valid but unknown IDs return 404. See [SESSIONS.md](SESSIONS.md) for the
complete summary fields, activities, provenance, and incomplete-data warnings.

Saved-map list limits are clamped to 1–1,000; nonintegers fall back to 100.
List entries contain `system_address`, `system_name`, `first_seen`,
`last_updated`, `body_count`, `known_complete`, and `visits`. Map lookups accept
an exact case-insensitive name or numeric address. Full map responses add
rendered text containing retained scan and signal data, not a raw `model` field.
Maps contain only recorded information and merge historical visits.

The HTML `/map` route accepts exactly one optional `system` parameter containing
ASCII digits, at most 19 characters, in the range 0–9223372036854775807.
Invalid, repeated, or unknown parameters produce an HTML 400 page; an unknown
saved address produces an HTML 404 page. The JSON saved-map lookup uses the
more permissive name/address lookup described above.

Unknown routes return an empty 404 response. Unimplemented methods use the
standard HTTP handler's 501 response. Handled JSON validation/not-found errors
use `{"error":"..."}`; unexpected failures do not have a guaranteed JSON
error envelope.

## PowerShell examples

```powershell
Invoke-RestMethod 'http://127.0.0.1:8080/state'
Invoke-RestMethod 'http://127.0.0.1:8080/state?history_summary=true&recent_events=250&loadout=true&live_files=true'
Invoke-RestMethod 'http://127.0.0.1:8080/history/search?event=FSDJump&start=2026-01-01T00:00:00Z&limit=20'
Invoke-RestMethod 'http://127.0.0.1:8080/sessions?limit=10'
Invoke-RestMethod 'http://127.0.0.1:8080/system-maps/get?system=Sol&detail=full'
```

URL-encode names and timestamps containing reserved characters, especially `+`
in timezone offsets. Initial requests can take longer while journals and derived
caches are indexed. `/health` reports indexing and stale-data conditions.
