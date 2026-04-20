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

## TASK-008 — 2026-04-20 — mineru-ocr-evaluation

**Status:** - [ ] Pending
**Branch:** `feat/mineru-ocr-evaluation`
**Class:** mechanical  **Model:** gemini
**Priority:** high
**Gate:** None — run immediately

### Context

DeepSeek-OCR-2 (current OCR engine) was confirmed hallucinating on dense regulatory tables.
Example: `tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.md` — pages 11-13
produce garbage loops (`PHUTI CHINHIM, THUC CHINH...`) and empty `<table>` repetitions.

We want to test **MinerU2.5-Pro-2604-1.2B** as a drop-in replacement. It uses a two-step
extraction approach (layout detection + per-region recognition) that avoids the table
hallucination failure mode.

This task: install MinerU on the Mac, run it on the broken file, save output, write a
side-by-side comparison report. Do NOT touch the indexing pipeline — this is evaluation only.

### Steps

**Phase 0 — Switch to correct branch:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
git checkout feat/mineru-ocr-evaluation
```

**Phase 1 — Install MinerU with MLX backend:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate
uv pip install "mineru[vlm]"
uv pip install "mineru-vl-utils[mlx]"
```

Verify:
```bash
python -c "import mineru; print(mineru.__version__)"
python -c "from mineru_vl_utils import MinerUClient; print('ok')"
```

**Phase 2 — Run MinerU on the broken PDF:**

Source PDF:
`firecrawl/data/daa/quydinh_huongdan/quyche-bogddt/pdf/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.pdf`

Output dir: `data/MinerU-test/tt16_bgddt/`

Write and run `LangGraph/scripts/eval/test_mineru_ocr.py`:

```python
"""Quick evaluation of MinerU2.5-Pro on a known-broken DeepSeek-OCR file."""
import asyncio
from pathlib import Path

INPUT_PDF = Path("/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa/quydinh_huongdan/quyche-bogddt/pdf/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.pdf")
OUTPUT_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/data/MinerU-test/tt16_bgddt")

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Try the high-level pipeline API first (handles PDF rendering internally)
    try:
        from mineru.cli import api_client as _api_client
        import httpx

        form_data = _api_client.build_parse_request_form_data(
            lang_list=["vi"],
            backend="vlm-mlx-engine",
            parse_method="auto",
            formula_enable=False,
            table_enable=True,
            server_url=None,
            start_page_id=0,
            end_page_id=None,
            return_md=True,
            return_images=False,
            response_format_zip=True,
            return_middle_json=False,
            return_model_output=False,
            return_content_list=False,
            return_original_file=False,
        )

        upload_assets = [_api_client.UploadAsset(path=INPUT_PDF, upload_name=INPUT_PDF.name)]

        async with httpx.AsyncClient(timeout=_api_client.build_http_timeout()) as http_client:
            local_server = _api_client.LocalAPIServer()
            base_url = local_server.start()
            await _api_client.wait_for_local_api_ready(http_client, local_server)

            submit = await _api_client.submit_parse_task(
                base_url=base_url,
                upload_assets=upload_assets,
                form_data=form_data,
            )
            await _api_client.wait_for_task_result(http_client, submit, INPUT_PDF.stem)
            result_zip = await _api_client.download_result_zip(http_client, submit, INPUT_PDF.stem)
            _api_client.safe_extract_zip(result_zip, OUTPUT_DIR)
            local_server.stop()

        print(f"Done. Output in {OUTPUT_DIR}")
        for f in sorted(OUTPUT_DIR.rglob("*.md")):
            print(f"  {f}")

    except Exception as e:
        print(f"Pipeline API failed: {e}")
        print("Falling back to page-by-page MLX approach...")
        _fallback_page_by_page()

def _fallback_page_by_page():
    """Fallback: render pages with fitz, run MinerUClient per page."""
    import fitz
    from PIL import Image
    import io
    from mlx_vlm import load as mlx_load
    from mineru_vl_utils import MinerUClient
    from mineru_vl_utils.post_process import json2md

    model, processor = mlx_load("opendatalab/MinerU2.5-Pro-2604-1.2B")
    client = MinerUClient(backend="mlx-engine", model=model, processor=processor, image_analysis=False)

    doc = fitz.open(str(INPUT_PDF))
    pages_md = []
    for i, page in enumerate(doc):
        print(f"Processing page {i+1}/{len(doc)}...")
        pix = page.get_pixmap(dpi=150)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        content_list = client.two_step_extract(img)
        md = json2md(content_list)
        pages_md.append(f"\n\n<!-- Page {i+1} -->\n\n{md}")

    output_md = OUTPUT_DIR / f"{INPUT_PDF.stem}_mineru.md"
    output_md.write_text("\n".join(pages_md), encoding="utf-8")
    print(f"Saved: {output_md}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:
```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate
python LangGraph/scripts/eval/test_mineru_ocr.py
```

NOTE: First run downloads model weights (~3 GB). This will take time. Be patient.

**Phase 3 — Compare outputs:**

Find the MinerU output markdown in `data/MinerU-test/tt16_bgddt/`.

Run comparison:
```bash
python3 - << 'EOF'
from pathlib import Path
import re

deepseek = Path("data/DeepSeek-OCR/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.md")
mineru_files = list(Path("data/MinerU-test/tt16_bgddt").rglob("*.md"))

if not mineru_files:
    print("No MinerU output found")
    exit(1)

mineru = mineru_files[0]

ds_content = deepseek.read_text()
mu_content = mineru.read_text()

# Check for garbage patterns
garbage_pattern = re.compile(r'(THUC CHINH|PHUTI CHINHIM|STT.*STT.*STT.*STT)', re.IGNORECASE)
ds_garbage = len(garbage_pattern.findall(ds_content))
mu_garbage = len(garbage_pattern.findall(mu_content))

print(f"=== COMPARISON ===")
print(f"DeepSeek-OCR-2:")
print(f"  File: {deepseek}")
print(f"  Chars: {len(ds_content)}")
print(f"  Non-empty lines: {len([l for l in ds_content.splitlines() if l.strip()])}")
print(f"  Garbage hits: {ds_garbage}")
print(f"")
print(f"MinerU2.5-Pro:")
print(f"  File: {mineru}")
print(f"  Chars: {len(mu_content)}")
print(f"  Non-empty lines: {len([l for l in mu_content.splitlines() if l.strip()])}")
print(f"  Garbage hits: {mu_garbage}")
print(f"")
print(f"Table presence (DeepSeek): {'<table>' in ds_content or '|' in ds_content}")
print(f"Table presence (MinerU): {'<table>' in mu_content or '|' in mu_content}")
print(f"")
# Print last 20 non-empty lines of each
print("--- DeepSeek last 10 non-empty lines ---")
for l in [l for l in ds_content.splitlines() if l.strip()][-10:]:
    print(f"  {repr(l[:100])}")
print("--- MinerU last 10 non-empty lines ---")
for l in [l for l in mu_content.splitlines() if l.strip()][-10:]:
    print(f"  {repr(l[:100])}")
EOF
```

Save the full comparison output to `data/MinerU-test/comparison_report.txt`.

**Phase 4 — Write comparison to file and commit:**

```bash
# Save comparison
python3 -c "
from pathlib import Path
import re, subprocess

deepseek = Path('data/DeepSeek-OCR/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.md')
mineru_files = list(Path('data/MinerU-test/tt16_bgddt').rglob('*.md'))
report = Path('data/MinerU-test/comparison_report.txt')

ds = deepseek.read_text()
mu = mineru_files[0].read_text() if mineru_files else ''
garbage = re.compile(r'(THUC CHINH|PHUTI CHINHIM|STT.*STT.*STT)', re.I)

lines = [
    'MinerU2.5-Pro vs DeepSeek-OCR-2 — tt16_bgddt (13-page table-heavy PDF)',
    '=' * 60,
    f'DeepSeek chars: {len(ds)}, garbage hits: {len(garbage.findall(ds))}',
    f'MinerU   chars: {len(mu)}, garbage hits: {len(garbage.findall(mu))}',
    '',
    'DeepSeek last 10 non-empty lines:',
]
for l in [l for l in ds.splitlines() if l.strip()][-10:]:
    lines.append(f'  {l[:120]}')
lines += ['', 'MinerU last 10 non-empty lines:']
for l in [l for l in mu.splitlines() if l.strip()][-10:]:
    lines.append(f'  {l[:120]}')

report.write_text('\n'.join(lines))
print('Report written:', report)
"

# Commit the test script and report
git add LangGraph/scripts/eval/test_mineru_ocr.py data/MinerU-test/comparison_report.txt
git commit -m "test: add MinerU2.5-Pro OCR evaluation script and comparison report"
```

### Acceptance Criteria

- [ ] `mineru` and `mineru_vl_utils` import without error
- [ ] MinerU output file exists in `data/MinerU-test/tt16_bgddt/`
- [ ] `comparison_report.txt` exists with garbage hit counts for both models
- [ ] MinerU garbage hits < DeepSeek garbage hits (should be 0 vs 3+)
- [ ] Commit lands on `feat/mineru-ocr-evaluation` branch

---

## TASK-007 — 2026-04-20 — backfill-file-path-urls

**Status:** - [ ] Pending
**Branch:** `develop`
**Class:** mechanical  **Model:** gemini
**Priority:** medium
**Gate:** Run ONLY after full indexing completes (101+ processed docs in `lightrag_doc_status`)

### Context

After indexing, many docs in `lightrag_doc_status` have `file_path` set to a bare filename
(e.g. `540-qd-dhcntt_5-9-2018_scan-6d8b546f.pdf`) instead of the actual UIT website URL
(e.g. `https://daa.uit.edu.vn/sites/daa/files/202309/540-qd-dhcntt.pdf`). The URL is needed
so Agent 3 can include a clickable source link in its answers.

The firecrawl markdown files under `firecrawl/data/daa/**/*.md` contain embedded links to
the PDF files (e.g. `[Download](https://daa.uit.edu.vn/sites/daa/files/YYYYMM/filename.pdf)`).
These can be mined to map local filename → source URL.

### Task

Write and run a Python script `LangGraph/scripts/operations/backfill_file_path_urls.py` that:

1. Queries all docs in `lightrag_doc_status` where `workspace='uit_docs_agent'`
   and `file_path NOT LIKE 'http%'` (bare filenames)

2. Scans all `*.md` files under `firecrawl/data/daa/` for markdown links that contain
   the bare filename (case-insensitive, strip the hash suffix before matching, e.g.
   `540-qd-dhcntt_5-9-2018_scan-6d8b546f.pdf` → match `540-qd-dhcntt`):
   ```python
   import re
   # Find all markdown links: [text](url)
   links = re.findall(r'\[.*?\]\((https?://[^\)]+\.pdf)\)', markdown_content)
   ```

3. For each doc where a URL match is found:
   - UPDATE `lightrag_doc_status SET file_path = '<url>' WHERE id = '<doc_id>'`
   - UPDATE Qdrant payload for all chunks with `full_doc_id = '<doc_id>'`:
     ```bash
     POST http://localhost:6336/collections/lightrag_vdb_chunks/points/payload
     {"payload": {"file_path": "<url>"}, "filter": {"must": [{"key": "full_doc_id", "match": {"value": "<doc_id>"}}]}}
     ```

4. Print a summary: matched N / total M docs, list unmatched filenames

### DB connection

```python
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, user='uitrag', password='admin123', dbname='lightrag')
```

### Qdrant connection

```python
import httpx
QDRANT = 'http://localhost:6336'
COLLECTION = 'lightrag_vdb_chunks'
```

### Acceptance criteria

- [ ] Script runs without errors: `cd LangGraph && python scripts/operations/backfill_file_path_urls.py`
- [ ] At least 80% of bare-filename docs get URL updated
- [ ] Spot-check: `SELECT file_path FROM lightrag_doc_status WHERE id='<known_doc_id>'` shows URL
- [ ] Qdrant spot-check: payload `file_path` for a chunk of that doc shows URL

---

## Archive

### TASK-001 — 2026-04-15 — codebase-cleanup

**Status:** - [x] Done  **Reviewed:** - [x] Claude verified
**Branch:** `refactor/codebase-cleanup`

6 commits landed: test → gitignore → remove artifacts → delete stale files → reorganize tests → consolidate docs.
99/99 unit tests passing. No egg-info or pycache tracked. Root `.langgraph_api/` deleted.
