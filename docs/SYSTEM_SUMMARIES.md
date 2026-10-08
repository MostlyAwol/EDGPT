# Compact system overview

Roadmap item 5A adds a separate overview of the merged saved system map.
It does not change `/state` or the existing simple/full maps.

Use `GET /system-map/summary` for the current system, or
`GET /system-map/summary?system=123` (or an exact case-insensitive system name)
for a saved system. MCP exposes `get_current_system_summary` and
`get_saved_system_summary(system: str)`. Both transports return the same JSON
object, including Markdown in `summary_text`. An unknown system or a system
without a retained `FSSAllBodiesFound` event returns `{}` with HTTP 200.
Blank, repeated or unknown HTTP parameters return 400.

The response includes `schema_version`, `system_address`, `system_name`,
`bodies_known`, `expected_body_count`, grouped `stars`, `planets`, `rings`,
and `curiosities`. Each grouped row contains `type` and `count`.
`exobiology` is present only when recorded biology exists and contains
`bodies`, `biological_signals`, `genera` and `species`.

Markdown sections appear in Stars, Planets, Rings, Exobiology, Curiosities
order, omitting empty sections. Stellar codes are retained as labels such as
`K star`. Planets include moons. Body counts require an actual stellar or
planetary scan; inferred parents, barycentres, rings and belt clusters are
excluded. Rings are deduplicated by name across embedded ring data and ring
nodes; asteroid belts are excluded. Types sort lexically.

The completion line is omitted when the expected count is unavailable,
conflicts between retained discovery/beacon/completion records, or is smaller
than the represented body count. A completion event can arrive before all scan
records are available, so a confirmed system can still show `2 of 3 bodies known`.

Biological counts use the maximum recorded FSS/SAA count per body to avoid
counting the same signals twice. Recorded genera and organic species are
deduplicated; organic Log/Sample/Analyse observations do not add signal counts.
No species are inferred from signal counts and no credit estimates are produced
in this version because the map lacks a versioned valuation model.

`bin/system_summary.py` owns the intermediate representation and renderer.
`bin/curiosities.py` exposes `find_curiosities(system_map) -> list[str]` through
an ordered rule registry that initially contains no rules. Detector results
retain rule order. Detectors must not mutate inputs; the builder also supplies
a copy of the map to protect the source of truth.

Planned detectors and research candidates are tracked separately in
[CURIOSITIES_ROADMAP.md](CURIOSITIES_ROADMAP.md).

Summaries are stored in the existing map SQLite database's `system_summaries`
table, keyed by SystemAddress with their own schema version. Ingestion creates
them after completion and refreshes them on FSD return visits. Each summary
retrieval rebuilds from the merged saved map, reruns current curiosity rules and
commits the refreshed result before returning it. Empty new curiosity results
remove earlier ones. Current identity follows the latest Location, FSDJump or
CarrierJump rather than falling back to a completed previous system.

Existing completed maps are adopted without replaying raw journals. Missing or
outdated summary rows rebuild from maps during synchronization. Map schema or
history-generation resets discard summaries together with their source maps.
The map itself remains unchanged by summary generation or retrieval.

Synthetic fixtures and tests cover gating, ingestion, restarts, migration,
history reset, grouping, optional sections, biology, return visits, curiosity
refresh and HTTP/MCP equivalence. Run the full suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
