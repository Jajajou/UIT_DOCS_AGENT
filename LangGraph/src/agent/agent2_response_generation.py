"""
Agent 2: Data Quality Assessment & Response Generation

This agent:
1. Evaluates quality of retrieved data
2. Calculates data quality confidence score
3. Decides whether to generate full answer or fallback
4. Generates response with hyperlinked references
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List
from openai import OpenAI
from langchain_core.messages import AIMessage
from agent.state_v2 import (
    QueryStateV2,
    DataQualityAssessment,
    ResponseGeneration,
    Reference,
    DATA_QUALITY_THRESHOLD_HIGH,
    DATA_QUALITY_THRESHOLD_LOW,
    FALLBACK_RESPONSE_TEMPLATE,
    PARTIAL_ANSWER_SUFFIX
)


# ============================================================================
# Configuration
# ============================================================================

# LLM client
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
ASSESSMENT_TEMPERATURE = float(os.getenv("AGENT2_ASSESSMENT_TEMP", "0.1"))
GENERATION_TEMPERATURE = float(os.getenv("AGENT2_GENERATION_TEMP", "0.3"))


# ============================================================================
# Prompt Templates
# ============================================================================

DATA_QUALITY_ASSESSMENT_PROMPT = """
Bạn là chuyên gia đánh giá chất lượng dữ liệu cho hệ thống RAG tư vấn sinh viên UIT.

<role>
Nhiệm vụ của bạn là đánh giá xem dữ liệu được retrieve có đủ chất lượng để trả lời câu hỏi của sinh viên hay không.
</role>

<user_query>
{parsed_intention}
</user_query>

<retrieved_data>
**Entities:**
{entities_summary}

**Relationships:**
{relationships_summary}

**Text Chunks:**
{chunks_summary}
</retrieved_data>

<assessment_criteria>
Đánh giá dựa trên các tiêu chí sau:

1. **Relevance (Độ liên quan):**
   - Data có liên quan trực tiếp đến câu hỏi không?
   - Có entities/chunks off-topic không?

2. **Completeness (Độ đầy đủ):**
   - Data có đủ để trả lời đầy đủ câu hỏi không?
   - Có thiếu thông tin quan trọng không?

3. **Consistency (Tính nhất quán):**
   - Các chunks có mâu thuẫn nhau không?
   - Thông tin có đồng nhất không?

4. **Recency (Tính cập nhật):**
   - Data có dấu hiệu lỗi thời không? (nếu có timestamp)
   - Có mention về "mới nhất", "hiện tại" không?

5. **Source Quality (Chất lượng nguồn):**
   - Nguồn có đáng tin cậy không? (quy chế chính thức, thông báo từ phòng ban...)
   - Có file_source URL không?
</assessment_criteria>

<scoring_guidelines>
**High Quality (0.7 - 1.0):**
- Data rất liên quan và đầy đủ
- Không có mâu thuẫn
- Từ nguồn chính thức, đáng tin cậy
- Có thể trả lời chính xác và đầy đủ

**Medium Quality (0.4 - 0.7):**
- Data liên quan nhưng có thể thiếu một số chi tiết
- Có thể trả lời được một phần
- Cần thêm thông tin để hoàn chỉnh

**Low Quality (0.0 - 0.4):**
- Data không liên quan hoặc quá ít
- Mâu thuẫn, lỗi thời
- Không đủ để trả lời chính xác
- Nên fallback sang "liên hệ cố vấn"
</scoring_guidelines>

<fallback_decision>
Nên fallback (should_fallback = true) khi:
- Quality score < 0.4
- Data mâu thuẫn nghiêm trọng
- Data rõ ràng lỗi thời (ví dụ: quy chế cũ)
- Câu hỏi yêu cầu thông tin cập nhật mà data không có
- Rủi ro cao nếu trả lời sai (ví dụ: thủ tục quan trọng)
</fallback_decision>

<output_format>
Trả về JSON với schema DataQualityAssessment:
{{
  "quality_score": 0.0-1.0,
  "quality_reason": "...",
  "coverage": "complete" | "partial" | "insufficient",
  "should_fallback": true/false,
  "fallback_reason": "..." (nếu should_fallback=true)
}}
</output_format>
"""


RESPONSE_GENERATION_PROMPT = """
Bạn là trợ lý tư vấn học tập cho sinh viên UIT (Đại học Công nghệ Thông tin - ĐHQG TP.HCM).

<role>
Nhiệm vụ của bạn là tạo câu trả lời chính xác, đầy đủ và thân thiện cho sinh viên dựa trên dữ liệu đã được retrieve.
</role>

<user_query>
{parsed_intention}
</user_query>

<retrieved_data>
{retrieved_data_formatted}
</retrieved_data>

<data_quality_assessment>
Quality Score: {quality_score}
Coverage: {coverage}
Reason: {quality_reason}
</data_quality_assessment>

<instructions>
1. **Trả lời chính xác:**
   - Dựa vào retrieved data, trả lời câu hỏi một cách chính xác
   - Không bịa đặt thông tin không có trong data
   - Nếu data không đủ trả lời một phần nào, hãy nói rõ

2. **Trích dẫn nguồn với hyperlink:**
   - Sử dụng markdown format: [Tên tài liệu](URL)
   - Ví dụ: "Theo [Quy chế đào tạo 2024](https://example.com/quy-che.pdf), sinh viên cần..."
   - Chỉ trích dẫn các nguồn có URL (file_source)
   - Đặt hyperlink ngay sau thông tin được trích dẫn

3. **Xử lý coverage:**
   - **complete**: Trả lời đầy đủ, tự tin
   - **partial**: Trả lời phần có thể trả lời, ghi chú phần thiếu, suggest liên hệ cố vấn
   - **insufficient**: Không nên xảy ra (đã fallback ở bước trước)

4. **Format response:**
   - Sử dụng markdown cho dễ đọc
   - Chia thành đoạn văn rõ ràng
   - Dùng bullet points nếu cần liệt kê
   - Thân thiện, lịch sự, chuyên nghiệp

5. **References:**
   - List tất cả tài liệu được sử dụng
   - Mỗi reference cần: title, url (nếu có), relevance score
   - Sắp xếp theo độ liên quan (cao nhất trước)
</instructions>

<output_format>
Trả về JSON với schema ResponseGeneration:
{{
  "response_text": "...",
  "response_type": "full_answer" | "partial_answer",
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
Example 1 (Full Answer):
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

Example 2 (Partial Answer):
{{
  "response_text": "Dựa trên thông tin hiện có, quy trình chuyển ngành cơ bản bao gồm các bước sau:\\n\\n1. Nộp đơn xin chuyển ngành tại Phòng Đào tạo\\n2. Đáp ứng điều kiện: GPA >= 2.5, không có môn nợ\\n3. Thi tuyển hoặc xét điểm (tùy ngành)\\n\\n**Lưu ý:** Thông tin trên được trích từ [Hướng dẫn chuyển ngành 2020](https://daa.uit.edu.vn/huong-dan-2020.pdf). Quy trình có thể đã được cập nhật. Để biết thông tin chính xác và mới nhất, bạn vui lòng liên hệ trực tiếp với **Phòng Đào tạo** hoặc **cố vấn học tập** của khoa.",
  "response_type": "partial_answer",
  "references": [
    {{
      "title": "Hướng dẫn chuyển ngành 2020",
      "url": "https://daa.uit.edu.vn/huong-dan-2020.pdf",
      "relevance": 0.6,
      "excerpt": "Quy trình chuyển ngành..."
    }}
  ]
}}
</examples>
"""


# ============================================================================
# Helper Functions
# ============================================================================

def _format_entities_summary(entities: List[Dict[str, Any]]) -> str:
    """Format entities for prompt."""
    if not entities:
        return "Không có entities được retrieve."
    
    summary_lines = []
    for i, ent in enumerate(entities[:10], 1):  # Limit to top 10
        name = ent.get("name", "Unknown")
        ent_type = ent.get("type", "unknown")
        description = ent.get("description", "")
        summary_lines.append(f"{i}. {name} ({ent_type}): {description[:100]}...")
    
    if len(entities) > 10:
        summary_lines.append(f"... và {len(entities) - 10} entities khác")
    
    return "\n".join(summary_lines)


def _format_relationships_summary(relationships: List[Dict[str, Any]]) -> str:
    """Format relationships for prompt."""
    if not relationships:
        return "Không có relationships được retrieve."
    
    summary_lines = []
    for i, rel in enumerate(relationships[:10], 1):
        source = rel.get("source", "Unknown")
        target = rel.get("target", "Unknown")
        rel_type = rel.get("type", "related_to")
        summary_lines.append(f"{i}. {source} --[{rel_type}]--> {target}")
    
    if len(relationships) > 10:
        summary_lines.append(f"... và {len(relationships) - 10} relationships khác")
    
    return "\n".join(summary_lines)


def _format_chunks_summary(chunks: List[Dict[str, Any]]) -> str:
    """Format text chunks for prompt."""
    if not chunks:
        return "Không có text chunks được retrieve."
    
    summary_lines = []
    for i, chunk in enumerate(chunks[:5], 1):  # Limit to top 5
        content = chunk.get("content", "")
        score = chunk.get("score", 0.0)
        source = chunk.get("file_source", "Unknown source")
        
        # Truncate content
        content_preview = content[:200] + "..." if len(content) > 200 else content
        
        summary_lines.append(
            f"{i}. [Score: {score:.2f}] {content_preview}\n   Source: {source}"
        )
    
    if len(chunks) > 5:
        summary_lines.append(f"... và {len(chunks) - 5} chunks khác")
    
    return "\n".join(summary_lines)


def _format_retrieved_data_for_generation(state: QueryStateV2) -> str:
    """Format all retrieved data for response generation prompt."""
    
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])
    chunks = state.get("retrieved_chunks", [])
    
    formatted = "**Entities:**\n"
    formatted += _format_entities_summary(entities)
    formatted += "\n\n**Relationships:**\n"
    formatted += _format_relationships_summary(relationships)
    formatted += "\n\n**Text Chunks:**\n"
    
    # For generation, include full chunks (not truncated)
    if chunks:
        for i, chunk in enumerate(chunks, 1):
            content = chunk.get("content", "")
            source = chunk.get("file_source", "Unknown")
            formatted += f"\n--- Chunk {i} (Source: {source}) ---\n{content}\n"
    else:
        formatted += "Không có text chunks."
    
    return formatted


def _extract_references_from_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract unique references from chunks."""
    
    references_map = {}  # file_source -> reference data
    
    for chunk in chunks:
        file_source = chunk.get("file_source")
        if not file_source or file_source == "Unknown":
            continue
        
        if file_source not in references_map:
            # Extract title from file_source (URL)
            # Assume URL like: https://daa.uit.edu.vn/path/to/document.pdf
            title = file_source.split("/")[-1]  # Get filename
            if title.endswith(".pdf"):
                title = title[:-4]  # Remove .pdf extension
            
            references_map[file_source] = {
                "title": title,
                "url": file_source,
                "relevance": chunk.get("score", 0.5),
                "excerpt": chunk.get("content", "")[:150] + "..."
            }
        else:
            # Update relevance to max score
            current_relevance = references_map[file_source]["relevance"]
            new_relevance = chunk.get("score", 0.5)
            references_map[file_source]["relevance"] = max(current_relevance, new_relevance)
    
    # Convert to list and sort by relevance
    references = list(references_map.values())
    references.sort(key=lambda x: x["relevance"], reverse=True)
    
    return references


# ============================================================================
# Agent 2 Nodes
# ============================================================================

def agent2_assess_data_quality(state: QueryStateV2) -> QueryStateV2:
    """
    Agent 2 Phase 1: Assess quality of retrieved data.
    
    This node:
    1. Evaluates retrieved entities, relationships, chunks
    2. Calculates data quality score
    3. Determines coverage level
    4. Decides if fallback is needed
    
    Args:
        state: Current QueryStateV2 with retrieved data
        
    Returns:
        Updated state with data quality assessment
    """
    
    parsed_intention = state.get("parsed_intention", state.get("query", ""))
    
    # Get retrieved data
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])
    chunks = state.get("retrieved_chunks", [])
    
    print("=" * 80)
    print(f"[AGENT 2 - ASSESSMENT] Evaluating data quality")
    print(f"[AGENT 2 - ASSESSMENT] Entities: {len(entities)}, Relationships: {len(relationships)}, Chunks: {len(chunks)}")
    print("=" * 80)
    
    # Format data summaries
    entities_summary = _format_entities_summary(entities)
    relationships_summary = _format_relationships_summary(relationships)
    chunks_summary = _format_chunks_summary(chunks)
    
    # Build prompt
    prompt = DATA_QUALITY_ASSESSMENT_PROMPT.format(
        parsed_intention=parsed_intention,
        entities_summary=entities_summary,
        relationships_summary=relationships_summary,
        chunks_summary=chunks_summary
    )
    
    try:
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format=DataQualityAssessment,
            temperature=ASSESSMENT_TEMPERATURE,
        )
        
        assessment = completion.choices[0].message.parsed
        
        if not assessment:
            raise ValueError("LLM did not return structured output")
        
        # Update state
        state["data_quality_score"] = assessment.quality_score
        state["data_quality_reason"] = assessment.quality_reason
        state["data_coverage"] = assessment.coverage
        state["should_fallback"] = assessment.should_fallback
        
        if assessment.fallback_reason:
            state["fallback_reason"] = assessment.fallback_reason
        
        # Log results
        print(f"[AGENT 2 - ASSESSMENT] Quality Score: {assessment.quality_score:.2f}")
        print(f"[AGENT 2 - ASSESSMENT] Coverage: {assessment.coverage}")
        print(f"[AGENT 2 - ASSESSMENT] Reason: {assessment.quality_reason}")
        print(f"[AGENT 2 - ASSESSMENT] Should Fallback: {assessment.should_fallback}")
        
        if assessment.should_fallback:
            print(f"[AGENT 2 - ASSESSMENT] Fallback Reason: {assessment.fallback_reason}")
        
    except Exception as e:
        error_msg = f"Agent 2 assessment error: {str(e)}"
        print(f"[AGENT 2 - ASSESSMENT] ✗ {error_msg}")
        
        # On error, set low quality and fallback
        state["data_quality_score"] = 0.0
        state["data_quality_reason"] = f"Error during assessment: {str(e)}"
        state["data_coverage"] = "insufficient"
        state["should_fallback"] = True
        state["fallback_reason"] = "Lỗi khi đánh giá chất lượng dữ liệu"
    
    return state


def agent2_generate_response(state: QueryStateV2) -> QueryStateV2:
    """
    Agent 2 Phase 2: Generate response based on data quality.
    
    This node:
    1. Checks if fallback is needed
    2. If fallback: generates fallback response
    3. If not fallback: generates full/partial answer with references
    
    Args:
        state: Current QueryStateV2 with data quality assessment
        
    Returns:
        Updated state with generated response
    """
    
    should_fallback = state.get("should_fallback", False)
    
    print("=" * 80)
    print(f"[AGENT 2 - GENERATION] Generating response (Fallback: {should_fallback})")
    print("=" * 80)
    
    # Check for fallback
    if should_fallback:
        return _generate_fallback_response(state)
    else:
        return _generate_full_response(state)


def _generate_fallback_response(state: QueryStateV2) -> QueryStateV2:
    """Generate fallback response suggesting to contact advisor."""
    
    # Extract topic from parsed_intention or query
    parsed_intention = state.get("parsed_intention", state.get("query", ""))
    topics = state.get("extracted_topics", [])
    topic = topics[0] if topics else "vấn đề này"
    
    fallback_reason = state.get("fallback_reason", "Thông tin trong hệ thống chưa đầy đủ")
    
    # Format fallback response
    response_text = FALLBACK_RESPONSE_TEMPLATE.format(
        topic=topic,
        fallback_reason=fallback_reason
    )
    
    state["generated_response"] = response_text
    state["response_type"] = "fallback"
    state["references"] = []
    state["final_answer"] = response_text
    
    print(f"[AGENT 2 - GENERATION] Fallback response generated")
    
    # Add to messages
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=response_text))
    state["messages"] = messages
    
    return state


def _generate_full_response(state: QueryStateV2) -> QueryStateV2:
    """Generate full or partial response with references."""
    
    parsed_intention = state.get("parsed_intention", state.get("query", ""))
    quality_score = state.get("data_quality_score", 0.5)
    quality_reason = state.get("data_quality_reason", "")
    coverage = state.get("data_coverage", "partial")
    
    # Format retrieved data
    retrieved_data_formatted = _format_retrieved_data_for_generation(state)
    
    # Build prompt
    prompt = RESPONSE_GENERATION_PROMPT.format(
        parsed_intention=parsed_intention,
        retrieved_data_formatted=retrieved_data_formatted,
        quality_score=quality_score,
        coverage=coverage,
        quality_reason=quality_reason
    )
    
    try:
        # Call LLM with structured output
        completion = client.beta.chat.completions.parse(
            model=LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format=ResponseGeneration,
            temperature=GENERATION_TEMPERATURE,
        )
        
        generation = completion.choices[0].message.parsed
        
        if not generation:
            raise ValueError("LLM did not return structured output")
        
        # Get response text
        response_text = generation.response_text
        
        # Add suffix for partial answers
        if generation.response_type == "partial_answer":
            response_text += PARTIAL_ANSWER_SUFFIX
        
        # Update state
        state["generated_response"] = response_text
        state["response_type"] = generation.response_type
        state["references"] = [ref.model_dump() for ref in generation.references]
        state["final_answer"] = response_text
        
        print(f"[AGENT 2 - GENERATION] Response generated ({generation.response_type})")
        print(f"[AGENT 2 - GENERATION] References: {len(generation.references)}")
        
        # Add to messages
        messages = list(state.get("messages", []))
        messages.append(AIMessage(content=response_text))
        state["messages"] = messages
        
    except Exception as e:
        error_msg = f"Agent 2 generation error: {str(e)}"
        print(f"[AGENT 2 - GENERATION] ✗ {error_msg}")
        
        # Fallback to simple response
        state["error"] = error_msg
        state["generated_response"] = f"Xin lỗi, tôi gặp lỗi khi tạo câu trả lời. Vui lòng thử lại hoặc liên hệ cố vấn học tập."
        state["response_type"] = "fallback"
        state["final_answer"] = state["generated_response"]
    
    return state
