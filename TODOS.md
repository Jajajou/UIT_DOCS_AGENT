# Project TODOs

## Evaluation & Metrics
- [x] **fix(eval): Pre-fetch and cache document metadata for TDCE**
  - **Why**: Currently `temporal_evaluation.py` relies on a live `psycopg2` connection to calculate Authority Resolution. This makes the experiment fragile and hard to reproduce.
  - **Context**: We need to script a one-time export of metadata (authority_level, document_type, effective_date) for all documents referenced in the 100 test pairs and save it to a JSON lookup file.
  - **Depends on**: Existing Postgres DB being reachable one last time.

## Eval Redesign (Defense Prep) — 2026-05-12

### P0 — Run immediately

- [ ] **Run run10** with cohort filter fix (is_empty removed from qdrant_cohort_client.py)
  - Expect cohort_boundary to improve from 0.32
  - Command: `cd LangGraph && python tests/eval/temporal_evaluation.py --pairs tests/eval/eval_pairs_v5.json`
  - Save as 1205_run10.json

- [ ] **Run ablation baseline** (USE_METADATA_ROUTING=false, same 200 pairs)
  - Required to prove temporal routing contributes — without it, 0.540 is uninterpretable
  - Command: `USE_METADATA_ROUTING=false python tests/eval/temporal_evaluation.py --pairs tests/eval/eval_pairs_v5.json`
  - Save as 1205_baseline.json
  - Compare per-category delta: routing ON vs OFF = thesis contribution table

### P1 — Metric improvements

- [ ] **Add MRR@3** to temporal_evaluation.py
  - Partial credit for rank 2/3 (1/2, 1/3); fixes single-label binary penalty
  - File: `LangGraph/tests/eval/temporal_evaluation.py`

- [ ] **Drop cascade from primary thesis table**
  - cascade_hit_rate always ~0.05 (2-3 hits in 200 pairs), not meaningful
  - Keep in JSON output, exclude from reported table
  - Replace with ablation_delta column

### P2 — Qualitative evidence

- [ ] **LLM-as-judge eval (30 pairs, reference-grounded)**
  - Pick 5 pairs from each TDCE category
  - Manually find correct doc excerpt per query (ground truth, ~2-3h work)
  - Run full pipeline → get system answer
  - Judge: [query] + [correct doc excerpt] + [system answer] → binary temporally correct?
  - Use Claude Sonnet as judge
  - Frame as "qualitative case study" in thesis, not statistical claim
  - Estimated effort: 4-5 hours total

### Known bugs fixed 2026-05-12

- [x] `qdrant_cohort_client.py`: removed `{"is_empty": {"key": "cohort_years"}}` from Qdrant filter
  - Was matching all 1689 untagged chunks → cohort filter was no-op
  - 200/1889 Qdrant points have cohort_years; filter now correctly restricts to those
