# EDGPT Suggested Implementation Roadmap

This document records the agreed direction for future EDGPT development. It is
ordered deliberately: first make the default state payload focused and easier
to understand, then make the bridge observable and safe to change, add
specialized state models, and finally add real-time and extension capabilities.

The roadmap is planning guidance rather than a promise that every detail must
be implemented exactly as written. Before starting an item, compare these notes
with the current source tree, current Elite journal output, and lessons from
the previously completed items.

## Guiding principles

- EDGPT remains an AI data bridge, not a replacement game client.
- Preserve raw Frontier data while adding compact, useful derived states.
- Keep core local HTTP/MCP operation independent of optional cloud services.
- Prefer additive and versioned API changes.
- Bound history queries and large output intended for LLM context windows.
- Treat commander identity, location, activity, and databases as private data.
- Make derived state rebuildable from raw journals whenever practical.
- Do not weaken current-state accuracy merely to reduce response payload size.
- Add fixtures and automated checks with every new state model.

## 1. Lean and configurable `/state` defaults

**Status: completed on 2026-09-26.** The four fields are independently
selectable, strict invalid values return HTTP 400, the relay explicitly opts
into the full payload, and committed HTTP contract tests cover default,
individual, combined, zero-event, false, and invalid requests. Capabilities
registration remains part of item 3 because that interface does not exist yet.

### Goal

Make the default `/state` response compact enough for routine LLM context while
retaining explicit, independent ways to request every currently available
field.

### New default response behavior

The following fields should not be returned by a plain `GET /state`:

- `history_summary`;
- `recent_events`;
- `loadout`; and
- `live_files`.

This is an output-selection change only. EDGPT may still use journal replay,
the latest loadout, and live files internally to derive accurate normalized
fields such as current system, ship, jump range, fuel, location, status, and
route.

### Proposed independent options

```text
GET /state?history_summary=true
GET /state?recent_events=25
GET /state?loadout=true
GET /state?live_files=true
GET /state?history_summary=true&recent_events=100&loadout=true&live_files=true
```

Proposed semantics:

- `history_summary` defaults to `false`; `true` includes the field.
- `recent_events` defaults to `0`; a value from 1 to 5,000 includes exactly
  that many recent events, subject to available history.
- When `recent_events` is absent, omit the field. When it is explicitly set to
  `0`, include `"recent_events": []` so clients can distinguish the request.
- `loadout` defaults to `false`; `true` includes the complete raw loadout.
- `live_files` defaults to `false`; `true` includes the decoded collection of
  all live JSON sidecars.
- Invalid values should produce a documented HTTP 400 response rather than
  silently selecting an unexpected payload.

The individual history, loadout, status, route, live-file, and system-map HTTP
endpoints/MCP tools remain available. Existing query options should be migrated
deliberately, with the changed defaults called out as an API compatibility
change.

### Efficiency expectations

- Do not serialize omitted fields.
- Avoid computing `history_summary` when it was not requested.
- Read the full loadout/live-file collection only when needed for internal
  derivation or explicitly requested output.
- Continue using an internal event replay window even when `recent_events` is
  omitted, so state accuracy is unchanged.

### Completion criteria

- Plain `/state` omits all four fields.
- Each field can be enabled independently.
- Enabling one field does not implicitly enable another.
- A request for `recent_events=0` returns the documented empty list while a
  plain request omits the field.
- Combined options return the requested fields and nothing extra.
- Default and full-response HTTP contract tests are committed.
- README, capabilities, changelog, and API compatibility notes describe the
  new defaults.

## 2. Human-readable `Status.json` flags

**Status: completed on 2026-09-27.** HTTP and MCP status reads now share a
single decoder, retain the original integers, list documented active flags in
bit order, and report unknown active bit positions explicitly. Tests cover all
documented bits, combinations, zero/missing/malformed values, unknown high
bits, and Frontier's published `16842765` example. The same decoder also adds a
human-readable `GuiFocusDecoded` label for documented `GuiFocus` values 0-11
while retaining the raw integer.

### Goal

Decode the numeric `Flags` and `Flags2` bitfields into stable human-readable
names while preserving the original numeric values exactly.

### Proposed output

Keep Frontier's raw fields and add decoded fields alongside them:

```json
{
  "Flags": 16842765,
  "FlagsDecoded": ["Docked", "LandingGearDown", "ShieldsUp", "FsdMassLocked", "InMainShip"],
  "FlagsUnknownBits": [],
  "Flags2": 5,
  "Flags2Decoded": ["OnFoot", "InMulticrew"],
  "Flags2UnknownBits": []
}
```

Names and positions follow section 14 of Frontier's
[Journal Manual v32](https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf).
EDGPT normalizes the documented labels into stable PascalCase identifiers.

### Design requirements

- Preserve `Flags` and `Flags2` as integers for lossless compatibility.
- Represent decoded active flags in deterministic bit order.
- Use stable, unlocalized machine-readable names suitable for LLMs and API
  clients.
- Do not guess at unknown/new bits. Preserve the raw integer and optionally
  expose unknown bit positions explicitly.
- Treat a missing `Flags2` as unavailable, not as a zero value.
- Centralize flag definitions in one tested module rather than scattering bit
  masks through HTTP and MCP code.
- Make HTTP and MCP status output use the same decoder.

### Testing requirements

- zero flags;
- every documented individual bit;
- representative combinations;
- high/unknown bits;
- missing `Flags` or `Flags2`;
- values observed in sanitized real `Status.json` fixtures; and
- confirmation that raw integers are unchanged.

### Completion criteria

- The status object within `/state` and MCP `get_status` agree.
- Both decoded lists are human readable and deterministically ordered.
- Unknown bits cannot silently disappear.
- Flag-definition provenance/version is documented.
- Existing consumers of numeric `Flags` and `Flags2` remain compatible.

## 3. Health, capabilities, and real diagnostics

Implemented: see [HEALTH.md](HEALTH.md). Tunnel connectivity remains explicitly
unverified; packaged runtime checks are part of the release checklist.

### Goal

Make it obvious whether EDGPT is ready, degraded, indexing, stale, or broken,
and let clients discover available features without relying on a README.

### Proposed interfaces

```text
GET /health
GET /capabilities
GET /version

MCP: get_edgpt_health
MCP: get_edgpt_capabilities
```

### Health information

- application version and process uptime;
- configured journal directory and whether it is readable;
- latest indexed journal event timestamp and age;
- history database availability, event count, and high-water mark;
- system-map database availability, map count, and backfill status;
- state-server and MCP readiness;
- GitHub relay/tunnel state when enabled;
- last successful update and last error for each component; and
- overall status such as `ready`, `indexing`, `degraded`, or `error`.

Do not expose tokens, commander names, private paths, or journal payloads in a
health response intended for diagnostics.

### Capabilities information

- API schema/version identifiers;
- endpoint and MCP-tool names;
- supported state models;
- maximum limits and available response profiles;
- enabled optional integrations; and
- supported transports.

### Launcher integration

Replace process-only CHECK results with actual endpoint checks. Report which
component failed and retain the last actionable error in the UI. A live child
process is not necessarily a healthy service.

### Completion criteria

- Each core component has a real readiness check.
- Responses distinguish startup/indexing from failure.
- Launcher CHECK uses the same health contract exposed to clients.
- Tests cover ready, missing journal directory, unavailable database, stale
  journal, and optional-component failure cases.

## 4. Shared state construction and automated test foundation

**Status: completed on 2026-09-27.** HTTP and MCP share one state builder and
pure reducer. Composite requests synchronize journals once. Versioned history
schema adoption, generation-based map rebuilds, and isolated fixture/reducer,
HTTP, import-safety and MCP client tests are documented in
[STATE_FOUNDATION.md](STATE_FOUNDATION.md).

### Goal

Remove duplicated state semantics and make future work safe to implement and
verify.

### Refactoring targets

- Move `server.py` startup behind `if __name__ == "__main__"`.
- Extract transport-neutral current-state construction into a shared module.
- Have HTTP and MCP call the same state builder.
- Synchronize journals once per composite request rather than through nested
  query helpers.
- Separate journal ingestion, state reduction, rendering, and transport code.
- Define schema versions for persisted derived-state databases.
- Add explicit migration/rebuild behavior for each persisted model.

### Test infrastructure

- Store sanitized journal fixtures covering ordinary and edge-case sessions.
- Use temporary journal/data directories for all tests.
- Test incremental append, restart, truncation, malformed lines, duplicate
  events, old journal formats, and multiple journal files.
- Add state-reducer tests independent of HTTP/MCP.
- Add HTTP contract and MCP tool-registration smoke tests.
- Add regression fixtures whenever a real journal pattern exposes a bug.

### Completion criteria

- Importing server modules has no network/listener side effects.
- HTTP and MCP current-state fields come from one reducer.
- Tests run from one documented command without live commander data.
- Existing history and system-map behavior remains compatible.

## 5. Session and activity summaries

### Goal

Give an LLM a compact description of what happened during the current or a
past play session without sending hundreds of raw events.

### Session boundaries

Start with `LoadGame` and end with `Shutdown` where available. Also handle
crashes, journal rollover, and a new `LoadGame` without a preceding shutdown.
Persist a stable internal session ID and source event-ID bounds.

### Derived information

- start, end, duration, game mode, and active commander/profile ID;
- systems visited, jumps, total distance, and docking locations;
- ship changes, deaths, rebuy, combat, and damage highlights;
- scans, mapped bodies, organic discoveries, and notable exploration finds;
- missions accepted/completed/failed;
- credits earned and spent where events support it;
- cargo and material changes; and
- warnings about incomplete or ambiguous source data.

### Proposed interfaces

```text
GET /sessions
GET /sessions/current
GET /sessions/get?id=...

MCP: get_current_session_summary
MCP: list_game_sessions
MCP: get_game_session
```

Offer compact structured data plus a text summary. Paginate session lists and
allow start/end time filters.

### Persistence

Use a rebuildable SQLite derived-state table keyed by session ID, with a
history event watermark and model schema version.

### Completion criteria

- Current and historical sessions can be retrieved.
- Restarting EDGPT does not split or duplicate a session.
- A compact summary stays useful without raw-event expansion.
- Important totals link back to source event ranges for investigation.

## 6. Mission tracking

### Goal

Maintain an actionable current and historical mission state so an LLM can
answer what the commander needs to do next.

### Likely journal inputs

Begin with `Missions`, `MissionAccepted`, `MissionRedirected`,
`MissionCompleted`, `MissionFailed`, and `MissionAbandoned`. Extend with cargo,
passenger, kill, donation, community-goal, and mission-related events only
after confirming their identifiers and lifecycle behavior in fixtures.

### Derived mission fields

- mission ID, type, faction, title, and status;
- origin, destination system/station/body, and target;
- commodity/passenger/item and required/current quantities;
- expiry time and time remaining;
- reward and reputation/influence choices;
- wing/team status where present;
- redirects and objective changes; and
- completion/failure reason when inferable.

### Proposed interfaces

```text
GET /missions
GET /missions?status=active
GET /missions/get?id=...

MCP: get_active_missions
MCP: get_mission
MCP: get_mission_priorities
```

`get_mission_priorities` should remain deterministic and explain its ordering
(expiry, current location, shared destination, cargo readiness); it should not
pretend to know the player's personal priorities.

### Persistence and recovery

Key by Frontier mission ID. Use startup `Missions` snapshots to reconcile
missed events and use journal history to retain completed mission records.

### Completion criteria

- Accept, redirect, complete, fail, and abandon lifecycles are tested.
- Restart reconciliation does not resurrect completed missions.
- Expiry calculations clearly state their timestamp basis.
- Missing optional details degrade gracefully.

## 7. Materials and engineering readiness

### Goal

Answer what materials the commander owns, what changed, and which chosen
engineering or synthesis goals are currently possible.

### Likely inputs

- startup `Materials` snapshots;
- `MaterialCollected`, `MaterialDiscarded`, and `MaterialTrade`;
- `Synthesis`;
- engineer progress/craft events;
- `Backpack.json`, `ShipLocker.json`, and relevant transfer events; and
- current `Loadout` engineering data.

### Proposed state and tools

```text
GET /materials
GET /engineering

MCP: get_material_inventory
MCP: get_material_changes
MCP: get_engineering_readiness
MCP: get_synthesis_options
MCP: compare_loadouts
```

Engineering recipes and module metadata should be versioned static data with a
documented source and game-version compatibility. Do not silently use an
outdated recipe catalog.

### User-defined goals

Allow saved goals such as a blueprint level, experimental effect, synthesis
recipe, or shopping list. Report owned, required, missing, and potential
material-trader conversions separately.

### Completion criteria

- Startup snapshot plus incremental events reconcile correctly.
- Ship, backpack, and locker inventories are not conflated.
- All quantities include provenance/update time.
- Recipe-data version is visible through capabilities/health.

## 8. Exploration annotations and recommendations

### Goal

Turn the existing system map into a practical exploration assistant while
keeping the current simple and full renderings compatible.

### Add an intermediate exploration profile

```text
GET /system-map/exploration
MCP: get_current_system_exploration
MCP: get_saved_system_exploration
```

### Candidate annotations

- expected versus scanned bodies and unresolved scan gaps;
- discovered, mapped, first-discovered, first-mapped, and first-footfall flags;
- landability and atmosphere suitability;
- terraformable status;
- Earth-like, water, ammonia, and other notable body classifications;
- biological, geological, human, guardian, and thargoid signal counts;
- organic genuses/species scanned and incomplete sampling;
- ring type/reserve information;
- estimated exploration/exobiology value, with formula version; and
- bodies that may merit DSS mapping or surface investigation.

### Rules

- Separate facts from recommendations in the output.
- Explain why a body is marked notable.
- Include confidence/provenance when journal data is incomplete.
- Version any value-estimation formula and make clear that it is an estimate.
- Keep the simple map limited unless explicitly revised later.

### Completion criteria

- Annotations merge correctly across repeat visits.
- Barycentre/ring hierarchy remains correct.
- Recommendation rules are deterministic and tested.
- Full raw event access remains available for verification.

## 9. Route and expedition tracking

### Goal

Combine the live navigation route with historical travel into saved expedition
progress and useful route warnings.

### Inputs

- `NavRoute.json` and route-related journal notifications;
- `FSDJump`, `StartJump`, `FSDTarget`, `NavRoute`, and `NavRouteClear` where
  confirmed by fixtures;
- fuel, scoop, neutron/jet-cone, repair, and synthesis events;
- system-map discoveries; and
- optional user-defined waypoints and notes.

### Derived state

- current destination and remaining route systems;
- completed/remaining jumps and distance;
- route deviation and replot detection;
- fuel and jump-range margin;
- scoopable-star and low-fuel warnings;
- neutron/white-dwarf boost status;
- discoveries made during the expedition; and
- elapsed time, travel rate, and estimated remaining time.

### Proposed interfaces

```text
GET /route
GET /expeditions
GET /expeditions/get?id=...

MCP: get_route_progress
MCP: get_route_risks
MCP: create_expedition
MCP: get_expedition_summary
```

Any MCP tool that creates, edits, or deletes an expedition is a mutation and
must be named/documented accordingly. Do not let an AI silently change routes
or notes as a side effect of a read operation.

### Completion criteria

- Empty, cleared, replotted, and completed routes are tested.
- Saved expeditions survive restarts and can be exported/imported.
- Risk warnings state the observed data and rule that triggered them.

## 10. Colonisation tracking

### Goal

Track colonisation projects, construction sites, required commodities, and the
commander's contribution history.

### Discovery work required first

The colonisation journal surface is newer and may change. Before designing the
schema, collect sanitized fixtures from project creation, docking, commodity
delivery, construction progress, completion, and failure/abandonment. Compare
them with current journal documentation and established community tools.

### Candidate state

- project/system identity and build type;
- construction depot/station identity;
- current construction phase and status;
- required, delivered, and remaining commodities;
- commander deliveries and contribution totals;
- nearby relevant market information when available locally; and
- last update time and source confidence.

### Proposed interfaces

```text
GET /colonisation
GET /colonisation/get?id=...

MCP: get_colonisation_projects
MCP: get_colonisation_requirements
MCP: get_colonisation_delivery_plan
```

A delivery plan must distinguish observed inventory/market facts from suggested
loads. External market data should be a separate optional integration with
timestamps and source attribution.

### Completion criteria

- No quantity is inferred from cargo changes unless the inference is explicitly
  labeled and tested.
- Multiple simultaneous projects and depots remain separate.
- Restart and missed-event reconciliation are defined.
- Private project/activity data follows existing relay/privacy controls.

## 11. Streaming events and alerts

### Goal

Let local clients react to state changes without polling large snapshots.

### Initial transport

Prefer Server-Sent Events for the first implementation:

```text
GET /events
GET /events?types=FSDJump,Scan,MissionCompleted
```

Each message should include a monotonically increasing local event ID,
timestamp, event type, and either the raw event or a documented derived-state
change. Define reconnect behavior with `Last-Event-ID` and a bounded retention
window.

### Derived alerts

- low fuel or non-scoopable route risk;
- mission approaching expiry;
- notable/high-value exploration discovery;
- incomplete FSS/DSS work before a jump;
- material/engineering goal reached;
- cargo relevant to the current destination or colonisation project; and
- unhealthy/stale EDGPT component.

Alert rules should be deterministic, configurable, rate-limited, and visible
through capabilities. Keep raw event streaming and derived alerts distinct.

### Completion criteria

- Slow/disconnected clients cannot block journal ingestion.
- Reconnect behavior is tested.
- Filters reduce output without changing stored state.
- No remote listener is enabled by default; loopback remains the default.

## 12. Extension/state-provider framework

### Goal

Make future state models independently implementable after the core patterns
have proven stable.

### Possible internal contract

```python
class StateProvider:
    name = "missions"
    schema_version = 1
    event_types = {"MissionAccepted", "MissionCompleted"}

    def migrate_or_rebuild(self): ...
    def apply_event(self, event_id, event): ...
    def current_state(self): ...
    def health(self): ...
    def capabilities(self): ...
```

The first version should be an internal provider registry, not arbitrary
third-party code execution. Extract existing system-map/session/mission models
only after at least two or three implementations reveal the common contract.

### Later considerations

- isolated third-party providers;
- manifest and compatibility declarations;
- explicit permissions for filesystem, network, secrets, and mutations;
- failure isolation and timeouts;
- provider-specific MCP tools/endpoints; and
- safe install/update/removal behavior.

### Completion criteria

- One broken provider cannot stop core history/state/MCP service.
- Health and capabilities report provider status.
- Provider schemas and migrations are independently versioned.
- Security boundaries are documented before third-party plugins are allowed.

## Cross-cutting work for every roadmap item

Each implementation should include:

1. a written input/output contract;
2. confirmed journal/live-file fixtures;
3. a bounded persistence/query design;
4. HTTP and MCP exposure decisions;
5. privacy and GitHub-relay impact review;
6. development and packaged-build verification;
7. unit, persistence, restart, and integration tests;
8. health/capability registration once those systems exist;
9. README, architecture, changelog, and release-checklist updates; and
10. backward-compatibility notes for existing clients.

## Reference projects and documentation

- [Frontier Journal Manual v31](https://hosting.zaonce.net/community/journal/v31/Journal_Manual_v31.pdf)
- [EDDiscovery feature overview](https://github.com/EDDiscovery/EDDiscovery/wiki/Using-the-Expeditions-Panel)
- [EDDiscovery expedition panel](https://github.com/EDDiscovery/EDDiscovery/wiki/4.-Expedition-Panel)
- [EDDiscovery scan properties](https://github.com/EDDiscovery/EDDiscovery/wiki/4.-Search-Scans-Panel)
- [EDDiscovery releases](https://github.com/EDDiscovery/EDDiscovery/releases)
- [EDMarketConnector plugin documentation](https://github.com/EDCD/EDMarketConnector/blob/main/PLUGINS.md)
- [EDDN schema guidance](https://github.com/EDCD/EDDN/blob/master/schemas/README-EDDN-schemas.md)
