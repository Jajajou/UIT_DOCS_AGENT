"""
Agent 3: Response Generation using Reranked Data

This agent generates the final response using high-quality reranked data.
It creates a comprehensive answer with hyperlinked references.
"""

from __future__ import annotations

import os
import re
import json
from typing import Any, Dict, List, Tuple
from datetime import datetime
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from agent.core.prompts import PROMPTS
from agent.states.query_state import (
    QueryState,
    ResponseGeneration,
)
from langchain.chat_models import init_chat_model
from agent.config import get_attr_safe, settings
from agent.utils import strip_think_tags, get_url


# ============================================================================
# Configuration
# ============================================================================

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.llm_model,
    streaming=False,
    temperature=settings.agent3_temperature,
    model_kwargs={"tool_choice": "none"}
)


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_expiration_warnings(
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    current_date: str = None
) -> str:
    """
    Generate warnings for expired, expiring, or amended documents.

    Checks three temporal conditions:
    1. Expired documents (past valid_until date)
    2. Expiring soon (within warning_days of valid_until)
    3. Amended documents (superseded by newer versions via amended_by field)

    Args:
        reranked_chunks: List of (chunk, score) tuples with metadata
        current_date: ISO date string for comparison. Defaults to today.

    Returns:
        Warning message string (empty if no warnings needed)
    """
    if current_date is None:
        current = datetime.now()
    else:
        current = datetime.fromisoformat(current_date)

    # Get thresholds from config
    temporal_config = getattr(settings, 'temporal', None)
    if temporal_config:
        warning_days = getattr(temporal_config.freshness_thresholds, 'warning_days', 30)
    else:
        warning_days = 30

    expired_docs = []
    expiring_soon_docs = []
    amended_docs = []

    # Track unique documents by file_path
    seen_sources = set()

    for chunk, score in reranked_chunks:
        metadata = chunk.get("metadata", {})
        file_source = chunk.get("file_path", "") or chunk.get("file_source", "")

        # Skip if already processed this source
        if file_source in seen_sources:
            continue
        seen_sources.add(file_source)

        doc_number = metadata.get("document_number", "Tài liệu")

        # Check for amended_by field (document has been superseded)
        amended_by = metadata.get("amended_by")
        if amended_by:
            # amended_by can be a list or string
            if isinstance(amended_by, list) and len(amended_by) > 0:
                amended_docs.append({
                    "number": doc_number,
                    "amended_by": amended_by,
                    "source": file_source
                })
            elif isinstance(amended_by, str) and amended_by.strip():
                amended_docs.append({
                    "number": doc_number,
                    "amended_by": [amended_by],
                    "source": file_source
                })

        # Check for valid_until (expiration)
        valid_until = metadata.get("valid_until")
        if not valid_until:
            continue

        try:
            until_date = datetime.fromisoformat(valid_until)

            # Check if expired
            if current > until_date:
                days_expired = (current - until_date).days
                expired_docs.append({
                    "number": doc_number,
                    "expired_date": valid_until,
                    "days_expired": days_expired,
                    "source": file_source
                })
            else:
                # Check if expiring soon
                days_until_expiry = (until_date - current).days
                if days_until_expiry <= warning_days:
                    expiring_soon_docs.append({
                        "number": doc_number,
                        "expiry_date": valid_until,
                        "days_remaining": days_until_expiry,
                        "source": file_source
                    })

        except (ValueError, TypeError):
            pass

    # Build warning message
    warnings = []

    if expired_docs:
        warnings.append("\n**[Cảnh báo] Tài liệu đã hết hạn:**")
        for doc in expired_docs:
            warnings.append(f"- {doc['number']} đã hết hiệu lực từ ngày {doc['expired_date']} ({doc['days_expired']} ngày trước)")

    if expiring_soon_docs:
        warnings.append("\n**[Lưu ý] Tài liệu sắp hết hạn:**")
        for doc in expiring_soon_docs:
            warnings.append(f"- {doc['number']} sẽ hết hiệu lực vào ngày {doc['expiry_date']} (còn {doc['days_remaining']} ngày)")

    if amended_docs:
        warnings.append("\n**[Thông báo] Tài liệu đã được sửa đổi/bổ sung:**")
        for doc in amended_docs:
            amended_list = ", ".join(doc["amended_by"])
            warnings.append(f"- {doc['number']} đã được sửa đổi/thay thế bởi: {amended_list}")
        warnings.append("  Vui lòng tham khảo văn bản mới nhất để có thông tin chính xác.")

    if warnings:
        warnings.append("\n**Khuyến nghị:** Vui lòng kiểm tra với phòng Đào tạo hoặc cố vấn học tập để xác nhận thông tin mới nhất.")
        return "\n".join(warnings)

    return ""


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
            meta = chunk.get("metadata", {})
            file_source = chunk.get("file_path", "") or chunk.get("file_source", "")
            doc_num = meta.get("document_number")
            
            lines.append(f"{i}. (score: {score:.2f})")
            if doc_num:
                lines.append(f"   Document: {doc_num}")
            lines.append(f"   Content: {content[:300]}...")
            if file_source:
                resolved = get_url(file_source)
                lines.append(f"   Source: {resolved or file_source}")
        lines.append("")
    
    return "\n".join(lines) if lines else "Không có dữ liệu."


def _extract_references(
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    min_score: float = 0.4
) -> List[Dict[str, Any]]:
    """Extract references from reranked chunks."""
    references = []
    seen_sources = set()
    
    for chunk, score in reranked_chunks:
        if score < min_score:
            continue
        
        file_source = chunk.get("file_path", "") or chunk.get("file_source", "")
        if not file_source or file_source in seen_sources:
            continue

        seen_sources.add(file_source)
        
        meta = chunk.get("metadata", {})
        doc_num = meta.get("document_number")

        # Use document number as title if available, otherwise filename
        if doc_num:
            title = doc_num
        else:
            title = file_source.split("/")[-1] if "/" in file_source else file_source
        
        # Get excerpt
        content = chunk.get("content", "")
        excerpt = content[:200] + "..." if len(content) > 200 else content
        
        resolved_url = get_url(file_source) if file_source else None
        references.append({
            "title": title,
            "url": resolved_url or file_source,
            "relevance": float(score),
            "excerpt": excerpt
        })
    
    # Sort by relevance
    references.sort(key=lambda x: x["relevance"], reverse=True)
    
    return references


def _generate_confidence_transparency(state: QueryState) -> str:
    """
    Generate a transparency note for responses with low confidence or temporal ambiguity.
    """
    confidence = state.get("rerank_confidence", 1.0)
    reranked_chunks = state.get("reranked_chunks", [])
    
    warnings = []
    
    # 1. Low overall confidence warning
    if confidence < 0.8:
        warnings.append(f"Thông tin này được tổng hợp với độ tin cậy thấp ({confidence:.1%}).")
        
    # 2. Temporal ambiguity check (multiple conflicting amendments or old docs)
    unique_docs = set()
    amendment_counts = 0
    oldest_valid_from = None
    
    for chunk, _ in reranked_chunks[:5]:
        meta = chunk.get("metadata", {})
        doc_id = meta.get("doc_id") or meta.get("document_number")
        if doc_id and doc_id not in unique_docs:
            unique_docs.add(doc_id)
            if meta.get("amended_by"):
                amendment_counts += 1
            valid_from = meta.get("valid_from")
            if valid_from:
                try:
                    dt = datetime.fromisoformat(valid_from)
                    if oldest_valid_from is None or dt < oldest_valid_from:
                        oldest_valid_from = dt
                except:
                    pass

    if amendment_counts > 1:
        warnings.append("Lưu ý: Có nhiều văn bản sửa đổi liên quan đến nội dung này, hệ thống đã ưu tiên các phiên bản mới nhất.")
        
    if oldest_valid_from and (datetime.now() - oldest_valid_from).days > 1095: # 3 years
        warnings.append("Lưu ý: Một số quy định tham chiếu đã ban hành hơn 3 năm, bạn nên kiểm tra lại tính cập nhật.")

    if warnings:
        header = "\n**[Tính minh bạch]**"
        return f"{header}\n- " + "\n- ".join(warnings)
    
    return ""


# ============================================================================
# Agent 3 Node
# ============================================================================

def agent3_generate_response(state: QueryState) -> Dict[str, Any]:
    """
    Agent 3: Generate response using reranked data.
    
    This node:
    1. Formats reranked data for LLM
    2. Calls LLM to generate response
    3. Extracts references from reranked chunks
    4. Returns partial state update with generated response and final answer
    
    Args:
        state: Current QueryState
        
    Returns:
        Partial state update with generated response
    """
    
    # Get inputs
    parsed_intention = state.get("parsed_intention", state.get("query", ""))

    reranked_entities = state.get("reranked_entities", [])
    reranked_relationships = state.get("reranked_relationships", [])
    reranked_chunks = state.get("reranked_chunks", [])

    print("=" * 80)
    print(f"[AGENT 3] Generating response")
    print(f"[AGENT 3] Reranked items: {len(reranked_entities)} entities, {len(reranked_relationships)} relationships, {len(reranked_chunks)} chunks")
    print("=" * 80)

    try:
        # Format reranked data
        reranked_data_formatted = _format_reranked_data(
            reranked_entities,
            reranked_relationships,
            reranked_chunks,
            top_n=10
        )

        # Prepare prompt
        prompt_text = PROMPTS["response_generation_prompt"].format(
            parsed_intention=parsed_intention,
            reranked_data_formatted=reranked_data_formatted,
        )
        
        # Call LLM directly, strip think tags, parse manually
        llm_json = llm.bind(response_format={"type": "json_object"})

        msgs = [
            SystemMessage(content=prompt_text),
            HumanMessage(content=f"{parsed_intention}\n\nGenerate JSON response.")
        ]
        raw_response = llm_json.invoke(input=msgs)
        content = raw_response.content if hasattr(raw_response, "content") else str(raw_response)

        content = strip_think_tags(content)

        data = json.loads(content)
        response_gen = ResponseGeneration(**data)

        if not response_gen:
            raise ValueError("LLM did not return structured output")
        
        # Extract references from reranked chunks
        references_list = _extract_references(reranked_chunks)

        # Get response parts
        generated_response = get_attr_safe(response_gen, "response_text")
        response_type = get_attr_safe(response_gen, "response_type")

        # Generate expiration warnings
        expiration_warnings = _generate_expiration_warnings(reranked_chunks)

        # Generate transparency notes
        transparency_notes = _generate_confidence_transparency(state)

        # Set final answer
        final_answer = generated_response

        # Add expiration warnings if any
        if expiration_warnings:
            final_answer += "\n\n---\n" + expiration_warnings
            
        # Add transparency notes if any
        if transparency_notes:
            if not expiration_warnings:
                final_answer += "\n\n---\n"
            else:
                final_answer += "\n"
            final_answer += transparency_notes

        # Add partial answer suffix if needed
        if response_type == "partial_answer":
            final_answer += PROMPTS["partial_answer_suffix"]
        
        # Log results
        print(f"[AGENT 3] ✓ Response generated")
        print(f"[AGENT 3] Response type: {response_type}")
        print(f"[AGENT 3] References: {len(references_list)}")
        print(f"[AGENT 3] Expiration warnings: {'Yes' if expiration_warnings else 'No'}")
        print(f"[AGENT 3] Response length: {len(final_answer)} chars")
        
        return {
            "generated_response": generated_response,
            "response_type": response_type,
            "references": references_list,
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
            "error": "",
            "logs": ["Agent 3 generated response"]
        }
        
    except Exception as e:
        error_msg = f"Agent 3 error: {str(e)}"
        print(f"[AGENT 3] ✗ {error_msg}")
        
        # Fallback to simple response
        fallback_text = "Xin lỗi, tôi gặp lỗi khi tạo câu trả lời. Vui lòng thử lại hoặc liên hệ cố vấn học tập."
        
        return {
            "error": error_msg,
            "generated_response": fallback_text,
            "response_type": "fallback",
            "references": [],
            "final_answer": fallback_text,
            "messages": [AIMessage(content=fallback_text)],
            "logs": [f"Agent 3 error: {error_msg}"]
        }


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "agent3_generate_response"
]
