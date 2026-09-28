# EDGPT Ideas

This document collects possibilities for discussion, not agreed implementation
work. Ideas can move into [ROADMAP.md](ROADMAP.md) once their purpose and scope
are clear.

## Saved expeditions and MCP reporting

**Status: needs more brainstorming.** Moved from roadmap item 9 (route and
expedition tracking). No implementation or interface design is agreed yet.

### Why it might be useful

A saved expedition could group travel across multiple play sessions into a
named journey. An LLM could access its facts through MCP and write a progress
report, captain's log, or final trip report. EDGPT would supply recorded facts;
the LLM would compose the narrative.

Session summaries describe individual play sessions. An expedition would add
a trip-level grouping over existing history, sessions, and system maps.

### Possible workflow

- Mark the start of a named trip, then end it when the journey is finished.
- Alternatively, select a past date range to describe a trip retrospectively.
- Ask an LLM for progress so far, notable discoveries, or a final report.
- Optionally add personal notes or waypoints to give the report context.

Possible report inputs include systems visited, jumps and distance travelled,
time spent, session summaries, and recorded exploration discoveries. Source
references and incomplete-data indicators would help keep reports grounded.

### Questions to explore

- Is a saved name and date range enough, or does a trip need explicit membership
  rules for sessions and events?
- Should trips be started and ended manually, defined afterward, or support both?
- Which report details would make this more useful than querying session history?
- How should detours, overlapping trips, and discoveries revisited later work?
- Are notes, waypoints, export, or import useful enough to include?
- What bounded MCP summary and detail queries would an LLM need?

Any future MCP operations that create or edit expeditions should be explicit
mutations. Reading an expedition should not change its definition or notes.

### Separate possibility: live route assistance

The original roadmap proposal also included remaining jumps and distance,
replot/deviation detection, fuel and scoopability warnings, boost status, and
estimated arrival time, using the live navigation route and journal events.

These serve in-flight assistance rather than trip reporting and are not required
for saved expeditions. Their usefulness and data requirements remain open for
discussion; they could be considered independently later.
