"""
Agent 3: Response Generation using Reranked Data

This agent generates the final response using high-quality reranked data.
It creates a comprehensive answer with hyperlinked references.
"""

from __future__ import annotations

import re
import time as _t
from typing import Any, Dict, List, Tuple
from datetime import datetime
from langchain_core.messages import AIMessage
from openai import OpenAI
from agent.core.prompts import PROMPTS
from agent.states.query_state import (
    QueryState,
    ResponseGeneration,
)
from agent.config import get_attr_safe, settings
from agent.utils import strip_think_tags, get_url


# ============================================================================
# Configuration
# ============================================================================

# Use raw openai client — LangChain adapter strips the `reasoning` field
# that vLLM --reasoning-parser qwen3 returns in additional_kwargs
_openai_client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


# ============================================================================
# Helper Functions
# ============================================================================

_FALLBACK_KEYWORDS = [
    "không tìm thấy thông tin", "không có thông tin", "xin lỗi, tôi không",
    "không thể trả lời", "không có dữ liệu",
]
_PARTIAL_KEYWORDS = [
    "không đủ thông tin", "thông tin chưa đầy đủ", "thông tin hạn chế",
    "chỉ tìm thấy một phần", "chưa tìm thấy đầy đủ",
]


def _classify_response_type(text: str) -> str:
    """Deterministic response_type classifier — no LLM needed."""
    if not text.strip():
        return "fallback"
    lower = text.lower()
    if any(k in lower for k in _FALLBACK_KEYWORDS):
        return "fallback"
    if any(k in lower for k in _PARTIAL_KEYWORDS):
        return "partial_answer"
    return "full_answer"


def _check_citation_validity(
    final_answer: str,
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    references_list: List[Dict[str, Any]],
) -> str:
    """Option A: Rule-based citation check — no LLM needed.

    Detects two classes of phantom citations:
    1. [Nguồn N] references where N > len(references_list)
    2. Doc numbers (e.g. 108/QĐ-ĐHCNTT) mentioned in answer but absent from retrieved chunks
    """
    # Collect retrieved doc numbers (normalised: strip separators, uppercase)
    def _norm(s: str) -> str:
        return re.sub(r"[\s/_\-]", "", s).upper()

    retrieved_norms: set[str] = set()
    for chunk, _ in reranked_chunks:
        dn = chunk.get("metadata", {}).get("document_number", "")
        if dn:
            retrieved_norms.add(_norm(dn))

    warnings: List[str] = []

    # Check [Nguồn N] numbered refs exceed available sources
    cited_nums = {int(m) for m in re.findall(r"\[Nguồn\s+(\d+)\]", final_answer)}
    max_valid = len(references_list)
    phantom_nums = sorted(n for n in cited_nums if n > max_valid)
    if phantom_nums:
        nums_str = ", ".join(str(n) for n in phantom_nums)
        warnings.append(f"[Nguồn {nums_str}] không tồn tại trong kết quả tìm kiếm.")

    # Check explicit doc numbers mentioned in answer
    # Pattern: digits/UPPERCASE-UPPERCASE (e.g. 108/QĐ-ĐHCNTT)
    mentioned = re.findall(r"\b\d+/[A-ZĐQTBCN][A-ZĐQTBCN\-]+", final_answer)
    phantom_docs = sorted({d for d in mentioned if _norm(d) not in retrieved_norms})
    if phantom_docs:
        docs_str = ", ".join(phantom_docs)
        warnings.append(f"Văn bản {docs_str} không có trong dữ liệu truy xuất.")

    if warnings:
        print(f"[AGENT 3] Citation check: {len(warnings)} issue(s) found")
        return "\n\n> **Cảnh báo trích dẫn:** " + " ".join(warnings)

    print("[AGENT 3] Citation check: OK")
    return ""


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
    
    # Format chunks — skip metadata-only points (content empty = Qdrant backfill artifacts)
    real_chunks = [(chunk, score) for chunk, score in reranked_chunks if chunk.get("content", "").strip()]
    if real_chunks:
        lines.append("**Text Chunks (theo độ liên quan):**")
        for i, (chunk, score) in enumerate(real_chunks[:top_n], 1):
            content = chunk.get("content", "")
            meta = chunk.get("metadata", {})
            file_source = chunk.get("file_path", "") or chunk.get("file_source", "")
            doc_num = meta.get("document_number")

            lines.append(f"{i}. (score: {score:.2f})")
            if doc_num:
                lines.append(f"   Document: {doc_num}")
            lines.append(f"   Content: {content[:800]}")
            if file_source:
                resolved = get_url(file_source)
                lines.append(f"   Source: {resolved or file_source}")
        lines.append("")
    
    return "\n".join(lines) if lines else "Không có dữ liệu."


def _extract_references(
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    min_score: float = 0.4,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """Extract references preserving 1-1 mapping with chunk indices in the prompt.

    Each entry at position i corresponds to [Nguon i+1] cited by the LLM.
    No score filtering or dedup here — the LLM sees chunks 1..N and may cite
    any of them. Filtering low-score chunks would shift indices and break
    citation numbering.
    """
    references = []

    for chunk, score in reranked_chunks[:top_n]:
        if not chunk.get("content", "").strip():
            continue  # skip metadata-only Qdrant backfill artifacts
        file_source = chunk.get("file_path", "") or chunk.get("file_source", "")
        meta = chunk.get("metadata", {})
        doc_num = meta.get("document_number")

        if doc_num:
            title = doc_num
        elif file_source:
            title = file_source.split("/")[-1] if "/" in file_source else file_source
        else:
            title = "Tài liệu UIT"

        content = chunk.get("content", "")
        excerpt = content[:200] + "..." if len(content) > 200 else content

        resolved_url = get_url(file_source) if file_source else None
        references.append({
            "title": title,
            "url": resolved_url or file_source or "",
            "relevance": float(score),
            "excerpt": excerpt,
        })

    return references


def _generate_confidence_transparency(state: QueryState) -> str:
    """
    Generate a transparency note for responses with low confidence or temporal ambiguity.
    """
    confidence = state.get("rerank_confidence", 1.0)
    reranked_chunks = state.get("reranked_chunks", [])
    
    warnings = []
    
    # 1. Low overall confidence warning
    # ViRanker outputs raw logits; HTTP server applies sigmoid → ~0-1 range.
    # sigmoid(-0.85) ≈ 0.3 is genuinely low relevance for this model.
    if confidence < 0.3:
        warnings.append("Thông tin này có thể chưa đầy đủ. Vui lòng xác nhận lại với Phòng Đào tạo.")
        
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
        # Format reranked data — chunks only (entities/rels are noise for regulatory RAG)
        reranked_data_formatted = _format_reranked_data(
            [],
            [],
            reranked_chunks,
            top_n=10
        )

        # Prepare prompt
        cohort_year = state.get("query_cohort_year")
        academic_year = state.get("query_academic_year")
        education_system = state.get("education_system")
        student_context_note = ""
        
        context_parts = []
        if cohort_year:
            context_parts.append(f"Khóa: {cohort_year}")
        if academic_year:
            context_parts.append(f"Năm học: {academic_year}")
        if education_system:
            context_parts.append(f"Hệ đào tạo: {education_system}")
            
        if context_parts:
            student_context_note = "<student_context>\n" + ", ".join(context_parts) + "\nƯu tiên thông tin áp dụng cho ngữ cảnh này.\n</student_context>"

        thinking_prompt = PROMPTS["response_generation_thinking_prompt"].format(
            parsed_intention=parsed_intention,
            reranked_data_formatted=reranked_data_formatted,
            student_context_note=student_context_note,
        )

        human_content = parsed_intention

        # Call 1: thinking pass — stream token-by-token so LangGraph forwards
        # chunks via SSE. Raw openai client preserves `reasoning` delta field
        # that vLLM --reasoning-parser qwen3 emits; LangChain adapter strips it.
        from langgraph.config import get_stream_writer
        _write = get_stream_writer()

        # Always enable thinking — without it Qwen3 leaks CoT as visible content
        needs_thinking = True

        _t1 = _t.perf_counter()
        stream = _openai_client.chat.completions.create(
            model=settings.agent3_llm_model,
            messages=[
                {"role": "system", "content": thinking_prompt},
                {"role": "user", "content": human_content},
            ],
            max_tokens=6000,
            temperature=settings.agent3_temperature,
            extra_body={
                "enable_thinking": needs_thinking,
                "thinking_token_budget": 512,
            },
            stream=True,
        )

        reasoning_parts: List[str] = []
        content_parts: List[str] = []
        _in_think_block = False
        _think_buf = ""
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            # vLLM reasoning-parser emits reasoning tokens in delta.reasoning
            r_token = (getattr(delta, "model_extra", {}) or {}).get("reasoning") or ""
            c_token = delta.content or ""
            if r_token:
                reasoning_parts.append(r_token)
                _write({"type": "reasoning", "content": r_token})
            if c_token:
                # Intercept <think>...</think> in content stream — redirect to reasoning
                _think_buf += c_token
                while True:
                    if _in_think_block:
                        end = _think_buf.find("</think>")
                        if end != -1:
                            reasoning_chunk = _think_buf[:end]
                            if reasoning_chunk:
                                reasoning_parts.append(reasoning_chunk)
                                _write({"type": "reasoning", "content": reasoning_chunk})
                            _think_buf = _think_buf[end + 8:]
                            _in_think_block = False
                        else:
                            if _think_buf:
                                reasoning_parts.append(_think_buf)
                                _write({"type": "reasoning", "content": _think_buf})
                            _think_buf = ""
                            break
                    else:
                        start = _think_buf.find("<think>")
                        if start != -1:
                            before = _think_buf[:start]
                            if before:
                                content_parts.append(before)
                                _write({"type": "token", "content": before})
                            _think_buf = _think_buf[start + 7:]
                            _in_think_block = True
                        else:
                            if _think_buf:
                                content_parts.append(_think_buf)
                                _write({"type": "token", "content": _think_buf})
                            _think_buf = ""
                            break
        # Flush remaining buffer
        if _think_buf:
            if _in_think_block:
                reasoning_parts.append(_think_buf)
                _write({"type": "reasoning", "content": _think_buf})
            else:
                content_parts.append(_think_buf)
                _write({"type": "token", "content": _think_buf})

        print(f"[TIMING] agent3_call1_thinking: {_t.perf_counter() - _t1:.2f}s")

        reasoning = "".join(reasoning_parts)
        thinking_content = "".join(content_parts)
        response_text = strip_think_tags(thinking_content).strip()
        print(f"[AGENT 3] Call 1 done, response length: {len(response_text)} chars, reasoning: {len(reasoning)} chars")

        # Classify response_type deterministically — no LLM Call 2 needed
        response_type_classified = _classify_response_type(response_text)
        response_gen = ResponseGeneration(
            response_type=response_type_classified,
            response_text=response_text,
        )

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

        # Option A: rule-based citation validity check
        citation_warning = _check_citation_validity(final_answer, reranked_chunks, references_list)
        if citation_warning:
            final_answer += citation_warning

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
            "messages": [AIMessage(content=f"<think>{reasoning}</think>{final_answer}" if reasoning else final_answer)],
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
