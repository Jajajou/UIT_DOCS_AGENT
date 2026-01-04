# UITRaph Documentation

**UITRaph: A Graph-Enhanced Retrieval-Augmented Generation Framework with Temporal Document Management for UIT Knowledge Resources**

> Thesis Project by Đặng Trần Long (22520805) & Hoàng Bảo Long (22520807)
> Advisors: Ths. Phạm Nguyễn Phúc Toàn, Ts. Lưu Thanh Sơn

---

## 📚 Documentation Structure

### 🏗️ Architecture
- [System Overview](architecture/system-overview.md) - High-level system architecture
- [Data Flow](architecture/data-flow.md) - Indexing & query pipeline flows
- [Technology Stack](architecture/technology-stack.md) - Components, services & dependencies

### 💻 Implementation
- [Metadata RAG Subgraph](implementation/metadata-rag-subgraph.md) - **Phase 1** (Current)
- [Temporal Scoring](implementation/temporal-scoring.md) - Temporal reranking algorithm
- [Hybrid RAG Architecture](implementation/hybrid-retrieval.md) - **Phase 2** (Planned)
- [Track_id Innovation](implementation/track-id-innovation.md) - Novel contribution

### 🔬 Research
- [Temporal RAG Survey](research/temporal-rag-survey.md) - EMNLP 2024/2025 papers
- [Novel Contributions](research/novel-contributions.md) - What makes UITRaph unique
- [Comparison Table](research/comparison-table.md) - vs GraphRAG, LightRAG, T-GRAG, VersionRAG

### 📖 Guides
- [Setup Guide](guides/setup.md) - Installation & configuration
- [Development Guide](guides/development.md) - Development workflow
- [Testing Guide](guides/testing.md) - Testing strategies & benchmarks

### 🎓 Thesis
- [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) - **Main thesis document**
- [Progress Log](thesis/progress-log.md) - Implementation timeline
- [Evaluation Plan](thesis/evaluation-plan.md) - Testing & metrics

---

## 🎯 Current Phase: Metadata RAG Subgraph

**Status:** ✅ COMPLETE (Phase 1.5)

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

## 🚀 Next Phase: Hybrid RAG

**Status:** Planned (Week 2-3)

**Goal:** Implement full hybrid retrieval architecture with metadata pre-filtering.

**Novel Contribution:**
- Two separate RAG pipelines (metadata vs content)
- Specialized chunking strategies (1024 for metadata, 512 for content)
- Temporal pre-filtering before semantic search
- Cohort-aware retrieval

**See:** [implementation/hybrid-retrieval.md](implementation/hybrid-retrieval.md)

---

## 📊 Key Metrics (Current)

| Metric | Value | Notes |
|--------|-------|-------|
| **Temporal Extraction Confidence** | **0.92 (Excellent)** | Metadata RAG Subgraph (vs 0.5-0.6 regex) |
| **Metadata Save Time** | **Instant (<1s)** | Track_id approach (vs 15-30s polling) |
| **Indexing Speed** | 8.5 min | 150 documents (includes OCR + graph) |
| **Query Confidence Accuracy** | 93% | 3-agent pipeline with ViRanker |
| **Temporal Scoring** | 70% semantic + 30% temporal | Expired docs get 0.5 penalty |

**See:** [thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá)

---

## 🔗 Quick Links

### For Developers
- [Setup Guide](guides/setup.md) - Get started in 10 minutes
- [Development Workflow](guides/development.md) - How to add features
- [Testing](guides/testing.md) - Run tests & benchmarks

### For Researchers
- [Novel Contributions](research/novel-contributions.md) - What's new in UITRaph
- [Temporal RAG Survey](research/temporal-rag-survey.md) - State of the art
- [Comparison Table](research/comparison-table.md) - How UITRaph compares

### For Thesis Committee
- [Technical Report](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) - Full thesis
- [System Architecture](architecture/system-overview.md) - High-level design
- [Evaluation Results](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md#7-kết-quả-và-đánh-giá) - Performance metrics

---

## 📝 Contributing to Documentation

When implementing new features:

1. **Before coding:** Document the design in `implementation/`
2. **While coding:** Update progress in `thesis/progress-log.md`
3. **After coding:** Document the implementation details
4. **Add tests:** Document test coverage in `guides/testing.md`

**Example workflow:**
```bash
# 1. Document design
docs/implementation/new-feature.md

# 2. Implement feature
LangGraph/src/agent/...

# 3. Update progress
docs/thesis/progress-log.md

# 4. Document tests
docs/guides/testing.md
```

---

## 📅 Timeline

| Phase | Duration | Status | Documents |
|-------|----------|--------|-----------|
| **Phase 1.5: Metadata RAG** | Week 1 | ✅ COMPLETE | [metadata-rag-subgraph.md](implementation/metadata-rag-subgraph.md) |
| **Phase 2: Agent Integration** | Week 2 | 🟡 In Progress | Agent 2 & 3 temporal features |
| **Phase 3: Testing & Evaluation** | Week 3-4 | ⚪ Planned | [evaluation-plan.md](thesis/evaluation-plan.md) |
| **Phase 4: Thesis Writing** | Week 5-6 | ⚪ Planned | [TECHNICAL_REPORT_COMPREHENSIVE.md](thesis/TECHNICAL_REPORT_COMPREHENSIVE.md) |

---

## 💡 Key Innovations

1. **Temporal Document Management** - Full temporal lifecycle (validity, amendments, archiving)
2. **Track_id Approach** - 60x faster metadata save (no polling)
3. **Hybrid RAG Architecture** - Specialized pipelines for metadata vs content
4. **Vietnamese-Optimized** - Regex patterns, ViRanker, Vietnamese LLM

---

## 📧 Contact

- **Students:** Đặng Trần Long, Hoàng Bảo Long
- **Institution:** UIT - VNUHCM
- **Project:** UITRaph - Temporal RAG for University Knowledge

---

**Last Updated:** 2026-01-04
**Version:** 0.2.0 (Phase 1.5 COMPLETE - Metadata RAG Subgraph)
