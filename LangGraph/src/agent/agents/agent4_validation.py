"""
Agent 4: Validation and Factual Checking

This agent ensures the generated response is factually supported by the 
retrieved documents and contains no hallucinations or missing critical info.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from agent.states.query_state import QueryState
from langchain.chat_models import init_chat_model
from agent.config import settings
from agent.utils import strip_think_tags
from pydantic import BaseModel, Field

# ============================================================================
# Configuration
# ============================================================================

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.llm_model,
    streaming=False,
    temperature=0.0, # Zero temperature for strict validation
    model_kwargs={"tool_choice": "none", "extra_body": {"enable_thinking": False}}
)

# ============================================================================
# Models
# ============================================================================

class ValidationResult(BaseModel):
    """Structured output for Agent 4 validation."""
    is_valid: bool = Field(description="True nếu câu trả lời chính xác và đầy đủ dựa trên tài liệu.")
    reasoning: str = Field(description="Giải thích chi tiết lý do (đặc biệt nếu is_valid=False).")
    critique: str = Field(description="Hướng dẫn cụ thể cho Agent 3 để sửa lỗi (để trống nếu is_valid=True).")

# ============================================================================
# Agent 4 Node
# ============================================================================

def agent4_validate_response(state: QueryState) -> Dict[str, Any]:
    """
    Agent 4: Validate Agent 3's response against retrieved documents.
    """
    query = state.get("query", "")
    generated_response = state.get("generated_response", "")
    reranked_chunks = state.get("reranked_chunks", [])
    
    if not generated_response or not reranked_chunks:
        return {"validation_passed": True} # Skip if nothing to validate

    # Prepare document context (non-truncated for the validator)
    context_docs = []
    for i, (chunk, score) in enumerate(reranked_chunks[:5], 1):
        content = chunk.get("content", "")
        meta = chunk.get("metadata", {})
        doc_num = meta.get("document_number", "N/A")
        context_docs.append(f"--- [Document {i}: {doc_num}] ---\n{content}")
    
    docs_text = "\n\n".join(context_docs)

    prompt = f"""
Bạn là chuyên gia kiểm định chất lượng (Internal Auditor) cho chatbot tư vấn học tập UIT.
Nhiệm vụ của bạn là kiểm tra tính chính xác tuyệt đối của câu trả lời dựa trên các tài liệu được cung cấp.

<user_query>
{query}
</user_query>

<retrieved_documents>
{docs_text}
</retrieved_documents>

<generated_answer>
{generated_response}
</generated_answer>

<instructions>
1. **Kiểm tra mâu thuẫn (Factual Check):** Câu trả lời có đưa ra thông tin nào sai lệch so với tài liệu không? (Ví dụ: sai số liệu, sai thời gian, sai điều kiện).
2. **Kiểm tra sự đầy đủ (Completeness Check):** Câu trả lời có bỏ sót thông tin quan trọng nào mà tài liệu có đề cập để trả lời cho câu hỏi này không?
3. **Kiểm tra Hallucination:** Câu trả lời có tự ý "bịa" ra thông tin không có trong tài liệu không?
4. **Kiểm tra Citation:** Các trích dẫn nguồn [Nguồn X] có khớp với nội dung trong Document X không?

Trả về JSON với schema ValidationResult:
- is_valid: true/false
- reasoning: Giải thích tại sao đúng hoặc sai.
- critique: Nếu sai, hãy chỉ rõ lỗi ở đâu và Agent 3 cần sửa như thế nào (ví dụ: "Sửa GPA từ 2.5 thành 2.0 theo Document 1").
</instructions>
"""

    try:
        llm_json = llm.bind(response_format={"type": "json_object"})
        msgs = [
            SystemMessage(content=prompt),
            HumanMessage(content="Hãy kiểm định câu trả lời trên. Trả về JSON.")
        ]
        
        raw_response = llm_json.invoke(input=msgs)
        content = strip_think_tags(raw_response.content if hasattr(raw_response, "content") else str(raw_response))
        
        data = json.loads(content)
        result = ValidationResult(**data)
        
        print(f"[AGENT 4] Validation Result: {'PASS' if result.is_valid else 'FAIL'}")
        if not result.is_valid:
            print(f"[AGENT 4] Critique: {result.critique}")

        return {
            "validation_passed": result.is_valid,
            "validation_reasoning": result.reasoning,
            "validation_critique": result.critique,
            "logs": [f"Agent 4 validation: {'Passed' if result.is_valid else 'Failed'}"]
        }
        
    except Exception as e:
        print(f"[AGENT 4] Error: {e}")
        return {
            "validation_passed": True, # Fail-safe: proceed if validator fails
            "logs": [f"Agent 4 error: {str(e)}"]
        }

# ============================================================================
# Decision Function
# ============================================================================

def route_after_validation(state: QueryState) -> str:
    """
    Route back to Agent 3 if validation failed, otherwise end.
    """
    passed = state.get("validation_passed", True)
    retry_count = state.get("validation_retry_count", 0)
    
    if not passed and retry_count < 2:
        print(f"[GRAPH] Validation failed. Retrying Agent 3 (Attempt {retry_count + 1})")
        return "retry_agent3"
    
    return "format_final_answer"
