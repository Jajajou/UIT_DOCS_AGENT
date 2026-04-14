# Prompts Migration Guide

## Tổng quan

Đã refactor tất cả prompts vào file tập trung `src/agent/prompts.py` theo chuẩn **Qwen chat template**.

## Thay đổi

### Before (Prompts rải rác trong các agent files)

```python
# agent1_query_understanding.py
QUERY_UNDERSTANDING_SYSTEM_PROMPT = """
Bạn là trợ lý phân tích câu hỏi...
"""

# agent3_response_generation.py
RESPONSE_GENERATION_PROMPT = """
Bạn là trợ lý tư vấn học tập...
"""
```

**Problems:**
- Prompts scattered across multiple files
- Hard to maintain consistency
- Difficult to A/B test different prompts
- No centralized prompt management

### After (Centralized prompts.py)

```python
# src/agent/prompts.py
PROMPTS = {
    "query_understanding_system": """<|im_start|>system
    Bạn là trợ lý phân tích câu hỏi...
    <|im_end|>""",

    "response_generation_system": """<|im_start|>system
    Bạn là trợ lý tư vấn học tập...
    <|im_end|>"""
}

def get_prompt(key: str, model_name: str | None = None) -> str:
    """Get prompt by key"""
    return PROMPTS.get(key, "")

def format_prompt(template: str, **kwargs) -> str:
    """Format prompt with variables"""
    return template.format(**kwargs)
```

**Benefits:**
- ✅ All prompts in one place
- ✅ Easy to maintain and update
- ✅ Support model-specific prompts (future)
- ✅ Consistent Qwen chat template format
- ✅ Easy to A/B test

## Qwen Chat Template Format

All prompts now follow Qwen3-4B-Instruct chat template:

```
<|im_start|>system
<XML-style instructions>
  <role>...</role>
  <instructions>...</instructions>
  <output_format>...</output_format>
  <examples>...</examples>
</XML-style instructions>
<|im_end|>
```

**Key features:**
- `<|im_start|>` and `<|im_end|>` are special tokens
- XML-style tags for semantic structure
- JSON output format for structured responses

## Usage

### Agent 1: Query Understanding

```python
from agent.prompts import get_prompt

# Load prompt
system_prompt = get_prompt("query_understanding_system", LLM_MODEL)

# Use in LLM call
completion = client.beta.chat.completions.parse(
    model=LLM_MODEL,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Phân tích câu hỏi sau:\n\n{query}"}
    ],
    response_format=QueryUnderstanding,
    temperature=LLM_TEMPERATURE,
)
```

### Agent 3: Response Generation

```python
from agent.prompts import get_prompt, format_prompt

# Load and format prompt
prompt_template = get_prompt("response_generation_system", LLM_MODEL)
prompt = format_prompt(
    prompt_template,
    parsed_intention=parsed_intention,
    retrieved_data_formatted=retrieved_data_formatted,
    quality_score=quality_score,
    coverage=coverage,
    quality_reason=quality_reason
)

# Use in LLM call
completion = client.beta.chat.completions.parse(
    model=LLM_MODEL,
    messages=[
        {"role": "user", "content": prompt}
    ],
    response_format=ResponseGeneration,
    temperature=GENERATION_TEMPERATURE,
)
```

## Prompts Available

| Key | Description | Variables |
|-----|-------------|-----------|
| `query_understanding_system` | Agent 1: Query analysis with confidence scoring | None (user query in separate message) |
| `response_generation_system` | Agent 3: Response generation with hyperlinks | `parsed_intention`, `retrieved_data_formatted` |

> **Note (v0.2.0):** Agent 2 prompts (`data_quality_assessment_system`, `confidence_assessment_system_prompt`) were removed in v0.2.0 when Agent 2 was eliminated. The pipeline is now a 2-agent linear flow: Agent 1 (query understanding) followed by Agent 3 (response generation).

## Customization

### Adding new prompts

```python
# In src/agent/prompts.py
PROMPTS["my_new_prompt"] = """<|im_start|>system
My custom prompt here
<|im_end|>"""
```

### Model-specific prompts

```python
# In src/agent/prompts.py
def get_prompt(key: str, model_name: str | None = None) -> str:
    # Check for model-specific version
    if model_name:
        model_key = f"{key}_{model_name.lower()}"
        if model_key in PROMPTS:
            return PROMPTS[model_key]
    
    # Fallback to default
    return PROMPTS.get(key, "")

# Usage
PROMPTS["query_understanding_system_qwen"] = """..."""  # Qwen-specific
PROMPTS["query_understanding_system_gpt4"] = """..."""  # GPT-4-specific

prompt = get_prompt("query_understanding_system", "qwen")  # Returns Qwen version
```

### A/B Testing

```python
# In .env
PROMPT_VERSION=v2

# In src/agent/prompts.py
PROMPTS["query_understanding_system_v1"] = """..."""
PROMPTS["query_understanding_system_v2"] = """..."""

def get_prompt(key: str, model_name: str | None = None) -> str:
    version = os.getenv("PROMPT_VERSION", "")
    if version:
        versioned_key = f"{key}_{version}"
        if versioned_key in PROMPTS:
            return PROMPTS[versioned_key]
    return PROMPTS.get(key, "")
```

## Backwards Compatibility

Old prompt constants are kept as `*_OLD` for reference:

```python
# In agent1_query_understanding.py
QUERY_UNDERSTANDING_SYSTEM_PROMPT_OLD = """..."""  # Old prompt for reference

# In agent3_response_generation.py
RESPONSE_GENERATION_PROMPT_OLD = """..."""  # Old prompt for reference
```

These are NOT used in code, only kept for comparison.

## Testing

### Verify prompts load correctly

```python
from agent.prompts import get_prompt

# Test all prompts
prompts_to_test = [
    "query_understanding_system",
    "response_generation_system"
]

for key in prompts_to_test:
    prompt = get_prompt(key)
    assert prompt, f"Prompt {key} is empty!"
    assert "<|im_start|>" in prompt, f"Prompt {key} missing Qwen format!"
    print(f"✓ {key}: {len(prompt)} chars")
```

### Compare old vs new prompts

```python
# In agent1_query_understanding.py
old_prompt = QUERY_UNDERSTANDING_SYSTEM_PROMPT_OLD
new_prompt = get_prompt("query_understanding_system")

print("Old prompt length:", len(old_prompt))
print("New prompt length:", len(new_prompt))
print("Difference:", len(new_prompt) - len(old_prompt))
```

## Migration Checklist

- [x] Create `src/agent/prompts.py` with all prompts
- [x] Add Qwen chat template format (`<|im_start|>`, `<|im_end|>`)
- [x] Add XML-style tags for structure
- [x] Update `agent1_query_understanding.py` to use `get_prompt()`
- [x] Update `agent3_response_generation.py` to use `get_prompt()` and `format_prompt()`
- [x] Keep old prompts as `*_OLD` for reference
- [x] Test compilation
- [ ] Test with real LLM calls
- [ ] Compare outputs (old vs new)
- [ ] Update documentation

## Next Steps

1. **Test with Qwen model:**
   ```bash
   LLM_MODEL=qwen3-4b-instruct langgraph dev
   ```

2. **Compare outputs:**
   - Run same queries with old and new prompts
   - Compare quality, accuracy, format

3. **Fine-tune prompts:**
   - Adjust based on Qwen's responses
   - Optimize XML structure
   - Add more examples if needed

4. **Add model-specific variants:**
   - Create GPT-4 specific prompts if needed
   - Create Claude specific prompts if needed

## References

- Qwen chat template: https://huggingface.co/Qwen/Qwen3-4B-Instruct
- XML vs JSON in prompts: See `/home/ubuntu/XML_vs_JSON_Prompt_Engineering.md`
- Anthropic's research on XML tags: Constitutional AI paper (2022)

## Support

Nếu gặp vấn đề:
1. Check prompt loads correctly: `get_prompt(key)` returns non-empty string
2. Check Qwen format: `<|im_start|>` and `<|im_end|>` present
3. Check variables: All `{variable}` placeholders are filled by `format_prompt()`
4. Compare with old prompts: Use `*_OLD` constants for reference
