# Changelog

## Unreleased

- Completed the initial curiosity detector families and additional exploration
  categories: body-relative close binaries, nested moons and ringed ancestors,
  inclined/polar moons, nearby stellar relationships, selective possible green
  gas giants, short/eccentric orbits, ringed terrestrial bodies, landable extremes,
  and unusual spin/orbit properties. Match descriptions report factual values
  and combine related ring, inclination and recorded biology details. Added
  sourced GGG examples, boundary/invalid-data tests and partial-map refresh checks.

- Implemented roadmap 5A: persistent compact system overviews for partial and
  complete maps, with grouped stars/planets/rings, recorded exobiology,
  and an independent initially empty curiosity registry. Added
  `/system-map/summary`, `get_current_system_summary`, and
  `get_saved_system_summary`, shared refresh/rebuild logic and fixture tests.
  Summary schema v2 adds `all_bodies_found` and an `All bodies found` text marker
  based only on a retained `FSSAllBodiesFound` event. Existing partial maps are
  adopted automatically without journal replay.

- Added persistent session/activity summaries via `/sessions`,
  `/sessions/current`, `/sessions/get` and three matching MCP tools, leaving
  `/state` unchanged. Includes bounded details, source event ranges, time
  filters, pagination, crash/rollover handling and automatic cache rebuilding.

- Shared HTTP/MCP current-state builder and pure reducer; MCP preserves raw
  context and adds normalized fields. Composite requests synchronize once.
- Fixed stale location/docking seeds beyond the recent-event window.
- Versioned history schema adoption and map invalidation by history generation.
  Truncation removes obsolete indexed rows; incomplete lines retry on append.
- Added synthetic ingestion/reducer/import tests and MCP client smoke checks.

- Added shared human-readable decoding for `Status.json` `Flags` and `Flags2`
  across HTTP and MCP while retaining raw integers and exposing unknown bits.
- Added `GuiFocusDecoded` labels for documented `Status.json` `GuiFocus` values
  while preserving the original integer.
- Added persistent simple and full text system maps built from exploration,
  FSS, SAA, barycentre, organic, and signal journal events.
- Added historical map backfill and per-system merging so repeat visits retain
  scan data that Elite does not emit again.
- Added current/historical system-map HTTP endpoints and MCP tools.
- Made `/state` compact by default, with independent opt-ins for
  `history_summary`, zero to 5,000 `recent_events`, raw `loadout`, and complete
  `live_files`; invalid option values now return HTTP 400.
- Added HTTP contract tests for compact and full state-response profiles.

## 0.2.0-beta

- Added Full Context historical journal indexing with local SQLite storage.
- Added raw access to historical Elite journal events.
- Added full live JSON/sidecar access.
- Added full loadout retrieval.
- Added GitHub Full Context mirror and manifest support.
- Added one-click automatic core bridge startup.
- OpenAI tunnel is now optional and disabled by default.
- Added built-in CHECK diagnostics.
- Added safer public release build with secret/runtime-data scan.
- Added portable ZIP + SHA-256 checksum generation.
- Improved first-run and quick-start documentation.

## 0.1.0-alpha

- Initial Windows bridge.
- Local state server.
- MCP server.
- Optional GitHub relay.
- Optional OpenAI tunnel integration.

## Unreleased

- Shared HTTP/MCP current-state builder and pure reducer; MCP preserves raw
  context and adds normalized fields. Composite requests synchronize once.
- Fixed stale location/docking seeds beyond the recent-event window.
- Versioned history schema adoption and map invalidation by history generation.
  Truncation removes obsolete indexed rows; incomplete lines retry on append.
- Added synthetic ingestion/reducer/import tests and MCP client smoke checks.

- Added shared HTTP/MCP health, capabilities and version discovery, background indexing, and launcher/dashboard diagnostics with private data excluded.
- Relay failures now report degraded health; tunnel connectivity is explicitly unverified.
- Added diagnostic contract tests and resolved existing test conflict markers.
