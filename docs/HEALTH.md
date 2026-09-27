# Health and capability contract (schema 1)

`GET /health`, `GET /capabilities`, and `GET /version` return uncached JSON.
MCP exposes `get_edgpt_health` and `get_edgpt_capabilities` with the same schemas.
Health always returns HTTP 200 when the diagnostic handler can respond; inspect
`status` for readiness. Existing state, history and map responses are unchanged.

Overall precedence is `error`, `degraded`, `indexing`, `stale`, then `ready`.
Core failures are `error` (broken); optional integration failures are `degraded`.
`indexing` means ingestion/backfill is active or persisted cursors lag source
files/history. `stale` means there are no dated events or the latest indexed
event is older than 3,600 seconds. This can be normal when the game is closed.
Disabled integrations do not affect readiness.

Health includes application/schema versions, process uptime, check time,
readable/configured journal-directory flags, event count and high-water mark,
latest event timestamp/age, map count/cursor/backfill status, actual HTTP version
and MCP initialization probes, and optional integration reports. Uptime belongs
to the process serving the response. Service checks have a two-second timeout;
database probes use read-only connections with a 200 ms busy timeout and never
start ingestion. The state server uses a background five-second indexing loop
and a threaded listener so diagnostics remain reachable during backfill.

Each component includes `last_success` and `last_error`; times are Unix seconds
and unknown values are null. Successful observations update service/directory
check times; database update times come from the indexing worker. Last errors
remain after recovery for diagnosis. Worker/integration reports survive restart
in `data/*_health.json`; ordinary probe observations are process-local. Indexing
reports expire after one hour; integration reports expire after 30 seconds.
The GitHub report reflects the last relay pass, including upload/mirror errors.
The tunnel reports degraded/unverified even with a running process because its
CLI does not expose a stable configured readiness endpoint. It is never reported
ready solely because its child process exists.

The launcher polls this contract every ten seconds in a background thread;
CHECK logs component results and the UI retains the last actionable issue.
The local dashboard displays current state only; health is available at `/health`.
Private journal paths, commander
names, raw events, tokens, repository names and exception text are excluded.
The directory is represented by flags rather than its private path.

Capabilities lists HTTP paths, MCP tool names, state models, profiles, limits,
enabled integrations and transports. `/version` contains the application and
schema identifiers. Defaults remain loopback ports 8080 (HTTP) and 8000 (MCP);
`EDGPT_STATE_PORT` and `EDGPT_MCP_PORT` can override them consistently.

Run tests with `.venv/Scripts/python.exe -m unittest discover -s tests`.
Fixtures are synthetic and use temporary directories. Test coverage includes
ready, stale, missing directory, unavailable database, cursor lag/restart,
index failure, optional failure/recovery, redaction, HTTP contracts and MCP
registration. For packaged releases also run the checks in RELEASE_CHECKLIST.
