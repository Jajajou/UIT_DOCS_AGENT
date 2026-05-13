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

**Status:** - [x] Done
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

**Status:** - [x] Done
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

## TASK-009 — 2026-04-20 — swap-deepseek-for-mineru

**Status:** - [ ] Pending
**Branch:** `feat/mineru-ocr-evaluation`
**Class:** mechanical  **Model:** gemini
**Priority:** high
**Gate:** None — run immediately

### Context

TASK-008 confirmed MinerU2.5-Pro-2604-1.2B beats DeepSeek-OCR-2 on tables (0 vs 339 garbage
hits). We now do a full swap: write `mineru_ocr_client.py`, add Vietnamese text normalization
via `underthesea`, remove `deepseek_ocr_client.py`, and update every touch-point that
references DeepSeek OCR. The new client must expose the same `parse_and_get_markdown()`
interface so the indexing graph change is minimal.

### Steps

**Phase 0 — Branch and install underthesea:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
git checkout feat/mineru-ocr-evaluation
source .venv/bin/activate
uv pip install underthesea
python -c "from underthesea import text_normalize; print(text_normalize('Xin chào'))"
```

Must print `Xin chào` without error.

---

**Phase 1 — Write `mineru_ocr_client.py`:**

Create file: `LangGraph/src/agent/clients/mineru_ocr_client.py`

```python
# mineru_ocr_client.py
import os
import io
import fitz
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from PIL import Image

from agent.config import settings

DEFAULT_TIMEOUT = 600  # 10 minutes for a full PDF

class MinerUOCRClientError(RuntimeError):
    pass

class MinerUOCRClient:
    """PDF parser using MinerU2.5-Pro with Vietnamese text normalization."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._model = None
        self._processor = None
        self._client = None

    def _ensure_loaded(self) -> None:
        if self._client is not None:
            return
        print("[MinerU OCR] Loading model: opendatalab/MinerU2.5-Pro-2604-1.2B")
        from mlx_vlm import load as mlx_load
        from mineru_vl_utils import MinerUClient
        model, processor = mlx_load("opendatalab/MinerU2.5-Pro-2604-1.2B")
        self._model = model
        self._processor = processor
        self._client = MinerUClient(
            backend="mlx-engine",
            model=model,
            processor=processor,
            image_analysis=False,
        )
        print("[MinerU OCR] Model loaded successfully")

    @staticmethod
    def _normalize_vietnamese(text: str) -> str:
        """Normalize Vietnamese Unicode diacritics to reduce OCR tone-mark errors."""
        try:
            from underthesea import text_normalize
            return text_normalize(text)
        except Exception:
            return text

    def parse_pdf(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        return_md: bool = True,
    ) -> Dict[str, Any]:
        """Parse a PDF file page-by-page using MinerU2.5-Pro."""
        if not os.path.exists(file_path):
            raise MinerUOCRClientError(f"File not found: {file_path}")
        if not file_path.lower().endswith(".pdf"):
            raise MinerUOCRClientError(f"Only PDF files are supported: {file_path}")

        self._ensure_loaded()

        from mineru_vl_utils.post_process import json2md

        print(f"[MinerU OCR] Processing PDF: {file_path}")
        doc = fitz.open(file_path)
        pages_md = []

        for i, page in enumerate(doc):
            print(f"[MinerU OCR] Processing page {i + 1}/{len(doc)}")
            pix = page.get_pixmap(matrix=fitz.Matrix(144 / 72, 144 / 72), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            content_list = self._client.two_step_extract(img)
            page_md = json2md(content_list)
            pages_md.append(page_md)

        doc.close()

        raw_markdown = "\n\n".join(pages_md) if pages_md else ""
        markdown = self._normalize_vietnamese(raw_markdown)

        result: Dict[str, Any] = {
            "status": "success",
            "pages_processed": len(pages_md),
            "total_pages": len(pages_md),
            "text": markdown,
        }

        if return_md:
            result["markdown"] = markdown

        if output_dir and markdown:
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(file_path).stem
            md_path = os.path.join(output_dir, f"{base_name}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            result["markdown_path"] = md_path
            print(f"[MinerU OCR] Saved markdown to: {md_path}")

        print(f"[MinerU OCR] Completed: {len(pages_md)} pages, {len(markdown):,} chars")
        return result

    def get_markdown_from_output(self, output_dir: str) -> Optional[str]:
        """Return cached markdown from output_dir if it exists."""
        output_path = Path(output_dir)
        if not output_path.exists():
            return None
        md_files = [f for f in output_path.rglob("*.md") if f.is_file()]
        if not md_files:
            return None
        md_file = max(md_files, key=lambda f: f.stat().st_mtime)
        try:
            return md_file.read_text(encoding="utf-8")
        except Exception as e:
            raise MinerUOCRClientError(f"Failed to read cached markdown: {e}")

    def parse_and_get_markdown(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """Parse PDF and return (markdown, output_dir). Checks cache first."""
        file_stem = Path(file_path).stem
        if output_dir is None:
            output_dir = str(settings.mineru_ocr_dir / file_stem)
        else:
            output_dir = str(Path(output_dir) / file_stem)

        if settings.mineru_ocr.skip_repeat:
            cached = self.get_markdown_from_output(output_dir)
            if cached:
                print(f"[MinerU OCR] Cache hit — skipping OCR for: {file_stem}")
                return cached, output_dir

        result = self.parse_pdf(file_path, output_dir=output_dir, return_md=True, **kwargs)

        if not result.get("markdown"):
            raise MinerUOCRClientError(f"No text extracted from PDF: {file_path}")

        return result["markdown"], output_dir
```

---

**Phase 2 — Update `config.yaml`:**

File: `LangGraph/src/agent/config.yaml`

Replace the entire `deepseek_ocr:` block (lines 1-19) with:

```yaml
# MinerU OCR Configuration
mineru_ocr:
  model_name: "opendatalab/MinerU2.5-Pro-2604-1.2B"
  skip_repeat: True
```

---

**Phase 3 — Update `config.py`:**

File: `LangGraph/src/agent/config.py`

Make these changes:

1. Change `DEEPSEEK_OCR_DIR = DATA_DIR / "DeepSeek-OCR"` → `MINERU_OCR_DIR = DATA_DIR / "MinerU-OCR"`

2. Replace `class DeepSeekOCRConfig(BaseModel):` with:
```python
class MinerUOCRConfig(BaseModel):
    model_name: str
    skip_repeat: bool = True
```

3. In the `Config` class:
   - Change `deepseek_ocr_dir: Path = DEEPSEEK_OCR_DIR` → `mineru_ocr_dir: Path = MINERU_OCR_DIR`
   - Change `deepseek_ocr: DeepSeekOCRConfig` → `mineru_ocr: MinerUOCRConfig`

4. In the `settings = Config(...)` instantiation:
   - Change `deepseek_ocr=_yaml_config.get("deepseek_ocr", {})` → `mineru_ocr=_yaml_config.get("mineru_ocr", {})`

5. Update the import export at the bottom:
   - Change `from agent.config import DEEPSEEK_OCR_DIR` usages — just rename the constant.

---

**Phase 4 — Update `indexing_state.py`:**

File: `LangGraph/src/agent/states/indexing_state.py`

Replace the `# DeepSeek_OCR fields` block (lines 46-50):
```python
    # DeepSeek_OCR fields
    parsed_content: NotRequired[Optional[str]]
    deepseek_ocr_output_dir: NotRequired[Optional[str]]
    deepseek_ocr_success: NotRequired[bool]
    deepseek_ocr_error: NotRequired[Optional[str]]
```
With:
```python
    # OCR fields
    parsed_content: NotRequired[Optional[str]]
    ocr_output_dir: NotRequired[Optional[str]]
    ocr_success: NotRequired[bool]
    ocr_error: NotRequired[Optional[str]]
```

---

**Phase 5 — Update `indexing_graph.py`:**

File: `LangGraph/src/agent/graphs/indexing_graph.py`

Make these changes:

1. Line 19-20: Replace imports:
```python
from agent.config import MINERU_OCR_DIR
from agent.clients.mineru_ocr_client import MinerUOCRClient, MinerUOCRClientError
```

2. Line 32: Replace client instantiation:
```python
mineru_client = MinerUOCRClient()
```

3. Replace the entire `parse_with_DeepSeek_OCR` function with:
```python
def parse_with_ocr(state: IndexingState) -> Dict[str, Any]:
    """Pre-processes and parses a PDF file with MinerU OCR."""
    file_path = state.get("current_file_path")
    if not file_path:
        return {"ocr_error": "No file path for OCR"}

    try:
        print(f"[OCR] Processing: {os.path.basename(file_path)}")
        file_stem = Path(file_path).stem
        output_path = str(MINERU_OCR_DIR / file_stem)

        md_content, output_path = mineru_client.parse_and_get_markdown(
            file_path,
            output_dir=output_path,
        )

        print(f"[OCR] Success - {len(md_content):,} chars")

        return {
            "parsed_content": md_content,
            "ocr_output_dir": output_path,
            "ocr_success": True,
            "file_path": file_path,
        }
    except Exception as e:
        print(f"[OCR] Failed: {str(e)}")
        return {
            "parsed_content": "",
            "ocr_success": False,
            "ocr_error": str(e),
        }
```

4. Find every reference to `deepseek_ocr_success`, `deepseek_ocr_output_dir`, `deepseek_ocr_error`, `deepseek_ocr_count`, `parse_with_DeepSeek_OCR` and rename:
   - `deepseek_ocr_success` → `ocr_success`
   - `deepseek_ocr_output_dir` → `ocr_output_dir`
   - `deepseek_ocr_error` → `ocr_error`
   - `parse_with_DeepSeek_OCR` → `parse_with_ocr` (node name string AND function)
   - `deepseek_ocr_count` → `ocr_count`
   - `"PDFs parsed with DeepSeek OCR:"` → `"PDFs parsed with MinerU OCR:"`
   - `"DeepSeek_OCR:"` → `"MinerU:"`
   - `"Direct - DeepSeek_OCR failed"` → `"Direct - OCR failed"`

5. In the state reset block (around line 688-690), rename the fields:
   - `"deepseek_ocr_success": False` → `"ocr_success": False`
   - `"deepseek_ocr_error": None` → `"ocr_error": None`

6. Update the `route_after_pdf_check` return value:
   - `return "parse_with_DeepSeek_OCR"` → `return "parse_with_ocr"`

7. Update `builder.add_node(...)`:
   - `builder.add_node("parse_with_DeepSeek_OCR", parse_with_DeepSeek_OCR)` → `builder.add_node("parse_with_ocr", parse_with_ocr)`

8. Update `builder.add_edge(...)`:
   - `builder.add_edge("parse_with_DeepSeek_OCR", "extract_temporal_metadata")` → `builder.add_edge("parse_with_ocr", "extract_temporal_metadata")`

9. Update the conditional edges dict:
   - `"parse_with_DeepSeek_OCR": "parse_with_DeepSeek_OCR"` → `"parse_with_ocr": "parse_with_ocr"`

---

**Phase 6 — Update `prompts.py`:**

File: `LangGraph/src/agent/core/prompts.py`

Replace both occurrences of:
```
"extraction_method": "deepseek_ocr",
```
With:
```
"extraction_method": "mineru_ocr",
```

---

**Phase 7 — Delete DeepSeek client:**

```bash
rm LangGraph/src/agent/clients/deepseek_ocr_client.py
```

---

**Phase 8 — Run tests:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT/LangGraph
source ../.venv/bin/activate
make test
```

All tests must pass. If any test imports `deepseek_ocr_client` or references `deepseek_ocr_*` state fields, update the test to use the new names.

---

**Phase 9 — Smoke test on the broken PDF:**

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate
python3 - << 'EOF'
import sys
sys.path.insert(0, "LangGraph/src")
from agent.clients.mineru_ocr_client import MinerUOCRClient

client = MinerUOCRClient()
md, out_dir = client.parse_and_get_markdown(
    "firecrawl/data/daa/quydinh_huongdan/quyche-bogddt/pdf/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.pdf",
    output_dir="data/MinerU-OCR"
)
print(f"Chars: {len(md)}, output: {out_dir}")
import re
garbage = re.compile(r'(THUC CHINH|PHUTI CHINHIM|STT.*STT.*STT)', re.I)
print(f"Garbage hits: {len(garbage.findall(md))}")  # must be 0
EOF
```

---

**Phase 10 — Commit:**

```bash
git add LangGraph/src/agent/clients/mineru_ocr_client.py \
        LangGraph/src/agent/graphs/indexing_graph.py \
        LangGraph/src/agent/states/indexing_state.py \
        LangGraph/src/agent/config.py \
        LangGraph/src/agent/config.yaml \
        LangGraph/src/agent/core/prompts.py
git rm LangGraph/src/agent/clients/deepseek_ocr_client.py
git commit -m "feat: replace DeepSeek-OCR-2 with MinerU2.5-Pro + Vietnamese text normalization"
```

### Acceptance Criteria

- [ ] `mineru_ocr_client.py` exists, `deepseek_ocr_client.py` deleted
- [ ] `underthesea` installed; `_normalize_vietnamese()` called on OCR output
- [ ] `config.yaml` has `mineru_ocr:` block, no `deepseek_ocr:` block
- [ ] `config.py` has `MinerUOCRConfig`, `MINERU_OCR_DIR`, `mineru_ocr` field
- [ ] `indexing_state.py` has `ocr_success`, `ocr_output_dir`, `ocr_error` fields
- [ ] `indexing_graph.py` node is `parse_with_ocr`, no `DeepSeek` references remain
- [ ] `make test` passes with 0 failures
- [ ] Smoke test: garbage hits = 0 on `tt16_bgddt` PDF
- [ ] Commit on `feat/mineru-ocr-evaluation`

---

## Archive

### TASK-001 — 2026-04-15 — codebase-cleanup

**Status:** - [x] Done  **Reviewed:** - [x] Claude verified
**Branch:** `refactor/codebase-cleanup`

6 commits landed: test → gitignore → remove artifacts → delete stale files → reorganize tests → consolidate docs.
99/99 unit tests passing. No egg-info or pycache tracked. Root `.langgraph_api/` deleted.

---

## TASK-010 — 2026-05-13 — backfill-temporal-and-amended-clauses

**Status:** - [x] Done
**Branch:** `develop`
**Priority:** high

### Context

Post-ablation sprint. Three code changes needed: (B) a backfill script to populate `temporal_metadata` for ~24 docs that are indexed but have no temporal scores; (C1) a SQL migration adding `amended_clauses` JSONB column; (C2) expanding `TemporalExtractionAgent` to produce `amended_clauses` dict from `amended_articles`; (C3) wiring `amended_clauses` into `lightrag_client.save_temporal_metadata()`. All changes are standalone — no live services needed except the backfill script which requires PostgreSQL at localhost:5433.

---

### Phase 1 — Create backfill_missing_temporal.py

Create `/Users/jajajou1778/UIT_DOCS_AGENT/LangGraph/scripts/backfill_missing_temporal.py`

The script must:
1. Connect to PostgreSQL: host=localhost, port=5433, user=lightrag, db=lightrag. Read POSTGRES_PASSWORD from `LangGraph/.env` (key `POSTGRES_PASSWORD`).
2. Query for docs missing from temporal_metadata:
```sql
SELECT lds.id AS doc_id, lds.file_path, lds.track_id, lds.metadata
FROM lightrag_doc_status lds
LEFT JOIN temporal_metadata tm ON tm.doc_id = lds.id
WHERE lds.workspace = 'default'
  AND tm.doc_id IS NULL
  AND lds.status IN ('success', 'completed', 'indexed')
ORDER BY lds.created_at;
```
3. For each doc, find text content:
   - Try `data/DeepSeek-OCR/<basename>.txt` first (OCR cache)
   - Fallback: read raw bytes from `file_path` as utf-8 (ignore errors)
   - If file_path is None or file not found, log warning and skip
4. Call `TemporalExtractionAgent.extract(content, filename, file_source)` — this is async, run via `asyncio.run()` or existing event loop.
   - Imports: `from agent.agents.agent_temporal_extraction import TemporalExtractionAgent`
   - Initialize agent: needs `llm_model` and `config`. Get config via `from agent.config import settings`. For llm_model, initialize a LangChain ChatOpenAI-compatible client using `OPENAI_BASE_URL` and `OPENAI_API_KEY` from env, model = `LLM_MODEL` from env or `"Qwen/Qwen3-4B-Instruct"`.
5. Compute cohort_scope from cohort_years:
   - `"universal"` if `cohort_years == ["*"]`
   - `"explicit"` if `len(cohort_years) > 0 and cohort_years != ["*"]`
   - `"unspecified"` if empty — **NEVER set "universal" for empty list**
6. Save via `LightRAGClient().save_temporal_metadata(track_id=track_id, doc_id=doc_id, metadata=meta_dict)`.
   - `from agent.clients.lightrag_client import LightRAGClient`
   - meta_dict keys: `document_number`, `document_type`, `valid_from`, `valid_until`, `cohort_years`, `cohort_scope`, `amends_documents`, `extraction_method` (set to `metadata_result.extraction_method`), `extraction_confidence` (set to `metadata_result.confidence`).
7. After all docs, call `LightRAGClient().backfill_amendment_links()` (method at lightrag_client.py lines 917-966).
8. CLI flags:
   - `--dry-run`: print what would be inserted, skip DB write
   - `--limit N`: process only first N docs

Run path from project root: `cd LangGraph && python scripts/backfill_missing_temporal.py --dry-run --limit 3`

Commit: `feat: add backfill_missing_temporal.py script for 24 orphan docs`

---

### Phase 2 — DB Migration SQL

Create `/Users/jajajou1778/UIT_DOCS_AGENT/LangGraph/scripts/migrations/04_add_amended_clauses.sql`:

```sql
ALTER TABLE temporal_metadata
  ADD COLUMN IF NOT EXISTS amended_clauses JSONB;

CREATE INDEX IF NOT EXISTS idx_temporal_amended_clauses
  ON temporal_metadata USING GIN(amended_clauses);
```

Do NOT run against the DB — just create the file. Verify syntax with `python -c "pass"` (or just review manually).

Commit: `feat: add migration 04_add_amended_clauses.sql`

---

### Phase 3 — Expand TemporalExtractionAgent (amended_clauses)

File: `/Users/jajajou1778/UIT_DOCS_AGENT/LangGraph/src/agent/agents/agent_temporal_extraction.py`

**Change 1**: Add `amended_clauses` field to `TemporalMetadata` Pydantic model (after `amended_articles` field, around line 63):
```python
amended_clauses: Optional[Dict[str, Dict[str, str]]] = Field(
    None,
    description="Clause-level amendment map: {'Điều 5': {'action': 'modified'}, 'Khoản 2': {'action': 'added'}}"
)
```
Also add `Dict` to the `typing` imports (already has `List`, `Optional`, etc.).

**Change 2**: After the `amended_articles` extraction block (lines 347-364), add logic to build `amended_clauses`:

```python
# Build amended_clauses dict from keyword context
if article_set:
    # Vietnamese action verb → enum
    _ACTION_MAP = [
        (["thay thế", "thế bằng", "bãi bỏ"], "replaced"),
        (["bổ sung"], "added"),
        (["xóa bỏ", "huỷ bỏ", "hủy bỏ"], "removed"),
        (["sửa đổi", "điều chỉnh", "chỉnh sửa"], "modified"),
    ]
    clauses_dict: Dict[str, Dict[str, str]] = {}
    for art in article_set:
        action = "modified"  # default
        # Search for art in content, check 100 chars before for action verb
        for m in re.finditer(re.escape(art), content, re.IGNORECASE):
            window = content[max(0, m.start()-100):m.start()]
            for verbs, act in _ACTION_MAP:
                if any(v in window.lower() for v in verbs):
                    action = act
                    break
        clauses_dict[art] = {"action": action}
    metadata.amended_clauses = clauses_dict
```

Keep `amended_articles` unchanged for backward compatibility.

Commit: `feat: extract amended_clauses with action verbs in TemporalExtractionAgent`

---

### Phase 4 — Wire amended_clauses into lightrag_client.save_temporal_metadata()

File: `/Users/jajajou1778/UIT_DOCS_AGENT/LangGraph/src/agent/clients/lightrag_client.py`

In `save_temporal_metadata()` (lines 466-590):

1. After line 508 (`amends_documents = metadata.get("amends_documents")`), add:
```python
amended_clauses = metadata.get("amended_clauses")
```

2. Add `amended_clauses` to `known_fields` set (line 513-516):
```python
known_fields = {
    "document_number", "document_type", "valid_from", "valid_until",
    "cohort_years", "cohort_scope", "student_cohorts", "amends_documents",
    "amended_clauses",  # ADD THIS
    "extraction_method", "extraction_confidence"
}
```

3. In the INSERT statement, add `amended_clauses` column after `amends_documents`:
```sql
amends_documents,
amended_clauses,
```
And in VALUES, add after `json.dumps(amends_documents) if amends_documents else None`:
```python
json.dumps(amended_clauses) if amended_clauses else None,
```

4. In ON CONFLICT DO UPDATE, add after `amends_documents = EXCLUDED.amends_documents,`:
```sql
amended_clauses = EXCLUDED.amended_clauses,
```

Commit: `feat: add amended_clauses JSONB field to save_temporal_metadata`

---

### Verification

After Phase 1:
```bash
source .venv/bin/activate && cd LangGraph && python scripts/backfill_missing_temporal.py --dry-run --limit 3
```
Expected: prints 3 doc entries with extracted metadata, no exceptions.

After Phase 3:
```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT && source .venv/bin/activate && cd LangGraph
python -c "from src.agent.agents.agent_temporal_extraction import TemporalMetadata; print('amended_clauses' in TemporalMetadata.__fields__)"
```
Expected: `True`

After Phase 4:
```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT && source .venv/bin/activate && cd LangGraph
python -c "from src.agent.clients.lightrag_client import LightRAGClient; import inspect; src=inspect.getsource(LightRAGClient.save_temporal_metadata); print('amended_clauses' in src)"
```
Expected: `True`

Run existing tests:
```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT/LangGraph && make test 2>&1 | tail -20
```
Expected: 0 failures.

---

### Acceptance Criteria
- [x] `LangGraph/scripts/backfill_missing_temporal.py` exists and runs with `--dry-run --limit 3` without exception
- [x] `LangGraph/scripts/migrations/04_add_amended_clauses.sql` exists with correct ALTER TABLE and CREATE INDEX
- [x] `TemporalMetadata` Pydantic model has `amended_clauses: Optional[Dict[str, Dict[str, str]]]` field
- [x] Extraction logic builds `amended_clauses` dict with action verbs after `amended_articles` block
- [x] `save_temporal_metadata()` includes `amended_clauses` in INSERT, known_fields, and ON CONFLICT UPDATE
- [x] `make test` passes with 0 failures
- [x] 4 commits exist with messages matching `feat:` convention
