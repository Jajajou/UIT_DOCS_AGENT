# Hybrid RAG Architecture (Phase 2)

**Phase:** 2 (Week 2-3)
**Status:** ⚪ Planned (Not Yet Started)
**Last Updated:** 2025-12-17

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture Design](#architecture-design)
3. [Two-Pipeline Approach](#two-pipeline-approach)
4. [Temporal Pre-filtering](#temporal-pre-filtering)
5. [Cohort-Aware Retrieval](#cohort-aware-retrieval)
6. [Implementation Plan](#implementation-plan)
7. [Novel Contributions](#novel-contributions)

---

## Overview

### What is Hybrid RAG?

**Hybrid RAG** separates the system into **two specialized RAG pipelines**:

1. **Metadata RAG** (Phase 1 - Current)
   - Purpose: Extract temporal metadata from documents
   - Chunking: 1024 tokens (large chunks for metadata context)
   - Embeddings: Vietnamese_Embedding_V2
   - Storage: In-memory ChromaDB (temporary)
   - Output: Temporal metadata → PostgreSQL

2. **Content RAG** (Phase 2 - Planned)
   - Purpose: Answer user queries with document content
   - Chunking: 512 tokens (smaller chunks for precise retrieval)
   - Embeddings: LightRAG's embedding model
   - Storage: Qdrant (persistent)
   - Pre-filtering: **Temporal + Cohort filters** before semantic search

### Why Hybrid?

**Problem with single-pipeline RAG:**
- Metadata extraction needs **large chunks** (1024 tokens) to capture context
- Query answering needs **small chunks** (512 tokens) for precision
- Same embedding space for both tasks → suboptimal for each

**Solution with hybrid RAG:**
- **Separate chunking strategies** optimized for each task
- **Separate embedding spaces** (can use different models)
- **Metadata pre-filtering** before content retrieval
- **Specialized prompts** for each pipeline

---

## Architecture Design

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      INDEXING PIPELINE                          │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │  PDF Document   │
                    └────────┬────────┘
                             │
                             ↓
                    ┌─────────────────┐
                    │ DeepSeek-OCR    │
                    │ Extract Text    │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ↓                         ↓
    ┌──────────────────────┐   ┌──────────────────────┐
    │  METADATA RAG        │   │  CONTENT RAG         │
    │  (Subgraph)          │   │  (LightRAG)          │
    │                      │   │                      │
    │  • Chunk: 1024 tok   │   │  • Chunk: 512 tok    │
    │  • Embed: ViEmbed    │   │  • Embed: LightRAG   │
    │  • Store: ChromaDB   │   │  • Store: Qdrant     │
    │  • Query: 6 fields   │   │  • Build: Graph      │
    │                      │   │                      │
    │  Output:             │   │  Output:             │
    │  • document_number   │   │  • Entities          │
    │  • valid_from/until  │   │  • Relationships     │
    │  • cohort_years      │   │  • Chunks            │
    │  • amends_documents  │   │                      │
    └──────────┬───────────┘   └──────────┬───────────┘
               │                          │
               ↓                          ↓
    ┌──────────────────────┐   ┌──────────────────────┐
    │  PostgreSQL          │   │  Qdrant              │
    │  Temporal Metadata   │   │  Vector Embeddings   │
    └──────────────────────┘   └──────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                       QUERY PIPELINE                            │
└─────────────────────────────────────────────────────────────────┘

                  ┌──────────────────┐
                  │  User Query      │
                  └────────┬─────────┘
                           │
                           ↓
                  ┌──────────────────┐
                  │  Agent 1         │
                  │  Parse Intent    │
                  │                  │
                  │  Extract:        │
                  │  • Entities      │
                  │  • Temporal cues │
                  │  • Cohort info   │
                  └────────┬─────────┘
                           │
                           ↓
            ┌──────────────────────────────┐
            │  TEMPORAL + COHORT FILTERS   │
            │                              │
            │  PostgreSQL Query:           │
            │  • valid_from <= NOW()       │
            │  • valid_until >= NOW()      │
            │  • is_archived = FALSE       │
            │  • cohort_years IN [2024]    │
            │    OR cohort_scope='universal'│
            │                              │
            │  Returns: doc_ids to search  │
            └──────────────┬───────────────┘
                           │
                           ↓
                  ┌──────────────────┐
                  │  CONTENT RAG     │
                  │  (LightRAG)      │
                  │                  │
                  │  • Query only    │
                  │    filtered docs │
                  │  • Semantic      │
                  │    search        │
                  └────────┬─────────┘
                           │
                           ↓
                  ┌──────────────────┐
                  │  Reranker        │
                  │  + Temporal      │
                  │    Boost         │
                  └────────┬─────────┘
                           │
                           ↓
                  ┌──────────────────┐
                  │  Agent 2 & 3     │
                  │  Generate Answer │
                  └──────────────────┘
```

---

## Two-Pipeline Approach

### Pipeline 1: Metadata RAG (Phase 1 - Current)

**Purpose:** Extract temporal metadata from documents during indexing

**Characteristics:**
| Aspect | Configuration | Rationale |
|--------|--------------|-----------|
| **Chunking** | 1024 tokens, 200 overlap | Metadata spans multiple pages |
| **Embedding** | AITeamVN/Vietnamese_Embedding_V2 | Optimized for Vietnamese |
| **Storage** | In-memory ChromaDB | Temporary, deleted after extraction |
| **Retrieval** | 6 targeted queries | One per metadata field |
| **Reranking** | UniML/UniML-VDR (ViRanker) | Cross-encoder precision |
| **Extraction** | Qwen 3.5 4B | LLM for structured output |

**Queries used:**
```python
METADATA_QUERIES = {
    "document_number": "Số hiệu văn bản, số quyết định, số thông báo",
    "valid_dates": "Ngày hiệu lực, ngày ký, ngày ban hành, ngày hết hạn",
    "cohorts": "Áp dụng cho khóa sinh viên nào? Khóa tuyển sinh năm bao nhiêu?",
    "amends": "Văn bản này sửa đổi, bổ sung, thay thế văn bản nào?",
    "academic_year": "Năm học nào? Niên khóa nào?",
    "scope": "Đối tượng áp dụng? Phạm vi áp dụng?"
}
```

**Output:**
```json
{
  "document_number": "108/QĐ-ĐHCNTT",
  "valid_from": "2024-09-01",
  "valid_until": "2028-12-31",
  "cohort_years": [2024, 2025, 2026, 2027],
  "cohort_scope": "explicit",
  "amends_documents": ["141/QĐ-ĐHCNTT"],
  "temporal_confidence": 0.92
}
```

**Status:** ⚠️ ~80% complete (see [metadata-rag-subgraph.md](metadata-rag-subgraph.md))

---

### Pipeline 2: Content RAG (Phase 2 - Planned)

**Purpose:** Answer user queries using document content

**Characteristics:**
| Aspect | Configuration | Rationale |
|--------|--------------|-----------|
| **Chunking** | 512 tokens, 100 overlap | Precise retrieval, less noise |
| **Embedding** | LightRAG default (bge-large-zh-v1.5) | Already optimized in LightRAG |
| **Storage** | Qdrant (persistent) | Production vector DB |
| **Retrieval** | Graph + Vector search | LightRAG's hybrid approach |
| **Pre-filtering** | ⭐ **Temporal + Cohort** | Filter BEFORE semantic search |
| **Reranking** | UniML/UniML-VDR + Temporal boost | Combine semantic + temporal |

**Pre-filtering logic:**
```sql
-- Step 1: Find valid doc_ids for this query
SELECT doc_id
FROM lightrag_doc_status
WHERE
  -- Temporal validity
  (valid_from IS NULL OR valid_from <= CURRENT_DATE)
  AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
  AND is_archived = FALSE

  -- Cohort filtering (if user specifies cohort)
  AND (
    cohort_scope = 'universal'  -- Applies to all students
    OR cohort_years @> ARRAY[2024]  -- Applies to user's cohort
    OR cohort_scope = 'unspecified'  -- No cohort info (assume valid)
  )

-- Step 2: Pass doc_ids to LightRAG for semantic search
-- LightRAG queries ONLY these doc_ids, not entire DB
```

**Benefits of pre-filtering:**
1. **Accuracy:** Never returns expired documents
2. **Speed:** Smaller search space (100 docs vs 1000 docs)
3. **Cohort-aware:** Students only see relevant policies
4. **Explainable:** Can show why docs were excluded

**Status:** ⚪ Not yet started

---

## Temporal Pre-filtering

### Why Pre-filter?

**Without pre-filtering:**
```
User query → LightRAG searches ALL 1000 docs → Returns top 100
  → Reranker applies temporal scoring → Many expired docs rank high semantically
  → Need to filter out 30-40% of results → Final top 10 may still have expired docs
```

**With pre-filtering:**
```
User query → PostgreSQL filters 1000 → 300 valid docs
  → LightRAG searches ONLY 300 valid docs → Returns top 100 (all valid)
  → Reranker applies temporal scoring → Only valid docs, sorted by recency
  → Final top 10 are ALL valid + relevant ✅
```

**Performance comparison:**

| Metric | Without Pre-filter | With Pre-filter | Improvement |
|--------|-------------------|-----------------|-------------|
| Docs searched | 1000 | 300 | **3.3x fewer** |
| Invalid results | 30-40% | 0% | **100% precision** |
| Query latency | ~500ms | ~200ms | **2.5x faster** |
| User trust | Low (expired docs) | High (only valid) | **Better UX** |

---

### Implementation Strategy

#### Option A: Metadata Join (Current Plan)

**Approach:** Store metadata in PostgreSQL, join during retrieval

```python
# Step 1: Get valid doc_ids from PostgreSQL
valid_doc_ids = postgres_client.query("""
    SELECT doc_id
    FROM lightrag_doc_status
    WHERE valid_from <= CURRENT_DATE
      AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
      AND is_archived = FALSE
""")

# Step 2: Query LightRAG with doc_id filter
results = lightrag_client.query(
    query=user_query,
    mode="hybrid",
    doc_ids=valid_doc_ids  # ⭐ Filter at source
)
```

**Pros:**
- ✅ Clean separation (metadata in SQL, content in vector DB)
- ✅ Easy to update metadata without reindexing content
- ✅ SQL queries are very fast (indexed)

**Cons:**
- ❌ Requires modifying LightRAG API to support doc_id filtering
- ❌ Two-step query (PostgreSQL → LightRAG)

#### Option B: Metadata in Vector DB

**Approach:** Duplicate metadata as vector DB metadata

```python
# During indexing
qdrant_client.upsert(
    collection_name="documents",
    points=[{
        "id": doc_id,
        "vector": embedding,
        "payload": {
            "content": chunk_text,
            "valid_from": "2024-09-01",
            "valid_until": "2028-12-31",
            "is_archived": False
        }
    }]
)

# During query
results = qdrant_client.search(
    collection_name="documents",
    query_vector=query_embedding,
    query_filter={
        "must": [
            {"key": "valid_until", "range": {"gte": today}},
            {"key": "is_archived", "match": {"value": False}}
        ]
    }
)
```

**Pros:**
- ✅ Single query (no PostgreSQL join)
- ✅ Qdrant has built-in filtering

**Cons:**
- ❌ Metadata duplication (PostgreSQL + Qdrant)
- ❌ Need to sync updates to both DBs
- ❌ Qdrant filters are less powerful than SQL

**Decision:** Use **Option A** (metadata join) for clean architecture.

---

## Cohort-Aware Retrieval

### The Cohort Problem

**Scenario:**
- Student from cohort 2024 asks: "Điều kiện tốt nghiệp là gì?"
- System has 3 documents:
  1. Quy chế 2020 (cohort_years: [2020, 2021, 2022, 2023])
  2. Quy chế 2024 (cohort_years: ["*"] - universal)
  3. Quyết định 108 (cohort_years: [2024, 2025] - exception for K2024-K2025)

**Expected behavior:**
- ✅ Show universal policy (Quy chế 2024)
- ✅ Show cohort-specific exception (QĐ 108)
- ❌ Hide old policy not applicable (Quy chế 2020)

---

### Cohort Detection

**Agent 1 needs to extract cohort from query:**

```python
# User profile (if available)
user_cohort = user_profile.get("cohort_year")  # e.g., 2024

# Or infer from query
query = "Tôi là sinh viên K24, điều kiện tốt nghiệp là gì?"
# → Agent 1 extracts: cohort_year = 2024

# Or use current enrollment year as default
if not user_cohort:
    # Assuming students enroll in September
    current_month = datetime.now().month
    current_year = datetime.now().year
    if current_month >= 9:
        user_cohort = current_year
    else:
        user_cohort = current_year - 1
```

---

### Cohort Filtering Logic

**Three cohort scopes:**

1. **Universal (`cohort_scope = 'universal'`):** Applies to all students
   - Example: General university regulations
   - Stored as: `cohort_years = ["*"]`

2. **Explicit (`cohort_scope = 'explicit'`):** Specific cohorts only
   - Example: Admission policy for K2024-K2028
   - Stored as: `cohort_years = [2024, 2025, 2026, 2027, 2028]`

3. **Unspecified (`cohort_scope = 'unspecified'`):** No cohort info extracted
   - Example: General announcements, event notices
   - Stored as: `cohort_years = []`
   - Treated as: Assume applies to current students

**SQL query with cohort filtering:**

```sql
-- Find documents applicable to cohort 2024
SELECT doc_id
FROM lightrag_doc_status
WHERE
  -- Temporal validity (as before)
  (valid_from IS NULL OR valid_from <= CURRENT_DATE)
  AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
  AND is_archived = FALSE

  -- Cohort filtering
  AND (
    cohort_scope = 'universal'           -- Applies to everyone
    OR 2024 = ANY(cohort_years)          -- Explicitly includes cohort 2024
    OR (cohort_scope = 'unspecified'     -- No cohort info
        AND valid_from >= '2023-09-01')  -- But recent enough to be relevant
  )
```

**Example results:**

| Document | cohort_years | cohort_scope | Applies to K2024? |
|----------|--------------|--------------|-------------------|
| Quy chế 2024 | ["*"] | universal | ✅ Yes |
| QĐ 108/2024 | [2024, 2025] | explicit | ✅ Yes |
| Quy chế 2020 | [2020, 2021, 2022, 2023] | explicit | ❌ No |
| Thông báo sự kiện | [] | unspecified | ✅ Yes (recent) |

---

### Cohort Edge Cases

#### Case 1: Multi-cohort documents

**Example:** "Chương trình đào tạo áp dụng cho K2024-K2028"

```python
cohort_years = [2024, 2025, 2026, 2027, 2028]
cohort_scope = "explicit"

# Student from 2024: ✅ Match
# Student from 2026: ✅ Match
# Student from 2029: ❌ No match (use older universal policy)
```

#### Case 2: Universal with exceptions

**Example:**
- Quy chế chung: cohort_years = ["*"], cohort_scope = "universal"
- Quyết định 108 (sửa đổi cho K2024): cohort_years = [2024], cohort_scope = "explicit"

**Query from K2024 student returns BOTH:**
1. Quyết định 108 (specific exception) - **higher rank**
2. Quy chế chung (universal rule) - **lower rank**

**Response generation:**
```
"Theo Quyết định 108/QĐ-ĐHCNTT (áp dụng cho K2024), điều kiện tốt nghiệp là...

Lưu ý: Quy định này là bổ sung riêng cho sinh viên K2024. Sinh viên các khóa khác
áp dụng theo Quy chế chung."
```

#### Case 3: Historical cohort queries

**Query:** "Quy định tốt nghiệp của K2020 là gì?"

**Solution:** Extract target cohort from query, not user profile

```python
# Agent 1 detects
query_about_cohort = 2020  # From "K2020" in query
user_cohort = 2024         # Current user

# Use query_about_cohort for filtering (historical query)
# Set include_archived=True to find old policies
```

---

## Implementation Plan

### Phase 2.1: LightRAG Modification (Week 2)

**Goal:** Add doc_id filtering to LightRAG API

**Tasks:**
1. Modify LightRAG `query()` function to accept `doc_ids` parameter
2. Update Qdrant query to filter by `doc_id IN (...)`
3. Update graph query to filter by `doc_id IN (...)`
4. Test with sample queries

**Code changes needed:**

```python
# LightRAG/lightrag/api.py
@router.post("/query")
async def query_endpoint(request: QueryRequest):
    # ⭐ NEW: Accept doc_ids parameter
    doc_ids = request.doc_ids if hasattr(request, 'doc_ids') else None

    # Pass to knowledge base
    results = await kg.query(
        query=request.query,
        mode=request.mode,
        doc_ids=doc_ids  # ⭐ NEW
    )
    return results

# LightRAG/lightrag/kg.py
async def query(self, query: str, mode: str = "hybrid", doc_ids: List[str] = None):
    # ⭐ NEW: Filter vector search by doc_ids
    if doc_ids:
        vector_results = self.vector_db.search(
            query_embedding=query_vec,
            filter={"doc_id": {"$in": doc_ids}}  # ⭐ NEW
        )
    else:
        vector_results = self.vector_db.search(query_embedding=query_vec)

    # ⭐ NEW: Filter graph search by doc_ids
    if doc_ids:
        graph_results = self.graph_db.query(
            query=query,
            filter={"doc_id": {"$in": doc_ids}}  # ⭐ NEW
        )
    else:
        graph_results = self.graph_db.query(query=query)

    return merge_results(vector_results, graph_results)
```

---

### Phase 2.2: Pre-filtering Integration (Week 2)

**Goal:** Add temporal + cohort pre-filtering to query pipeline

**Tasks:**
1. Create `TemporalFilter` class in `LangGraph/src/agent/filters/`
2. Add `apply_temporal_filter_node` to query graph
3. Update Agent 1 to extract cohort info
4. Test with expired/valid/cohort-specific documents

**New node:**

```python
# LangGraph/src/agent/filters/temporal_filter.py
from datetime import datetime
from typing import List, Optional
import asyncpg

class TemporalFilter:
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def get_valid_doc_ids(
        self,
        user_cohort: Optional[int] = None,
        current_date: Optional[str] = None,
        include_archived: bool = False
    ) -> List[str]:
        """
        Get list of valid doc_ids based on temporal + cohort filters.
        """
        if current_date is None:
            current_date = datetime.now().date().isoformat()

        query = """
            SELECT doc_id::text
            FROM lightrag_doc_status
            WHERE
              -- Temporal validity
              (valid_from IS NULL OR valid_from <= $1::date)
              AND (valid_until IS NULL OR valid_until >= $1::date)
              AND ($2 OR is_archived = FALSE)  -- Include archived if requested

              -- Cohort filtering
              AND (
                $3::int IS NULL  -- No cohort specified
                OR cohort_scope = 'universal'
                OR $3 = ANY(cohort_years)
                OR cohort_scope = 'unspecified'
              )
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, current_date, include_archived, user_cohort)
            return [row['doc_id'] for row in rows]


# LangGraph/src/agent/graphs/query_graph.py
async def apply_temporal_filter_node(state: QueryState) -> QueryState:
    """Apply temporal + cohort pre-filtering before retrieval."""

    # Extract cohort from query or user profile
    user_cohort = state.get("user_cohort") or state.get("query_cohort")

    # Check if this is a historical query
    include_archived = state.get("is_historical_query", False)

    # Get valid doc_ids
    temporal_filter = TemporalFilter(db_pool)
    valid_doc_ids = await temporal_filter.get_valid_doc_ids(
        user_cohort=user_cohort,
        include_archived=include_archived
    )

    logger.info(f"🔍 Pre-filter: {len(valid_doc_ids)} valid documents")

    return {
        "valid_doc_ids": valid_doc_ids,
        "prefilter_applied": True
    }
```

**Update query graph:**

```python
# Add node
query_graph.add_node("apply_temporal_filter", apply_temporal_filter_node)

# Update edges
query_graph.set_entry_point("parse_query")  # Agent 1
query_graph.add_edge("parse_query", "apply_temporal_filter")  # ⭐ NEW
query_graph.add_edge("apply_temporal_filter", "retrieve_from_lightrag")
query_graph.add_edge("retrieve_from_lightrag", "rerank_results")
# ... rest of graph
```

---

### Phase 2.3: Agent 1 Enhancement (Week 2-3)

**Goal:** Extract cohort information from queries

**Tasks:**
1. Update Agent 1 prompt to detect cohort mentions
2. Add `query_cohort` to `QueryState`
3. Add Vietnamese cohort patterns (K24, khóa 2024, năm 2024)
4. Test with cohort-specific queries

**Updated Agent 1 output:**

```python
class QueryUnderstanding(BaseModel):
    parsed_intention: str
    extracted_entities: List[str]
    query_confidence: float
    needs_clarification: bool

    # ⭐ NEW fields
    query_cohort: Optional[int] = None  # Extracted cohort year
    is_historical_query: bool = False    # Asking about past cohorts
    temporal_context: Optional[str] = None  # "current", "past", "future"
```

**Prompt addition:**

```python
COHORT_EXTRACTION_PROMPT = """
Phân tích câu hỏi và xác định:

1. **Khóa sinh viên (Cohort):** Câu hỏi đề cập đến khóa nào?
   - "K24", "K2024", "khóa 24" → 2024
   - "khóa 2025", "sinh viên năm 2025" → 2025
   - Không đề cập → null

2. **Bối cảnh thời gian:**
   - "hiện tại", "bây giờ" → "current"
   - "năm ngoái", "K2020", "trước đây" → "past" (is_historical_query=true)
   - "năm sau", "sắp tới" → "future"

Ví dụ:
- "Điều kiện tốt nghiệp của K24 là gì?" → cohort=2024, temporal="current"
- "Quy định điểm danh năm 2020 như thế nào?" → cohort=2020, temporal="past", historical=true
- "Tôi là SV K25, học phí là bao nhiêu?" → cohort=2025, temporal="current"
"""
```

---

### Phase 2.4: Testing & Validation (Week 3)

**Goal:** Comprehensive testing of hybrid RAG system

**Test scenarios:**

1. **Temporal filtering:**
   - Query expired document → should not appear
   - Query current document → should appear
   - Query expiring-soon document → should appear with warning

2. **Cohort filtering:**
   - K2024 student queries → only see universal + K2024 docs
   - K2020 student queries → only see universal + K2020 docs
   - No cohort specified → see all non-expired docs

3. **Amendment ranking:**
   - Query amended topic → amended doc ranks higher
   - Original doc should appear but deprioritized

4. **Historical queries:**
   - "K2020's policy" → should search archived docs
   - Should return old policies with clear labels

**See:** [testing-guide.md](../guides/testing.md) for full test suite

---

## Novel Contributions

### What Makes This Hybrid Architecture Unique?

| Feature | Our Approach | Existing Systems |
|---------|--------------|------------------|
| **Dual pipelines** | Separate metadata + content RAG with different chunking | Single pipeline for both |
| **Pre-filtering** | Temporal + cohort filter BEFORE semantic search | Post-filtering (slower, less accurate) |
| **Cohort awareness** | First-class support with scope detection | Not supported or manual tagging |
| **Vietnamese patterns** | Optimized Vietnamese cohort/date extraction | English-only or basic regex |
| **Track_id approach** | Instant metadata save using track_id | Polling (slow) or no metadata |

### Comparison to Related Work

#### GraphRAG (Microsoft)
- ✅ Graph-based RAG with entity/relationship extraction
- ❌ No temporal awareness
- ❌ No metadata extraction pipeline
- ❌ English-only

#### LightRAG (Original)
- ✅ Fast graph + vector hybrid retrieval
- ✅ Supports incremental updates
- ⚠️ Basic timestamp tracking only
- ❌ No temporal scoring, no pre-filtering
- ❌ No cohort awareness

#### T-GRAG (EMNLP 2025)
- ✅ Temporal graph with time-sensitive relationships
- ✅ Temporal scoring in ranking
- ❌ Requires manual temporal annotation
- ❌ English-only
- ❌ No cohort concept

#### VersionRAG (Arxiv 2024)
- ✅ Version tracking with timestamps
- ✅ Historical queries
- ❌ Manual version linking
- ❌ No automatic amendment detection
- ❌ English-only

#### **UITRaph (Ours)**
- ✅ Automatic temporal metadata extraction (RAG-based)
- ✅ Pre-filtering before semantic search (faster + more accurate)
- ✅ Cohort-aware retrieval (university-specific)
- ✅ Vietnamese-optimized (regex + LLM)
- ✅ Amendment graph (automatic detection)
- ✅ Soft delete with historical queries

---

## Performance Expectations

### Latency Breakdown

**Without pre-filtering:**
```
Query → LightRAG (1000 docs) → Rerank (100 results) → Filter expired (60 remain)
  300ms      +      150ms      +        50ms         =  500ms total
```

**With pre-filtering:**
```
Query → PostgreSQL filter → LightRAG (300 docs) → Rerank (100 valid) → Done
  50ms   +       100ms      +       150ms         =  300ms total
```

**Improvement:** 40% faster + 100% precision (no expired docs)

---

### Accuracy Expectations

| Metric | Without Hybrid | With Hybrid | Target |
|--------|---------------|-------------|--------|
| **Temporal precision** | 60-70% | 95-100% | >95% |
| **Cohort precision** | N/A | 90-95% | >90% |
| **Semantic relevance** | 85-90% | 85-90% | >85% |
| **Overall F1** | 0.70-0.75 | 0.85-0.90 | >0.85 |

**Baseline:** Current system without temporal features
**Target:** After Phase 2 implementation

---

## Next Steps

### Week 2: Core Implementation

1. ✅ Design hybrid architecture (this document)
2. ⏳ Modify LightRAG for doc_id filtering
3. ⏳ Implement `TemporalFilter` class
4. ⏳ Add pre-filtering node to query graph
5. ⏳ Update Agent 1 for cohort extraction

### Week 3: Testing & Refinement

6. ⏳ Write unit tests for temporal filter
7. ⏳ Write integration tests for query pipeline
8. ⏳ Test with real UIT documents
9. ⏳ Benchmark latency and accuracy
10. ⏳ Tune temporal_weight parameter

### Week 4: Documentation & Thesis

11. ⏳ Document implementation details
12. ⏳ Write evaluation section for thesis
13. ⏳ Prepare demo scenarios
14. ⏳ Create comparison tables vs related work

---

**See also:**
- [Metadata RAG Subgraph](metadata-rag-subgraph.md) - Phase 1 implementation
- [Temporal Scoring](temporal-scoring.md) - Reranking algorithm
- [Novel Contributions](../research/novel-contributions.md) - Thesis contributions
- [Testing Guide](../guides/testing.md) - Test scenarios
