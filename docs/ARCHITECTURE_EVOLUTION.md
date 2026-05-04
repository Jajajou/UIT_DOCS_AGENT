# Architecture Evolution: 3-Agent to 2-Agent Pipeline

**Last Updated:** 2026-04-14
**Version:** v0.2.0

This document explains the transition from the original 3-agent pipeline to the current 2-agent pipeline.

---

## Before: v0.1.x — 3-Agent Pipeline

```
User Query
  -> Agent 1 (Query Understanding)
       |
       +--[confidence < 0.5]--> ask_clarification (DEAD END for most queries)
       |
       v
  -> Retrieval (LightRAG: entities, relationships, chunks)
       v
  -> Reranking (MultiSourceReranker)
       v
  -> Agent 2 (Confidence Assessment)
       |
       +--[quality < 0.4]--> fallback_response
       |
       +--[quality 0.4-0.7]--> partial_answer
       |
       +--[quality >= 0.7]--> full_answer
       v
  -> Agent 3 (Response Generation)
       v
  -> format_final_answer
```

Agent 2 was a pure scoring node. It evaluated data quality, applied temporal penalties, and decided whether to route to full/partial/fallback responses.

---

## After: v0.2.0 — 2-Agent Linear Pipeline

```
prepare_input
  -> agent1_understand_query
  -> retrieve_data
  -> enrich_with_temporal_metadata
  -> rerank_data
  -> agent3_generate_response
  -> format_final_answer
```

Agent 3 now always produces a direct answer. It synthesizes retrieved data and handles cases where data is insufficient gracefully, without a separate confidence gate.

---

## Why the Change

Agent 2 caused problems:
1. Clarification gating: Agent 1 confidence < 0.5 routed to ask_clarification, which triggered on most real queries due to short/ambiguous Vietnamese questions. Users never got answers.
2. Fallback gating: Agent 2 quality < 0.4 triggered fallback responses instead of letting Agent 3 try. This masked retrievable information.
3. Dead code: ~400 lines of Agent 2 scaffolding (Pydantic models, prompts, state fields) added complexity without value.

Temporal freshness (the core value of Agent 2's scoring) is now handled by the MultiSourceReranker with amendment override and cohort boosting. Agent 3 has the context to handle low-quality retrieval gracefully.

For the full design rationale, see TECHNICAL_REPORT_COMPREHENSIVE.md Section 9.1.2.

---

## State Field Migration

| Removed Field | Was Written By | Replacement |
|--------------|---------------|-------------|
| `data_quality_score` | Agent 2 | Inferred from reranking scores |
| `data_coverage` | Agent 2 | Removed — not needed |
| `should_fallback` | Agent 2 | Agent 3 decides directly |
| `overall_confidence` | Agent 2 | Removed — no separate assessment |
| `confidence_reason` | Agent 2 | Removed |
| `needs_followup` | Agent 2 | Removed |
| `followup_question` | Agent 2 | Removed |
| `needs_clarification` | Agent 1 | Removed — all queries proceed |
| `clarification_question` | Agent 1 | Removed |

---

## Code Files Affected

| File | Change |
|------|--------|
| `LangGraph/src/agent/agents/agent2_confidence_assessment.py` | Removed entirely |
| `LangGraph/src/agent/graphs/query_graph.py` | Simplified — linear add_edge instead of conditional routing |
| `LangGraph/src/agent/states/query_state.py` | 9 fields removed |
| `LangGraph/src/agent/core/prompts.py` | 3 prompt blocks removed (confidence_assessment, data_quality, fallback) |
| `LangGraph/src/agent/agents/agent1_query_understanding.py` | needs_clarification output removed |
| `LangGraph/src/agent/agents/agent3_response_generation.py` | file_path/file_source bug fixed |

---

## Archive

The original 3-agent design document is preserved at:
`docs/archive/2_agent_rag_design_deprecated.md`

It contains the full original design with Agent 2 specifications — useful for thesis committee questions about the evolution.
