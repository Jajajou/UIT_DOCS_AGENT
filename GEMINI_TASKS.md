# Gemini Task Queue

Shared coordination file between Claude (planner) and Gemini (executor).

**Protocol:**
- Claude writes tasks here using `/plan-for-gemini`
- Gemini reads the latest PENDING task using `/gemini-tasks` (or equivalent)
- Gemini checks the box and updates status when done
- Claude reviews Gemini's work, then moves completed tasks to Archive

---

### TASK-002 — 2026-04-15 — plan-eng-review

**Status:** - [x] Done  **Branch:** `develop`
**Class:** planning  **Model:** gemini

**Context:**
Claude hit its context limit mid-skill while running /plan-eng-review. The preamble
already completed (branch detected, learnings loaded, telemetry running). Pick up
from the Design Doc Check step and run the full review interactively with the user.

The plan being reviewed is the design doc for a NEW open source repo
`claude-gemini-workflow`. No code exists yet — this is a pre-implementation
architecture review of a design plan.

Design doc path:
`~/.gstack/projects/Jajajou-UIT_DOCS_AGENT/jajajou1778-refactor-codebase-cleanup-design-20260415-185714.md`

What the plan describes:
- A standalone repo formalizing the Claude-plans-Gemini-executes workflow pattern
- Core artifact: GEMINI_TASKS.md typed task manifest with 4 cognitive classes
  (mechanical | cleanup | documentation | planning)
- Repo structure: README.md + ROLE_TAXONOMY.md + GEMINI_TASKS_SPEC.md +
  OPTIONAL_INTEGRATIONS.md + demo/ (calculator refactor fixture)
- Core constraint: zero new installs — vanilla Claude Code + Gemini CLI only
- gstack + MemPalace are optional power-ups, clearly labeled as such
- Timeline: ~15 hours, one focused weekend, after thesis milestone (~May 2026)
- Design already passed 2 adversarial review rounds (score 7.5/10)
  Two known minor concerns in `## Reviewer Concerns` — treat as acknowledged

Preamble vars (already established by Claude):
- BRANCH=develop
- SLUG=Jajajou-UIT_DOCS_AGENT
- REPO_MODE=collaborative

**Acceptance:**
/plan-eng-review runs to completion — all sections covered:
Step 0 scope challenge, architecture review, code quality review, test coverage
diagram, performance review, outside voice offer, completion summary, and review
readiness dashboard written to ~/.gstack/analytics/.

**Commands:**
Run /plan-eng-review from your gstack installation.
Your gstack skills are at ~/.gemini/skills/.
Load the skill with: /plan-eng-review
Working directory: /Users/jajajou1778/UIT_DOCS_AGENT

---

## TASK-003 — 2026-04-16 — fix-test-configuration-import

**Status:** - [x] Done
**Branch:** `develop`
**Class:** mechanical  **Model:** gemini
**Priority:** high

### Context
`test_configuration.py` imports from `agent.graph` which no longer exists after the codebase refactor in v0.3.1. The module moved to `agent.graphs.query_graph`. This is a P0 unblocked fix — no gate condition, run immediately.

### Steps

**Phase 1 — Fix the import:**

File: `LangGraph/tests/unit_tests/test_configuration.py`

Find every line that starts with `from agent.graph import` and change it to `from agent.graphs.query_graph import`.

**Phase 2 — Verify tests pass:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT/LangGraph && make test
```

All tests must pass (expect 60+ passing, 0 failing).

Commit: `fix: update test_configuration.py import from agent.graph to agent.graphs.query_graph`

### Acceptance Criteria
- [ ] `from agent.graph import` no longer appears in `test_configuration.py`
- [ ] `from agent.graphs.query_graph import` is present in `test_configuration.py`
- [ ] `make test` exits 0 with no failures

---

## TASK-004 — 2026-04-16 — ablation-evaluation-run

**Status:** - [x] Done
**Branch:** `develop`
**Class:** mechanical  **Model:** gemini
**Priority:** high
**Depends on:** LangGraph server running (manual restart by user — Gemini cannot do this)

### Context
The ablation study compares three retrieval configurations (Baseline-S, Baseline-T, System) across all eval splits. Results feed TASK-005 (documentation update). This is the critical path item for thesis defense.

**CRITICAL: Pre-flight check first. If server not ready, abort entirely — do NOT continue.**

### Steps

**Phase 0 — Pre-flight health check:**

```bash
curl -s http://localhost:2024/health || (echo "LangGraph not ready — abort TASK-004" && exit 1)
```

If this fails, stop. Report server not running. Do not proceed to Phase 1.

**Phase 1 — Run ablation evaluation:**

Working directory: `/Users/jajajou1778/UIT_DOCS_AGENT/LangGraph`

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT/LangGraph && python tests/eval/run_evaluation.py --split all --all-configs --out tests/eval/ablation_results_v031.json
```

NOTE: Use `--out` not `--output`. The flag `--output` is unrecognized and will cause an error.

**Phase 2 — Verify output:**

```bash
python -c "import json; d=json.load(open('tests/eval/ablation_results_v031.json')); print([r['config_name'] for r in d])"
```

Must show all 3 config names: Baseline-S, Baseline-T, System.

Commit: `test: run ablation evaluation v0.3.1 and save results to tests/eval/ablation_results_v031.json`

### Acceptance Criteria
- [ ] Pre-flight curl to `http://localhost:2024/health` returns 200 before proceeding
- [ ] `tests/eval/ablation_results_v031.json` exists after the run
- [ ] JSON contains results for all 3 configs: Baseline-S, Baseline-T, System
- [ ] Each result entry has `mrr`, `hit_rate`, and `routing_accuracy` keys

---

## TASK-005 — 2026-04-16 — update-technical-report-ablation

**Status:** - [x] Done
**Branch:** `develop`
**Class:** documentation  **Model:** gemini
**Priority:** high
**Depends on:** TASK-004 (ablation_results_v031.json must exist)

### Context
The TECHNICAL_REPORT Section 7 ablation table and MEETING_PREP metrics section both have placeholder or v0.2.0 numbers. Update both with v0.3.0 numbers from the ablation results JSON. Every numeric cell must trace to a value in the JSON.

### Steps

**Phase 1 — Read results JSON:**

File: `LangGraph/tests/eval/ablation_results_v031.json`

Schema mapping:
- `config_name` → table column headers (Baseline-S, Baseline-T, System)
- `mrr` → MRR column
- `hit_rate` → Hit@1 column
- `routing_accuracy` → Routing Acc column

**Phase 2 — Update TECHNICAL_REPORT Section 7:**

File: `LangGraph/docs/TECHNICAL_REPORT_COMPREHENSIVE.md`

Find Section 7 ablation table. Replace all numeric cells with v0.3.0 values from the JSON. Do not change table structure, headings, or any non-numeric content.

**Phase 3 — Update MEETING_PREP metrics section:**

File: `LangGraph/docs/MEETING_PREP_20260410.md`

Find the metrics section. Update the same three metrics (MRR, Hit@1, Routing Acc) for each configuration with the same v0.3.0 values.

Commit: `docs: update ablation table in TECHNICAL_REPORT and MEETING_PREP with v0.3.1 results`

### Acceptance Criteria
- [ ] Every numeric cell in TECHNICAL_REPORT Section 7 ablation table traces to `ablation_results_v031.json`
- [ ] MEETING_PREP metrics section shows v0.3.1 numbers for all 3 configs
- [ ] No placeholder values (e.g., "TBD", "XX.X", "0.00") remain in either file

---

## TASK-006 — 2026-04-16 — draft-new-test-pairs

**Status:** - [x] Done
**Branch:** `develop`
**Class:** documentation  **Model:** gemini
**Priority:** medium
**Depends on:** Claude confirming doc IDs (TASK-006 is GATED — do not run until Claude provides doc IDs below)

**DOC IDs FOR NEW PAIRS (confirmed by Claude 2026-04-16):**

id=19 — AMENDMENT path
- expected_doc_ids: ["doc-4401adba766625ddce0f1eb38c8e1e8c"]
- expected_doc_numbers: ["02/2022/TT-BGDDT"]
- relationship: 02/2022/TT-BGDDT amends ["22/2017/TT-BGDDT", "09/2017/TT-BGDDT"]
- query_document_ref: "22/2017/TT-BGDDT"
- chunk_count: 22

id=20 — AMENDMENT path
- expected_doc_ids: ["doc-25919be32573c58534f3477c02c3c2f5"]
- expected_doc_numbers: ["17/2021/TT-BGDDT"]
- relationship: 17/2021/TT-BGDDT amends ["07/2015/TT-BGDDT"]
- query_document_ref: "07/2015/TT-BGDDT"
- chunk_count: 12

id=21 — AMENDMENT path
- expected_doc_ids: ["doc-ed600bb2c49e17558bff4f7fb37be746"]
- expected_doc_numbers: ["30/2023/TT-BGDDT"]
- relationship: 30/2023/TT-BGDDT amends ["12/2016/TT-BGDDT"]
- query_document_ref: "12/2016/TT-BGDDT"
- chunk_count: 4

id=22 — AMENDMENT path
- expected_doc_ids: ["doc-ffb7bdba1039e89c350553b2ebdbf86f"]
- expected_doc_numbers: ["333/QD-DHCNTT"]
- relationship: 333/QD-DHCNTT amends ["807/QD-DHCNTT"]
- query_document_ref: "807/QD-DHCNTT"
- chunk_count: 3

id=23 — COHORT path
- expected_doc_ids: ["doc-a2b3b9aa94518ef4efb5514ca228b9c1"]
- expected_doc_numbers: ["262/QD-DHQG"]
- relationship: 262/QD-DHQG has cohort_years=[2022], amends 671/DHQG-DT
- query_cohort_year: 2022
- chunk_count: 5

### Context
The eval set currently has 19 pairs (ids 0-18). Need 5 more pairs (ids 19-23) to reach 24 pairs for defense. Gemini drafts the shells using the existing schema. Leave `expected_doc_ids` as placeholders — Claude will fill in the real doc IDs after review.

### Steps

**Phase 1 — Read existing pairs to understand schema:**

File: `LangGraph/tests/eval/temporal_test_pairs.json`

Read the full file and understand the schema used by existing pairs (especially the routing_test type pairs which test temporal/amendment reasoning).

**Phase 2 — Draft 5 new pair shells (ids 19-23):**

Append 5 new entries to `LangGraph/tests/eval/temporal_test_pairs.json`. Use this schema:

```json
{
  "id": 19,
  "type": "routing_test",
  "query": "<Vietnamese query string>",
  "expected_doc_ids": ["PLACEHOLDER"],
  "confounding_doc_ids": [],
  "expected_keywords": [],
  "temporal_aspect": "<what temporal reasoning this tests>",
  "confound_reason": "<why naive retrieval would fail>",
  "notes": "Drafted by Gemini — Claude to confirm doc IDs"
}
```

Write 5 diverse pairs covering: amendment detection, document expiration, cohort-specific retrieval, version supersession, and historical lookup.

**Phase 3 — Validate JSON:**

```bash
python -m json.tool LangGraph/tests/eval/temporal_test_pairs.json > /dev/null && echo "JSON valid"
```

Must print "JSON valid".

Commit: `test: draft 5 new temporal test pair shells (ids 19-23) for review`

### Acceptance Criteria
- [ ] `temporal_test_pairs.json` has 24 entries (ids 0-23)
- [ ] All 5 new entries follow the existing schema exactly
- [ ] `python -m json.tool temporal_test_pairs.json` exits 0 (valid JSON)
- [ ] `expected_doc_ids` is marked as `["PLACEHOLDER"]` (Claude fills in later)
- [ ] Each new pair has a distinct `temporal_aspect` covering different test dimensions

---

## Archive

### TASK-001 — 2026-04-15 — codebase-cleanup

**Status:** - [x] Done  **Reviewed:** - [x] Claude verified
**Branch:** `refactor/codebase-cleanup`

6 commits landed: test → gitignore → remove artifacts → delete stale files → reorganize tests → consolidate docs.
99/99 unit tests passing. No egg-info or pycache tracked. Root `.langgraph_api/` deleted.
