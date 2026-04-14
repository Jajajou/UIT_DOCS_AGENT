# Documentation Index — UIT_DOCS_AGENT

**Last Updated:** 2026-04-14

One-page navigation guide for 20+ documentation files.

---

## Start Here by Role

### Developer (new to the project)
1. README.md — project overview, setup, running services
2. CLAUDE.md — current phase, active work, development commands
3. SESSION_HANDOFF.md — current status and quick start
4. LangGraph/docs/STATE_PASSING_GUIDE.md — how data flows between nodes

### Thesis Committee
1. docs/thesis/TECHNICAL_REPORT_COMPREHENSIVE.md — full system design and rationale
2. docs/ARCHITECTURE_DIAGRAM.md — visual system architecture
3. docs/thesis/MEETING_PREP_20260410.md — demo prep and Q&A readiness
4. CHANGELOG.md — version history with rationale

### Feature Contributor
1. CLAUDE.md — patterns, conventions, development commands
2. LangGraph/docs/STATE_PASSING_GUIDE.md — state management
3. LangGraph/docs/PROMPTS_MIGRATION_GUIDE.md — adding/modifying prompts
4. TODO.md — open tasks and priorities

---

## All Documentation Files

| File | Purpose | Audience | Status |
|------|---------|----------|--------|
| README.md | Project overview, setup | Everyone | [AUTHORITATIVE] |
| CLAUDE.md | Dev guidelines, architecture, commands | Developer | [AUTHORITATIVE] |
| CHANGELOG.md | Version history | Everyone | [AUTHORITATIVE] |
| DESIGN.md | UI/UX design system | Frontend | [AUTHORITATIVE] |
| SESSION_HANDOFF.md | Current session context, quick start | Developer | Updated per session |
| TODO.md | Task tracking with priorities | Developer | Updated per session |
| TESTING_CHECKLIST.md | Testing procedures | Developer | |
| QUICK_REFERENCE_PERFORMANCE.md | Performance config reference | Developer | |
| docs/README.md | Documentation navigation | Everyone | |
| docs/ARCHITECTURE_DIAGRAM.md | Full system architecture diagram | Developer, Thesis | |
| docs/PROGRESS_LOG.md | Development progress log | Developer | |
| docs/technical_report.md | Technical report (short) | Thesis | |
| docs/thesis/TECHNICAL_REPORT_COMPREHENSIVE.md | Full thesis technical report | Thesis Committee | |
| docs/thesis/MEETING_PREP_20260410.md | Thesis defense prep | Thesis | |
| docs/implementation/TEMPORAL_IMPLEMENTATION_SUMMARY.md | Temporal features status | Developer | |
| docs/implementation/temporal-scoring.md | Temporal scoring design | Developer | |
| docs/implementation/hybrid-retrieval.md | Retrieval design | Developer | |
| docs/implementation/metadata-rag-subgraph.md | Metadata RAG design | Developer | |
| docs/research/comparison-table.md | RAG comparison research | Thesis | |
| docs/research/novel-contributions.md | Novel contributions | Thesis | |
| LangGraph/docs/STATE_PASSING_GUIDE.md | State management guide | Developer | |
| LangGraph/docs/PROMPTS_MIGRATION_GUIDE.md | Prompt system guide | Developer | |
| DOCUMENTATION_INDEX.md | This file | Everyone | |

### Archived (docs/archive/)
| File | Original | Archived |
|------|---------|----------|
| docs/archive/2_agent_rag_design_deprecated.md | LangGraph/docs/2_agent_rag_design.md | v0.2.0 |
| docs/archive/SESSION_HANDOFF_20260410.md | SESSION_HANDOFF.md | 2026-04-10 |
| docs/archive/PERFORMANCE_OPTIMIZATION_M1_20251229.md | PERFORMANCE_OPTIMIZATION_M1.md | 2026-04-14 |
| docs/archive/BAO_CAO_TIEN_DO_22_12_2024.md | Original Dec 2024 report | — |

---

## Navigation by Question

**"Why was Agent 2 removed?"**
→ CHANGELOG.md [0.2.0] + docs/thesis/TECHNICAL_REPORT_COMPREHENSIVE.md Section 9.1.2

**"How does the query pipeline work?"**
→ docs/ARCHITECTURE_DIAGRAM.md + LangGraph/docs/STATE_PASSING_GUIDE.md

**"What's the current state of the project?"**
→ SESSION_HANDOFF.md + TODO.md

**"How do I add a new agent or node?"**
→ CLAUDE.md section "Adding a New Agent to Query Pipeline"

**"How does temporal scoring work?"**
→ docs/implementation/temporal-scoring.md + docs/implementation/TEMPORAL_IMPLEMENTATION_SUMMARY.md

**"What are the ablation results?"**
→ docs/thesis/TECHNICAL_REPORT_COMPREHENSIVE.md Section 7 (NOTE: update pending after ablation re-run)

---

## Dependency Graph

To understand X, read Y first:

```
TECHNICAL_REPORT_COMPREHENSIVE.md
  <- docs/ARCHITECTURE_DIAGRAM.md
  <- LangGraph/docs/STATE_PASSING_GUIDE.md
  <- README.md

LangGraph/docs/STATE_PASSING_GUIDE.md
  <- CLAUDE.md (state patterns)
  <- LangGraph/src/agent/states/query_state.py (source of truth)

docs/implementation/temporal-scoring.md
  <- docs/implementation/TEMPORAL_IMPLEMENTATION_SUMMARY.md
  <- LangGraph/src/agent/clients/reranker.py (source of truth)
```
