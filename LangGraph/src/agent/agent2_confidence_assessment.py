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
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from agent.prompts import PROMPTS
from agent.query_state import (
    QueryState,
    ConfidenceAssessment,
    OVERALL_CONFIDENCE_THRESHOLD,
    FALLBACK_CONFIDENCE_THRESHOLD
)
from langchain.chat_models import init_chat_model
from agent.config import get_attr_safe


# ============================================================================
# Configuration
# ============================================================================

llm = init_chat_model(
    model_provider="openai",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    model=os.getenv("LLM_MODEL"),
    temperature=float(os.getenv("AGENT2_TEMPERATURE", "0.2"))
)


# ============================================================================
# Prompt Template
# ============================================================================



# ============================================================================
# Agent 2 Node
# ============================================================================

def agent2_assess_confidence(state: QueryState) -> QueryState:
    """
    Agent 2: Assess overall confidence and decide next action.
    
    This node:
    1. Combines query_confidence and rerank_confidence
    2. Analyzes top rerank scores
    3. Calculates overall_confidence
    4. Decides whether to generate response or ask follow-up
    5. Generates follow-up question if needed
    
    Args:
        state: Current QueryState
        
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
        llm_structured_output = llm.with_structured_output(ConfidenceAssessment)

        msgs = [
            SystemMessage(content=PROMPTS["confidence_assessment_system_prompt"]),
            HumanMessage(content=f"Đánh giá confidence cho trường hợp sau:\n\n{context}")
        ]

        assessment = llm_structured_output.invoke(input=msgs)
        
        
        if not assessment:
            raise ValueError("LLM did not return structured output")
        
        # Update state
        state["overall_confidence"] = get_attr_safe(assessment,"overall_confidence")
        state["needs_followup"] = get_attr_safe(assessment,"needs_followup")
        state["confidence_reason"] = get_attr_safe(assessment,"confidence_reason")
        
        if get_attr_safe(assessment,"followup_question") != None:
            state["followup_question"] = get_attr_safe(assessment,"followup_question")
        
        # Log results
        print(f"[AGENT 2] Overall Confidence: {get_attr_safe(assessment,"overall_confidence"):.2f}")
        print(f"[AGENT 2] Needs Follow-up: {get_attr_safe(assessment,"needs_followup")}")
        print(f"[AGENT 2] Reason: {get_attr_safe(assessment,"confidence_reason")}")
        
        if get_attr_safe(assessment,"needs_followup"):
            print(f"[AGENT 2] Follow-up Question: {get_attr_safe(assessment,"followup_question")}")
        
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

def ask_followup(state: QueryState) -> QueryState:
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
