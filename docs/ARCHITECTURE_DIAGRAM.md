# UIT_DOCS_AGENT - Complete System Architecture

**Version:** 2.1 (v0.2.0 - 2-Agent Pipeline)
**Last Updated:** 2026-04-14
**Phase:** v0.2.0 SHIPPED (Agent 2 removed, 2-agent linear pipeline)

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        UIT_DOCS_AGENT SYSTEM                          │
│                                                                       │
│  Temporal-Aware RAG System for Vietnamese University Documents       │
│  Key Innovation: Metadata RAG Subgraph (0.92 confidence)            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. Data Collection Layer

```
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA COLLECTION LAYER                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐       │
│  │  Firecrawl   │  │   Manual     │  │  Email/             │       │
│  │   Website    │  │   Upload     │  │  Announcements      │       │
│  │   Crawler    │  │  (Streamlit) │  │  Integration        │       │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬───────────┘       │
│         │                 │                     │                   │
│         └─────────────────┴─────────────────────┘                   │
│                             │                                        │
│                             v                                        │
│                   ./data/inputs/                                     │
│              (PDF/HTML/Markdown files)                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Processing Layer - Indexing Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PROCESSING LAYER - INDEXING PIPELINE                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                          Indexing Graph (LangGraph)                          │
│                                                                              │
│  1. Check Document Type                                                      │
│     ├─ PDF? → Continue                                                       │
│     └─ Text/HTML? → Skip OCR                                                 │
│                         │                                                    │
│                         v                                                    │
│  2. DeepSeek-OCR Processing                                                  │
│     ├─ Model: DeepSeek-OCR-8bit (MLX optimized for M1)                      │
│     ├─ Extract: Text + Layout + Structure                                    │
│     └─ Cache: ./data/DeepSeek-OCR/ (skip repeat)                            │
│                         │                                                    │
│                         v                                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │             3. METADATA RAG SUBGRAPH (6-Node Workflow)                │   │
│  │                                                                       │   │
│  │  NEW - PRIMARY METHOD (Phase 1.5 COMPLETE)                           │   │
│  │  Confidence: 0.92 (Excellent) vs 0.5-0.6 (regex fallback)            │   │
│  │                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ Node 1: Chunk Document                                        │    │   │
│  │  │  - RecursiveCharacterTextSplitter                            │    │   │
│  │  │  - Chunk size: 1024 tokens (large for metadata context)      │    │   │
│  │  │  - Overlap: 200 tokens                                        │    │   │
│  │  │  - Language-aware splitting (Vietnamese)                      │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  │  ┌─────────────────────v──────────────────────────────────────┐    │   │
│  │  │ Node 2: Index to ChromaDB (In-Memory)                       │    │   │
│  │  │  - Temporary vector database (deleted after extraction)     │    │   │
│  │  │  - Embedding: Vietnamese_Embedding_V2 (1024-dim)            │    │   │
│  │  │  - Collection: metadata_extraction_{doc_id}                 │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  │  ┌─────────────────────v──────────────────────────────────────┐    │   │
│  │  │ Node 3: Query Metadata Fields (RAG Retrieval)               │    │   │
│  │  │                                                              │    │   │
│  │  │  Two-Stage Retrieval:                                        │    │   │
│  │  │  Stage 1: Bi-Encoder (Broad Retrieval)                      │    │   │
│  │  │   - Model: Vietnamese_Embedding_V2                          │    │   │
│  │  │   - Top-K: 50 chunks                                         │    │   │
│  │  │   - Fast semantic search                                     │    │   │
│  │  │                                                              │    │   │
│  │  │  Stage 2: Cross-Encoder Reranking (Precision)               │    │   │
│  │  │   - Model: ViRanker (Vietnamese cross-encoder)              │    │   │
│  │  │   - Top-K: 5 chunks                                          │    │   │
│  │  │   - High-precision relevance scoring                         │    │   │
│  │  │                                                              │    │   │
│  │  │  Query 4 Metadata Fields:                                    │    │   │
│  │  │  1. Document Number (e.g., "108/QĐ-ĐHCNTT")                 │    │   │
│  │  │  2. Valid Dates (valid_from, valid_until)                   │    │   │
│  │  │  3. Student Cohorts (cohort_years, academic_year)           │    │   │
│  │  │  4. Amendments (amends_documents)                           │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  │  ┌─────────────────────v──────────────────────────────────────┐    │   │
│  │  │ Node 4: Calculate Confidence                                 │    │   │
│  │  │                                                              │    │   │
│  │  │  Weighted Scoring:                                           │    │   │
│  │  │  - 40% Completeness (fields successfully extracted)         │    │   │
│  │  │  - 40% LLM Confidence (extraction quality score)            │    │   │
│  │  │  - 20% Chunk Quality (relevance scores from reranker)       │    │   │
│  │  │                                                              │    │   │
│  │  │  Confidence Rating:                                          │    │   │
│  │  │  - 0.9-1.0: Excellent                                        │    │   │
│  │  │  - 0.7-0.9: Good                                             │    │   │
│  │  │  - 0.5-0.7: Fair                                             │    │   │
│  │  │  - 0.0-0.5: Low (trigger fallback to regex)                 │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  │  ┌─────────────────────v──────────────────────────────────────┐    │   │
│  │  │ Node 5: Format & Validate Metadata                          │    │   │
│  │  │                                                              │    │   │
│  │  │  Pydantic Validation (DocumentMetadata model):              │    │   │
│  │  │  - Date format: YYYY-MM-DD validation                        │    │   │
│  │  │  - Year range expansion: "2024-2028" → [2024,2025,...]     │    │   │
│  │  │  - Cohort scope: explicit | universal | unspecified         │    │   │
│  │  │  - Temporal awareness: current_date parameter               │    │   │
│  │  │  - Student lifecycle: 6-year assumption                     │    │   │
│  │  │  - Document number normalization                            │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  │  ┌─────────────────────v──────────────────────────────────────┐    │   │
│  │  │ Node 6: Cleanup                                              │    │   │
│  │  │  - Delete temporary ChromaDB collection                     │    │   │
│  │  │  - Free memory                                               │    │   │
│  │  └──────────────────────┬──────────────────────────────────────┘    │   │
│  │                         │                                             │   │
│  └─────────────────────────┼─────────────────────────────────────────  │   │
│                            │                                             │   │
│                            v                                             │   │
│         Metadata Extraction Result:                                     │   │
│         - document_number: "108/QĐ-ĐHCNTT"                              │   │
│         - valid_from: "2024-09-01"                                       │   │
│         - valid_until: "2029-08-31"                                      │   │
│         - academic_year: "2024-2025"                                     │   │
│         - cohort_years: [2024, 2025, 2026, 2027, 2028]                 │   │
│         - cohort_scope: "explicit"                                       │   │
│         - amends_documents: ["141/QĐ-ĐHCNTT"]                           │   │
│         - temporal_confidence: 0.92                                      │   │
│                            │                                             │   │
│         ┌──────────────────v──────────────────────────┐                │   │
│         │ Fallback: Regex-based Extraction (if RAG fails) │            │   │
│         │ - Vietnamese date patterns                   │                │   │
│         │ - Cohort detection regex                     │                │   │
│         │ - Amendment patterns                         │                │   │
│         │ - Lower confidence (0.5-0.6)                 │                │   │
│         └──────────────────┬──────────────────────────┘                │   │
│                            │                                             │   │
│  4. Upload to LightRAG                                                  │   │
│     ├─ POST /documents (text, file_source)                             │   │
│     ├─ Returns: track_id (instant!)                                     │   │
│     └─ No polling required                                              │   │
│                            │                                             │   │
│                            v                                             │   │
│  5. Save Metadata to PostgreSQL (via track_id)                         │   │
│     ├─ Table: lightrag_doc_status                                       │   │
│     ├─ Update using track_id (NO POLLING!)                             │   │
│     ├─ Time: <1 second (vs 15-30s polling)                             │   │
│     └─ Get doc_id from response                                         │   │
│                            │                                             │   │
│                            v                                             │   │
│                    Document Indexed Successfully                        │   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Storage Layer

```
┌─────────────────────────────────────────────────────────────────────┐
│                          STORAGE LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐  ┌────────────────┐  ┌─────────────────┐    │
│  │   LightRAG       │  │  PostgreSQL    │  │    Qdrant       │    │
│  │ Knowledge Graph  │  │  Temporal      │  │  Vector Store   │    │
│  │                  │  │  Metadata      │  │                 │    │
│  ├──────────────────┤  ├────────────────┤  ├─────────────────┤    │
│  │ - Entities       │  │ - doc_id       │  │ - Embeddings    │    │
│  │ - Relationships  │  │ - track_id     │  │ - HNSW index    │    │
│  │ - Text Chunks    │  │ - metadata:    │  │ - Cosine sim    │    │
│  │ - Graph links    │  │   • valid_from │  │ - Collections:  │    │
│  │                  │  │   • valid_until│  │   • entities    │    │
│  │ Storage:         │  │   • cohorts    │  │   • relations   │    │
│  │ - NetworkX       │  │   • amendments │  │   • chunks      │    │
│  │ - PostgreSQL KV  │  │   • doc_number │  │                 │    │
│  └──────────────────┘  └────────────────┘  └─────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Query Processing Layer - 2-Agent Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   QUERY PROCESSING LAYER - 2-AGENT PIPELINE                  │
│                                                                              │
│  Linear 7-node graph (v0.2.0):                                              │
│  prepare_input -> agent1_understand_query -> retrieve_data ->               │
│  enrich_with_temporal_metadata -> rerank_data ->                            │
│  agent3_generate_response -> format_final_answer                            │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Query (Vietnamese)                                                     │
│         │                                                                    │
│         v                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 1: prepare_input                                                │   │
│  │  - Extract query from messages                                        │   │
│  │  - Initialize pipeline state                                          │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 2: AGENT 1 - Query Understanding & Parameter Tuning             │   │
│  │                                                                       │   │
│  │ Input: User query (Vietnamese)                                        │   │
│  │                                                                       │   │
│  │ Processing:                                                           │   │
│  │ - Parse user intention                                                │   │
│  │ - Extract key entities and topics                                     │   │
│  │ - Calculate query confidence (0-1)                                    │   │
│  │ - Tune retrieval parameters:                                          │   │
│  │   - retrieval_mode: naive/local/global/hybrid/mix                    │   │
│  │   - top_k: number of results                                          │   │
│  │   - chunk_top_k: number of text chunks                               │   │
│  │                                                                       │   │
│  │ Output:                                                               │   │
│  │ - parsed_intention: "Thu tuc dang ky hoc bong khuyen khich"          │   │
│  │ - extracted_entities: ["Hoc bong", "Khuyen khich", "Dang ky"]        │   │
│  │ - query_confidence: 0.85                                              │   │
│  │                                                                       │   │
│  │ Note: All queries proceed to retrieval (no clarification branch).    │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 3: retrieve_data - LightRAG Retrieval                           │   │
│  │                                                                       │   │
│  │  - Call LightRAG /query/data endpoint                                │   │
│  │  - Returns: entities, relationships, text chunks                     │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 4: enrich_with_temporal_metadata                                │   │
│  │                                                                       │   │
│  │  - Fetch temporal metadata from PostgreSQL for retrieved documents   │   │
│  │  - Attach valid_from, valid_until, cohort_years, amends_documents   │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 5: TEMPORAL RERANKING                                           │   │
│  │  Semantic + Recency + Cohort + Amendment Scoring                     │   │
│  │                                                                       │   │
│  │ Step 1: ViRanker Reranking                                           │   │
│  │  - Model: namdp-ptit/ViRanker (Vietnamese cross-encoder)             │   │
│  │  - Rerank all retrieved items                                         │   │
│  │  - Semantic relevance scores (0-1)                                    │   │
│  │                                                                       │   │
│  │ Step 2: Temporal Scoring                                             │   │
│  │  - Combine semantic + temporal scores:                                │   │
│  │    final_score = 0.7 * semantic_score + 0.3 * temporal_score        │   │
│  │                                                                       │   │
│  │  - Temporal penalties:                                                │   │
│  │    - Expired documents: 0.5x penalty                                  │   │
│  │    - Expiring soon (30 days): 0.8x penalty                           │   │
│  │    - Amended documents: 0.3x penalty                                  │   │
│  │    - Archived documents: 0.0 score (hidden)                          │   │
│  │                                                                       │   │
│  │  - Sort by final_score (descending)                                   │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 6: AGENT 3 - Response Generation                                │   │
│  │                                                                       │   │
│  │ Input: Reranked data with temporal metadata and reranking scores     │   │
│  │                                                                       │   │
│  │ Processing:                                                           │   │
│  │ - Decide response type based on retrieved data (no separate          │   │
│  │   confidence assessment -- Agent 3 decides directly):                │   │
│  │   - Sufficient high-scoring data: Full, detailed answer              │   │
│  │   - Partial data available: Partial answer with caveats              │   │
│  │   - Insufficient data: Fallback "Please contact advisor"             │   │
│  │                                                                       │   │
│  │ - Add expiration warnings:                                            │   │
│  │   "WARNING: This document expires on 2024-12-31"                    │   │
│  │                                                                       │   │
│  │ - Format references with hyperlinks:                                  │   │
│  │   [Quyet dinh 108/QD-DHCNTT](https://uit.edu.vn/docs/108)           │   │
│  │                                                                       │   │
│  │ Output:                                                               │   │
│  │ - generated_response: Vietnamese answer text                         │   │
│  │ - response_type: full_answer | partial_answer | fallback            │   │
│  │ - references: [{title, url, relevance}, ...]                        │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NODE 7: format_final_answer                                          │   │
│  │  - Format markdown with warnings and references                      │   │
│  │  - Produce final_answer field                                         │   │
│  └───────────────────────────┬───────────────────────────────────────── │   │
│                              │                                            │   │
│                              v                                            │   │
│                  Final Answer to User (Vietnamese)                       │   │
│                  with References and Warnings                            │   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Technology Stack

### AI/ML Models
- **LLM**: Qwen/Qwen3-4B-Instruct (4B params, multilingual)
- **Embedding**: AITeamVN/Vietnamese_Embedding_v2 (1024-dim, Vietnamese-optimized)
- **Reranker**: namdp-ptit/ViRanker (Vietnamese cross-encoder)
- **OCR**: DeepSeek-OCR-8bit (MLX optimized for M1)

### Frameworks
- **LangGraph**: Multi-agent workflow orchestration
- **LangChain**: LLM application framework
- **LightRAG**: Graph-based RAG system
- **Pydantic**: Data validation and type safety
- **ChromaDB**: Temporary vector storage (in Metadata RAG Subgraph)

### Storage
- **PostgreSQL**: Temporal metadata, document status, LLM cache
- **Qdrant**: Vector embeddings (HNSW index, cosine similarity)
- **NetworkX**: Knowledge graph structure

### Infrastructure
- **Docker Compose**: Service orchestration
- **M1 Metal**: GPU acceleration (unified memory)
- **Firecrawl**: Web scraping and document collection

---

## 6. Key Performance Metrics

| Metric | Value | Improvement | Notes |
|--------|-------|-------------|-------|
| **Metadata Extraction Confidence** | 0.92 | +83% | Metadata RAG vs regex (0.5-0.6) |
| **Metadata Save Time** | <1s | 60x faster | Track_id approach vs polling (15-30s) |
| **Temporal Scoring Accuracy** | 70% semantic + 30% temporal | N/A | Balanced relevance + freshness |
| **Query Confidence** | 93% | N/A | Pre-v0.2.0 3-agent pipeline metric |
| **Concurrent Embeddings (M1)** | 8 | -87.5% | Reduced from 64 to prevent GPU timeout |
| **GPU Timeout Errors** | 0 | -100% | Resolved with M1 optimizations |

---

## 7. Novel Contributions

1. **Metadata RAG Subgraph**
   - RAG-powered metadata extraction (vs regex-only approaches)
   - 0.92 confidence (83% improvement over regex baseline)
   - 6-node workflow with two-stage retrieval
   - Temporal-aware cohort calculation

2. **Track_id Innovation**
   - Instant metadata save (<1s vs 15-30s polling)
   - 60x performance improvement
   - Direct PostgreSQL update using track_id
   - No polling, no timeouts

3. **Temporal Scoring Algorithm**
   - Hybrid scoring: 70% semantic + 30% temporal
   - Penalties for expired/amended documents
   - Soft delete with archiving
   - Cohort-aware retrieval (6-year student lifecycle)

4. **Vietnamese Optimization**
   - Vietnamese_Embedding_v2 for embeddings
   - ViRanker cross-encoder for reranking
   - Qwen multilingual LLM
   - Vietnamese regex patterns

---

## 8. System Flow Summary

### Indexing Pipeline
```
PDF → DeepSeek-OCR → Metadata RAG Subgraph → LightRAG Upload → PostgreSQL Save
                            (6 nodes)              (track_id)      (<1s)
                          (0.92 confidence)
```

### Query Pipeline (v0.2.0 - 2-Agent, 7 Nodes)
```
User Query → prepare_input → Agent 1 (Understanding) → retrieve_data →
             enrich_with_temporal_metadata → rerank_data (ViRanker + Temporal) →
             Agent 3 (Response) → format_final_answer → Final Answer with Warnings
```

---

**Architecture Version:** 2.1 (v0.2.0)
**Phase Status:** v0.2.0 SHIPPED (2-agent linear pipeline, Agent 2 removed)
**Next Milestones:**
- Agent 3: Expiration warnings in responses
- Ping service: Automated document archiving
- Comprehensive testing suite
