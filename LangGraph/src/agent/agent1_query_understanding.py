"""
Agent 1: Query Understanding with Confidence Scoring

This agent analyzes user queries to:
1. Parse and clarify user intention
2. Extract key entities and topics
3. Calculate confidence score
4. Decide if clarification is needed
"""

from __future__ import annotations

import os
from typing import Any, List
from openai import OpenAI
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from agent.state_v2 import QueryStateV2, QueryUnderstanding, QUERY_CONFIDENCE_THRESHOLD
from agent.prompts import get_prompt


# ============================================================================
# Configuration
# ============================================================================

# LLM client - using OpenAI-compatible API
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("AGENT1_TEMPERATURE", "0.1"))


# ============================================================================
# Prompt Template (from prompts.py)
# ============================================================================

# Prompt is loaded from prompts.py
# QUERY_UNDERSTANDING_SYSTEM_PROMPT = get_prompt("query_understanding_system", LLM_MODEL)

# For backwards compatibility, keep old prompt as fallback
QUERY_UNDERSTANDING_SYSTEM_PROMPT_OLD = """
Bạn là trợ lý phân tích câu hỏi của sinh viên UIT (Đại học Công nghệ Thông tin - ĐHQG TP.HCM).

<role>
Nhiệm vụ của bạn là phân tích câu hỏi của sinh viên để:
1. Hiểu rõ ý định thực sự của sinh viên
2. Trích xuất các thực thể và chủ đề quan trọng
3. Đánh giá độ tự tin về việc hiểu đúng câu hỏi
4. Quyết định có cần hỏi lại sinh viên để làm rõ không
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
- organization: Phòng ban, khoa, đơn vị (Phòng Đào tạo, Khoa KHMT...)
- person: Sinh viên, cán bộ, giảng viên
- regulation: Quy chế, quy định, quy trình
- procedure: Thủ tục hành chính
- scholarship: Học bổng, hỗ trợ tài chính
- system: Hệ thống thông tin (Portal, LMS...)
- location: Địa điểm, phòng học, cơ sở
- event: Sự kiện, hoạt động sinh viên
- document: Văn bản, tài liệu
- academic: Học thuật (tín chỉ, môn học, ngành...)
</entity_types>

<confidence_scoring>
Đánh giá confidence dựa trên:

**High Confidence (0.8 - 1.0):**
- Query rõ ràng, cụ thể
- Có đủ context để hiểu
- Entities được xác định rõ ràng
- Không có nhiều cách hiểu khác nhau

Ví dụ:
- "Sinh viên ngành Khoa học máy tính cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?"
- "Thủ tục xin giấy xác nhận sinh viên ở đâu?"
- "Học bổng khuyến khích học tập kỳ 1 năm 2024 bao giờ công bố?"

**Medium Confidence (0.5 - 0.8):**
- Query hơi chung chung nhưng có thể infer được
- Thiếu một vài chi tiết nhưng không critical
- Có thể trả lời được nhưng không chắc 100%

Ví dụ:
- "Làm sao để chuyển ngành?" (thiếu: chuyển từ ngành nào sang ngành nào)
- "Học bổng nào dễ xin nhất?" (thiếu: dựa trên tiêu chí gì)

**Low Confidence (0.0 - 0.5):**
- Query quá mơ hồ, không rõ ràng
- Thiếu context quan trọng
- Có nhiều cách hiểu khác nhau
- Cần clarification để trả lời chính xác

Ví dụ:
- "Làm sao để xin học bổng?" (không rõ loại học bổng nào)
- "Thủ tục này như thế nào?" (không rõ thủ tục gì)
- "Bao giờ mở đăng ký?" (không rõ đăng ký gì)
</confidence_scoring>

<clarification_guidelines>
Cần hỏi lại (needs_clarification = true) khi:
- Confidence < 0.5
- Query có nhiều cách hiểu
- Thiếu thông tin quan trọng để trả lời chính xác
- Có thể dẫn đến câu trả lời sai nếu hiểu nhầm

Câu hỏi clarification nên:
- Ngắn gọn, dễ hiểu
- Đưa ra các lựa chọn cụ thể (nếu có thể)
- Thân thiện, lịch sự

Ví dụ:
- "Bạn muốn hỏi về loại học bổng nào? Ví dụ: học bổng khuyến khích học tập, học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?"
- "Bạn đang hỏi về thủ tục chuyển ngành hay chuyển lớp?"
</clarification_guidelines>

<output_format>
Trả về JSON với schema QueryUnderstanding:
{
  "parsed_intention": "...",
  "extracted_entities": ["...", "..."],
  "extracted_topics": ["...", "..."],
  "confidence": 0.0-1.0,
  "confidence_reason": "...",
  "needs_clarification": true/false,
  "clarification_question": "..." (nếu needs_clarification=true)
}
</output_format>

<examples>
Example 1:
User: "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp ngành Khoa học máy tính?"
Output:
{
  "parsed_intention": "Hỏi về số tín chỉ tối thiểu để tốt nghiệp ngành Khoa học máy tính",
  "extracted_entities": ["Khoa học máy tính", "tín chỉ tốt nghiệp"],
  "extracted_topics": ["quy chế đào tạo", "điều kiện tốt nghiệp"],
  "confidence": 0.95,
  "confidence_reason": "Query rất rõ ràng, cụ thể về ngành học và thông tin cần tìm. Có đủ context để trả lời chính xác.",
  "needs_clarification": false,
  "clarification_question": null
}

Example 2:
User: "Làm sao để xin học bổng?"
Output:
{
  "parsed_intention": "Hỏi về quy trình/thủ tục xin học bổng",
  "extracted_entities": ["học bổng"],
  "extracted_topics": ["học bổng", "thủ tục hành chính"],
  "confidence": 0.3,
  "confidence_reason": "Query quá chung chung, không rõ loại học bổng nào (khuyến khích, tài trợ, chính phủ...). Mỗi loại có quy trình khác nhau.",
  "needs_clarification": true,
  "clarification_question": "Bạn muốn hỏi về loại học bổng nào? Ví dụ: học bổng khuyến khích học tập, học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?"
}

Example 3:
User: "Thủ tục chuyển ngành từ CNTT sang KHMT như thế nào?"
Output:
{
  "parsed_intention": "Hỏi về quy trình và thủ tục chuyển từ ngành Công nghệ Thông tin sang ngành Khoa học Máy tính",
  "extracted_entities": ["Công nghệ Thông tin", "Khoa học Máy tính", "chuyển ngành"],
  "extracted_topics": ["thủ tục hành chính", "chuyển ngành"],
  "confidence": 0.85,
  "confidence_reason": "Query rõ ràng về ngành chuyển đi và ngành chuyển đến. Có đủ thông tin để tìm kiếm quy trình cụ thể.",
  "needs_clarification": false,
  "clarification_question": null
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
# Agent 1 Node
# ============================================================================

def agent1_understand_query(state: QueryStateV2) -> QueryStateV2:
    """
    Agent 1: Analyze user query and calculate confidence score.
    
    This node:
    1. Extracts query from messages or state
    2. Calls LLM with structured output to analyze query
    3. Updates state with parsed intention, entities, topics, confidence
    4. Determines if clarification is needed
    
    Args:
        state: Current QueryStateV2
        
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
    print(f"[AGENT 1] Analyzing query: {query}")
    print("=" * 80)
    
    try:
        # Load prompt from prompts.py
        system_prompt = get_prompt("query_understanding_system", LLM_MODEL)
        
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Phân tích câu hỏi sau:\n\n{query}"}
            ],
            response_format=QueryUnderstanding,
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
        
        # Log results
        print(f"[AGENT 1] Parsed Intention: {understanding.parsed_intention}")
        print(f"[AGENT 1] Entities: {understanding.extracted_entities}")
        print(f"[AGENT 1] Topics: {understanding.extracted_topics}")
        print(f"[AGENT 1] Confidence: {understanding.confidence:.2f}")
        print(f"[AGENT 1] Reason: {understanding.confidence_reason}")
        print(f"[AGENT 1] Needs Clarification: {understanding.needs_clarification}")
        
        if understanding.needs_clarification:
            print(f"[AGENT 1] Clarification Question: {understanding.clarification_question}")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Agent 1 error: {str(e)}"
        print(f"[AGENT 1] ✗ {error_msg}")
        state["error"] = error_msg
        state["status_message"] = "Error in query understanding"
        
        # Set default low confidence on error
        state["query_confidence"] = 0.0
        state["needs_clarification"] = True
        state["clarification_question"] = "Xin lỗi, tôi gặp lỗi khi phân tích câu hỏi. Bạn có thể diễn đạt lại câu hỏi được không?"
    
    return state


# ============================================================================
# Decision Function for Conditional Edge
# ============================================================================

def decide_after_agent1(state: QueryStateV2) -> str:
    """
    Decide next step after Agent 1 based on confidence score.
    
    Returns:
        "ask_clarification" if confidence is low or clarification needed
        "retrieve_data" if confidence is high enough to proceed
    """
    
    # Check for errors
    if state.get("error"):
        return "ask_clarification"
    
    # Get confidence and clarification flag
    confidence = state.get("query_confidence", 0.0)
    needs_clarification = state.get("needs_clarification", False)
    
    # Get threshold (can be overridden in state)
    threshold = state.get("confidence_threshold", QUERY_CONFIDENCE_THRESHOLD)
    
    print(f"[DECISION] Confidence: {confidence:.2f}, Threshold: {threshold:.2f}")
    print(f"[DECISION] Needs Clarification: {needs_clarification}")
    
    # Decision logic
    if confidence < threshold or needs_clarification:
        print("[DECISION] → ask_clarification")
        return "ask_clarification"
    else:
        print("[DECISION] → retrieve_data")
        return "retrieve_data"


# ============================================================================
# Clarification Node
# ============================================================================

def ask_clarification(state: QueryStateV2) -> QueryStateV2:
    """
    Ask user for clarification and end the flow.
    
    This node sends the clarification question to the user and waits for response.
    """
    
    clarification_q = state.get("clarification_question", "Bạn có thể cung cấp thêm thông tin được không?")
    
    print(f"[CLARIFICATION] Asking: {clarification_q}")
    
    # Add AI message with clarification question
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=clarification_q))
    state["messages"] = messages
    
    # Set final answer to clarification question
    state["final_answer"] = clarification_q
    state["response_type"] = "clarification"  # type: ignore
    state["status_message"] = "Waiting for user clarification"
    
    return state
