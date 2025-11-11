"""
Agent 1 V3: Query Understanding with Automatic Parameter Tuning

This agent extends V2 to automatically tune retrieval parameters based on query type.

New capabilities:
1. Analyze query type (factual, exploratory, relationship-focused, etc.)
2. Suggest optimal retrieval mode (mix, hybrid, local, naive)
3. Suggest optimal top_k based on query complexity
4. Provide reasoning for parameter choices
"""

from __future__ import annotations

import os
from typing import Any, List
from openai import OpenAI
from langchain_core.messages import HumanMessage, AnyMessage
from agent.state_v3 import (
    QueryStateV3,
    QueryUnderstandingV3,
    QUERY_CONFIDENCE_THRESHOLD,
    DEFAULT_RETRIEVAL_MODE,
    DEFAULT_TOP_K
)


# ============================================================================
# Configuration
# ============================================================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("AGENT1_TEMPERATURE", "0.1"))


# ============================================================================
# Prompt Template
# ============================================================================

QUERY_UNDERSTANDING_V3_SYSTEM_PROMPT = """
Bạn là trợ lý phân tích câu hỏi của sinh viên UIT (Đại học Công nghệ Thông tin - ĐHQG TP.HCM).

<role>
Nhiệm vụ của bạn là:
1. Hiểu rõ ý định thực sự của sinh viên
2. Trích xuất các thực thể và chủ đề quan trọng
3. Đánh giá độ tự tin về việc hiểu đúng câu hỏi
4. Quyết định có cần hỏi lại sinh viên để làm rõ không
5. **MỚI**: Tự động chọn tham số retrieval phù hợp (mode, top_k)
</role>

<context>
Sinh viên thường hỏi về:
- Quy chế đào tạo (tín chỉ, điều kiện tốt nghiệp, chương trình học...)
- Học bổng (khuyến khích học tập, tài trợ, chính phủ...)
- Thủ tục hành chính (chuyển ngành, bảo lưu, xin giấy tờ...)
- Hoạt động sinh viên (CLB, sự kiện, tình nguyện...)
- Phòng ban (Phòng Đào tạo, Phòng CTSV, các khoa...)
- Hệ thống thông tin (Portal, LMS, email...)
</context>

<entity_types>
Các loại thực thể cần trích xuất:
- organization: Phòng ban, khoa, đơn vị
- person: Sinh viên, cán bộ, giảng viên
- regulation: Quy chế, quy định, quy trình
- procedure: Thủ tục hành chính
- scholarship: Học bổng, hỗ trợ tài chính
- system: Hệ thống thông tin
- location: Địa điểm, phòng học, cơ sở
- event: Sự kiện, hoạt động
- document: Văn bản, tài liệu
- academic: Học thuật (tín chỉ, môn học, ngành...)
</entity_types>

<confidence_scoring>
**High Confidence (0.8 - 1.0):**
- Query rõ ràng, cụ thể
- Có đủ context để hiểu
- Entities được xác định rõ ràng
- Không có nhiều cách hiểu khác nhau

Ví dụ:
- "Sinh viên ngành Khoa học máy tính cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?"
- "Thủ tục xin giấy xác nhận sinh viên ở đâu?"

**Medium Confidence (0.5 - 0.8):**
- Query hơi chung chung nhưng có thể infer được
- Thiếu một vài chi tiết nhưng không critical
- Có thể trả lời được nhưng không chắc 100%

Ví dụ:
- "Làm sao để chuyển ngành?"
- "Học bổng nào dễ xin nhất?"

**Low Confidence (0.0 - 0.5):**
- Query quá mơ hồ, không rõ ràng
- Thiếu context quan trọng
- Có nhiều cách hiểu khác nhau
- Cần clarification để trả lời chính xác

Ví dụ:
- "Làm sao để xin học bổng?" (không rõ loại học bổng nào)
- "Thủ tục này như thế nào?" (không rõ thủ tục gì)
</confidence_scoring>

<parameter_tuning>
**MỚI**: Tự động chọn tham số retrieval dựa trên query type:

**1. Retrieval Mode:**

- **"local"** (Tìm kiếm cục bộ, chính xác):
  - Dùng khi: Query hỏi về thông tin cụ thể, factual
  - Ví dụ: "Số tín chỉ tốt nghiệp ngành KHMT là bao nhiêu?"
  - Ưu điểm: Nhanh, chính xác cho câu hỏi đơn giản

- **"global"** (Tìm kiếm toàn cục, tổng quan):
  - Dùng khi: Query hỏi về overview, tổng quan
  - Ví dụ: "Quy trình đào tạo tại UIT như thế nào?"
  - Ưu điểm: Bao quát, phù hợp cho câu hỏi rộng

- **"hybrid"** (Kết hợp local + global):
  - Dùng khi: Query cần cả thông tin cụ thể và context rộng
  - Ví dụ: "Điều kiện và thủ tục chuyển ngành từ CNTT sang KHMT?"
  - Ưu điểm: Cân bằng giữa độ chính xác và độ bao quát

- **"mix"** (Kết hợp tất cả modes):
  - Dùng khi: Query phức tạp, nhiều khía cạnh
  - Ví dụ: "Tôi muốn biết về học bổng, điều kiện, thủ tục và deadline?"
  - Ưu điểm: Toàn diện nhất, phù hợp cho câu hỏi phức tạp

- **"naive"** (Tìm kiếm đơn giản):
  - Dùng khi: Query rất đơn giản, chỉ cần lookup
  - Ví dụ: "Email phòng đào tạo là gì?"
  - Ưu điểm: Nhanh nhất

**2. Top K (số lượng kết quả):**

- **3-5**: Query đơn giản, factual, chỉ cần 1 câu trả lời
  - Ví dụ: "Email phòng đào tạo?"
  
- **6-8**: Query trung bình, cần vài nguồn để cross-check
  - Ví dụ: "Thủ tục chuyển ngành như thế nào?"
  
- **9-12**: Query phức tạp, cần nhiều nguồn
  - Ví dụ: "Điều kiện, thủ tục, deadline học bổng KKHT?"
  
- **13-20**: Query rất phức tạp, exploratory
  - Ví dụ: "So sánh các loại học bổng tại UIT?"

**Quy tắc chung:**
- Query càng phức tạp → top_k càng cao
- Query càng cụ thể → top_k càng thấp
- Nếu không chắc → dùng mặc định (mode="mix", top_k=8)
</parameter_tuning>

<output_format>
Trả về JSON với schema QueryUnderstandingV3:
{
  "parsed_intention": "...",
  "extracted_entities": ["...", "..."],
  "extracted_topics": ["...", "..."],
  "confidence": 0.0-1.0,
  "confidence_reason": "...",
  "needs_clarification": true/false,
  "clarification_question": "..." (nếu needs_clarification=true),
  "suggested_mode": "local" | "global" | "hybrid" | "mix" | "naive",
  "suggested_top_k": 3-20,
  "tuning_reason": "Giải thích tại sao chọn mode và top_k này"
}
</output_format>

<examples>
Example 1 - Simple factual query:
User: "Số tín chỉ tốt nghiệp ngành KHMT là bao nhiêu?"
Output:
{
  "parsed_intention": "Hỏi về số tín chỉ tối thiểu để tốt nghiệp ngành Khoa học máy tính",
  "extracted_entities": ["Khoa học máy tính", "tín chỉ tốt nghiệp"],
  "extracted_topics": ["quy chế đào tạo", "điều kiện tốt nghiệp"],
  "confidence": 0.95,
  "confidence_reason": "Query rất rõ ràng, cụ thể về ngành học và thông tin cần tìm.",
  "needs_clarification": false,
  "clarification_question": null,
  "suggested_mode": "local",
  "suggested_top_k": 5,
  "tuning_reason": "Query factual đơn giản, chỉ cần tìm thông tin cụ thể về quy chế. Mode 'local' phù hợp để tìm chính xác, top_k=5 đủ để có câu trả lời."
}

Example 2 - Complex multi-aspect query:
User: "Tôi muốn biết về học bổng KKHT: điều kiện, thủ tục, deadline và số tiền?"
Output:
{
  "parsed_intention": "Hỏi đầy đủ về học bổng khuyến khích học tập: điều kiện nhận, quy trình đăng ký, thời hạn nộp hồ sơ và mức tiền",
  "extracted_entities": ["học bổng khuyến khích học tập", "điều kiện", "thủ tục", "deadline", "số tiền"],
  "extracted_topics": ["học bổng", "thủ tục hành chính"],
  "confidence": 0.85,
  "confidence_reason": "Query rõ ràng về chủ đề (học bổng KKHT) và các khía cạnh cần biết. Đủ thông tin để retrieve.",
  "needs_clarification": false,
  "clarification_question": null,
  "suggested_mode": "mix",
  "suggested_top_k": 12,
  "tuning_reason": "Query phức tạp với nhiều khía cạnh (điều kiện, thủ tục, deadline, số tiền). Mode 'mix' để tìm toàn diện, top_k=12 để có đủ thông tin từ nhiều nguồn."
}

Example 3 - Ambiguous query:
User: "Làm sao để xin học bổng?"
Output:
{
  "parsed_intention": "Hỏi về quy trình/thủ tục xin học bổng",
  "extracted_entities": ["học bổng"],
  "extracted_topics": ["học bổng", "thủ tục hành chính"],
  "confidence": 0.3,
  "confidence_reason": "Query quá chung chung, không rõ loại học bổng nào (khuyến khích, tài trợ, chính phủ...). Mỗi loại có quy trình khác nhau.",
  "needs_clarification": true,
  "clarification_question": "Bạn muốn hỏi về loại học bổng nào? Ví dụ: học bổng khuyến khích học tập, học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?",
  "suggested_mode": "mix",
  "suggested_top_k": 8,
  "tuning_reason": "Mặc dù cần clarification, vẫn suggest params mặc định (mix, 8) để sẵn sàng retrieve nếu user không trả lời clarification."
}
</examples>
"""


# ============================================================================
# Helper Functions
# ============================================================================

def _content_to_text(content: Any) -> str:
    """Extract text from message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                txt = (part.get("text") or "").strip()
                if txt:
                    texts.append(txt)
        return " ".join(texts) if texts else ""
    return ""


def _last_human_text(messages: List[AnyMessage]) -> str:
    """Get text from the last human message."""
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return _content_to_text(getattr(msg, "content", ""))
    return ""


# ============================================================================
# Agent 1 V3 Node
# ============================================================================

def agent1_understand_query_v3(state: QueryStateV3) -> QueryStateV3:
    """
    Agent 1 V3: Analyze user query and automatically tune retrieval parameters.
    
    This node:
    1. Extracts query from messages or state
    2. Calls LLM with structured output to analyze query
    3. Updates state with parsed intention, entities, topics, confidence
    4. Determines if clarification is needed
    5. **NEW**: Suggests optimal retrieval mode and top_k
    
    Args:
        state: Current QueryStateV3
        
    Returns:
        Updated state with Agent 1 outputs
    """
    
    # Extract query
    query = state.get("query")
    if not query:
        query = _last_human_text(state.get("messages", []))
    
    if not query:
        state["error"] = "No query provided"
        state["status_message"] = "Error: No query"
        return state
    
    # Store original query
    state["query"] = query
    
    print("=" * 80)
    print(f"[AGENT 1 V3] Analyzing query: {query}")
    print("=" * 80)
    
    try:
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": QUERY_UNDERSTANDING_V3_SYSTEM_PROMPT},
                {"role": "user", "content": f"Phân tích câu hỏi sau:\n\n{query}"}
            ],
            response_format=QueryUnderstandingV3,
            temperature=LLM_TEMPERATURE,
        )
        
        # Parse structured output
        understanding = completion.choices[0].message.parsed
        
        if not understanding:
            raise ValueError("LLM did not return structured output")
        
        # Update state with Agent 1 outputs
        state["parsed_intention"] = understanding.parsed_intention
        state["extracted_entities"] = understanding.extracted_entities
        state["extracted_topics"] = understanding.extracted_topics
        state["query_confidence"] = understanding.confidence
        state["query_confidence_reason"] = understanding.confidence_reason
        state["needs_clarification"] = understanding.needs_clarification
        
        if understanding.clarification_question:
            state["clarification_question"] = understanding.clarification_question
        
        # NEW: Update retrieval parameters
        state["retrieval_mode"] = understanding.suggested_mode
        state["top_k"] = understanding.suggested_top_k
        state["tuning_reason"] = understanding.tuning_reason
        
        # Log results
        print(f"[AGENT 1 V3] Parsed Intention: {understanding.parsed_intention}")
        print(f"[AGENT 1 V3] Entities: {understanding.extracted_entities}")
        print(f"[AGENT 1 V3] Topics: {understanding.extracted_topics}")
        print(f"[AGENT 1 V3] Confidence: {understanding.confidence:.2f}")
        print(f"[AGENT 1 V3] Reason: {understanding.confidence_reason}")
        print(f"[AGENT 1 V3] Needs Clarification: {understanding.needs_clarification}")
        
        # NEW: Log parameter tuning
        print(f"[AGENT 1 V3] Suggested Mode: {understanding.suggested_mode}")
        print(f"[AGENT 1 V3] Suggested Top-K: {understanding.suggested_top_k}")
        print(f"[AGENT 1 V3] Tuning Reason: {understanding.tuning_reason}")
        
        if understanding.needs_clarification:
            print(f"[AGENT 1 V3] Clarification Question: {understanding.clarification_question}")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Agent 1 V3 error: {str(e)}"
        print(f"[AGENT 1 V3] ✗ {error_msg}")
        state["error"] = error_msg
        state["status_message"] = "Error in query understanding"
        
        # Set default values on error
        state["query_confidence"] = 0.0
        state["needs_clarification"] = True
        state["clarification_question"] = "Xin lỗi, tôi gặp lỗi khi phân tích câu hỏi. Bạn có thể diễn đạt lại câu hỏi được không?"
        
        # Set default retrieval params
        state["retrieval_mode"] = DEFAULT_RETRIEVAL_MODE
        state["top_k"] = DEFAULT_TOP_K
        state["tuning_reason"] = "Error occurred, using default parameters"
    
    return state


# ============================================================================
# Decision Function
# ============================================================================

def decide_after_agent1_v3(state: QueryStateV3) -> str:
    """
    Decide next step after Agent 1 V3.
    
    Returns:
        - "ask_clarification" if needs_clarification is True
        - "retrieve_data" otherwise
    """
    if state.get("needs_clarification", False):
        return "ask_clarification"
    return "retrieve_data"


# ============================================================================
# Clarification Node
# ============================================================================

def ask_clarification_v3(state: QueryStateV3) -> QueryStateV3:
    """
    Ask clarification question to user.
    
    This node adds the clarification question to messages and ends the flow.
    User will need to respond before continuing.
    """
    from langchain_core.messages import AIMessage
    
    question = state.get("clarification_question", "Bạn có thể cung cấp thêm thông tin được không?")
    
    print("=" * 80)
    print(f"[CLARIFICATION] Asking user: {question}")
    print("=" * 80)
    
    # Add AI message with clarification question
    msgs = list(state.get("messages", []))
    msgs.append(AIMessage(content=question))
    state["messages"] = msgs
    
    state["status_message"] = "Waiting for user clarification"
    
    return state


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "agent1_understand_query_v3",
    "decide_after_agent1_v3",
    "ask_clarification_v3"
]
