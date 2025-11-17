"""
Agent 3: Response Generation using Reranked Data

This agent generates the final response using high-quality reranked data.
It creates a comprehensive answer with hyperlinked references.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from agent.core.prompts import PROMPTS
from agent.states.query_state import (
    QueryState,
    ResponseGeneration,
    Reference,
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
    streaming=False,
    temperature=settings.agent3_temperature,
    model_kwargs={"tool_choice": "none"}
)


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

def agent3_generate_response(state: QueryState) -> QueryState:
    """
    Agent 3: Generate response using reranked data.
    
    This node:
    1. Formats reranked data for LLM
    2. Calls LLM to generate response
    3. Extracts references from reranked chunks
    4. Updates state with final answer
    5. Adds AI message to chat
    
    Args:
        state: Current QueryState
        
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
    if overall_confidence < settings.query_thresholds.fallback_confidence_threshold:
        print(f"[AGENT 3] Low confidence ({overall_confidence:.2f}), using fallback response")
        
        topic = state.get("extracted_topics", ["câu hỏi của bạn"])[0] if state.get("extracted_topics") else "câu hỏi của bạn"
        fallback_text = PROMPTS["fallback_response_template"].format(
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
        prompt_text = PROMPTS["response_generation_prompt"].format(
            parsed_intention=parsed_intention,
            reranked_data_formatted=reranked_data_formatted,
            overall_confidence=overall_confidence,
            confidence_reason=confidence_reason
        )
        
        # Call LLM with structured output
        llm_json = llm.bind(response_format={"type": "json_object"})
        llm_structured_output = llm_json.with_structured_output( #type: ignore
            ResponseGeneration,          
            method="json_schema",       
            include_raw=False             
        ) 

        msgs = [
            SystemMessage(content=prompt_text),
            HumanMessage(content=f"{parsed_intention}\n\nGenerate response cho query trên.")
        ]
        print(f"GOI LLM: {prompt_text}")
        response_gen = llm_structured_output.invoke(input=prompt_text)
        
        if not response_gen:
            raise ValueError("LLM did not return structured output")
        
        # Update state
        state["generated_response"] = get_attr_safe(response_gen,"response_text")
        state["response_type"] = get_attr_safe(response_gen,"response_type")
        
        # Convert Pydantic references to dicts
        references_list = [ref.model_dump() for ref in get_attr_safe(response_gen,"references")]
        state["references"] = references_list
        
        # Set final answer
        final_answer = get_attr_safe(response_gen,"response_text")
        
        # Add partial answer suffix if needed
        if get_attr_safe(response_gen,"response_type") == "partial_answer":
            final_answer += PROMPTS["partial_answer_suffix"]
        
        state["final_answer"] = final_answer
        
        # Add to messages
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=final_answer))
        state["messages"] = msgs
        
        # Log results
        print(f"[AGENT 3] ✓ Response generated")
        print(f"[AGENT 3] Response type: {get_attr_safe(response_gen,"response_type")}")
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
