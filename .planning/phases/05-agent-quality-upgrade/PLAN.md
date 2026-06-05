# Phase 05 — Agent Quality Upgrade

**Branch:** `feat/student-context-and-validation`  
**Goal:** Fix 3 root causes of vague answers → target acc@1 ≥ 0.82 (from current 0.770)  
**Effort:** ~2-3 hours  
**No graph changes. No new dependencies. 4 files only.**

---

## Root Causes (from system rethink session 2026-05-27)

| ID | Problem | Impact |
|----|---------|--------|
| P0 | Agent 3 uses Qwen3-4B — too weak for Vietnamese regulatory synthesis | −8–12pp acc, vague answers |
| P1 | Student context (cohort_year, education_system) never injected into Agent 3 prompt | −3–5pp, generic framing |
| P2 | Agent 3 receives 15 entities + 15 relationships + 15 chunks — entities/rels are noise | noise in generation context |

**Why 4B fails:** not context length (128K is fine). Fails at multi-constraint synthesis:
JSON output + Vietnamese legal text + inline citations + amended-doc preference = exceeds 4B reliability.

**Why student context matters:** COHORT retrieval already filters Qdrant by cohort_years metadata.
But Agent 3 doesn't KNOW student is K2022/chinh_quy → generates generic answer instead of
"Đối với sinh viên K2022 hệ chính quy, học phí là...".

**Why entities/rels are noise:** For regulatory doc RAG, answers are always in chunks.
Entities = `[Phòng Đào tạo] (score: 0.72) - Đơn vị quản lý...` — zero answer content.
Relationships = graph nav aids, not answer sources.

---

## What's Working (DO NOT TOUCH)

- Agent 1 routing (COHORT/AMENDMENT/GENERAL) — correct
- Temporal metadata extraction (0.92 confidence) — solid
- Reranker (ViRanker, semantic 70% + temporal 30%) — correct
- HITL interrupt + resume (stream_resumable=true) — working
- Amendment chain detection (PostgreSQL) — stable
- LightRAG retrieval modes (local/global/hybrid/mix) — keep as-is

---

## Task List

### Task 1 — P0: Separate Agent 3 model config

**File 1:** `LangGraph/.env`
```diff
+ AGENT3_LLM_MODEL=Qwen/Qwen3-14B-Instruct
```
(Keep `LLM_MODEL=Qwen/Qwen3-4B-Instruct-2507` for Agent 1 and indexing)

**File 2:** `LangGraph/src/agent/config.py`
Add field after `llm_model`:
```python
agent3_llm_model: Optional[str] = Field(
    default_factory=lambda: os.getenv("AGENT3_LLM_MODEL") or os.getenv("LLM_MODEL")
)
```

**File 3:** `LangGraph/src/agent/agents/agent3_response_generation.py`
Change LLM init (line ~30):
```python
llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.agent3_llm_model,   # was: settings.llm_model
    streaming=False,
    temperature=settings.agent3_temperature,
    model_kwargs={"tool_choice": "none"}
)
```

**Pre-check:** `curl http://localhost:8002/v1/models` — confirm 14B loaded.  
**Fallback priority:** Qwen3-14B → Qwen3-8B → DeepSeek-R1-Distill-Qwen-14B

---

### Task 2 — P1: Inject student context into Agent 3 prompt

**File 4:** `LangGraph/src/agent/core/prompts.py`
Add new template after `partial_answer_suffix`:
```python
PROMPTS["student_context_note_template"] = """<student_context>
Sinh viên này thuộc: Khóa {cohort_year}, Hệ đào tạo: {education_system}.
Ưu tiên thông tin áp dụng cho khóa này. Nếu tài liệu không có thông tin cho khóa cụ thể, ghi rõ điều đó.
</student_context>"""
```

Add `{student_context_note}` placeholder to `response_generation_prompt` between
`</user_query>` and `<reranked_data>`:
```python
PROMPTS["response_generation_prompt"] = """
...
<user_query>
{parsed_intention}
</user_query>

{student_context_note}

<reranked_data>
...
```

**File 3 (continued):** `LangGraph/src/agent/agents/agent3_response_generation.py`
In `agent3_generate_response()`, before `prompt_text = PROMPTS[...].format(...)`:
```python
cohort_year = state.get("query_cohort_year")
education_system = state.get("education_system")
student_context_note = ""
if cohort_year and education_system:
    student_context_note = PROMPTS["student_context_note_template"].format(
        cohort_year=cohort_year,
        education_system=education_system
    )
elif cohort_year:
    student_context_note = f"<student_context>\nSinh viên khóa {cohort_year}.\n</student_context>"

prompt_text = PROMPTS["response_generation_prompt"].format(
    parsed_intention=parsed_intention,
    reranked_data_formatted=reranked_data_formatted,
    student_context_note=student_context_note,
)
```

---

### Task 3 — P2: Chunks-only for Agent 3

**File 3 (continued):** `LangGraph/src/agent/agents/agent3_response_generation.py`
In `agent3_generate_response()`, change `_format_reranked_data` call (~line 345):
```python
# BEFORE:
reranked_data_formatted = _format_reranked_data(
    reranked_entities,
    reranked_relationships,
    reranked_chunks,
    top_n=15
)

# AFTER:
reranked_data_formatted = _format_reranked_data(
    [],
    [],
    reranked_chunks,
    top_n=15
)
```

---

### Task 4 — Verify + Eval

```bash
cd LangGraph
source ../.venv/bin/activate

# Tests must still pass
make test

# Run eval
python temporal_evaluation.py --output results/run_phase05.json

# Expected: acc@1 >= 0.82
# Qualitative check: answers should contain specific articles "Điều X, Khoản Y"
```

---

## Files Changed

```
LangGraph/.env                                              # AGENT3_LLM_MODEL
LangGraph/src/agent/config.py                              # agent3_llm_model field
LangGraph/src/agent/agents/agent3_response_generation.py   # model + context + chunks-only
LangGraph/src/agent/core/prompts.py                        # student_context_note_template + placeholder
```

**4 files. No graph/state/dependency changes.**

---

## Open Questions (discuss before executing)

1. **14B on Vast.ai:** current instance (ssh9.vast.ai:14760) — does it have capacity to serve 14B alongside vllm for MinerU? May need separate instance or swap model.
2. **Thinking mode:** enable `enable_thinking=True` for Agent 3 at 14B? Tradeoff: +quality vs +latency (~2x). Worth discussing.
3. **top_n for chunks:** currently 15. With entities/rels removed, bump to 20? More signal in same context budget.
4. **Agent 1 prompt trim (P3):** trim 431→200 lines by cutting to 4 best examples? Low risk, marginal gain. Do or skip?

---

## Commit Plan

```
feat: separate agent3 model config (agent3_llm_model field)
feat: inject student context into agent3 prompt
refactor: chunks-only context for agent3 generation
test: verify 60/60 still pass post-changes
```
