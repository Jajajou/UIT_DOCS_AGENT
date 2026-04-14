# Changelog

## [0.3.0] - 2026-04-14

### Added
- **Tri-mode metadata retrieval routing** (`feat/metadata-filtered-retrieval`):
  - `COHORT` queries bypass LightRAG entirely, hitting Qdrant directly with a
    `cohort_years HAS [year OR "*"]` + `must_not is_archived` pre-filter vector search.
    Falls back to GENERAL path if 0 results.
  - `AMENDMENT` queries traverse a PostgreSQL recursive CTE (`lightrag_doc_status`)
    to find the amendment chain leaf, then fetch those chunks from Qdrant.
    Falls back to GENERAL path if no `query_document_ref` or 0 results.
  - `GENERAL` queries continue through the existing LightRAG → enrich → filter → rerank path.
- **`QdrantCohortClient`** (`clients/qdrant_cohort_client.py`): embeds queries using
  the same endpoint as LightRAG (`settings.embedding_base_url`) for vector parity,
  performs filtered Qdrant search, converts `ScoredPoint` to standard chunk shape.
- **`AmendmentChainClient`** (`clients/amendment_chain_client.py`): PostgreSQL recursive
  CTE resolves amendment chains (max depth 10), fetches leaf-doc chunks from Qdrant
  via `full_doc_id` filter + vector search.
- **`retrieve_cohort_data` node** (`agents/retrieve_cohort.py`): COHORT retrieval path.
- **`retrieve_amendment_data` node** (`agents/retrieve_amendment.py`): AMENDMENT retrieval path.
- **`USE_METADATA_ROUTING` flag**: env var / `settings.use_metadata_routing` toggle.
  When `false`, `route_retrieval` bypasses tri-mode logic and all queries use GENERAL
  path (enables clean v0.2.0 vs v0.3.0 ablation comparison).
- **New ablation configs** in `run_evaluation.py`:
  - `v0.3.0_No_Routing`: reranker-only best config, routing disabled (ablation control)
  - `v0.3.0_Full`: tri-mode routing fully enabled
- **QueryState fields**: `cohort_fallback`, `amendment_fallback`, `query_document_ref`.
- **Unit tests**: 49 tests covering `QdrantCohortClient._point_to_chunk`, `route_retrieval`
  (including bypass), `route_after_cohort`, `retrieve_cohort_data`, `AmendmentChainClient`
  chain traversal (mocked psycopg2), `route_after_amendment`, `retrieve_amendment_data`.

### Changed
- `route_retrieval` now checks `settings.use_metadata_routing` first; when disabled it
  routes everything to `retrieve_data` regardless of `query_type`.
- `set_env_for_config` in eval harness now also sets `USE_METADATA_ROUTING`.
- Existing ablation configs (`Baseline-S`, `Baseline-T`, `System`, `System+Amend`) all
  carry explicit `USE_METADATA_ROUTING=false` to preserve v0.2.0 evaluation semantics.

## [0.2.0] - 2026-04-14

### Changed
- **2-agent pipeline**: removed Agent 2 (confidence assessment) entirely. Pipeline is now a
  linear 7-node graph: `prepare_input` -> `agent1_understand_query` -> `retrieve_data` ->
  `enrich_with_temporal_metadata` -> `rerank_data` -> `agent3_generate_response` ->
  `format_final_answer`. Agent 3 always produces a direct answer.
- **Clarification gating removed**: `decide_after_agent1` no longer routes to `ask_clarification`.
  Both failure modes (Agent 1 confidence gate and Agent 2 confidence gate) have been eliminated.
  All queries proceed directly to retrieval regardless of query confidence score.

### Fixed
- **`file_path` vs `file_source` mismatch** in agent3: `_generate_expiration_warnings`,
  `_format_reranked_data`, and `_extract_references` all read `file_source` but enrichment
  layer writes `file_path`. Fixed with fallback: `chunk.get("file_path", "") or chunk.get("file_source", "")`.
  Previously caused silent dedup failures and broken reference URLs.
- Removed debug prints from `agent3_generate_response` that leaked full prompt and retrieved
  document content to stdout on every request.

### Removed
- `ConfidenceAssessment` Pydantic model (Agent 2 artifact) from `query_state.py`.
- Orphan `QueryState` fields: `overall_confidence`, `needs_followup`, `followup_question`,
  `confidence_reason` (all written only by the removed Agent 2 node).
- Dead `needs_clarification` / `clarification_question` fields from Agent 1 extraction,
  return dict, error fallback, `query_understanding_system` output schema, and all 3 examples.
- Dead `confidence_assessment_system_prompt` and `data_quality_assessment_system` prompt blocks.
- Dead `fallback_response_template` prompt (never called without Agent 2).
- Dead `decide_after_agent1` import in `query_graph.py` (function exists but graph uses `add_edge` directly).
- Dead `ask_clarification` export from `agent1_query_understanding.__all__` (function deleted in prior session).

### Added
- **Eval harness unit tests** (`tests/eval/test_eval_harness.py`): 42 tests covering
  `_normalise`, `_found`, `accuracy_at_1`, `mrr`, and `ndcg_at_k` from `run_evaluation.py`.
  Includes Vietnamese diacritics normalisation, flexible separator matching, rank-based metrics,
  and edge cases (empty input, empty expected list, k-truncation).

## [0.1.1] - 2026-04-10

### Added
- **Amendment override**: when `USE_AMENDMENT_OVERRIDE=true`, any retrieved item
  whose `metadata.amended_by` is non-empty gets its temporal score forced to 0.3,
  ensuring superseded documents rank below the documents that supersede them.
  Controlled per-query via env var; off by default.
- **4-way ablation**: `System+Amend` config added to `run_evaluation.py` for
  measuring amendment override impact against the 15 frozen test pairs.

### Fixed
- Amendment override `amended_by` check uses explicit `isinstance(list)` guard
  (defensive against schema drift where field arrives as a non-list falsy value).
- Override score clamped to `[0.0, 1.0]` to prevent config errors from inverting
  ranking behavior.
- Audit log printed when override fires (helps debug ranking decisions).
- `use_amendment_override` comment in `config.yaml` clarified: value is env-var only.

## [0.1.0] - 2026-04-10

### Added
- **Cohort-aware reranking**: 3-weight scoring formula (0.55 semantic / 0.20 temporal / 0.25 cohort)
  activated when query contains a cohort year and `use_cohort_boost=True`. Prevents cross-cohort
  documents from surfacing for specific student cohort queries.
- **HTTP reranker mode**: `reranker_base_url` config routes scoring to a remote vLLM endpoint
  instead of the local FlagEmbedding model. Enables GPU offload to a separate inference server.
- **Ablation evaluation framework**: 3-way ablation (Baseline-S / Baseline-T / System) with
  15 frozen test pairs in `LangGraph/tests/eval/temporal_test_pairs.json`. Reproducible scoring
  via `LangGraph/tests/eval/run_evaluation.py`.
- **`strip_think_tags()` utility** in `utils.py`: centralizes Qwen3 `<think>...</think>` token
  stripping used across Agent 1, Agent 2, Agent 3, and metadata_rag_nodes. Replaced 4 duplicate
  inline regex patterns (one of which was inconsistent).
- **Admin `--url` flag** for single-file uploads: `upload /path/to/file.pdf --url https://...`
  tags the document with an explicit source URL instead of auto-discovery.
- **Dedup indexing**: `_dedupe_file_copies()` prevents duplicate files from being indexed twice.
- **vLLM reranker integration** in metadata RAG subgraph nodes.

### Fixed
- `explicit_url` is now only applied for single-file uploads; batch folder uploads no longer
  receive the same URL across all files.
- DB connection leak in polling loop: `conn.close()` is now guaranteed via `try/finally`,
  preventing connection pool exhaustion on cursor errors.
- Empty `cohort_years` list now returns neutral score 0.5 (was hard 0.0 penalty, same as
  wrong-cohort mismatch).
- `verbose=args.verbose or True` always-True bug in `run_evaluation.py` fixed to `args.verbose`.
- LightRAG submodule bumped to fix `input_text` KeyError during indexing.
- Removed `already_linked` counter from `backfill_amendment_links()` summary (initialized but
  never incremented, causing misleading output).
- Removed redundant function-local `import re` / `from urllib.parse import unquote` in
  `indexing_graph.py` and `utils.py`.

### Changed
- `compute_cohort_score()` docstring updated to reflect neutral-score behavior for missing/empty
  cohort metadata.
