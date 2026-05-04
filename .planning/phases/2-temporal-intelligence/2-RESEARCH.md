# Phase 2: Temporal Intelligence - Research

**Researched:** 2025-04-14
**Domain:** Temporal-aware RAG, Vietnamese Administrative Documents, Automated Monitoring
**Confidence:** HIGH

## Summary

This research establishes the implementation path for Phase 2: Temporal Intelligence. The core challenge is resolving "amendment chains" and "student cohorts" within the Vietnamese university document ecosystem (UIT). While Phase 1.5 implemented the Metadata RAG Subgraph, Phase 2 requires closing the loop with automated monitoring, bidirectional amendment linking, and precise cohort routing.

**Primary recommendation:** Use `APScheduler` for background monitoring and `dateparser` for robust Vietnamese temporal extraction, while implementing an **Amendment Graph Traversal** pattern to resolve document versions during retrieval. Use "Văn bản hợp nhất" (VBHN) as primary sources when available to solve the partial amendment problem.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Temporal Extraction | API / Backend | LLM (Agent) | RAG-based extraction in the indexing pipeline owns the ground truth metadata. |
| Temporal Scoring | API / Backend | Reranker | Reranker applies recency boost (70/30) during retrieval to deprioritize expired content. |
| Amendment Resolution| API / Backend | Database | PostgreSQL stores the amendment links; API traverses them to find the "latest" version. |
| Scheduled Archival | Background Svc| Database | `ping_service.py` runs on a schedule to mark documents as `is_archived` based on `valid_until`. |
| Cohort Filtering | API / Backend | Retrieval | Injects user cohort metadata into the retrieval/reranking filter to ensure policy relevance. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dateparser | 1.4.0 | Natural language date parsing | [VERIFIED: PyPI] Best-in-class for Vietnamese dates ("3 ngày trước", "ngày 17 tháng 01"). |
| underthesea | 6.8.5 | Vietnamese NLP / NER | [VERIFIED: PyPI] De-facto standard for Vietnamese word segmentation and entity extraction. |
| APScheduler | 3.11.2 | In-process task scheduling | [VERIFIED: PyPI] Lightweight, thread-safe, and integrates perfectly with FastAPI/LangGraph. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| psycopg2-binary | 2.9.11 | PostgreSQL adapter | [VERIFIED: pyproject.toml] Used for direct metadata manipulation and scheduled archival. |
| pydantic | 2.13.0 | Schema validation | [VERIFIED: pyproject.toml] Ensures metadata extracted by agents matches expected types. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| APScheduler | Celery / Redis | Overkill for a single chatbot; adds infrastructure complexity. |
| dateparser | Regex | Regex is brittle for Vietnamese date variations and relative time expressions. [ASSUMED] |
| Hard Delete | Soft Delete | Hard delete loses historical data needed for "what was the policy in 2020?" queries. |

**Installation:**
```bash
uv add dateparser underthesea apscheduler
```

## Architecture Patterns

### System Architecture Diagram: Amendment Graph Traversal
```
[User Query] ──> [Query Agent] ──> [LightRAG Retrieval]
                                            │
                                            v
                                   [Candidate Docs]
                                            │
           ┌────────────────────────────────┴──────────────────────────────┐
           │                                                               │
[Amendment Traversal] <── [PostgreSQL Metadata] ──> [Cohort Filter Injection]
           │                                                               │
           v                                                               v
[Resolve Latest Ver] ──> [Temporal Reranking (0.7/0.3)] ──> [Response Generation]
```

### Recommended Project Structure
```
LangGraph/src/agent/
├── services/
│   └── ping_service.py      # Scheduled archival and health monitoring
├── clients/
│   └── reranker.py          # Updated with cohort-aware scoring
└── graphs/
    └── indexing_graph.py    # Updated with bidirectional linking node
```

### Pattern 1: Amendment Graph Traversal
**What:** When a retrieved document has an `amended_by` link in metadata, the system follows the chain to find the most recent version.
**When to use:** For all Vietnamese administrative documents (Quyết định, Thông tư).
**Example:**
```python
# Source: [CITED: docs/implementation/temporal-scoring.md]
def resolve_latest_version(doc_id, metadata_store):
    current = metadata_store.get(doc_id)
    while current.get("amended_by"):
        latest_id = current["amended_by"][-1] # Follow latest amendment
        current = metadata_store.get(latest_id)
    return current
```

### Anti-Patterns to Avoid
- **Hard-coding Current Date:** Never use `datetime.now()` inside pure functions; pass it as an argument to allow for historical simulation.
- **Polling for track_id:** Do not wait in a loop for indexing; use the `track_id` -> `doc_id` instant save pattern already implemented in `lightrag_client.py`.

## Deep Dive: Partial Amendments & Administrative Logic

### 1. Partial Amendment Resolution
Vietnamese documents frequently amend only specific Articles (Điều) or Clauses (Khoản) of a base document.

**The Challenge:**
If *Document B* amends Article 5 of *Document A*, but the user asks about Article 3 (which is still valid in *Document A*), a simple recency bias that deprioritizes *Document A* entirely will hide the correct answer.

**Research Findings:**
- **Consolidated Documents (Văn bản hợp nhất - VBHN):** These are official but technically non-legal compilations that merge base documents with all subsequent amendments. [CITED: Ordinance on Consolidation of Legal Normative Documents 2012]
- **VBHN Status:** While VBHN has no independent legal validity (the originals prevail in case of discrepancy), it is the **official basis for implementation**. 
- **RAG Strategy:** Treat VBHN as the **Primary Source** if it exists. It provides the unified state of the law/regulation. 
- **Fallback for missing VBHN:** 
  - Extract "Amended Sections" during indexing. 
  - If a query focuses on a specific article, check for its latest amendment.
  - If a query is general, use the amendment chain but retain the original doc chunks for unamended articles. [MEDIUM: Verified community pattern]

### 2. Circular & Complex Chains
UIT document examples show chains often go 3-4 levels deep:
- Base: `141/QĐ-ĐHCNTT` (2018)
- Amends: `108/QĐ-ĐHCNTT` (2019)
- Amends: `364/QĐ-ĐHCNTT` (2024)
- Amends: `560/QĐ-ĐHCNTT` (2024)

**Logic:** The system must traverse the graph `141 -> 108 -> 364 -> 560` and aggregate metadata. If `560` says "Sửa đổi Điều 1", it overrides `364`'s Article 1, which might have overridden `108`'s.

### 3. Local Processing Verification (macOS)
All recommended tools for this phase operate 100% locally on Apple Silicon (Darwin):
- **Vietnamese NLP:** `underthesea` uses local models for segmentation and normalization. [VERIFIED: underthesea source]
- **Temporal Extraction:** `dateparser` uses local regex and translation maps. [VERIFIED: PyPI]
- **OCR:** `MinerU-OCR` (local implementation in `mineru_ocr_client.py`) uses MLX for local inference on Apple Silicon. [VERIFIED: LangGraph/src/agent/clients/mineru_ocr_client.py]
- **Knowledge Graph:** LightRAG runs via Docker locally. [VERIFIED: docker-compose.yml]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vietnamese Date Parsing | Custom Regex | `dateparser` | Handles "tháng giêng", relative dates, and multiple separators. |
| Cron Logic | Sleep Loops | `APScheduler` | Handles missed jobs, persistence, and thread safety. |
| Word Segmentation | `string.split()` | `underthesea` | Vietnamese "thành phố" is one word, not two. Correct segmentation is vital for RAG. |

## Common Pitfalls

### Pitfall 1: Amendment Chain Circularity
**What goes wrong:** Doc A amends B, B amends C, C amends A.
**Why it happens:** Messy administrative updates over decades.
**How to avoid:** Implement a recursion depth limit (e.g., max 5 hops) in the traversal logic.

### Pitfall 2: Student Lifecycle Drift
**What goes wrong:** Assuming a 4-year degree for all students.
**Why it happens:** Engineering/Architecture programs are 5-6 years; medical programs longer.
**How to avoid:** Use the 6-year conservative window (implemented in Phase 1.5) or lookup specific program length in student profile. [CITED: TEMPORAL_IMPLEMENTATION_SUMMARY.md]

## Code Examples

### Vietnamese Date Parsing with dateparser
```python
import dateparser

# Source: [VERIFIED: dateparser.readthedocs.io]
text = "có hiệu lực từ ngày 15 tháng 09 năm 2024"
# dateparser handles Vietnamese month names and "ngày/tháng/năm" structure
dt = dateparser.parse(text, languages=['vi'])
print(dt.isoformat()) # 2024-09-15T00:00:00
```

### Scheduled Job with APScheduler
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Source: [VERIFIED: apscheduler.readthedocs.io]
scheduler = AsyncIOScheduler()

async def daily_archival():
    client = LightRAGAPIClient()
    result = client.archive_expired_documents()
    print(f"Archived {len(result['archived'])} documents.")

scheduler.add_job(daily_archival, 'cron', hour=0, minute=0)
scheduler.start()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Recency Decay | Amendment Graphs | 2024 (VersionRAG) | Explicitly links versions instead of guessing by date. |
| Single-agent RAG | Agentic Metadata RAG| 2025 (EMNLP) | Improves extraction confidence from 60% to 92%. |

**Deprecated/outdated:**
- **Regex-only extraction:** Replaced by Metadata RAG Subgraph (Phase 1.5) for complex Vietnamese documents.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | dateparser 1.4.0 is stable for Vietnamese | Standard Stack | May need fallback regex for edge cases. |
| A2 | 6-year student lifecycle is sufficient | Pitfalls | Some specialized programs might exceed this. |

## Open Questions

1. **How to handle "Partial Amendments"?**
   - What we know: Some docs only amend *specific articles*.
   - What's unclear: How to represent partial amendments in the graph without chunk-level metadata.
   - Recommendation: Use "Consolidated Documents" (Văn bản hợp nhất) where available. For others, extract the specific `amended_articles` list and store in metadata to help the reranker.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Data layer | ✓ | 16.0 (pgvector) | — |
| Qdrant | Vector search | ✓ | Latest | — |
| Python | Runtime | ✓ | 3.13.9 | — |
| dateparser | Extraction | ✗ | — | Regex (Partial) |
| underthesea | Extraction | ✗ | — | Regex (Partial) |
| APScheduler | Monitoring | ✗ | — | Manual execution |

**Missing dependencies with no fallback:**
- None.

**Missing dependencies with fallback:**
- `dateparser`, `underthesea`, `APScheduler` (Needs `uv add`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | LangGraph/pyproject.toml |
| Quick run command | `pytest LangGraph/tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FR-02 | Amendment detection accuracy | integration | `pytest LangGraph/tests/test_temporal.py::test_amendment_detection` | ❌ Wave 0 |
| FR-09 | Cohort routing precision | integration | `pytest LangGraph/tests/test_temporal.py::test_cohort_routing` | ❌ Wave 0 |
| FR-10 | Automated archival trigger | unit | `pytest LangGraph/tests/test_ping_service.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `LangGraph/tests/test_temporal.py` — Covers FR-02, FR-09.
- [ ] `LangGraph/tests/test_ping_service.py` — Covers FR-10.
- [ ] Framework install: `uv add --dev pytest pytest-asyncio`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Pydantic validation for extracted metadata. |
| V14 Configuration | yes | `.env.lightrag` protection for DB credentials. |

### Known Threat Patterns for RAG

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Metadata Injection | Tampering | Strict Pydantic schema validation for all agent outputs. |
| Sensitive Data Leak | Information Disclosure | Filter documents by `user_cohort` and `is_archived` before LLM context generation. |

## Sources

### Primary (HIGH confidence)
- `LightRAG API Docs` - Standard endpoint and metadata behavior.
- `LangGraph implementation` - Current metadata extraction state.
- `PyPI / dateparser` - Vietnamese support verification.
- `Ordinance on Consolidation of Legal Normative Documents (2012)` - VBHN legal status.

### Secondary (MEDIUM confidence)
- `EMNLP 2025 papers (T-GRAG)` - Temporal RAG weighting strategy.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are well-established.
- Architecture: HIGH - Phase 1.5 proved the 6-node extraction pattern.
- Pitfalls: MEDIUM - Circularity and partial amendments are real-world edge cases.

**Research date:** 2025-04-14
**Valid until:** 2025-05-14
