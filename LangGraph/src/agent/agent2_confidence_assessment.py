"""
Agent 2: Confidence Assessment based on Rerank Scores

This agent evaluates overall confidence by combining:
1. Query confidence from Agent 1
2. Rerank confidence from Reranker

Based on overall confidence, it decides whether to:
- Generate response (high confidence)
- Ask follow-up question (medium confidence)
- Fallback response (low confidence)
"""

from __future__ import annotations

import os
from typing import Any
from openai import OpenAI
from langchain_core.messages import AIMessage
from agent.state_v3 import (
    QueryStateV3,
    ConfidenceAssessment,
    OVERALL_CONFIDENCE_THRESHOLD,
    FALLBACK_CONFIDENCE_THRESHOLD
)


# ============================================================================
# Configuration
# ============================================================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("AGENT2_TEMPERATURE", "0.2"))


# ============================================================================
# Prompt Template
# ============================================================================

CONFIDENCE_ASSESSMENT_SYSTEM_PROMPT = """
Bạn là chuyên gia đánh giá độ tin cậy cho hệ thống RAG tư vấn sinh viên UIT.

<role>
Nhiệm vụ của bạn là đánh giá xem hệ thống có đủ tự tin để trả lời câu hỏi của sinh viên hay không.
</role>

<inputs>
Bạn được cung cấp:
1. **Query confidence** (từ Agent 1): Độ tự tin về việc hiểu đúng câu hỏi (0.0-1.0)
2. **Rerank confidence** (từ Reranker): Độ liên quan của dữ liệu đã retrieve (0.0-1.0)
3. **Top rerank scores**: Điểm của các kết quả hàng đầu
4. **Query**: Câu hỏi gốc của sinh viên
</inputs>

<assessment_criteria>
Đánh giá overall confidence dựa trên:

**1. Query Confidence (40% weight):**
- Cao (>0.8): Hiểu rõ câu hỏi
- Trung bình (0.5-0.8): Hiểu được nhưng có thể thiếu chi tiết
- Thấp (<0.5): Không chắc chắn về ý định

**2. Rerank Confidence (60% weight):**
- Cao (>0.7): Dữ liệu rất liên quan
- Trung bình (0.4-0.7): Dữ liệu có liên quan một phần
- Thấp (<0.4): Dữ liệu ít liên quan hoặc không đủ

**3. Top Scores Consistency:**
- Nếu top scores đều cao và đồng đều → tăng confidence
- Nếu top scores thấp hoặc chênh lệch lớn → giảm confidence

**Overall Confidence Formula:**
overall_confidence = 0.4 * query_confidence + 0.6 * rerank_confidence

**Adjustments:**
- Nếu top score < 0.5 → giảm 0.1
- Nếu std(top_scores) > 0.3 → giảm 0.05 (không nhất quán)
</assessment_criteria>

<decision_rules>
**High Confidence (>= 0.7):**
- needs_followup = False
- Hệ thống sẽ generate câu trả lời đầy đủ
- Không cần hỏi thêm user

**Medium Confidence (0.4 - 0.7):**
- needs_followup = True
- Generate câu hỏi follow-up để làm rõ hoặc thu hẹp phạm vi
- Câu hỏi nên:
  - Ngắn gọn, dễ hiểu
  - Hướng vào điểm yếu (entities thiếu, ambiguity...)
  - Đưa ra lựa chọn cụ thể nếu có thể

**Low Confidence (< 0.4):**
- needs_followup = False
- Hệ thống sẽ fallback sang response "liên hệ cố vấn"
- Không nên generate câu trả lời vì rủi ro cao
</decision_rules>

<output_format>
Trả về JSON với schema ConfidenceAssessment:
{
  "overall_confidence": 0.0-1.0,
  "needs_followup": true/false,
  "followup_question": "..." (nếu needs_followup=true),
  "confidence_reason": "Giải thích chi tiết cho quyết định"
}
</output_format>

<examples>
Example 1 - High confidence:
Query: "Số tín chỉ tốt nghiệp ngành KHMT?"
Query confidence: 0.95
Rerank confidence: 0.85
Top scores: [0.92, 0.88, 0.85, 0.82, 0.80]

Output:
{
  "overall_confidence": 0.89,
  "needs_followup": false,
  "followup_question": null,
  "confidence_reason": "Query rất rõ ràng (0.95) và dữ liệu rất liên quan (0.85). Top scores đều cao và nhất quán. Overall = 0.4*0.95 + 0.6*0.85 = 0.89. Đủ tự tin để trả lời."
}

Example 2 - Medium confidence (needs follow-up):
Query: "Học bổng nào dễ xin?"
Query confidence: 0.6
Rerank confidence: 0.55
Top scores: [0.65, 0.58, 0.52, 0.48, 0.45]

Output:
{
  "overall_confidence": 0.57,
  "needs_followup": true,
  "followup_question": "Bạn đang quan tâm đến loại học bổng nào? Ví dụ: học bổng khuyến khích học tập (dựa vào điểm), học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?",
  "confidence_reason": "Query hơi chung chung (0.6) và dữ liệu chỉ liên quan một phần (0.55). Overall = 0.4*0.6 + 0.6*0.55 = 0.57. Cần hỏi thêm để thu hẹp phạm vi và tìm thông tin chính xác hơn."
}

Example 3 - Low confidence (fallback):
Query: "Thủ tục này như thế nào?"
Query confidence: 0.3
Rerank confidence: 0.25
Top scores: [0.35, 0.28, 0.22, 0.18, 0.15]

Output:
{
  "overall_confidence": 0.27,
  "needs_followup": false,
  "followup_question": null,
  "confidence_reason": "Query quá mơ hồ (0.3) và dữ liệu ít liên quan (0.25). Overall = 0.4*0.3 + 0.6*0.25 = 0.27. Confidence quá thấp, nên fallback sang 'liên hệ cố vấn' thay vì generate câu trả lời có thể sai."
}
</examples>
"""


# ============================================================================
# Agent 2 Node
# ============================================================================

def agent2_assess_confidence(state: QueryStateV3) -> QueryStateV3:
    """
    Agent 2: Assess overall confidence and decide next action.
    
    This node:
    1. Combines query_confidence and rerank_confidence
    2. Analyzes top rerank scores
    3. Calculates overall_confidence
    4. Decides whether to generate response or ask follow-up
    5. Generates follow-up question if needed
    
    Args:
        state: Current QueryStateV3
        
    Returns:
        Updated state with confidence assessment
    """
    
    # Get inputs
    query = state.get("query", "")
    query_confidence = state.get("query_confidence", 0.0)
    rerank_confidence = state.get("rerank_confidence", 0.0)
    
    # Get top scores for analysis
    chunk_scores = state.get("chunk_scores", [])
    entity_scores = state.get("entity_scores", [])
    relationship_scores = state.get("relationship_scores", [])
    
    all_scores = chunk_scores + entity_scores + relationship_scores
    top_scores = sorted(all_scores, reverse=True)[:5] if all_scores else [0.0]
    
    print("=" * 80)
    print(f"[AGENT 2] Assessing confidence")
    print(f"[AGENT 2] Query confidence: {query_confidence:.2f}")
    print(f"[AGENT 2] Rerank confidence: {rerank_confidence:.2f}")
    print(f"[AGENT 2] Top scores: {[f'{s:.2f}' for s in top_scores]}")
    print("=" * 80)
    
    try:
        # Prepare context for LLM
        context = f"""
Query: {query}

Query Confidence: {query_confidence:.2f}
Rerank Confidence: {rerank_confidence:.2f}
Top Rerank Scores: {', '.join([f'{s:.2f}' for s in top_scores])}

Total items retrieved: {len(all_scores)}
"""
        
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": CONFIDENCE_ASSESSMENT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Đánh giá confidence cho trường hợp sau:\n\n{context}"}
            ],
            response_format=ConfidenceAssessment,
            temperature=LLM_TEMPERATURE,
        )
        
        # Parse structured output
        assessment = completion.choices[0].message.parsed
        
        if not assessment:
            raise ValueError("LLM did not return structured output")
        
        # Update state
        state["overall_confidence"] = assessment.overall_confidence
        state["needs_followup"] = assessment.needs_followup
        state["confidence_reason"] = assessment.confidence_reason
        
        if assessment.followup_question:
            state["followup_question"] = assessment.followup_question
        
        # Log results
        print(f"[AGENT 2] Overall Confidence: {assessment.overall_confidence:.2f}")
        print(f"[AGENT 2] Needs Follow-up: {assessment.needs_followup}")
        print(f"[AGENT 2] Reason: {assessment.confidence_reason}")
        
        if assessment.needs_followup:
            print(f"[AGENT 2] Follow-up Question: {assessment.followup_question}")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Agent 2 error: {str(e)}"
        print(f"[AGENT 2] ✗ {error_msg}")
        state["error"] = error_msg
        
        # Fallback to simple calculation
        overall_confidence = 0.4 * query_confidence + 0.6 * rerank_confidence
        state["overall_confidence"] = overall_confidence
        state["needs_followup"] = overall_confidence < OVERALL_CONFIDENCE_THRESHOLD
        state["confidence_reason"] = f"Simple calculation: 0.4*{query_confidence:.2f} + 0.6*{rerank_confidence:.2f} = {overall_confidence:.2f}"
        
        if state["needs_followup"]:
            state["followup_question"] = "Bạn có thể cung cấp thêm thông tin để tôi có thể trả lời chính xác hơn được không?"
    
    return state


# ============================================================================
# Decision Function
# ============================================================================

def decide_after_agent2(state: QueryStateV3) -> str:
    """
    Decide next step after Agent 2.
    
    Returns:
        - "ask_followup" if needs_followup is True
        - "generate_response" otherwise
    """
    if state.get("needs_followup", False):
        return "ask_followup"
    return "generate_response"


# ============================================================================
# Follow-up Question Node
# ============================================================================

def ask_followup(state: QueryStateV3) -> QueryStateV3:
    """
    Ask follow-up question to user.
    
    This node adds the follow-up question to messages and ends the flow.
    """
    question = state.get("followup_question", "Bạn có thể cung cấp thêm thông tin được không?")
    
    print("=" * 80)
    print(f"[FOLLOW-UP] Asking user: {question}")
    print("=" * 80)
    
    # Add AI message with follow-up question
    msgs = list(state.get("messages", []))
    msgs.append(AIMessage(content=question))
    state["messages"] = msgs
    
    state["status_message"] = "Waiting for user follow-up response"
    
    return state


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "agent2_assess_confidence",
    "decide_after_agent2",
    "ask_followup"
]
