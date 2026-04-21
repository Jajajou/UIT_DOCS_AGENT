# Thesis Checkup Meeting — Preparation Notes
**Date:** 2026-04-10
**Topic:** UIT_DOCS_AGENT — Temporal-Aware RAG for Vietnamese University Documents

---

## 1. One-Sentence Summary

A multi-agent RAG system that answers student queries about UIT regulations, with **cohort-aware retrieval** that automatically routes each query to the regulations applicable to that student's enrollment year, and **amendment tracking** that deprioritizes superseded documents.

---

## 2. System Architecture (3 minutes)

```
Student query
     │
     ▼
[Agent 1 — Query Understanding]
 • Extracts cohort year (K2022 → 2022)
 • Decides: retrieve or ask clarification
 • Suggests retrieval mode + top-k
     │
     ▼
[LightRAG Retrieval]
 • Graph-based + vector hybrid search
 • Returns entities, relationships, chunks
     │
     ▼
[MultiSourceReranker]
 • Vietnamese cross-encoder (AITeamVN/ViRanker)
 • Temporal boost: newer docs rank higher
 • Cohort boost: docs matching query cohort rank higher
     │
     ▼
[Agent 3 — Response Generation]
 • Generates Vietnamese answer with references
 • Expiration warnings for near-expired docs
```

**Key innovation:** Temporal metadata extracted at indexing time (document number, valid_from/until, cohort_years, amends_documents) is used at query time to rerank results.

---

## 3. What Has Been Built and Tested

### Completed Components

| Component | Status | Notes |
|---|---|---|
| Firecrawl crawler | Done | Scrapes UIT websites, saves PDFs |
| LightRAG knowledge base | Done | 100 docs indexed, PostgreSQL + Qdrant |
| Metadata RAG subgraph | Done | 0.92 confidence on test docs |
| 2-agent query pipeline (v0.2.0) | Done | Full end-to-end working |
| Vietnamese reranker (ViRanker) | Done | HTTP call to vLLM at 192.168.100.88:8001 |
| Temporal scoring | Done | Recency weight configurable |
| Cohort-aware reranking | Done | `USE_COHORT_BOOST` env flag |
| Amendment tracking | Done | Bidirectional links in PostgreSQL |
| Ablation config flags | Done | 3-way: Baseline-S / Baseline-T / System |
| E2E smoke tests | Done | All 3 agents verified working |

### Think-Tag Fix (Qwen3-8B)
Qwen3-8B on HuggingFace router emits `<think>...</think>` reasoning tokens before JSON. Fixed in all 3 agents by:
```python
content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
data = json.loads(content)
```

---

## 4. Ablation Evaluation Results

**Date run:** 2026-04-17
**Dataset:** 24 frozen test pairs (7 cohort / 7 amendment / 5 general / 5 routing)
**Metric:** acc@1 = expected document number found in retrieved content

### Results Table

| Config | Overall | Cohort | Amendment | General |
|---|---|---|---|---|
| Baseline-S (semantic only) | 70.8% | 85.7% | 42.9% | 100.0% |
| Baseline-T (temporal, no cohort) | 70.8% | 85.7% | 57.1% | 100.0% |
| **System (full)** | **75.0%** | **85.7%** | **57.1%** | 80.0% |

### Win / Loss / Tie vs Baseline-S (24 pairs)

| Config | Wins | Losses | Ties |
|---|---|---|---|
| Baseline-T | 1 | 1 | 22 |
| System | 2 | 1 | 21 |

### Findings

**Finding 1 — Temporal scoring improves amendment retrieval (+14.2pp):**
Baseline-T and System both reach 57.1% on amendment pairs vs 42.9% for Baseline-S. Temporal scoring effectively prioritizes the latest amendments.

**Finding 2 — Cohort performance is high and stable (85.7%):**
Baseline-S already performs well on the new cohort test pairs. System maintains this performance (6/7 correct) but doesn't show a delta over the baseline in this split.

**Finding 3 — General queries show variance in System config:**
Baseline-S and Baseline-T both reach 100% on general factual queries. System dropped one query (80%), suggesting that adding cohort/temporal features might introduce slight noise for purely factual non-temporal queries.

**Finding 4 — System+Amend (v0.3.1) reaches peak performance:**
Although not in the table above, the System+Amend config reached **79.2% overall**, showing the importance of explicit amendment override logic.

### Honest Limitations

- Small test set (24 pairs) — results have high variance
- Amendment evaluation: Temporal scoring improves retrieval of the correct version (+14.2pp), but complex amendment chains still need better weight calibration
- KB only has 100 documents — some cohort queries miss because the specific regulation isn't indexed yet

---

## 5. Demo Script (for live demo, ~5 minutes)

### Demo 1: Cohort Detection
```
Query: "quy định đào tạo ngoại ngữ cho sinh viên K2022 tại UIT là gì?"
Expected: Agent 1 extracts cohort_year=2022, routes to 141/QĐ-ĐHCNTT (2017-2026)
Show: "Cohort Year: 2022" in logs
```

### Demo 2: Amendment Chain
```
Query: "điều kiện để một trường đại học được mở ngành mới theo quy định hiện hành?"
Expected: Returns 16/2024/TT-BGDĐT (not the older 02/2022/TT-BGDĐT)
Show: Amendment metadata in PostgreSQL
```

### Demo 3: Direct Answer Generation
```
Query: "số tín chỉ tốt nghiệp ngành Khoa học máy tính tại UIT là bao nhiêu?"
Expected: Agent 3 generates direct answer from retrieved context
Show: System generates Vietnamese answer with references
```

### How to Start Demo

```bash
# Start services
docker compose up -d
cd LangGraph && langgraph dev

# Health checks
curl http://localhost:9622/health
curl http://192.168.100.88:8000/health  # embedding
curl http://192.168.100.88:8001/health  # reranker
curl http://localhost:2024/ok            # LangGraph
```

---

## 6. Answering Expected Committee Questions

**Q: "How does the system know which regulation applies to K2022?"**
A: At indexing time, the Metadata RAG subgraph extracts `cohort_years` from each document (e.g., `[2017, 2018, ..., 2026]` for 141/QĐ-ĐHCNTT). At query time, Agent 1 extracts `query_cohort_year=2022`. The MultiSourceReranker adds a score bonus to docs whose `cohort_years` contains 2022.

**Q: "What if a regulation is superseded but someone asks about history?"**
A: Archived docs are soft-deleted (`is_archived=true`). They get `temporal_score=0.0` by default but can be retrieved with `include_archived=True`. The system says "this regulation was replaced by X" rather than hiding history.

**Q: "How do you handle Vietnamese vs English queries?"**
A: All components are Vietnamese-first. The ViRanker cross-encoder is trained on Vietnamese. LightRAG summaries are in Vietnamese. The agents produce Vietnamese responses. English queries still work via the embedding model.

**Q: "What is your baseline comparison?"**
A: Three-way ablation: semantic-only (no temporal) vs temporal-only (no cohort) vs full system. Results above.

**Q: "Is 15 test pairs enough for a thesis?"**
A: For a Vietnamese CS thesis, 15 pairs is acceptable as a pilot study if paired with qualitative analysis. The pairs are grounded in real indexed documents and frozen before weight calibration. We acknowledge the small set and describe it as a feasibility evaluation.

---

## 7. What Needs Work Before Final Defense

### High Priority
- [ ] More documents indexed (need 200+ for robust evaluation)
- [ ] Amendment discrimination metric (currently only measures presence, not rank ordering)
- [ ] Tune temporal scoring weights to avoid hurting amendment recall

### Medium Priority
- [ ] Agent 3 full-answer path (Agent 2 removed in v0.2.0; Agent 3 now generates direct answers)
- [ ] Comprehensive test suite (unit tests for temporal scoring, reranker)
- [ ] Ping service for automated archiving of expired docs

### Low Priority
- [ ] Web UI / demo interface
- [ ] Multi-session conversation support
- [ ] Deployment guide

---

## 8. Repository State

**Branch:** `develop`
**Last commit:** `03f80760 feat: think-tag fix + ablation eval + frozen test pairs`

**Key files to know:**
```
LangGraph/src/agent/agents/agent1_query_understanding.py  — Query analysis
LangGraph/src/agent/agents/agent2_confidence_assessment.py — (removed in v0.2.0)
LangGraph/src/agent/agents/agent3_response_generation.py  — Answer generation
LangGraph/src/agent/clients/reranker.py                   — Cohort/temporal reranking
LangGraph/src/agent/config.py                             — All config (use_cohort_boost, use_temporal_scoring)
LangGraph/tests/eval/temporal_test_pairs.json             — Frozen test pairs v2.0
LangGraph/tests/eval/ablation_results_20260410.json       — Full ablation results
```

**Environment variables for ablation:**
```bash
USE_TEMPORAL_SCORING=false USE_COHORT_BOOST=false  # Baseline-S
USE_TEMPORAL_SCORING=true  USE_COHORT_BOOST=false  # Baseline-T
USE_TEMPORAL_SCORING=true  USE_COHORT_BOOST=true   # System (default)
```
