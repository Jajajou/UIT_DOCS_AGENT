# Phase 06 — Post-Phase05 Bug Fixes & Quality Improvements

**Goal:** Fix 2 P0 bugs (infinite loop, context mismatch), 1 P1 data flow gap (COHORT/AMENDMENT skip temporal enrichment), 2 P2 prompt improvements.  
**Branch:** `fix/post-phase05-bugs`  
**Base branch:** `develop`  
**Commit format:** `fix: <description>`

---

## Context

Full audit after phase05 revealed these issues (see memory: session_20260527_post_phase05_rethink):

- **P0-A**: `validation_retry_count` never incremented → infinite validation loop on any failure
- **P0-B**: agent3 sees `content[:300]`, agent4 sees full content → guaranteed false validation failures → infinite loop
- **P1**: COHORT + AMENDMENT retrieval paths skip `enrich_with_temporal_metadata` → expiration warnings dead for ~40% of queries
- **P2-A**: Thinking prompt missing "cite exact numbers" directive → vague answers
- **P2-B**: Think budget 150 words too small for complex queries

---

## Tasks (execute in order — each is a separate commit)

---

### Task 1 — Fix P0-A: validation_retry_count never incremented

**File:** `LangGraph/src/agent/agents/agent4_validation.py`

**What/Why:** `query_state.py:246` declares `validation_retry_count: Annotated[int, operator.add]`. The `operator.add` reducer means each node return adds to the counter. But agent4 never returns this field, so the counter stays 0 forever. `route_after_validation` checks `retry_count < 2` but always sees 0 → infinite retry loop.

**Change:**

In `agent4_validate_response`, both return dicts must include `"validation_retry_count": 1`.

Success path (line 114-118):
```python
return {
    "validation_passed": result.is_valid,
    "validation_reasoning": result.reasoning,
    "validation_critique": result.critique,
    "validation_retry_count": 1,
    "logs": [f"Agent 4 validation: {'Passed' if result.is_valid else 'Failed'}"]
}
```

Error/fallback path (line 123-126):
```python
return {
    "validation_passed": True,
    "validation_retry_count": 1,
    "logs": [f"Agent 4 error: {str(e)}"]
}
```

**Verify:** `route_after_validation` already reads `state.get("validation_retry_count", 0)` — no other changes needed there. After 1 failed run: count=1, `1 < 2` → retry. After 2nd failed run: count=2, `2 < 2` is False → proceed to `format_final_answer`.

**Commit message:** `fix: increment validation_retry_count in agent4 to prevent infinite loop`

---

### Task 2 — Fix P0-B: content truncation mismatch between agent3 and agent4

**File:** `LangGraph/src/agent/agents/agent3_response_generation.py`

**What/Why:** `_format_reranked_data` truncates chunk content to 300 chars before passing to agent3's LLM. But agent4 passes full content to its validator. Agent3 misses info beyond char 300 → agent4 correctly flags it missing → retry loop. Vietnamese regulatory clauses (điều kiện, quy trình) easily exceed 300 chars and lose critical numbers.

**Changes:**

1. In `_format_reranked_data` (around line 220), change content slice:
```python
# BEFORE
lines.append(f"   Content: {content[:300]}...")

# AFTER
lines.append(f"   Content: {content[:800]}...")
```

2. In `agent3_generate_response` (around line 356-361), reduce top_n from 15 to 10 (offset the larger content per chunk):
```python
# BEFORE
reranked_data_formatted = _format_reranked_data(
    [],
    [],
    reranked_chunks,
    top_n=15
)

# AFTER
reranked_data_formatted = _format_reranked_data(
    [],
    [],
    reranked_chunks,
    top_n=10
)
```

**Rationale for top_n reduction:** 15 chunks × 800 chars = 12000 chars context (fine for 128k model), but 10 × 800 is enough and reduces noise. Reranker already surfaced the best 10.

**Commit message:** `fix: increase chunk content from 300 to 800 chars and reduce top_n from 15 to 10 in agent3`

---

### Task 3 — Fix P1: COHORT/AMENDMENT paths skip temporal enrichment

**Files:**
- `LangGraph/src/agent/agents/retrieve_cohort.py`
- `LangGraph/src/agent/agents/retrieve_amendment.py`
- `LangGraph/src/agent/graphs/query_graph.py`

**What/Why:** COHORT and AMENDMENT retrieval paths route directly to `rerank_data`, bypassing `enrich_with_temporal_metadata`. This means retrieved chunks have no `valid_until`, `amended_by`, `cohort_years` in their `metadata` dict. Consequence: `_generate_expiration_warnings()` in agent3 produces no warnings for these paths, and the reranker's temporal scoring has no metadata to work with.

The fix is: route success cases through `enrich_with_temporal_metadata` (which then leads to `filter_by_metadata` → `rerank_data` via existing edges). `filter_by_metadata` is safe for both paths:
- COHORT: Qdrant already filtered by cohort — filter is redundant but harmless
- AMENDMENT: `query_cohort_year` is typically null for amendment queries → filter does nothing

**Change 1 — retrieve_cohort.py** (line 135):
```python
# BEFORE
def route_after_cohort(state: QueryState) -> str:
    """
    0 results (fallback=True) → retrieve_data (GENERAL path)
    Has results               → rerank_data (skip enrich + filter)
    """
    if state.get("cohort_fallback", False):
        return "retrieve_data"
    return "rerank_data"

# AFTER
def route_after_cohort(state: QueryState) -> str:
    """
    0 results (fallback=True) → retrieve_data (GENERAL path)
    Has results               → enrich_with_temporal_metadata
    """
    if state.get("cohort_fallback", False):
        return "retrieve_data"
    return "enrich_with_temporal_metadata"
```

**Change 2 — retrieve_amendment.py** (line 111-114):
```python
# BEFORE
def route_after_amendment(state: QueryState) -> str:
    """
    0 results / no ref (fallback=True) → retrieve_data (GENERAL path)
    Has results                         → rerank_data (skip enrich + filter)
    """
    if state.get("amendment_fallback", False):
        return "retrieve_data"
    return "rerank_data"

# AFTER
def route_after_amendment(state: QueryState) -> str:
    """
    0 results / no ref (fallback=True) → retrieve_data (GENERAL path)
    Has results                         → enrich_with_temporal_metadata
    """
    if state.get("amendment_fallback", False):
        return "retrieve_data"
    return "enrich_with_temporal_metadata"
```

**Change 3 — query_graph.py** (lines 605-622): Update conditional edge routing maps to include `"enrich_with_temporal_metadata"` as a valid destination.

```python
# BEFORE
builder.add_conditional_edges(
    "retrieve_cohort_data",
    route_after_cohort,
    {
        "rerank_data": "rerank_data",
        "retrieve_data": "retrieve_data",
    },
)

builder.add_conditional_edges(
    "retrieve_amendment_data",
    route_after_amendment,
    {
        "rerank_data": "rerank_data",
        "retrieve_data": "retrieve_data",
    },
)

# AFTER
builder.add_conditional_edges(
    "retrieve_cohort_data",
    route_after_cohort,
    {
        "enrich_with_temporal_metadata": "enrich_with_temporal_metadata",
        "retrieve_data": "retrieve_data",
    },
)

builder.add_conditional_edges(
    "retrieve_amendment_data",
    route_after_amendment,
    {
        "enrich_with_temporal_metadata": "enrich_with_temporal_metadata",
        "retrieve_data": "retrieve_data",
    },
)
```

**Note:** The existing edges `enrich_with_temporal_metadata → filter_by_metadata → rerank_data` already exist in the graph — no new edges needed. COHORT/AMENDMENT paths now share the same `enrich → filter → rerank` tail as GENERAL.

**Commit message:** `fix: route COHORT and AMENDMENT paths through temporal enrichment before reranking`

---

### Task 4 — Fix P2-A & P2-B: Thinking prompt specificity + budget

**File:** `LangGraph/src/agent/core/prompts.py`

**What/Why:** Agent3's thinking step paraphrases specific numbers/values instead of citing them verbatim. Eval answers say "đủ điều kiện" instead of "GPA ≥ 2.0", "đạt chuẩn ngoại ngữ" instead of "IELTS 4.5+". Also think budget of 150 words is too small for complex multi-clause regulatory answers.

**Change — `PROMPTS["response_generation_thinking_prompt"]`** (around line 807):

```python
# BEFORE
PROMPTS["response_generation_thinking_prompt"] = """Bạn là trợ lý tư vấn học tập UIT. Nhiệm vụ: tổng hợp tài liệu → trả lời trực tiếp, không hỏi lại sinh viên.

<user_query>{parsed_intention}</user_query>

{student_context_note}

<reranked_data>
{reranked_data_formatted}
</reranked_data>

Bước 1 — Suy nghĩ trong <think>...</think> (tối đa 150 từ, chỉ trả lời 4 câu hỏi này):
- Chunks nào liên quan nhất? (liệt kê số thứ tự)
- Văn bản nào có `amended_by`? (cần loại khỏi nguồn chính)
- Thông tin có đủ cho full answer hay partial? (full/partial)
- Cần structure gì? (ví dụ: điều kiện → quy trình → lưu ý)

Bước 2 — Sau </think>, viết câu trả lời markdown tiếng Việt:
- Tiêu đề rõ ràng (### 1. ..., ### 2. ...)
- Trích dẫn nguồn: [Nguồn 1], [Nguồn 2, 3]
- Hyperlink URL khi có: [Tên văn bản](URL)
- Nếu partial: thêm "**Lưu ý:** Thông tin về [X] chưa có, liên hệ Phòng Đào tạo."
- Cuối: "## Tài liệu tham khảo" với danh sách hyperlink"""

# AFTER
PROMPTS["response_generation_thinking_prompt"] = """Bạn là trợ lý tư vấn học tập UIT. Nhiệm vụ: tổng hợp tài liệu → trả lời trực tiếp, không hỏi lại sinh viên.

<user_query>{parsed_intention}</user_query>

{student_context_note}

<reranked_data>
{reranked_data_formatted}
</reranked_data>

Bước 1 — Suy nghĩ trong <think>...</think> (tối đa 350 từ, trả lời 4 câu hỏi này):
- Chunks nào liên quan nhất? (liệt kê số thứ tự)
- Văn bản nào có `amended_by`? (cần loại khỏi nguồn chính)
- Thông tin có đủ cho full answer hay partial? (full/partial)
- Cần structure gì? (ví dụ: điều kiện → quy trình → lưu ý)

Bước 2 — Sau </think>, viết câu trả lời markdown tiếng Việt:
- Tiêu đề rõ ràng (### 1. ..., ### 2. ...)
- **BẮT BUỘC trích dẫn số liệu chính xác từ văn bản** (VD: "130 tín chỉ", "GPA ≥ 2.0", "IELTS ≥ 4.5", "30% điểm quá trình"). TUYỆT ĐỐI không dùng ngôn ngữ mơ hồ như "đủ điều kiện", "đáp ứng yêu cầu", "tương đương" mà không kèm con số cụ thể.
- Trích dẫn nguồn: [Nguồn 1], [Nguồn 2, 3]
- Hyperlink URL khi có: [Tên văn bản](URL)
- Nếu partial: thêm "**Lưu ý:** Thông tin về [X] chưa có, liên hệ Phòng Đào tạo."
- Cuối: "## Tài liệu tham khảo" với danh sách hyperlink"""
```

**Commit message:** `fix: add specificity directive and increase think budget 150→350 in agent3 prompt`

---

## Final step — run tests

After all 4 commits:

```bash
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate
cd LangGraph && make test
```

Expected: all existing tests still pass (no behavioral changes to test mocks). If tests fail, investigate before pushing.

---

## Verification checklist

- [ ] Task 1: `agent4_validate_response` returns `"validation_retry_count": 1` in all branches
- [ ] Task 2: `_format_reranked_data` uses `content[:800]`, `agent3_generate_response` calls with `top_n=10`
- [ ] Task 3: `route_after_cohort` returns `"enrich_with_temporal_metadata"`, `route_after_amendment` returns `"enrich_with_temporal_metadata"`, graph edges updated in both conditional_edges blocks
- [ ] Task 4: thinking prompt has specificity directive, "150" changed to "350"
- [ ] All tests pass

---

## Out of scope for this phase

- Agent4 model upgrade (Qwen3-4B → Qwen3.5-9B): requires eval to measure impact, defer
- Dead code removal (`response_generation_prompt`, entity/rel handling): low risk but separate PR
- Reduce agent1 prompt length: separate PR, needs careful testing
