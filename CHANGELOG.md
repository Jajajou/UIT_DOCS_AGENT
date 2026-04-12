# Changelog

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
