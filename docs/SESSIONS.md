# Session and activity summaries

Roadmap item 5 adds independent HTTP endpoints and MCP tools. `/state`,
`get_elite_state`, and relay payloads are unchanged. No new dependency or
launcher setting is required.

| HTTP | MCP | Result |
| --- | --- | --- |
| `/sessions/current` | `get_current_session_summary` | Latest observed session, including after shutdown; `{}` with no sessions |
| `/sessions/get?id=SESSION_ID` | `get_game_session(session_id)` | One session; HTTP 404 or MCP `{}` if unknown |
| `/sessions?limit=20&before=0&start=...&end=...` | `list_game_sessions(limit=20, before=0, start_time="", end_time="")` | `{items, count, next_before}` |

Lists are newest first in source journal order. Pass `next_before` back as
`before`; `null` means the final page. Limits are 1–100. Time filters are
inclusive **session start time** bounds, expressed as ISO 8601 with a timezone
(for example `2026-01-01T00:00:00Z`). They do not select sessions by overlap.
Unknown start times are excluded when a time filter is supplied. URL-encode
positive timezone offsets. Invalid limits, cursors, times, reversed ranges,
or repeated/unknown HTTP query parameters return HTTP 400; invalid MCP values
return tool errors. Restart pagination after a source-history/cache rebuild.

## Boundaries and recovery

- `LoadGame` starts a session; `Shutdown` completes it.
- A new `LoadGame` without shutdown closes the previous session as incomplete.
- A fresh `FileHeader` with `part: 1` also closes an unclosed session. Rollover
  headers with larger part numbers and `Continued` retain the session.
- Activity without a preceding `LoadGame` creates an incomplete-start session.
  Header/Commander preambles alone do not create empty sessions. Commander
  identity from the preamble supplies a missing `LoadGame` profile ID.
- An unclosed latest session remains `open`, with a warning that a crash cannot
  be distinguished from an active game. No idle timeout invents a logout.
- `end` for an interrupted session is its last observed timestamp, not the next
  login. `duration_seconds` is elapsed observed-event time, never wall-clock
  time since login or a claim about active play time. Missing timestamps produce
  `null`; backwards timestamps produce a warning.

Sessions have a stable ID derived from their initial source filename, line,
event type and timestamp. Normal app restarts, append, rollover and a cache
rebuild preserve it. Replacing the starting source event can change the ID.

## Summary contract

Each session includes schema version, ID, start/end/last event timestamps,
status/end reason, commander, profile ID, game mode, duration, event count,
`activities`, `summary_text`, warnings, and source provenance. Absent activities
are omitted; absent numeric source fields are not silently counted as zero.

Activity groups have `count`, named `totals`, `source_event_range`, at most 20
`examples`, and `examples_omitted`. Examples retain selected fields, their raw
timestamp and event ID, with strings capped at 256 characters. Counts/totals
continue accumulating after the example cap. These are **observations**, not
deduplicated discoveries or inferred inventory balances. Consecutive location
reports for the same system do not add visits; returning later does. Scan/map
counts may include repeat scans. Material changes count observed changes,
including both sides of trades and each consumed ingredient.

Supported activities:

- System visits (`Location`, `FSDJump`, `CarrierJump`), FSD jumps and known
  distance, carrier jumps separately, docking locations (including docked
  startup locations), and ship changes from loadout/shipyard events.
- Deaths, resurrection/rebuy costs, bounty awards, PvP kills, combat bonds,
  attacks and hull-damage examples. Award events are not necessarily kills or
  cashed income; hull damage can also describe a non-player craft.
- Scans, DSS completions, Codex entries, organic samples and completed Analyse
  observations. Water/ammonia/Earth-like and terraformable scans are notable.
- Mission acceptance, completion, failure and abandonment.
- Credits from explicit supported transactions: market, mission rewards,
  redeemed vouchers, exploration/organic sales, module and ship purchases/sales,
  refuelling, repair, drones, vehicle restocking, fines, bounties, rebuy,
  search-and-rescue rewards and microresource sales. Trade-ins are counted
  separately. Bounty awards and startup balances are not counted as income.
- Cargo additions/removals from market trades, collection, ejection and refining;
  material collection/discard, trades, synthesis and engineering ingredients.

Unsupported transfers, mission cargo/rewards, on-foot inventories, loans and
other unhandled events are not a complete ledger. Every summary explicitly
warns that credits/cargo/material totals are partial. Missing/malformed fields
on supported events add a warning. Raw duplicate source lines count separately.
Malformed lines skipped by the history index cannot be reconstructed here.

Session and activity source ID bounds are inclusive min/max IDs, accompanied by
`history_generation` on the session. To investigate, use MCP
`get_raw_history_page(before_id=last_id+1)` and page toward `first_id`; example
IDs pinpoint particular events. Late historical imports can make ranges
noncontiguous, so a range may include unrelated events. Bounds are valid only
for the current history generation and are recalculated after a rebuild.

Field mappings follow Frontier's
[Journal Manual v32](https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf).
Newer/unknown event types remain available in raw history. This model does not
estimate monetary value for exploration finds or infer unsupported transactions.

## Persistence and privacy

`bin/session_summary.py` contains the transport-neutral reducer and rendering;
`bin/session_store.py` owns `data/edgpt_sessions.db` (or `EDGPT_DATA_DIR`). The
cache uses `sessions` and `session_meta` tables, schema version 1, a history
watermark and generation. Requests index journals once and replay new source
rows in filename/line order with bounded memory. SQLite transactions serialize
updates across HTTP/MCP and read a consistent history snapshot.

A model-version mismatch, history generation change, watermark regression or
late insertion into an earlier source position rebuilds the derived sessions.
The raw history schema is unchanged. Removing only this cache while helpers
are stopped regenerates it from indexed journals. The first summary request
can take longer on a large history; subsequent requests process new events.

Session data includes private identity, location and activity history. It stays
in local storage and is returned to callers of these HTTP/MCP interfaces; the
existing optional MCP tunnel also exposes the tools. It is not added to health
diagnostics or the GitHub state relay. Capabilities advertise the tools, model
version and limits without personal data. PyInstaller follows the new normal
module imports; no helper executable is added.

Tests use synthetic journals and temporary databases, including real HTTP and
MCP client calls. Run the full suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
