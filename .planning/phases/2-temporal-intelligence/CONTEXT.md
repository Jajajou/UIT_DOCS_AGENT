# Phase 2 Context: Temporal Intelligence

## Objective
Implement advanced temporal awareness for document versions, amendments, and student cohorts.

## Deep Dive Findings (Vietnamese Administrative Context)

### 1. The Partial Amendment Problem
Vietnamese documents (Quyết định, Thông tư) often amend specific Articles (Điều) without replacing the entire document.
- **VBHN Solution:** Prioritize "Văn bản hợp nhất" (Consolidated Documents) as primary RAG sources. They provide the "state of the world" after all amendments.
- **Article-level Metadata:** Extract specific amended articles (e.g., "Sửa đổi Điều 5") during indexing to help the reranker distinguish between valid and superseded content within the same document.

### 2. Amendment Chain Traversal
Chains can go 3-4 levels deep (e.g., 2018 -> 2019 -> 2024 -> 2024).
- **Recursive CTE:** Use the existing `AmendmentChainClient` logic to find the latest leaf.
- **Bidirectional Linking:** Ensure `amended_by` is updated in older documents when a new amending document is indexed (Task 2 of Plan 02).

### 3. Student Cohorts (Khóa)
Student policies are cohort-specific (e.g., Khóa 2021 follows a different graduation regulation than Khóa 2024).
- **6-Year Lifecycle:** Standard conservative window for UIT students.
- **Reranking Weights:** Refined to **0.55 semantic**, **0.20 temporal**, **0.25 cohort** for optimal routing.

### 4. Local-First Guarantee
All tools must run locally on macOS (Darwin/Apple Silicon):
- `underthesea`: Local NLP word segmentation and normalization.
- `dateparser`: Local Vietnamese date parsing.
- `APScheduler`: Local background task scheduling for `ping_service.py`.
- `MinerU-OCR`: Local MLX inference.

## Implementation Checklist

### Extraction (indexing_graph.py)
- [ ] Integrate `dateparser` and `underthesea` for high-accuracy local parsing.
- [ ] Flag `is_vbhn: true` for consolidated documents.
- [ ] Extract `amended_articles` list.
- [ ] Update `amended_by` in parent documents.

### Monitoring (ping_service.py)
- [ ] Daily archival job using `APScheduler`.
- [ ] PostgreSQL direct update for `is_archived`.

### Retrieval (reranker.py / query_graph.py)
- [ ] Apply 55/20/25 weights with cohort boost.
- [ ] Apply VBHN boost (+0.1).
- [ ] Handle `is_archived` documents (score 0.0).
- [ ] Implement historical query bypass for amendment penalties.
- [ ] Article-level prioritization in `query_graph.py`.

## Success Criteria
- [ ] Accuracy on amendment chains ≥ 95% (FR-02).
- [ ] Cohort routing precision ≥ 90% (FR-09).
- [ ] Automated archival triggers within 24h of expiration (FR-10).
- [ ] All operations remain 100% local.
