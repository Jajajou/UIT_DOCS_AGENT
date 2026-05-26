---
phase: 04-sprint-a-system-completeness-bug-fixes-citation-url-educatio
plan: "01"
subsystem: agent3-citation-urls
tags: [bug-fix, citation, url-resolution, tdd]
dependency_graph:
  requires: []
  provides: [citation-url-resolution]
  affects: [LangGraph/src/agent/agents/agent3_response_generation.py]
tech_stack:
  added: []
  patterns: [get_url resolver, fallback pattern]
key_files:
  created:
    - LangGraph/tests/unit_tests/test_citation_url.py
  modified:
    - LangGraph/src/agent/agents/agent3_response_generation.py
decisions:
  - "Used get_url() with fallback to raw path rather than erroring on unresolvable paths"
  - "Also patched _format_reranked_data source line for consistent URL display in prompt"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-23"
  tasks_completed: 2
  files_changed: 2
---

# Phase 04 Plan 01: Citation URL Fix Summary

**One-liner:** Patch `_extract_references()` to resolve filesystem paths to HTTPS URLs via `get_url()` with raw path fallback.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write failing tests (RED) | b805eaef | LangGraph/tests/unit_tests/test_citation_url.py |
| 2 | Patch _extract_references (GREEN) | 1e1c0f3f | LangGraph/src/agent/agents/agent3_response_generation.py |

## What Was Done

Bug A1: `_extract_references()` was setting `url: file_source` directly (raw filesystem path like `firecrawl/data/daa/.../file.pdf`). Users clicking references got no valid link.

Fix: added `from agent.utils import get_url` and replaced the URL assignment with:
```python
resolved_url = get_url(file_source) if file_source else None
references.append({"url": resolved_url or file_source, ...})
```

Also updated `_format_reranked_data` source display for consistency.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `/Users/jajajou1778/UIT_DOCS_AGENT/.claude/worktrees/agent-a9ed4d5a0c3e0c2c9/LangGraph/tests/unit_tests/test_citation_url.py` - FOUND
- `/Users/jajajou1778/UIT_DOCS_AGENT/.claude/worktrees/agent-a9ed4d5a0c3e0c2c9/LangGraph/src/agent/agents/agent3_response_generation.py` - FOUND
- Commit b805eaef - FOUND
- Commit 1e1c0f3f - FOUND
- 5 tests pass GREEN - VERIFIED
