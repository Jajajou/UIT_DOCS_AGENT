# Metadata RAG Subgraph Implementation

**Phase:** 1 (Week 1)
**Status:** COMPLETE
**Last Updated:** 2026-04-14

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Why RAG for Metadata Extraction?](#why-rag-for-metadata-extraction)
3. [Architecture](#architecture)
4. [Implementation Status](#implementation-status)
5. [Design Decisions](#design-decisions)
6. [Code Reference](#code-reference)
7. [Next Steps](#next-steps)

---

## Overview

### What We're Building

A **dedicated RAG pipeline** that lives as a **LangGraph subgraph** within the indexing workflow. Its sole purpose: extract temporal metadata from Vietnamese legal documents with high accuracy.

### The Problem

Vietnamese university documents (Quyết định, Quy chế, Thông báo) can be **hundreds of pages long**. Extracting metadata like:
- Document number (Số hiệu văn bản)
- Validity period (Ngày hiệu lực, Ngày hết hạn)
- Applicable cohorts (Khóa sinh viên áp dụng)
- Amendment relationships (Sửa đổi/Bổ sung văn bản nào)

...requires understanding **context scattered across the document**. Simply passing the entire document to an LLM exceeds context windows and produces low-quality extractions.

### The Solution

**Full RAG for ALL metadata fields:**
1. **Chunk** the document (1024 tokens, fixed-size)
2. **Embed** chunks using Vietnamese embedding model
3. **Query** for each metadata field using targeted Vietnamese queries
4. **Retrieve** top candidates with bi-encoder (fast)
5. **Rerank** with cross-encoder (precise)
6. **Extract** metadata from reranked context using LLM
7. **Calculate confidence** based on extraction quality
8. **Clean up** temporary vector DB

---

## Why RAG for Metadata Extraction?

### Teacher's Feedback

> "Với đề tài này, mình trước mắt tập trung vào **độ chính xác** nhỉ. Vì, tư vấn cho SV thì cần **độ chính xác cao** 1 tí nó mới khả thi."

**Accuracy > Speed** for a student advising system.

### Why Not Simple Regex/Header Extraction?

| Approach | Pros | Cons |
|----------|------|------|
| **Regex-only** | ✅ Fast, deterministic | ❌ Fails on variations, misses amendments in body text |
| **Header extraction** | ✅ Works for simple docs | ❌ Amendments are in body, not header/footer |
| **Full-doc LLM** | ✅ No chunking needed | ❌ Context window limits, poor focus, expensive |
| **RAG (our approach)** | ✅ Accurate, scalable, context-aware | ⚠️ More complex, requires embedding/reranking |

### Why Full RAG (Not Hybrid)?

Initial proposal: Use regex for simple fields (document_number, dates) + RAG for complex fields (cohorts, amendments).

**User decision:** "Tôi muốn **full RAG cho tất cả fields**"

**Rationale:**
- Uniform pipeline = consistent accuracy
- Regex patterns still fail on edge cases (e.g., "108/2024/QĐ-ĐHCNTT" vs "QĐ-ĐHCNTT-108/2024")
- RAG can learn patterns from context, not just format

---

## Architecture

### Subgraph vs Node

**Why subgraph?**
- Multi-step workflow (chunking → indexing → querying → extraction → cleanup)
- Internal state management (chunks, collection_name, intermediate results)
- Reusable across different documents
- Clean separation of concerns

**Parent Graph:** `indexing_graph.py` (IndexingState)
**Subgraph:** `metadata_rag_subgraph.py` (MetadataRAGState)

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      INDEXING GRAPH (Parent)                    │
│                                                                 │
│  [DeepSeek-OCR] → [Metadata RAG Subgraph] → [Upload to KB]      │
│                          ↓                                      │
│                   passes: doc_text,                             │
│                          file_source,                           │
│                          doc_id                                 │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              METADATA RAG SUBGRAPH (Internal)                   │
│                                                                 │
│  1. [chunk_document_node]                                       │
│       ↓ chunks (1024 tokens, fixed-size)                        │
│                                                                 │
│  2. [index_to_vector_db_node]                                   │
│       ↓ collection_name (in-memory ChromaDB)                    │
│                                                                 │
│  3. [query_metadata_fields_node]                                │
│       ↓ document_number_chunks                                  │
│       ↓ valid_from_chunks, valid_until_chunks                   │
│       ↓ cohort_years_chunks                                     │
│       ↓ amends_documents_chunks                                 │
│       ↓ extracted metadata                                      │
│                                                                 │
│  4. [calculate_confidence_node]                                 │
│       ↓ extraction_confidence                                   │
│                                                                 │
│  5. [format_metadata_node]                                      │
│       ↓ final_metadata (validated, typed)                       │
│                                                                 │
│  6. [cleanup_node]                                              │
│       ↓ Delete temp collection                                  │
│                                                                 │
│  Returns: final_metadata, success, error                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                   BACK TO INDEXING GRAPH                        │
│                                                                 │
│  [Save to PostgreSQL using track_id]                            │
│       ↓ document_metadata.valid_from                            │
│       ↓ document_metadata.valid_until                           │
│       ↓ document_metadata.cohort_years                          │
│       ↓ document_metadata.amends_documents                      │
│       ↓ temporal_extraction_complete = True                     │
└─────────────────────────────────────────────────────────────────┘
```

### Two-Stage Retrieval

```
┌──────────────────────────────────────────────────────────────┐
│                    QUERY: "Số hiệu văn bản"                  │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STAGE 1: Bi-encoder (Fast Initial Retrieval)                │
│                                                              │
│  Model: AITeamVN/Vietnamese_Embedding_V2                     │
│  Method: Cosine similarity (precomputed embeddings)          │
│  Speed: ~0.1ms per comparison                                │
│                                                              │
│  500 chunks → 50 candidates                                  │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STAGE 2: Cross-encoder (Precise Reranking)                  │
│                                                              │
│  Model: UniML/UniML-VDR (ViRanker)                           │
│  Method: Pairwise scoring (query + doc concatenated)         │
│  Speed: ~10ms per pair                                       │
│                                                              │
│  50 candidates → 5 top results                               │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STAGE 3: LLM Extraction                                     │
│                                                              │
│  Model: Qwen 3.5 4B                                          │
│  Input: Concatenated top 5 chunks + extraction prompt        │
│  Output: Structured JSON with extracted metadata             │
└──────────────────────────────────────────────────────────────┘
```

**Why both stages?**

Without bi-encoder: 500 chunks × 6 queries = **3000 cross-encoder forward passes** (~30 seconds)
With bi-encoder: 50 candidates × 6 queries = **300 cross-encoder forward passes** (~3 seconds)

**10x speedup** while maintaining accuracy.

---

## Implementation Status

### ✅ Completed

#### 1. State Schema ([metadata_rag_state.py:4-48](../../LangGraph/src/agent/states/metadata_rag_state.py#L4-L48))

```python
class MetadataRAGState(TypedDict):
    # --- INPUT (from Indexing Graph) ---
    doc_text: str
    file_source: str
    doc_id: str

    # --- PROCESSING (Internal) ---
    chunks: NotRequired[List[str]]
    chunk_count: NotRequired[int]
    collection_name: NotRequired[str]

    # --- QUERY RESULTS (Raw Chunks) ---
    document_number_chunks: NotRequired[List[str]]
    valid_from_chunks: NotRequired[List[str]]
    valid_until_chunks: NotRequired[List[str]]
    cohort_years_chunks: NotRequired[List[str]]
    amends_documents_chunks: NotRequired[List[str]]

    # --- EXTRACTED METADATA ---
    document_number: NotRequired[Optional[str]]
    valid_from: NotRequired[Optional[str]]
    valid_until: NotRequired[Optional[str]]
    cohort_years: NotRequired[List[Union[int, str]]]  # [2024, 2025] or ["*"]
    cohort_scope: NotRequired[str]  # "universal", "explicit", "unspecified"
    amends_documents: NotRequired[List[str]]
    extraction_confidence: NotRequired[float]

    # --- OUTPUT ---
    final_metadata: NotRequired[Dict[str, Any]]
    success: bool
    error: NotRequired[str]
```

**Design notes:**
- `NotRequired` fields allow flexible state updates
- Separate storage for raw chunks vs extracted values (debugging)
- `cohort_scope` distinguishes universal (`["*"]`) vs explicit (`[2024, 2025]`)

#### 2. Chunk Document Node ([metadata_rag_nodes.py:57-78](../../LangGraph/src/agent/agents/metadata_rag_nodes.py#L57-L78))

```python
def chunk_document_node(state: MetadataRAGState) -> MetadataRAGState:
    """Chia nhỏ văn bản thành chunks 1024 tokens."""
    text = state["doc_text"]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1024,
        chunk_overlap=200,  # High overlap to preserve context across pages
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = splitter.split_text(text)

    logger.info(f"📄 Document split into {len(chunks)} chunks.")

    return {
        "chunks": chunks,
        "chunk_count": len(chunks)
    }
```

**Design decisions:**
- **Fixed-size chunking** (user decision: "fixed sized là đủ cho feature này")
- **1024 tokens** = ~3 pages per chunk (enough context for metadata patterns)
- **200 token overlap** = preserve context across chunk boundaries

#### 3. Index to Vector DB Node ([metadata_rag_nodes.py:80-113](../../LangGraph/src/agent/agents/metadata_rag_nodes.py#L80-L113))

```python
def index_to_vector_db_node(state: MetadataRAGState) -> MetadataRAGState:
    """Embed chunks và lưu vào ChromaDB in-memory tạm thời."""
    chunks = state["chunks"]

    # Create unique collection name
    clean_source = ''.join(e for e in state['file_source'] if e.isalnum())[-10:]
    collection_name = f"temp_{uuid.uuid4().hex[:8]}_{clean_source}"

    collection = CHROMA_CLIENT.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    # Embedding (Batch processing)
    embeddings = EMBEDDING_MODEL.encode(chunks, show_progress_bar=False)

    # Add to Chroma
    ids = [f"id_{i}" for i in range(len(chunks))]
    collection.add(
        documents=chunks,
        embeddings=embeddings.tolist(),
        ids=ids
    )

    logger.info(f"💾 Indexed {len(chunks)} chunks to collection '{collection_name}'")
    return {"collection_name": collection_name}
```

**Design decisions:**
- **In-memory ChromaDB** = temporary storage (deleted after extraction)
- **Unique collection name** = supports parallel processing
- **Batch embedding** = efficient use of GPU (if available)
- **Cosine similarity** = standard for semantic search

#### 4. Retrieve and Rerank Helper ([metadata_rag_nodes.py:115-140](../../LangGraph/src/agent/agents/metadata_rag_nodes.py#L115-L140))

```python
def _rag_retrieve_and_rerank(
    collection_name: str,
    query: str,
    top_k_retrieve=50,
    top_k_rerank=5
) -> List[str]:
    """Helper function: Retrieve (Bi-encoder) -> Rerank (Cross-encoder)."""
    collection = CHROMA_CLIENT.get_collection(collection_name)

    # 1. Bi-encoder Retrieval
    query_vec = EMBEDDING_MODEL.encode([query])[0].tolist()
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k_retrieve
    )
    candidates = results['documents'][0]

    # 2. Cross-encoder Reranking
    pairs = [[query, doc] for doc in candidates]
    scores = RERANKER_MODEL.predict(pairs)
    sorted_indices = np.argsort(scores)[::-1][:top_k_rerank]
    top_docs = [candidates[i] for i in sorted_indices]

    return top_docs
```

**Design decisions:**
- **top_k_retrieve=50** = balance between recall and reranking speed
- **top_k_rerank=5** = enough context for LLM without overwhelming it
- **Reusable helper** = called 6 times (one per metadata field)

#### 5. Cleanup Node ([metadata_rag_nodes.py:202-211](../../LangGraph/src/agent/agents/metadata_rag_nodes.py#L202-L211))

```python
def cleanup_node(state: MetadataRAGState) -> MetadataRAGState:
    """Dọn dẹp Vector DB."""
    try:
        col_name = state.get("collection_name")
        if col_name:
            CHROMA_CLIENT.delete_collection(col_name)
            logger.info(f"🧹 Deleted temp collection {col_name}")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
    return {"success": True}
```

**Design decisions:**
- Always returns `success=True` (cleanup failure is non-critical)
- Logs warning but doesn't fail the pipeline

#### 6. LLM Prompts ([prompts.py:26-67](../../LangGraph/src/agent/core/prompts.py#L26-L67))

Prompts already exist for:
- `document_number`: Extract official document number
- `valid_dates`: Extract validity period with temporal context
- `cohorts`: Extract applicable student cohorts with scope detection

---

### ⚠️ Partially Implemented

#### 7. Query Metadata Fields Node ([metadata_rag_nodes.py:142-200](../../LangGraph/src/agent/agents/metadata_rag_nodes.py#L142-L200))

**Current implementation:**
- ✅ Document number extraction
- ✅ Valid dates extraction
- ✅ Cohorts extraction
- ❌ **Amends extraction incomplete** (line 194: "# (Logic extract amends tương tự...)")

**Missing:**
- Full amends extraction logic
- Error handling for LLM failures
- Confidence tracking per field

---

### ❌ Not Implemented

#### 8. Calculate Confidence Node

**Purpose:** Aggregate extraction quality into a single confidence score (0.0-1.0)

**Planned logic:**
```python
def calculate_confidence_node(state: MetadataRAGState) -> MetadataRAGState:
    """
    Calculate extraction confidence based on:
    1. Field completeness (how many fields extracted?)
    2. LLM confidence (did LLM return "NULL"?)
    3. Reranker scores (were top chunks highly relevant?)
    4. Cross-field consistency (do dates make sense?)
    """
    scores = []

    # 1. Field completeness
    required_fields = ["document_number", "valid_from", "cohort_years"]
    filled = sum(1 for f in required_fields if state.get(f))
    completeness_score = filled / len(required_fields)
    scores.append(completeness_score)

    # 2. LLM confidence (check for NULL values)
    null_count = sum(1 for f in required_fields if state.get(f) in [None, "NULL", ""])
    llm_confidence = 1.0 - (null_count / len(required_fields))
    scores.append(llm_confidence)

    # 3. TODO: Add reranker score averaging
    # 4. TODO: Add cross-field validation

    final_confidence = np.mean(scores)

    return {"extraction_confidence": final_confidence}
```

#### 9. Format Metadata Node

**Purpose:** Validate and format extracted metadata into final schema

**Planned implementation:**
```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Union
from datetime import datetime

class DocumentMetadata(BaseModel):
    """Validated metadata schema matching PostgreSQL table."""

    document_number: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    cohort_years: List[Union[int, str]] = Field(default_factory=list)
    cohort_scope: str = "unspecified"  # "universal", "explicit", "unspecified"
    amends_documents: List[str] = Field(default_factory=list)
    temporal_confidence: float = Field(ge=0.0, le=1.0)

    @validator("valid_from", "valid_until")
    def validate_date_format(cls, v):
        """Ensure dates are YYYY-MM-DD or None."""
        if v is None or v == "NULL":
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            return None

    @validator("cohort_years", pre=True)
    def normalize_cohorts(cls, v):
        """Convert ["*"] to universal scope, validate year format."""
        if v == ["*"]:
            return ["*"]
        # Convert strings to ints if possible
        normalized = []
        for year in v:
            if isinstance(year, int):
                normalized.append(year)
            elif isinstance(year, str) and year.isdigit():
                normalized.append(int(year))
        return normalized if normalized else []

def format_metadata_node(state: MetadataRAGState) -> MetadataRAGState:
    """Validate and format metadata using Pydantic."""
    try:
        metadata = DocumentMetadata(
            document_number=state.get("document_number"),
            valid_from=state.get("valid_from"),
            valid_until=state.get("valid_until"),
            cohort_years=state.get("cohort_years", []),
            cohort_scope=state.get("cohort_scope", "unspecified"),
            amends_documents=state.get("amends_documents", []),
            temporal_confidence=state.get("extraction_confidence", 0.0)
        )

        return {
            "final_metadata": metadata.dict(exclude_none=True),
            "success": True
        }
    except Exception as e:
        logger.error(f"Metadata validation failed: {e}")
        return {"error": str(e), "success": False}
```

#### 10. Metadata RAG Subgraph Definition

**File:** `LangGraph/src/agent/graphs/metadata_rag_subgraph.py` (not yet created)

**Planned structure:**
```python
from langgraph.graph import StateGraph, END
from ..states.metadata_rag_state import MetadataRAGState
from ..agents.metadata_rag_nodes import (
    chunk_document_node,
    index_to_vector_db_node,
    query_metadata_fields_node,
    calculate_confidence_node,
    format_metadata_node,
    cleanup_node
)

# Create subgraph
metadata_rag_graph = StateGraph(MetadataRAGState)

# Add nodes
metadata_rag_graph.add_node("chunk_document", chunk_document_node)
metadata_rag_graph.add_node("index_to_vector_db", index_to_vector_db_node)
metadata_rag_graph.add_node("query_metadata", query_metadata_fields_node)
metadata_rag_graph.add_node("calculate_confidence", calculate_confidence_node)
metadata_rag_graph.add_node("format_metadata", format_metadata_node)
metadata_rag_graph.add_node("cleanup", cleanup_node)

# Add edges
metadata_rag_graph.set_entry_point("chunk_document")
metadata_rag_graph.add_edge("chunk_document", "index_to_vector_db")
metadata_rag_graph.add_edge("index_to_vector_db", "query_metadata")
metadata_rag_graph.add_edge("query_metadata", "calculate_confidence")
metadata_rag_graph.add_edge("calculate_confidence", "format_metadata")
metadata_rag_graph.add_edge("format_metadata", "cleanup")
metadata_rag_graph.add_edge("cleanup", END)

# Compile
metadata_rag_subgraph = metadata_rag_graph.compile()
```

#### 11. Integration into Indexing Graph

**File:** `LangGraph/src/agent/graphs/indexing_graph.py` (needs modification)

**Current flow:**
```
[DeepSeek-OCR] → [Upload to LightRAG] → END
```

**New flow:**
```
[DeepSeek-OCR] → [Metadata RAG Subgraph] → [Upload to LightRAG] → [Save Temporal Metadata] → END
```

**Code changes needed:**
```python
# Import subgraph
from .metadata_rag_subgraph import metadata_rag_subgraph

# Add subgraph as node
indexing_graph.add_node("extract_temporal_metadata", metadata_rag_subgraph)

# Update edges
indexing_graph.add_edge("deepseek_ocr", "extract_temporal_metadata")
indexing_graph.add_edge("extract_temporal_metadata", "upload_to_lightrag")
```

---

## Design Decisions

### 1. Fixed-Size vs Semantic Chunking

**Decision:** Fixed-size (1024 tokens)

**Rationale:**
- User preference: "fixed sized là đủ cho feature này"
- Simpler implementation
- Metadata patterns span multiple pages → need large chunks anyway
- Semantic chunking adds complexity without clear benefit for this use case

### 2. Bi-encoder + Cross-encoder vs Cross-encoder Only

**Decision:** Two-stage retrieval

**User question:** "tại sao cần bi-encoder không rerank qua Vireranker luôn được hả"

**Rationale:**
- Performance: 500 chunks × 6 queries = 3000 forward passes (~30s) is too slow
- With bi-encoder: 50 candidates × 6 queries = 300 forward passes (~3s)
- **10x speedup** while maintaining precision
- Cross-encoders are O(n²) for pairwise scoring → need filtering first

**Exception:** Could skip bi-encoder if:
- Documents are short (<100 chunks)
- Offline indexing (user willing to wait)
- GPU acceleration available

### 3. In-Memory vs Persistent Vector DB

**Decision:** In-memory ChromaDB

**Rationale:**
- Temporary storage (only needed during extraction)
- Avoid polluting main Qdrant instance with temporary data
- Faster startup (no disk I/O)
- Automatic cleanup on process exit (fail-safe)

### 4. Subgraph vs Flat Nodes

**Decision:** Subgraph

**User suggestion:** "tôi đang nghĩ nếu làm RAG có thể để nó thành 1 subgraph trong langgraph thay vì 1 node"

**Rationale:**
- Multi-step workflow (6 nodes)
- Internal state management (chunks, collection_name)
- Reusable across different documents
- Clean separation of concerns (parent graph doesn't need to know about chunking/indexing details)

### 5. Full RAG vs Hybrid Extraction

**Decision:** Full RAG for all fields

**User preference:** "tôi muốn full RAG cho tất cả fields"

**Rationale:**
- Uniform pipeline = consistent accuracy
- Regex still fails on edge cases
- RAG can learn contextual patterns
- Simpler codebase (no special-case logic)

---

## Code Reference

### Key Files

| File | Lines | Status | Purpose |
|------|-------|--------|---------|
| [metadata_rag_state.py](../../LangGraph/src/agent/states/metadata_rag_state.py) | 1-48 | ✅ Complete | State schema |
| [metadata_rag_nodes.py](../../LangGraph/src/agent/agents/metadata_rag_nodes.py) | 1-211 | ⚠️ Partial | Node implementations |
| [prompts.py](../../LangGraph/src/agent/core/prompts.py) | 26-67 | ✅ Complete | LLM extraction prompts |
| metadata_rag_subgraph.py | N/A | ❌ Not created | Subgraph definition |
| [indexing_graph.py](../../LangGraph/src/agent/graphs/indexing_graph.py) | TBD | ❌ Needs update | Integration point |

### Models Used

| Model | Purpose | Size | Provider |
|-------|---------|------|----------|
| AITeamVN/Vietnamese_Embedding_V2 | Bi-encoder (embedding) | ~400MB | HuggingFace |
| UniML/UniML-VDR (ViRanker) | Cross-encoder (reranking) | ~500MB | HuggingFace |
| Qwen 3.5 4B | LLM extraction | 4B params | OpenAI-compatible API |

---

## Next Steps

### Immediate (Before Code Implementation)

1. ✅ Document Metadata RAG Subgraph (this file)
2. ⏳ Document Temporal Scoring Strategy
3. ⏳ Document Hybrid RAG Architecture (Phase 2 plan)
4. ⏳ Document Novel Contributions for thesis

### Implementation Phase

1. **Complete missing nodes:**
   - `calculate_confidence_node` (aggregate quality metrics)
   - `format_metadata_node` (Pydantic validation)
   - Finish `query_metadata_fields_node` (amends extraction)

2. **Create subgraph:**
   - `metadata_rag_subgraph.py` with node connections
   - Test subgraph in isolation

3. **Integrate into indexing graph:**
   - Update `indexing_graph.py` with subgraph node
   - Add conditional edge (skip if temporal extraction disabled)

4. **Test with sample document:**
   - Run full pipeline end-to-end
   - Verify metadata saved to PostgreSQL
   - Check confidence scores

5. **Optimize:**
   - Tune top_k parameters
   - Benchmark extraction time
   - Improve prompts based on test results

---

## Novel Contributions (Thesis)

### What Makes This Unique?

1. **RAG-based metadata extraction** (vs regex-only approaches in existing systems)
2. **Temporal-aware chunking** (1024 tokens preserves metadata context)
3. **Two-stage retrieval** (bi-encoder + cross-encoder for Vietnamese)
4. **Instant metadata save** using track_id approach (60x faster than polling)
5. **Universal document detection** (["*"] for cohort_scope)

### Comparison to Related Work

| System | Metadata Extraction | Temporal Awareness | Vietnamese Support |
|--------|---------------------|--------------------|--------------------|
| GraphRAG | ❌ None | ❌ None | ❌ English-only |
| LightRAG | ❌ None | ⚠️ Incremental updates | ⚠️ Multilingual (not optimized) |
| T-GRAG (EMNLP 2025) | ❌ Manual tagging | ✅ Temporal graph | ❌ English-only |
| **UITRaph (Ours)** | ✅ RAG-based | ✅ Full temporal lifecycle | ✅ Vietnamese-optimized |

---

**See also:**
- [Temporal Scoring Strategy](temporal-scoring.md) (coming next)
- [Hybrid RAG Architecture](hybrid-retrieval.md) (Phase 2)
- [Novel Contributions](../research/novel-contributions.md) (thesis)
