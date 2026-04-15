# Gemini Task Queue

Shared coordination file between Claude (planner) and Gemini (executor).

**Protocol:**
- Claude writes tasks here using `/plan-for-gemini`
- Gemini reads the latest PENDING task using `/gemini-tasks` (or equivalent)
- Gemini checks the box and updates status when done
- Claude checks status here before assuming work is complete

---

## TASK-001 — 2026-04-15 — codebase-cleanup

**Status:** - [x] Done
**Branch:** `refactor/codebase-cleanup`
**Priority:** medium

### Context
Full cleanup pass on the UIT_DOCS_AGENT repo before the thesis sprint. No feature changes — purely housekeeping.

### Steps

**Phase 1 — Commit pending work:**
Stage and commit these files together:
- `LangGraph/tests/test_insert_text.py`
- `LangGraph/tests/test_pg_schema.py`
- `LangGraph/tests/test_temporal_workflow.py`
- `LangGraph/tests/test_track_id_metadata.py`
- `LangGraph/tests/eval/ablation_results_thesis_final.json`
- `LangGraph/tests/eval/run_evaluation.py`
- `LangGraph/tests/eval/temporal_test_pairs.json`

Commit: `test: commit new unit tests and final ablation results`

**Phase 2 — Fix .gitignore:**
Add to `/.gitignore`:
```
mempalace.yaml
entities.json
GEMINI.md
.gemini/
.langgraph_api/
```
Commit: `chore: update .gitignore to cover leaked local artifacts`

**Phase 3 — Remove build artifacts from git (not from disk):**
```bash
git rm -r --cached LangGraph/agent.egg-info/ LangGraph/src/uit_docs_agent.egg-info/
find LangGraph/tests -type d -name __pycache__ -exec git rm -r --cached {} + 2>/dev/null; true
```
Commit: `chore: remove build artifacts and pycache from git tracking`

**Phase 4 — Delete stale files:**
- Delete: `LangGraph/requirements_v3.txt`
- Delete: `LangGraph/tests/eval/ablation_results_20260410.json`
- Delete: `LangGraph/tests/eval/ablation_results_final.json`
- Delete: `LangGraph/tests/eval/ablation_results_fixed.json`
- Delete: `LangGraph/src/testScripts/lightrag.log`
- Delete: `rm -rf .langgraph_api/` at project root (duplicate — keep `LangGraph/.langgraph_api/`)

Commit: `chore: delete stale files and duplicate runtime dir`

**Phase 5 — Reorganize test files:**
Move to `LangGraph/tests/integration/` (create dir with `__init__.py`):
- `LangGraph/tests/test_insert_text.py`
- `LangGraph/tests/test_pg_schema.py`
- `LangGraph/tests/test_temporal_workflow.py`
- `LangGraph/tests/test_track_id_metadata.py`

Check `LangGraph/tests/conftest.py` still covers the integration/ subdir after move.
Commit: `refactor: move integration tests to tests/integration/`

**Phase 6 — Consolidate docs:**
Move to `docs/reference/` (create if needed):
- `QUICK_REFERENCE_PERFORMANCE.md`
- `TESTING_CHECKLIST.md`
- `lightrag-openapi.json`

Move to `docs/`:
- `DOCUMENTATION_INDEX.md`

Move to `LangGraph/tests/notebooks/`:
- `inspect_metadata.ipynb`
- `test_temporal_extraction.ipynb`

Move to `docs/langgraph/` (create if needed):
- `LangGraph/docs/STATE_PASSING_GUIDE.md`
- `LangGraph/docs/PROMPTS_MIGRATION_GUIDE.md`

Commit: `refactor: consolidate docs into docs/ hierarchy`

**Phase 7 — Final audit:**
Run `git status` — verify clean.
Run `cd LangGraph && make test` — all tests must pass.
Fix any remaining .gitignore issues.
Commit if needed: `chore: final gitignore cleanup pass`

### Acceptance Criteria
- [x] `git status` shows clean (only expected untracked items)
- [x] `make test` passes in LangGraph/
- [x] No `.egg-info/` dirs tracked in git
- [x] No `__pycache__/` tracked in git
- [x] Root-level doc sprawl moved to `docs/`
- [x] `/.langgraph_api/` (root) deleted
