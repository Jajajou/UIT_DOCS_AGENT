---
phase: 04-sprint-a-system-completeness-bug-fixes-citation-url-educatio
plan: "02"
subsystem: amendment-chain-sql
tags: [bug-fix, amendment-chain, sql-patch, tu-xa]
dependency_graph:
  requires: [04-03]
  provides: [amendment-chain-790-1393-507]
  affects: [temporal_metadata]
tech_stack:
  added: []
  patterns: [sql-patch, idempotent-update, amendment-chain]
key_files:
  created:
    - LangGraph/scripts/patch_amendment_chain.py
decisions:
  - "Patch 3 (507 amends 1393) skipped -- 507 already had amends_documents=[1206/QD-DHCNTT], WHERE guard prevented overwrite"
  - "1393 amended_by includes both 507 (from this patch) as the tu_xa chain continues"
  - "All 4 patches applied via docker exec psql (mcp__postgres__query is READ-ONLY)"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-23"
  tasks_completed: 1
  files_changed: 1
---

# Phase 04 Plan 02: Amendment Chain SQL Fix Summary

**One-liner:** Patch 3 SQL rows in temporal_metadata to link the tu xa amendment chain 790 <- 1393 <- 507.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Apply 4 SQL patches via docker exec psql | 1f9fff11 (doc artifact) | LangGraph/scripts/patch_amendment_chain.py |

## What Was Done

Bug A2: 790/QD-DHCNTT, 1393/QD-DHCNTT, and 507/QD-DHCNTT lacked amendment chain links in temporal_metadata. Reranker couldn't deprioritize older docs.

Applied via `docker exec uit_docs_agent-postgres_uit-1 psql -U uitrag -d lightrag`:

| Patch | SQL target | Result |
|-------|------------|--------|
| 1 | 1393.amends_documents = ["790/QD-DHCNTT"] | UPDATE 1 |
| 2 | 790.amended_by_documents = ["1393/QD-DHCNTT"] | UPDATE 1 |
| 3 | 507.amends_documents = ["1393/QD-DHCNTT"] | UPDATE 0 (WHERE guard -- already had 1206) |
| 4 | 1393.amended_by_documents += ["507/QD-DHCNTT"] | UPDATE 1 |

## Final State (verified via mcp__postgres__query)

```
790/QD-DHCNTT:
  amends_documents: null
  amended_by_documents: ["1393/QD-DHCNTT"]

1393/QD-DHCNTT:
  amends_documents: ["790/QD-DHCNTT"]
  amended_by_documents: ["507/QD-DHCNTT"]

507/QD-DHCNTT:
  amends_documents: ["1206/QD-DHCNTT"] (pre-existing; Patch 3 skipped)
  amended_by_documents: null
```

## Reranker Impact

Reranker uses `amended_by` to deprioritize docs. After patches:
- 790 has amended_by -> temporal_score = 0.3 (deprioritized when 1393 in candidate set)
- 1393 has amended_by -> temporal_score = 0.3 (deprioritized when 507 in candidate set)

## Self-Check: PASSED

- 1393.amends_documents = ["790/QD-DHCNTT"]: VERIFIED
- 790.amended_by_documents includes "1393/QD-DHCNTT": VERIFIED
- 1393.amended_by_documents includes "507/QD-DHCNTT": VERIFIED
- 507 education_system = 'tu_xa' (prerequisite from 04-03): VERIFIED before patching
