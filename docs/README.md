# UITRaph Documentation

**UITRaph: A Graph-Enhanced Retrieval-Augmented Generation Framework with Temporal Document Management for UIT Knowledge Resources**

> Thesis Project by Đặng Trần Long (22520805) & Hoàng Bảo Long (22520807)
> Advisors: Ths. Phạm Nguyễn Phúc Toàn, Ts. Lưu Thanh Sơn

---

## Documentation Structure

### Architecture
- [System Overview](ARCHITECTURE_DIAGRAM.md) - High-level system architecture
- Data Flow - Indexing & query pipeline flows (see [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md))
- Technology Stack - Components, services & dependencies (see [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md))

### Implementation
- [Metadata RAG Subgraph](implementation/metadata-rag-subgraph.md) - **Phase 1** (Current)
- [Temporal Scoring](implementation/temporal-scoring.md) - Temporal reranking algorithm
- [Hybrid RAG Architecture](implementation/hybrid-retrieval.md) - **Phase 2** (Planned)
- Track_id Innovation - Novel contribution (see [Temporal Implementation Summary](implementation/TEMPORAL_IMPLEMENTATION_SUMMARY.md))

### Research
- Temporal RAG Survey - EMNLP 2024/2025 papers (planned)
- [Novel Contributions](research/novel-contributions.md) - What makes UITRaph unique
- [Comparison Table](research/comparison-table.md) - vs GraphRAG, LightRAG, T-GRAG, VersionRAG

### Guides
- [Setup Guide](../README.md) - Installation & configuration (root README)
- Development Guide - Development workflow (see [CLAUDE.md](../CLAUDE.md))
- Testing Guide - Testing strategies & benchmarks (see [CLAUDE.md](../CLAUDE.md))

### Thesis
- [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) - **Main thesis document**
- [Progress Log](PROGRESS_LOG.md) - Implementation timeline
- Evaluation Plan - Testing & metrics (see [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md))

---

## Current Phase: Metadata RAG Subgraph

**Status:** COMPLETE (Phase 1.5)

**Goal:** Build a dedicated RAG pipeline for extracting temporal metadata from documents.

**Novel Contribution:**
- RAG-based metadata extraction (0.92 confidence vs 0.5-0.6 regex-only)
- 6-node workflow: chunk → index → query → confidence → validate → cleanup
- Temporal-aware chunking (1024 tokens for metadata context)
- Two-stage retrieval: Bi-encoder (Vietnamese_Embedding_V2) → Cross-encoder (ViRanker)
- Instant metadata save using track_id approach (60x faster, NO POLLING)
- Pydantic validation with DocumentMetadata model

**See:** [implementation/metadata-rag-subgraph.md](implementation/metadata-rag-subgraph.md)

---

## Next Phase: Hybrid RAG

**Status:** Planned (Week 2-3)

**Goal:** Implement full hybrid retrieval architecture with metadata pre-filtering.

**Novel Contribution:**
- Two separate RAG pipelines (metadata vs content)
- Specialized chunking strategies (1024 for metadata, 512 for content)
- Temporal pre-filtering before semantic search
- Cohort-aware retrieval

**See:** [implementation/hybrid-retrieval.md](implementation/hybrid-retrieval.md)

---

## Key Metrics (Current)

| Metric | Value | Notes |
|--------|-------|-------|
| **Temporal Extraction Confidence** | **0.92 (Excellent)** | Metadata RAG Subgraph (vs 0.5-0.6 regex) |
| **Metadata Save Time** | **Instant (<1s)** | Track_id approach (vs 15-30s polling) |
| **Indexing Speed** | 8.5 min | 150 documents (includes OCR + graph) |
| **Query Confidence Accuracy** | 93% | 2-agent pipeline with ViRanker (v0.2.0) |
| **Temporal Scoring** | 70% semantic + 30% temporal | Expired docs get 0.5 penalty |

**See:** [thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá)

---

## Quick Links

### For Developers
- [Setup Guide](../README.md) - Get started in 10 minutes (root README)
- [Development Workflow](../CLAUDE.md) - How to add features
- Testing - Run tests & benchmarks (see [CLAUDE.md](../CLAUDE.md))

### For Researchers
- [Novel Contributions](research/novel-contributions.md) - What's new in UITRaph
- Temporal RAG Survey - State of the art (planned)
- [Comparison Table](research/comparison-table.md) - How UITRaph compares

### For Thesis Committee
- [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) - Full thesis
- [System Architecture](ARCHITECTURE_DIAGRAM.md) - High-level design
- [Evaluation Results](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá) - Performance metrics

---

## Contributing to Documentation

When implementing new features:

1. **Before coding:** Document the design in `implementation/`
2. **While coding:** Update progress in `PROGRESS_LOG.md`
3. **After coding:** Document the implementation details
4. **Add tests:** Document test coverage in the technical report

**Example workflow:**
```bash
# 1. Document design
docs/implementation/new-feature.md

# 2. Implement feature
LangGraph/src/agent/...

# 3. Update progress
docs/PROGRESS_LOG.md

# 4. Document tests
docs/thesis/TECHNICAL_REPORT_COMPREHENSIVE.md
```

---

## Timeline

| Phase | Duration | Status | Documents |
|-------|----------|--------|-----------|
| **Phase 1.5: Metadata RAG** | Week 1 | COMPLETE | [metadata-rag-subgraph.md](implementation/metadata-rag-subgraph.md) |
| **Phase 2: Agent Integration** | Week 2 | COMPLETE | v0.2.0: 2-agent pipeline COMPLETE |
| **Phase 3: Testing & Evaluation** | Week 3-4 | Planned | [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) |
| **Phase 4: Thesis Writing** | Week 5-6 | Planned | [TECHNICAL_REPORT_COMPREHENSIVE.md](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) |

---

## Key Innovations

1. **Temporal Document Management** - Full temporal lifecycle (validity, amendments, archiving)
2. **Track_id Approach** - 60x faster metadata save (no polling)
3. **Hybrid RAG Architecture** - Specialized pipelines for metadata vs content
4. **Vietnamese-Optimized** - Regex patterns, ViRanker, Vietnamese LLM

---

## Contact

- **Students:** Đặng Trần Long, Hoàng Bảo Long
- **Institution:** UIT - VNUHCM
- **Project:** UITRaph - Temporal RAG for University Knowledge

---

**Last Updated:** 2026-04-14
**Version:** 0.2.0 (2-agent pipeline -- Agent 2 removed, dead code purged)
