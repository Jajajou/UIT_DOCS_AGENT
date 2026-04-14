# Session Handoff: Think-tag Fix + Ablation Evaluation

**Date:** 2026-04-10
**Session Focus:** Qwen3-8B think-tag stripping, infrastructure fix, ablation config flags, frozen test pairs v2.0, 3-way ablation run
**Status:** IMPLEMENTATION COMPLETE, ABLATION RESULTS SAVED, READY FOR THESIS WRITE-UP

---

## What Was Accomplished This Session

### 1. Think-tag Fix (Qwen3-8B structured output)

Qwen3-8B emits `<think>...</think>` blocks before its JSON output, which broke `with_structured_output` parsing.

**Changes in all 3 agent files:**
- Removed `extra_body` parameter from all `.invoke()` calls (HuggingFace router rejects it)
- Replaced `with_structured_output` with direct `.invoke()` + manual JSON extraction
- Pattern applied: `re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)` then `json.loads()`
- E2E smoke tests PASSED: no JSON parse errors

**Files modified:**
- `LangGraph/src/agent/agents/agent1_query_understanding.py`
- `LangGraph/src/agent/agents/agent2_confidence_assessment.py`
- `LangGraph/src/agent/agents/agent3_response_generation.py`

### 2. Infrastructure Fix

LightRAG container had stale embedding URL (`192.168.1.103` instead of `192.168.100.88`) in env vars.

**Fix:** `docker compose up -d --force-recreate` (not just restart — force-recreate picks up new env vars)

**Lesson learned:** Always use `--force-recreate` when env vars change, not just `docker compose restart`.

### 3. Ablation Config Flags

Added toggle flags to enable/disable temporal scoring features for ablation experiments.

**Changes:**
- `use_temporal_scoring` field added to `LangGraph/src/agent/config.py`
- `use_temporal_boost=settings.use_temporal_scoring` wired into `rerank_all()` call in `LangGraph/src/agent/graphs/query_graph.py`
- Ablation controlled entirely by env vars: `USE_TEMPORAL_SCORING`, `USE_COHORT_BOOST`

**Files modified:**
- `LangGraph/src/agent/config.py`
- `LangGraph/src/agent/graphs/query_graph.py`

### 4. Test Pairs Frozen (v2.0)

File: `LangGraph/tests/eval/temporal_test_pairs.json`

- 15 pairs total: 5 cohort-specific, 5 amendment-sensitive, 5 general
- Grounded in actual indexed documents (100 docs in KB)
- **Cohort pairs** anchored to 141/QD-DHCNTT (2017-2026) vs 108/QD-DHCNTT (2015-2017) vs 128, 170
- **Amendment pairs:** 2101 -> 1314 (semiconductor, both indexed), 16/2024 -> 02/2022 (program opening, both indexed)
- These pairs are FROZEN — do not modify without creating a new versioned file

### 5. 3-Way Ablation Results (2026-04-10)

Ran full ablation over 3 configurations:
- **Baseline-S**: Semantic only (no temporal scoring, no cohort boost)
- **Baseline-T**: Temporal scoring only (no cohort boost)
- **System**: Full system (temporal scoring + cohort boost)

**Results table:**

| Config      | Overall | Cohort | Amendment | General |
|-------------|---------|--------|-----------|---------|
| Baseline-S  | 73.3%   | 20%    | 100%      | 100%    |
| Baseline-T  | 60.0%   | 20%    |  60%      | 100%    |
| System      | 60.0%   | 40%    |  40%      | 100%    |

**Win/Loss/Tie vs Baseline-S:**
- Baseline-T: W=0 L=2 T=13
- System: W=1 L=3 T=11

**Results saved to:** `LangGraph/tests/eval/ablation_results_20260410.json`

---

## Key Findings for Thesis

1. **Cohort boost (+20pp):** System achieves 40% vs Baseline-S 20% on cohort-specific pairs — demonstrates measurable improvement from cohort-aware reranking
2. **Temporal scoring hurts amendment recall:** Temporal scoring alone drops amendment accuracy from 100% to 60%; combined System drops to 40% — needs calibration
3. **General pairs unaffected:** All configs score 100% on general queries — confirms no regression for standard use cases
4. These results are suitable for the thesis evaluation section with appropriate methodology description

---

## Current Status

### What's Working
- Think-tag stripping in all 3 agents — no JSON parse errors
- Ablation flags wired into config and reranker call
- Test pairs v2.0 frozen at 15 pairs
- 3-way ablation completed and results saved

### What Needs Investigation
- **Why temporal scoring hurts amendment retrieval**: Check reranker weights for temporal vs semantic balance (currently 30%/70%)
- Hypothesis: amendment docs have similar recency, so temporal scoring adds noise rather than signal

### Known Gaps
- Many cohort pairs still MISS (doc not in top-K retrieval) — retrieval recall issue, not reranking
- Need more cohort-specific documents in KB to improve cohort pair coverage

---

## Next Steps

### Priority 1: Thesis Preparation

1. **Investigate amendment recall drop:**
   - Check `rerank_all()` temporal weight (currently `recency_weight=0.3`)
   - Try reducing to 0.1 or 0.15 for amendment-sensitive queries
   - Re-run ablation with tuned weights

2. **Expand KB for cohort queries:**
   - Add more cohort-specific docs (QD 141, 108, 128, 170 related circulars)
   - Re-run ablation after KB expansion
   - Target: cohort recall from 40% to 60%+

3. **Write thesis evaluation section:**
   - Methodology: 3-way ablation design, 15 test pairs, scoring rubric
   - Results table (see above)
   - Analysis: cohort improvement, amendment tradeoff, general stability

### Priority 2: System Improvements

4. **Comprehensive test suite** for temporal scoring (unit tests)
5. **Ping service** for automated daily archiving of expired documents
6. **Agent 2 freshness integration** — apply temporal penalties to data quality score
7. **Agent 3 expiration warnings** — surface warnings when retrieved docs are expired/expiring

---

## Important Technical Notes

### Think-tag Pattern (Qwen3-8B)
When using Qwen3-8B or other reasoning models that emit `<think>` blocks, the extraction pattern is:
```python
content = response.content
content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
data = json.loads(content)
```
Do NOT use `with_structured_output` for these models — it fails on think-tagged output.

### Ablation Env Vars
Control ablation via `.env`:
```
USE_TEMPORAL_SCORING=true   # enables temporal penalty/boost in reranker
USE_COHORT_BOOST=true       # enables cohort-aware score boost
```

### Docker Force-Recreate
When environment variables in `.env` or `.env.lightrag` change:
```bash
docker compose up -d --force-recreate
```
Simple `docker compose restart` does NOT pick up env var changes.

### Test Pair File Versioning
- Current frozen version: `temporal_test_pairs.json` (v2.0, 2026-04-10)
- DO NOT modify this file — create a new versioned file if test set needs updating
- Ablation results reference this exact set

---

## Troubleshooting

### JSON parse error in agent output
- Check if model emits `<think>` blocks
- Verify `re.sub` pattern covers full think block (use `re.DOTALL` flag)
- Add debug logging: `print(f"[AGENT] Raw content: {content[:200]}")`

### Ablation results differ from expected
- Verify env vars are set correctly before running: `echo $USE_TEMPORAL_SCORING`
- Force recreate LightRAG container after env changes
- Check test pair file has not been modified: `git diff LangGraph/tests/eval/temporal_test_pairs.json`

### Low cohort pair accuracy
- Root cause is retrieval (not reranking): docs not in top-K from LightRAG
- Check KB has the target documents: query LightRAG directly for the document number
- Consider adding `hybrid` retrieval mode for better cohort recall

---

## File References

| File | Purpose |
|------|---------|
| `LangGraph/src/agent/agents/agent1_query_understanding.py` | Think-tag fix applied |
| `LangGraph/src/agent/agents/agent2_confidence_assessment.py` | Think-tag fix applied |
| `LangGraph/src/agent/agents/agent3_response_generation.py` | Think-tag fix applied |
| `LangGraph/src/agent/config.py` | Added `use_temporal_scoring` flag |
| `LangGraph/src/agent/graphs/query_graph.py` | Wired ablation flags into rerank call |
| `LangGraph/tests/eval/temporal_test_pairs.json` | Frozen test set v2.0 (15 pairs) |
| `LangGraph/tests/eval/run_evaluation.py` | Evaluation runner |
| `LangGraph/tests/eval/ablation_results_20260410.json` | Ablation results (2026-04-10) |

---

## Git Status

**Branch:** develop

**Committed this session:**
```
feat: think-tag fix + ablation eval + frozen test pairs
```

**Files included in commit:**
```
M LangGraph/src/agent/agents/agent1_query_understanding.py
M LangGraph/src/agent/agents/agent2_confidence_assessment.py
M LangGraph/src/agent/agents/agent3_response_generation.py
M LangGraph/src/agent/config.py
M LangGraph/src/agent/graphs/query_graph.py
M LangGraph/tests/eval/run_evaluation.py
M LangGraph/tests/eval/temporal_test_pairs.json
A LangGraph/tests/eval/ablation_results_20260410.json
A cspell.json
M SESSION_HANDOFF.md
```

**Excluded (in .gitignore):**
```
LangGraph/.langgraph_api/*.pckl
```

---

**Session ended:** 2026-04-10
**Next session should:** Investigate temporal scoring impact on amendment pairs, expand KB for cohort queries, begin thesis evaluation write-up
