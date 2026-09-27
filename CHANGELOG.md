# Changelog

## Unreleased

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
