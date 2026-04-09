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
from typing import Any, Dict, List, Tuple
from datetime import datetime
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from agent.core.prompts import PROMPTS
from agent.states.query_state import (
    QueryState,
    ConfidenceAssessment,
)
from langchain.chat_models import init_chat_model
from agent.config import get_attr_safe, settings


# ============================================================================ 
# Configuration
# ============================================================================ 

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.llm_model,
    temperature=settings.agent2_temperature,
    model_kwargs={}
)


# ============================================================================
# Helper Functions
# ============================================================================

def assess_temporal_freshness(
    reranked_chunks: List[Tuple[Dict[str, Any], float]],
    current_date: str = None
) -> Dict[str, Any]:
    """
    Assess temporal freshness of retrieved documents.

    Evaluates three temporal factors:
    1. Expired documents (past valid_until date)
    2. Expiring soon (within warning_days of valid_until)
    3. Amended documents (superseded by newer versions via amended_by field)

    Args:
        reranked_chunks: List of (chunk, score) tuples with metadata
        current_date: ISO date string for comparison. Defaults to today.

    Returns:
        Dict with:
        - freshness_penalty: Penalty factor (0.0-1.0) to apply to confidence
        - expired_count: Number of expired documents
        - expiring_soon_count: Number of documents expiring within warning_days
        - amended_count: Number of documents that have been amended
        - freshness_summary: Human-readable summary
    """
    if current_date is None:
        current = datetime.now()
    else:
        current = datetime.fromisoformat(current_date)

    # Get thresholds from config
    temporal_config = getattr(settings, 'temporal', None)
    if temporal_config:
        warning_days = getattr(temporal_config.freshness_thresholds, 'warning_days', 30)
        expired_penalty = getattr(temporal_config.quality_penalties, 'expired_penalty', 0.5)
        expiring_soon_penalty = getattr(temporal_config.quality_penalties, 'expiring_soon_penalty', 0.8)
        amended_penalty = getattr(temporal_config.quality_penalties, 'amended_penalty', 0.7)
    else:
        warning_days = 30
        expired_penalty = 0.5
        expiring_soon_penalty = 0.8
        amended_penalty = 0.7

    expired_count = 0
    expiring_soon_count = 0
    amended_count = 0
    total_with_temporal_metadata = 0
    total_with_amendment_info = 0

    for chunk, score in reranked_chunks:
        metadata = chunk.get("metadata", {})

        # Check for amended_by field (document has been superseded)
        amended_by = metadata.get("amended_by")
        if amended_by:
            # amended_by can be a list or string
            if isinstance(amended_by, list) and len(amended_by) > 0:
                amended_count += 1
                total_with_amendment_info += 1
            elif isinstance(amended_by, str) and amended_by.strip():
                amended_count += 1
                total_with_amendment_info += 1

        # Check for valid_until (expiration)
        valid_until = metadata.get("valid_until")
        if not valid_until:
            continue

        total_with_temporal_metadata += 1

        try:
            until_date = datetime.fromisoformat(valid_until)

            # Check if expired
            if current > until_date:
                expired_count += 1
            else:
                # Check if expiring soon
                days_until_expiry = (until_date - current).days
                if days_until_expiry <= warning_days:
                    expiring_soon_count += 1

        except (ValueError, TypeError):
            pass

    # Calculate combined penalty
    total_docs_assessed = max(total_with_temporal_metadata, total_with_amendment_info, 1)

    if total_with_temporal_metadata == 0 and amended_count == 0:
        # No temporal metadata available
        penalty = 1.0
        summary = "Không có thông tin về độ mới của tài liệu."
    else:
        # Calculate individual penalty components
        penalty = 1.0

        # Apply expired penalty
        if total_with_temporal_metadata > 0:
            expired_ratio = expired_count / total_with_temporal_metadata
            expiring_ratio = expiring_soon_count / total_with_temporal_metadata

            # Weighted penalty for expired/expiring docs
            temporal_penalty = 1.0 - (
                expired_ratio * (1 - expired_penalty) +
                expiring_ratio * (1 - expiring_soon_penalty)
            )
            penalty *= temporal_penalty

        # Apply amended penalty (independent of expiration)
        if amended_count > 0:
            # Each amended doc reduces confidence by (1 - amended_penalty)
            # Scale by ratio of amended docs
            amended_ratio = amended_count / len(reranked_chunks) if reranked_chunks else 0
            amendment_penalty = 1.0 - (amended_ratio * (1 - amended_penalty))
            penalty *= amendment_penalty

        # Generate summary
        parts = []
        if expired_count > 0:
            parts.append(f"{expired_count} tài liệu đã hết hạn")
        if expiring_soon_count > 0:
            parts.append(f"{expiring_soon_count} tài liệu sắp hết hạn (trong {warning_days} ngày)")
        if amended_count > 0:
            parts.append(f"{amended_count} tài liệu đã bị sửa đổi/thay thế bởi văn bản mới")

        if parts:
            summary = f"Phát hiện: {', '.join(parts)}."
        else:
            summary = f"Tất cả {total_docs_assessed} tài liệu đều còn hiệu lực và chưa bị sửa đổi."

    return {
        "freshness_penalty": penalty,
        "expired_count": expired_count,
        "expiring_soon_count": expiring_soon_count,
        "amended_count": amended_count,
        "freshness_summary": summary
    }


# ============================================================================
# Prompt Template
# ============================================================================ 



# ============================================================================ 
# Agent 2 Node
# ============================================================================ 

def agent2_assess_confidence(state: QueryState) -> Dict[str, Any]:
    """
    Agent 2: Assess overall confidence and decide next action.

    This node:
    1. Combines query_confidence and rerank_confidence
    2. Analyzes top rerank scores
    3. Assesses temporal freshness of documents
    4. Applies freshness penalties to confidence
    5. Calculates overall_confidence
    6. Returns partial state update with confidence assessment

    Args:
        state: Current QueryState

    Returns:
        Partial state update with confidence assessment
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

    # Get reranked chunks for temporal assessment
    reranked_chunks = state.get("reranked_chunks", [])

    # Assess temporal freshness
    freshness_assessment = assess_temporal_freshness(reranked_chunks)
    freshness_penalty = freshness_assessment["freshness_penalty"]

    print("=" * 80)
    print(f"[AGENT 2] Assessing confidence")
    print(f"[AGENT 2] Query confidence: {query_confidence:.2f}")
    print(f"[AGENT 2] Rerank confidence: {rerank_confidence:.2f}")
    print(f"[AGENT 2] Top scores: {[f'{s:.2f}' for s in top_scores]}")
    print(f"[AGENT 2] Temporal freshness: {freshness_assessment['freshness_summary']}")
    print(f"[AGENT 2] - Expired: {freshness_assessment['expired_count']}, Expiring soon: {freshness_assessment['expiring_soon_count']}, Amended: {freshness_assessment.get('amended_count', 0)}")
    print(f"[AGENT 2] Combined freshness penalty: {freshness_penalty:.2f}")
    print("=" * 80)
    
    try:
        # Prepare context for LLM
        context = f"""
                Query: {query}

                Query Confidence: {query_confidence:.2f}
                Rerank Confidence: {rerank_confidence:.2f}
                Top Rerank Scores: {', '.join([f'{s:.2f}' for s in top_scores])}

                Total items retrieved: {len(all_scores)}

                Temporal Freshness Assessment:
                - {freshness_assessment['freshness_summary']}
                - Expired documents: {freshness_assessment['expired_count']}
                - Expiring soon: {freshness_assessment['expiring_soon_count']}
                - Amended/superseded documents: {freshness_assessment.get('amended_count', 0)}
                - Combined freshness penalty: {freshness_penalty:.2f}
                """
        
        # Call LLM with structured output
        llm_structured_output = llm.with_structured_output(ConfidenceAssessment)

        msgs = [
            SystemMessage(content=PROMPTS["confidence_assessment_system_prompt"]),
            HumanMessage(content=f"Đánh giá confidence cho trường hợp sau:\n\n{context}")
        ]

        assessment = llm_structured_output.invoke(input=msgs)
        
        
        if not assessment:
            raise ValueError("LLM did not return structured output")
        
        # Extract values safely
        base_confidence = get_attr_safe(assessment,"overall_confidence")
        needs_followup = get_attr_safe(assessment,"needs_followup")
        confidence_reason = get_attr_safe(assessment,"confidence_reason")
        followup_question = get_attr_safe(assessment,"followup_question")

        # Apply temporal freshness penalty
        overall_confidence = base_confidence * freshness_penalty

        # Update reason if penalty was applied
        if freshness_penalty < 1.0:
            confidence_reason = f"{confidence_reason}\n\nLưu ý: Độ tin cậy đã được điều chỉnh do {freshness_assessment['freshness_summary']}"

        # Log results
        print(f"[AGENT 2] Base Confidence: {base_confidence:.2f}")
        print(f"[AGENT 2] Overall Confidence (after freshness penalty): {overall_confidence:.2f}")
        print(f"[AGENT 2] Needs Follow-up: {needs_followup}")
        print(f"[AGENT 2] Reason: {confidence_reason}")
        
        if needs_followup:
            print(f"[AGENT 2] Follow-up Question: {followup_question}")
        
        # Return partial update
        return {
            "overall_confidence": overall_confidence,
            "needs_followup": needs_followup,
            "confidence_reason": confidence_reason,
            "followup_question": followup_question if followup_question is not None else None,
            "error": None,
            "logs": ["Agent 2 assessed confidence"]
        }
        
    except Exception as e:
        error_msg = f"Agent 2 error: {str(e)}"
        print(f"[AGENT 2] ✗ {error_msg}")

        # Fallback to simple calculation with freshness penalty
        base_fallback_confidence = 0.4 * query_confidence + 0.6 * rerank_confidence
        fallback_confidence = base_fallback_confidence * freshness_penalty
        needs_followup_fallback = fallback_confidence < settings.query_thresholds.overall_confidence_threshold
        
        # Build confidence reason with freshness info
        reason_text = f"Simple calculation: 0.4*{query_confidence:.2f} + 0.6*{rerank_confidence:.2f} = {base_fallback_confidence:.2f}"
        if freshness_penalty < 1.0:
            reason_text += f"\nĐã áp dụng freshness penalty {freshness_penalty:.2f}: {freshness_assessment['freshness_summary']}"
            reason_text += f"\nOverall confidence sau penalty: {fallback_confidence:.2f}"

        fallback_update = {
            "error": error_msg,
            "overall_confidence": fallback_confidence,
            "needs_followup": needs_followup_fallback,
            "confidence_reason": reason_text,
            "logs": [f"Agent 2 error: {error_msg}"]
        }
        
        if needs_followup_fallback:
            fallback_update["followup_question"] = "Bạn có thể cung cấp thêm thông tin để tôi có thể trả lời chính xác hơn được không?"
            
        return fallback_update


# ============================================================================ 
# Decision Function
# ============================================================================ 

def decide_after_agent2(state: QueryState) -> str:
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

def ask_followup(state: QueryState) -> Dict[str, Any]:
    """
    Ask follow-up question to user.
    
    This node adds the follow-up question to messages and ends the flow.
    """
    question = state.get("followup_question", "Bạn có thể cung cấp thêm thông tin được không?")
    
    print("=" * 80)
    print(f"[FOLLOW-UP] Asking user: {question}")
    print("=" * 80)
    
    # Return partial update with new message
    return {
        "messages": [AIMessage(content=question)],
        "status_message": "Waiting for user follow-up response"
    }


# ============================================================================ 
# Export
# ============================================================================ 

__all__ = [
    "agent2_assess_confidence",
    "decide_after_agent2",
    "ask_followup"
]