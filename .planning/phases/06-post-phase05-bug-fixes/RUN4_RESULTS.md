# Run4 Results — 2026-06-04

## TDCE Summary
- accuracy@1: 0.805
- mrr@3: 0.498
- ap@3: 0.815
- authority_score: 0.735

## By Type Breakdown
| Type | acc@1 | mrr@3 | ap@3 | authority | n |
|------|-------|-------|------|-----------|---|
| admissions_boundary | 0.68 | 0.48 | 0.74 | 0.49 | 19 |
| amendment_boundary | 0.76 | 0.60 | 0.79 | 0.60 | 42 |
| authority_collision | 0.90 | 0.50 | 0.90 | 0.99 | 42 |
| catalog_boundary | 0.71 | 0.50 | 0.71 | 0.50 | 7 |
| cohort_boundary | 0.82 | 0.59 | 0.82 | 0.50 | 22 |
| local_vs_system | 0.80 | 0.52 | 0.80 | 1.00 | 30 |
| notice_override | 0.92 | 0.32 | 0.92 | 0.80 | 24 |
| workflow_boundary | 0.64 | 0.35 | 0.64 | 0.50 | 14 |

## Key Insights
- **amendment_boundary**: Strong performance at 0.76 (42 pairs)
- **cohort_boundary**: 0.82 accuracy, major improvement from earlier 0.32-0.55 range
- **authority_collision**: 0.90 accuracy, 0.99 authority score (near-perfect routing)
- **Weak spots**: 
  - admissions_boundary (0.68, auth=0.49) — UIT local docs not outranking system-level
  - workflow_boundary (0.64, auth=0.50) — procedure vs notice distinction still fragile

## Branch State
- Branch: feat/canonical-registry
- Commit: eb1f9de "fix: reranker temporal decay + test fixes (Phase 4 complete)"
- 9 files modified, not yet committed

## Fixes Applied This Session
1. Reranker temporal decay — use valid_from for recency scoring
2. Boost confirmed latest documents
3. Enforce authority_scope='local' for all queries
4. Reranker 400 truncation fix (6000 char limit)
5. Query_date point-in-time penalty

## Comparison to Historical Runs
- run1 (0602): 0.645
- run2 (0602): 0.685
- run3 (0530): 0.640
- run4 (0604): **0.805** ← current

Next: commit changes, update SESSION_HANDOFF.md, run ablation baseline