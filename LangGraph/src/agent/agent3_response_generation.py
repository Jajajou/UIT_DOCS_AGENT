"""
Agent 3: Response Generation using Reranked Data

This agent generates the final response using high-quality reranked data.
It creates a comprehensive answer with hyperlinked references.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from openai import OpenAI
from langchain_core.messages import AIMessage
from agent.state_v3 import (
    QueryStateV3,
    ResponseGeneration,
    Reference,
    FALLBACK_CONFIDENCE_THRESHOLD,
    FALLBACK_RESPONSE_TEMPLATE,
    PARTIAL_ANSWER_SUFFIX
)


# ============================================================================
# Configuration
# ============================================================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("AGENT3_TEMPERATURE", "0.3"))


# ============================================================================
# Prompt Template
# ============================================================================

RESPONSE_GENERATION_PROMPT = """
Bạn là trợ lý tư vấn học tập cho sinh viên UIT (Đại học Công nghệ Thông tin - ĐHQG TP.HCM).

<role>
Nhiệm vụ của bạn là tạo câu trả lời chính xác, đầy đủ và thân thiện cho sinh viên dựa trên dữ liệu đã được rerank (sắp xếp theo độ liên quan).
</role>

<user_query>
{parsed_intention}
</user_query>

<reranked_data>
Dữ liệu sau đã được sắp xếp theo độ liên quan (cao nhất trước):

{reranked_data_formatted}
</reranked_data>

<confidence_info>
Overall Confidence: {overall_confidence:.2f}
Confidence Reason: {confidence_reason}
</confidence_info>

<instructions>
1. **Trả lời chính xác:**
   - Ưu tiên sử dụng data có score cao (>0.7)
   - Không bịa đặt thông tin không có trong data
   - Nếu data không đủ trả lời một phần nào, hãy nói rõ

2. **Trích dẫn nguồn với hyperlink:**
   - Sử dụng markdown format: [Tên tài liệu](URL)
   - Ví dụ: "Theo [Quy chế đào tạo 2024](https://example.com/quy-che.pdf), sinh viên cần..."
   - Chỉ trích dẫn các nguồn có URL (file_source)
   - Đặt hyperlink ngay sau thông tin được trích dẫn

3. **Xử lý theo confidence:**
   - **High (>= 0.7)**: Trả lời đầy đủ, tự tin → response_type = "full_answer"
   - **Medium (0.4-0.7)**: Không nên xảy ra (đã hỏi follow-up ở bước trước)
   - **Low (< 0.4)**: Fallback response → response_type = "fallback"

4. **Format response:**
   - Sử dụng markdown cho dễ đọc
   - Chia thành đoạn văn rõ ràng
   - Dùng bullet points nếu cần liệt kê
   - Thân thiện, lịch sự, chuyên nghiệp

5. **References:**
   - List tất cả tài liệu được sử dụng
   - Mỗi reference cần: title, url (nếu có), relevance score
   - Sắp xếp theo độ liên quan (cao nhất trước)
   - Chỉ include references có score >= 0.5
</instructions>

<output_format>
Trả về JSON với schema ResponseGeneration:
{{
  "response_text": "...",
  "response_type": "full_answer" | "partial_answer" | "fallback",
  "references": [
    {{
      "title": "...",
      "url": "...",
      "relevance": 0.0-1.0,
      "excerpt": "..." (optional)
    }}
  ]
}}
</output_format>

<examples>
Example 1 (Full Answer - High Confidence):
{{
  "response_text": "Theo [Quy chế đào tạo 2024](https://daa.uit.edu.vn/quy-che-2024.pdf), sinh viên ngành Khoa học Máy tính cần tích lũy tối thiểu **140 tín chỉ** để đủ điều kiện tốt nghiệp.\\n\\nCụ thể, 140 tín chỉ này bao gồm:\\n- Kiến thức giáo dục đại cương: 40 tín chỉ\\n- Kiến thức cơ sở ngành: 50 tín chỉ\\n- Kiến thức chuyên ngành: 45 tín chỉ\\n- Thực tập và khóa luận: 5 tín chỉ\\n\\nNgoài ra, sinh viên cũng cần đạt các điều kiện khác như GPA tối thiểu 2.0, hoàn thành chương trình giáo dục thể chất và giáo dục quốc phòng.",
  "response_type": "full_answer",
  "references": [
    {{
      "title": "Quy chế đào tạo 2024",
      "url": "https://daa.uit.edu.vn/quy-che-2024.pdf",
      "relevance": 0.95,
      "excerpt": "Điều 15: Điều kiện tốt nghiệp..."
    }}
  ]
}}

Example 2 (Fallback - Low Confidence):
{{
  "response_text": "Cảm ơn bạn đã đặt câu hỏi.\\n\\nDựa trên thông tin hiện có trong hệ thống, tôi chưa thể cung cấp câu trả lời đầy đủ và chính xác cho câu hỏi này.\\n\\n**Đề xuất:**\\nĐể được tư vấn chi tiết và chính xác nhất, bạn vui lòng liên hệ:\\n- **Cố vấn học tập** của lớp/khoa\\n- **Phòng Đào tạo** (nếu liên quan đến quy chế, quy trình đào tạo)\\n- **Phòng Công tác Sinh viên** (nếu liên quan đến học bổng, hoạt động sinh viên)",
  "response_type": "fallback",
  "references": []
}}
</examples>
"""


# ============================================================================
# Helper Functions
# ============================================================================

def _format_reranked_data(
    reranked_entities: List[Tuple[Dict[str, Any], float]],
    reranked_relationships: List[Tuple[Dict[str, Any], float]],
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    top_n: int = 10
) -> str:
    """Format reranked data for prompt."""
    lines = []
    
    # Format entities
    if reranked_entities:
        lines.append("**Entities (theo độ liên quan):**")
        for i, (ent, score) in enumerate(reranked_entities[:top_n], 1):
            name = ent.get("name", "Unknown")
            desc = ent.get("description", "")
            lines.append(f"{i}. [{name}] (score: {score:.2f})")
            if desc:
                lines.append(f"   {desc[:200]}...")
        lines.append("")
    
    # Format relationships
    if reranked_relationships:
        lines.append("**Relationships (theo độ liên quan):**")
        for i, (rel, score) in enumerate(reranked_relationships[:top_n], 1):
            desc = rel.get("description", str(rel))
            lines.append(f"{i}. (score: {score:.2f}) {desc[:200]}...")
        lines.append("")
    
    # Format chunks
    if reranked_chunks:
        lines.append("**Text Chunks (theo độ liên quan):**")
        for i, (chunk, score) in enumerate(reranked_chunks[:top_n], 1):
            content = chunk.get("content", "")
            file_source = chunk.get("file_source", "")
            lines.append(f"{i}. (score: {score:.2f})")
            lines.append(f"   Content: {content[:300]}...")
            if file_source:
                lines.append(f"   Source: {file_source}")
        lines.append("")
    
    return "\n".join(lines) if lines else "Không có dữ liệu."


def _extract_references(
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    min_score: float = 0.5
) -> List[Dict[str, Any]]:
    """Extract references from reranked chunks."""
    references = []
    seen_sources = set()
    
    for chunk, score in reranked_chunks:
        if score < min_score:
            continue
        
        file_source = chunk.get("file_source", "")
        if not file_source or file_source in seen_sources:
            continue
        
        seen_sources.add(file_source)
        
        # Extract title from file_source URL
        title = file_source.split("/")[-1] if "/" in file_source else file_source
        
        # Get excerpt
        content = chunk.get("content", "")
        excerpt = content[:200] + "..." if len(content) > 200 else content
        
        references.append({
            "title": title,
            "url": file_source,
            "relevance": float(score),
            "excerpt": excerpt
        })
    
    # Sort by relevance
    references.sort(key=lambda x: x["relevance"], reverse=True)
    
    return references


# ============================================================================
# Agent 3 Node
# ============================================================================

def agent3_generate_response(state: QueryStateV3) -> QueryStateV3:
    """
    Agent 3: Generate response using reranked data.
    
    This node:
    1. Formats reranked data for LLM
    2. Calls LLM to generate response
    3. Extracts references from reranked chunks
    4. Updates state with final answer
    5. Adds AI message to chat
    
    Args:
        state: Current QueryStateV3
        
    Returns:
        Updated state with generated response
    """
    
    # Get inputs
    parsed_intention = state.get("parsed_intention", state.get("query", ""))
    overall_confidence = state.get("overall_confidence", 0.0)
    confidence_reason = state.get("confidence_reason", "")
    
    reranked_entities = state.get("reranked_entities", [])
    reranked_relationships = state.get("reranked_relationships", [])
    reranked_chunks = state.get("reranked_chunks", [])
    
    print("=" * 80)
    print(f"[AGENT 3] Generating response")
    print(f"[AGENT 3] Overall confidence: {overall_confidence:.2f}")
    print(f"[AGENT 3] Reranked items: {len(reranked_entities)} entities, {len(reranked_relationships)} relationships, {len(reranked_chunks)} chunks")
    print("=" * 80)
    
    # Check if should fallback
    if overall_confidence < FALLBACK_CONFIDENCE_THRESHOLD:
        print(f"[AGENT 3] Low confidence ({overall_confidence:.2f}), using fallback response")
        
        topic = state.get("extracted_topics", ["câu hỏi của bạn"])[0] if state.get("extracted_topics") else "câu hỏi của bạn"
        fallback_text = FALLBACK_RESPONSE_TEMPLATE.format(
            topic=topic,
            fallback_reason=confidence_reason
        )
        
        state["generated_response"] = fallback_text
        state["response_type"] = "fallback"
        state["references"] = []
        state["final_answer"] = fallback_text
        
        # Add to messages
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=fallback_text))
        state["messages"] = msgs
        
        return state
    
    try:
        # Format reranked data
        reranked_data_formatted = _format_reranked_data(
            reranked_entities,
            reranked_relationships,
            reranked_chunks,
            top_n=10
        )
        
        # Prepare prompt
        prompt_text = RESPONSE_GENERATION_PROMPT.format(
            parsed_intention=parsed_intention,
            reranked_data_formatted=reranked_data_formatted,
            overall_confidence=overall_confidence,
            confidence_reason=confidence_reason
        )
        
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": "Generate response cho query trên."}
            ],
            response_format=ResponseGeneration,
            temperature=LLM_TEMPERATURE,
        )
        
        # Parse structured output
        response_gen = completion.choices[0].message.parsed
        
        if not response_gen:
            raise ValueError("LLM did not return structured output")
        
        # Update state
        state["generated_response"] = response_gen.response_text
        state["response_type"] = response_gen.response_type
        
        # Convert Pydantic references to dicts
        references_list = [ref.model_dump() for ref in response_gen.references]
        state["references"] = references_list
        
        # Set final answer
        final_answer = response_gen.response_text
        
        # Add partial answer suffix if needed
        if response_gen.response_type == "partial_answer":
            final_answer += PARTIAL_ANSWER_SUFFIX
        
        state["final_answer"] = final_answer
        
        # Add to messages
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=final_answer))
        state["messages"] = msgs
        
        # Log results
        print(f"[AGENT 3] ✓ Response generated")
        print(f"[AGENT 3] Response type: {response_gen.response_type}")
        print(f"[AGENT 3] References: {len(references_list)}")
        print(f"[AGENT 3] Response length: {len(final_answer)} chars")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Agent 3 error: {str(e)}"
        print(f"[AGENT 3] ✗ {error_msg}")
        state["error"] = error_msg
        
        # Fallback to simple response
        fallback_text = "Xin lỗi, tôi gặp lỗi khi tạo câu trả lời. Vui lòng thử lại hoặc liên hệ cố vấn học tập."
        state["generated_response"] = fallback_text
        state["response_type"] = "fallback"
        state["references"] = []
        state["final_answer"] = fallback_text
        
        # Add to messages
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=fallback_text))
        state["messages"] = msgs
    
    return state


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "agent3_generate_response"
]
