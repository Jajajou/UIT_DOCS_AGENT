"""
Agent 1: Query Understanding with Automatic Parameter Tuning

This agent automatically tune retrieval parameters based on query type.

New capabilities:
1. Analyze query type (factual, exploratory, relationship-focused, etc.)
2. Suggest optimal retrieval mode (mix, hybrid, local, naive)
3. Suggest optimal top_k and chunk_top_k based on query complexity
4. Provide reasoning for parameter choices
"""

from __future__ import annotations

import os
from typing import Any, List
from openai import OpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from agent.query_state import (
    QueryState,
    QueryUnderstanding,
    QUERY_CONFIDENCE_THRESHOLD,
    DEFAULT_RETRIEVAL_MODE,
    DEFAULT_TOP_K,
    DEFAULT_CHUNK_TOP_K
)

from langchain.chat_models import init_chat_model
from agent.prompts import PROMPTS



# ============================================================================
# Configuration
# ============================================================================

llm = init_chat_model(
    model_provider="openai",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    model=os.getenv("LLM_MODEL"),
    temperature=float(os.getenv("AGENT1_TEMPERATURE", "0.1"))
)

# client = OpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     base_url=os.getenv("OPENAI_BASE_URL", "https://router.huggingface.co/v1")
# )

# LLM_MODEL = os.getenv("LLM_MODEL", "")
# LLM_TEMPERATURE = float(os.getenv("AGENT1_TEMPERATURE", "0.1"))


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

def agent1_understand_query(state: QueryState) -> QueryState:
    """
    Agent 1: Analyze user query and automatically tune retrieval parameters.
    
    This node:
    1. Extracts query from messages or state
    2. Calls LLM with structured output to analyze query
    3. Updates state with parsed intention, entities, topics, confidence
    4. Determines if clarification is needed
    5. Suggests optimal retrieval mode, top_k and chunk_top_k
    
    Args:
        state: Current QueryState
        
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
        # Call LLM with structured output
        llm_structured_output = llm.with_structured_output(QueryUnderstanding)

        msgs = [
                SystemMessage(content=PROMPTS["query_understanding_system"]),
                HumanMessage(content=f"Phân tích câu hỏi sau:\n\n{query}")
                ]

        completion = llm_structured_output.invoke(
            input=msgs
        )

        # Parse structured output
        understanding = completion
        
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
        
        # Update retrieval parameters
        state["retrieval_mode"] = understanding.suggested_mode
        state["top_k"] = understanding.suggested_top_k
        state["chunk_top_k"] = understanding.suggested_chunk_top_k
        state["tuning_reason"] = understanding.tuning_reason
        
        # Log results
        print(f"[AGENT 1] Parsed Intention: {understanding.parsed_intention}")
        print(f"[AGENT 1] Entities: {understanding.extracted_entities}")
        print(f"[AGENT 1] Topics: {understanding.extracted_topics}")
        print(f"[AGENT 1] Confidence: {understanding.confidence:.2f}")
        print(f"[AGENT 1] Reason: {understanding.confidence_reason}")
        print(f"[AGENT 1] Needs Clarification: {understanding.needs_clarification}")
        
        # Log parameter tuning
        print(f"[AGENT 1] Suggested Mode: {understanding.suggested_mode}")
        print(f"[AGENT 1] Suggested Top-K: {understanding.suggested_top_k}")
        print(f"[AGENT 1] Tuning Reason: {understanding.tuning_reason}")
        
        if understanding.needs_clarification:
            print(f"[AGENT 1] Clarification Question: {understanding.clarification_question}")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"{e}"
        print(f"[AGENT 1] ✗ {error_msg}")
        state["error"] = error_msg
        state["status_message"] = "Error in query understanding"
        
        # Set default values on error
        state["query_confidence"] = 0.0
        state["needs_clarification"] = True
        state["clarification_question"] = "Xin lỗi, tôi gặp lỗi khi phân tích câu hỏi. Bạn có thể diễn đạt lại câu hỏi được không?"
        
        # Set default retrieval params
        state["retrieval_mode"] = DEFAULT_RETRIEVAL_MODE
        state["top_k"] = DEFAULT_TOP_K
        state["chunk_top_k"] = DEFAULT_CHUNK_TOP_K
        state["tuning_reason"] = "Error occurred, using default parameters"
    
    return state


# ============================================================================
# Decision Function
# ============================================================================

def decide_after_agent1(state: QueryState) -> str:
    """
    Decide next step after Agent 1.
    
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

def ask_clarification(state: QueryState) -> QueryState:
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
    "agent1_understand_query",
    "decide_after_agent1",
    "ask_clarification"
]
