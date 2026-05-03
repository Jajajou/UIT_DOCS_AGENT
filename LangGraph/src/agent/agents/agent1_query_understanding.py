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
import re
import json as json_module
import unicodedata
from typing import Any, List, Dict
from openai import OpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from agent.states.query_state import (
    QueryState,
    QueryUnderstanding,
)

from langchain.chat_models import init_chat_model
from agent.core.prompts import PROMPTS
from agent.config import get_attr_safe, settings
from agent.utils import strip_think_tags


# ============================================================================
# Configuration
# ============================================================================

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.llm_model,
    streaming=False,
    temperature=settings.agent1_temperature,
    model_kwargs={"tool_choice": "none"}
)


# ============================================================================
# Helper Functions
# ============================================================================

def _remove_accents(text: str) -> str:
    """Strip Vietnamese diacritics, return ASCII-only lowercase string."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()


_HISTORICAL_PATTERNS_ASCII = [
    "trong thoi gian",
    "trong dich",
    "thoi dich",
    "khi do",
    "luc do",
    "truoc day",
    "hoi do",
    "ngay truoc",
    "nam do",
    "giai doan dich",
    "thoi ky dich",
]


def _is_historical_query(query: str) -> bool:
    """Return True if query asks about a past period (historical, pandemic era)."""
    q_ascii = _remove_accents(query)
    return any(pat in q_ascii for pat in _HISTORICAL_PATTERNS_ASCII)


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

def agent1_understand_query(state: QueryState) -> Dict[str, Any]:
    """
    Agent 1: Analyze user query and automatically tune retrieval parameters.
    
    This node:
    1. Extracts query from messages or state
    2. Calls LLM with structured output to analyze query
    3. Returns partial state update with parsed intention, entities, topics, confidence, etc.
    
    Args:
        state: Current QueryState
        
    Returns:
        Partial state update with Agent 1 outputs
    """
    
    # Extract query
    query = state.get("query")
    if not query:
        query = _last_human_text(state.get("messages", []))
    
    # Detect historical query (post-LLM, regex-based — no LLM prompt change)
    query_is_historical = False
    if query:
        query_is_historical = _is_historical_query(query)
        if query_is_historical:
            print(f"[AGENT 1] Historical query detected: {query[:60]}")

    if not query:
        return {
            "error": "No query provided",
            "status_message": "Error: No query",
            "query_is_historical": False
        }
    
    print("=" * 80)
    print(f"[AGENT 1] Analyzing query: {query}")
    print("=" * 80)
    
    try:
        # Call LLM directly, strip think tags, parse manually
        llm_json = llm.bind(response_format={"type": "json_object"})

        msgs = [
                SystemMessage(content=PROMPTS["query_understanding_system"]),
                HumanMessage(content=f"Phân tích câu hỏi sau:\n\n{query}")
                ]

        raw_response = llm_json.invoke(input=msgs)
        content = raw_response.content if hasattr(raw_response, "content") else str(raw_response)

        content = strip_think_tags(content)

        data = json_module.loads(content)
        understanding = QueryUnderstanding(**data)
        print(understanding)
        if not understanding:
            raise ValueError("LLM did not return structured output")
        
        # Extract values safely
        parsed_intention = get_attr_safe(understanding,"parsed_intention")
        extracted_entities = get_attr_safe(understanding,"extracted_entities")
        extracted_topics = get_attr_safe(understanding,"extracted_topics")
        query_confidence = get_attr_safe(understanding,"confidence")
        query_confidence_reason = get_attr_safe(understanding,"confidence_reason")
        query_cohort_year = get_attr_safe(understanding,"query_cohort_year")
        query_type = get_attr_safe(understanding,"query_type", "GENERAL")
        query_document_ref = get_attr_safe(understanding,"query_document_ref")

        # Retrieval parameters
        suggested_mode = get_attr_safe(understanding,"suggested_mode")
        suggested_top_k = get_attr_safe(understanding,"suggested_top_k")
        suggested_chunk_top_k = get_attr_safe(understanding,"suggested_chunk_top_k")
        tuning_reason = get_attr_safe(understanding,"tuning_reason")

        # Log results
        print(f"[AGENT 1] Parsed Intention: {parsed_intention}")
        print(f"[AGENT 1] Entities: {extracted_entities}")
        print(f"[AGENT 1] Topics: {extracted_topics}")
        print(f"[AGENT 1] Confidence: {query_confidence:.2f}")
        print(f"[AGENT 1] Reason: {query_confidence_reason}")
        print(f"[AGENT 1] Cohort Year: {query_cohort_year}")
        print(f"[AGENT 1] Query Type: {query_type}")
        print(f"[AGENT 1] Document Ref: {query_document_ref}")

        # Log parameter tuning
        print(f"[AGENT 1] Suggested Mode: {suggested_mode}")
        print(f"[AGENT 1] Suggested Top-K: {suggested_top_k}")
        print(f"[AGENT 1] Tuning Reason: {tuning_reason}")

        # Return partial update
        return {
            "query": query,
            "parsed_intention": parsed_intention,
            "extracted_entities": extracted_entities,
            "extracted_topics": extracted_topics,
            "query_confidence": query_confidence,
            "query_confidence_reason": query_confidence_reason,
            "query_cohort_year": query_cohort_year,
            "query_type": query_type,
            "query_document_ref": query_document_ref,
            "query_is_historical": query_is_historical,
            "retrieval_mode": suggested_mode,
            "top_k": suggested_top_k,
            "chunk_top_k": suggested_chunk_top_k,
            "tuning_reason": tuning_reason,
            "error": None,
            "logs": [f"Agent 1 analyzed query: {query}"]
        }
        
    except Exception as e:
        error_msg = f"{e}"
        print(f"[AGENT 1] ✗ {error_msg}")
        
        # Return error state and default values to allow graceful degradation
        return {
            "error": error_msg,
            "status_message": "Error in query understanding",
            "query": query,
            "query_confidence": 0.0,
            "query_is_historical": query_is_historical,
            "retrieval_mode": settings.retrieval.default_mode,
            "top_k": settings.retrieval.default_top_k,
            "chunk_top_k": settings.retrieval.default_chunk_top_k,
            "tuning_reason": "Error occurred, using default parameters",
            "logs": [f"Agent 1 error: {error_msg}"]
        }


# ============================================================================
# Decision Function
# ============================================================================

def decide_after_agent1(state: QueryState) -> str:
    """
    Decide next step after Agent 1.
    Always retrieves — clarification gating removed.
    Temporal reranking handles result quality downstream.
    """
    return "retrieve_data"


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "agent1_understand_query",
    "decide_after_agent1",
]
