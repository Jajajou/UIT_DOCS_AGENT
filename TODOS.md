# Project TODOs — 2026-06-06

## Status: THESIS-READY (acc@1 = 0.815)

All P0/P1 tasks from May 12 are DONE.

## Completed

- [x] Run ablation study: BM25, Gemini no-RAG, Naive RAG, Full System
- [x] Reach 80% accuracy milestone (v0.5.0.0)
- [x] Push to 81.5% (0605_thinking_eval_run2)
- [x] Add MRR@3 metric to eval pipeline
- [x] Fix Qdrant cohort filter (is_empty bug)
- [x] Fix reranker 400 truncation
- [x] Temporal decay + point-in-time precision in reranker
- [x] Cohort boost in reranker
- [x] Clean thinking prompt for agent3
- [x] Add education_system field
- [x] Chapter 3 design evolution section (design doc written)

## Optional (not blocking thesis)

- [ ] LLM-as-judge eval (30 pairs, reference-grounded) — qualitative case study
- [ ] Commit `LangGraph/src/agent/agents/agent1_query_understanding.py`
- [ ] Update CLAUDE.md project status section

## Known Weak Points (for thesis defense prep)

- **amendment_boundary** = 0.69 (13/42 fail) — temporal amendment chain sometimes retrieves older doc
- **admissions_boundary** = 0.68 (6/19 fail) — DHQG-level vs UIT-level authority confusion
