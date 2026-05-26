---
phase: 04-sprint-a-system-completeness-bug-fixes-citation-url-educatio
plan: "03"
subsystem: education-system-routing
tags: [bug-fix, education-system, routing, db-migration]
dependency_graph:
  requires: []
  provides: [education-system-classification, education-system-routing]
  affects:
    - LangGraph/src/agent/states/query_state.py
    - LangGraph/src/agent/agents/agent1_query_understanding.py
    - LangGraph/src/agent/core/prompts.py
    - LangGraph/src/agent/graphs/query_graph.py
    - LangGraph/scripts/backfill_education_system.py
tech_stack:
  added: []
  patterns: [db-classification, literal-field, filter-guard]
key_files:
  created:
    - LangGraph/scripts/backfill_education_system.py
  modified:
    - LangGraph/src/agent/states/query_state.py
    - LangGraph/src/agent/agents/agent1_query_understanding.py
    - LangGraph/src/agent/core/prompts.py
    - LangGraph/src/agent/graphs/query_graph.py
decisions:
  - "Default chinh_quy is safe majority case; wrong classification = broader results, not data leak"
  - "Items with education_system=None or universal always pass the filter (ministry docs)"
  - "KNOWN_OVERRIDES hardcodes 507/QD-DHCNTT as tu_xa before pattern matching"
metrics:
  duration: "~30 minutes"
  completed: "2026-05-23"
  tasks_completed: 3
  files_changed: 5
---

# Phase 04 Plan 03: Education System Routing Summary

**One-liner:** Add `education_system` field (chinh_quy/tu_xa/tien_tien/song_nganh) to DB, Agent 1, QueryState, and filter_by_metadata to prevent cross-system document contamination.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | DB schema + classification via mcp__postgres__query + Qdrant backfill script | a700943e | LangGraph/scripts/backfill_education_system.py |
| 2 | Human checkpoint (approved) | — | — |
| 3 | Add education_system to Agent 1 + prompts + QueryState + filter | 59bb97fa | 4 files |

## What Was Done

Bug A3: 507/QD-DHCNTT (tu xa regulations) was mixing with chinh_quy results. Students asking about chinh_quy got tu xa docs in results.

**Task 1 (DB):**
- ALTER TABLE temporal_metadata ADD COLUMN education_system TEXT DEFAULT 'universal'
- Classified all 163 docs: chinh_quy=97, universal=58, song_nganh=5, tien_tien=2, tu_xa=1
- 507/QD-DHCNTT confirmed tu_xa (KNOWN_OVERRIDES applied)
- backfill_education_system.py created for Qdrant payload update (no psycopg2)

**Task 3 (Code):**
- `QueryUnderstanding` model: added `education_system: Literal[...]` field with default chinh_quy
- `QueryState`: added `education_system: NotRequired[Optional[Literal[...]]]`
- `agent1_query_understanding.py`: extracts `education_system` from LLM output, returns in state
- `prompts.py`: added `<education_system_detection>` section with tu_xa/tien_tien/song_nganh keywords + added field to output_format JSON schema
- `query_graph.py filter_by_metadata`: added education_system filter -- items from different edu system (not universal) are dropped

## DB State (verified via mcp__postgres__query)

```
chinh_quy  | 97
universal  | 58
song_nganh |  5
tien_tien  |  2
tu_xa      |  1 (507/QD-DHCNTT)
```

## Self-Check: PASSED

- education_system in QueryUnderstanding: FOUND (line 91)
- education_system in QueryState: FOUND (line 196)
- education_system in agent1: FOUND (3 lines)
- tu_xa in prompts.py: FOUND (4 lines)
- filter_by_metadata education_system guard: FOUND
- Import check: `education_system=chinh_quy` default verified
- 67/68 tests pass (1 pre-existing failure in test_lightrag_client unrelated to this plan)
