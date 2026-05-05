# Changelog

## [0.4.1.0] - 2026-05-05

### Added
- Added 10 contrastive test pairs for temporal evaluation (`contrastive_test_pairs.json`).
- Introduced concurrency and a `mock_mode` to the TDCE runner to improve robustness against transient API failures and speed up thesis evaluation runs.
- Established a `ContextVar`-based dependency injection system in `config.py` for thread-safe testing parameters without mutating global settings.
- Initialized `TODOS.md` for structured task tracking.

### Fixed
- Fixed regex matching and false displacement penalization in the TDCE metrics calculation.

## [0.4.0.0] - 2026-05-05

### Added
- Added `LangGraph/tests/test_deployed_api.py` as a health check script for the deployed LangGraph API.
- Configured CORS origins in `LangGraph/.env.example` to prepare for cross-origin requests from the separated frontend.

### Changed
- Prepared `web/` directory for extraction into a separate repository via `git subtree split`. The `web-frontend-only` branch was successfully created and the frontend code was cleanly removed from the AI repository.
- Replaced wildcard backend proxy logic in `web/` with direct LangGraph SSE connections using `@langchain/react`.

### Removed
- Entire `web/` directory removed from the AI backend repository (`UIT_DOCS_AGENT`) to reduce cognitive overhead and allow independent deployment.
- Removed `docker/init-admin-dashboard-db.sql`.
- Removed `web/` entries from `.gitignore` and `docker-compose.yml`.

## [0.3.2] - 2026-04-21

### Changed
- Replaced `DeepSeek-OCR-2` with `MinerU2.5-Pro-2604-1.2B` for PDF OCR. DeepSeek-OCR-2 produced hallucination loops on dense Vietnamese tables (339 garbage hits); MinerU2.5-Pro yields 0 garbage hits.
- OCR node renamed from `parse_with_DeepSeek_OCR` to `parse_with_ocr` in `indexing_graph.py`.
- Indexing state fields renamed: `deepseek_ocr_text` → `ocr_text`, `deepseek_ocr_output_dir` → `ocr_output_dir`.
- `config.yaml` and `config.py`: `deepseek_ocr` block replaced with `mineru_ocr` (adds `api_url` for remote service).
- Cache directory changed from `data/DeepSeek-OCR/` to `data/MinerU-OCR/`.

### Added
- `LangGraph/src/agent/clients/mineru_ocr_client.py`: new OCR client supporting two modes:
  - Remote: single-file `POST /file_parse` upload to the official MinerU Docker API (RTX 3060 via Tailscale at `http://100.102.11.75:8000`, ~6 s/PDF).
  - Local: MLX `two_step_extract` fallback when `api_url` is `null` (~38 s/page).
- 18 unit tests for `MinerUOCRClient` covering remote path, error cases, cache hit/miss, and Vietnamese normalization.

### Removed
- `LangGraph/src/agent/clients/deepseek_ocr_client.py`: deleted, fully replaced by `mineru_ocr_client.py`.

## [0.3.1] - 2026-04-15

### Changed
- Moved 4 new integration tests (`test_insert_text`, `test_pg_schema`, `test_temporal_workflow`, `test_track_id_metadata`) from `tests/` root into `tests/integration/` for clearer test organization.
- Consolidated scattered docs: `QUICK_REFERENCE_PERFORMANCE.md`, `TESTING_CHECKLIST.md`, `lightrag-openapi.json` moved to `docs/reference/`; `DOCUMENTATION_INDEX.md` moved to `docs/`; `LangGraph/docs/` guides moved to `docs/langgraph/`.
- Updated `.gitignore` to cover `mempalace.yaml`, `entities.json`, `GEMINI.md`, `.gemini/`, `.langgraph_api/`.

### Removed
- Deleted stale `LangGraph/requirements_v3.txt` (superseded by `pyproject.toml` + `uv.lock`).
- Deleted 3 superseded ablation result files (`ablation_results_20260410.json`, `ablation_results_final.json`, `ablation_results_fixed.json`); canonical results kept in `ablation_results_thesis_final.json`.
- Removed `LangGraph/agent.egg-info/` and `LangGraph/src/uit_docs_agent.egg-info/` build artifacts from git tracking.
- Deleted duplicate `/.langgraph_api/` directory at project root (~101 MB).
- Removed stale `LangGraph/src/testScripts/lightrag.log`.

### Added
- `GEMINI_TASKS.md`: shared Claude-Gemini task coordination queue at project root.
- Final ablation evaluation results (`ablation_results_thesis_final.json`) with 19 temporal test pairs.
- `routing_test` split option added to `run_evaluation.py` `--split` argument.

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
