import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from unittest.mock import MagicMock, patch

from agent.graphs.metadata_rag_subgraph import create_metadata_rag_subgraph
from agent.graphs.indexing_graph import review_temporal_tags_node, decide_after_hitl
from agent.states.metadata_rag_state import MetadataRAGState
from agent.states.indexing_state import IndexingState


@pytest.fixture
def mock_subgraph():
    checkpointer = MemorySaver()
    return create_metadata_rag_subgraph().compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Subgraph: linear extraction (no interrupt inside)
# ---------------------------------------------------------------------------

@patch("agent.agents.metadata_rag_nodes.llm")
@patch("agent.agents.metadata_rag_nodes.get_embeddings_from_vllm")
@patch("agent.agents.metadata_rag_nodes.compute_rerank_scores_http")
def test_subgraph_linear_extraction(mock_rerank, mock_embed, mock_llm, mock_subgraph):
    """Subgraph runs to END with no interrupt, outputs document_metadata."""
    mock_llm.invoke.return_value.content = '{"valid_from": "2024-09-01", "valid_until": null, "cohort_years": [2024]}'
    mock_embed.return_value = [[0.1] * 768]
    mock_rerank.return_value = [0.9]

    initial_state = {
        "doc_text": "Sample decision content",
        "file_source": "test.pdf",
        "doc_id": "doc_1",
        "success": False,
    }
    config = {"configurable": {"thread_id": "test_linear"}}

    result = mock_subgraph.invoke(initial_state, config)

    assert "__interrupt__" not in result
    assert result.get("temporal_extraction_complete") is True
    assert result.get("success") is True
    assert isinstance(result.get("document_metadata"), dict)


# ---------------------------------------------------------------------------
# Parent-level HITL: review_temporal_tags_node
# ---------------------------------------------------------------------------

@patch("agent.graphs.indexing_graph.interrupt")
def test_parent_hitl_approve(mock_interrupt):
    """Approved decision updates document_metadata and sets review_status."""
    mock_interrupt.return_value = {"action": "approved", "document_number": "108/QD-DHCNTT"}

    state: IndexingState = {
        "messages": [],
        "upload_results": [],
        "document_metadata": {"document_number": None, "cohort_years": []},
        "temporal_extraction_complete": True,
        "loop_count": 0,
        "human_feedback": None,
        "review_status": "pending",
    }

    result = review_temporal_tags_node(state)
    updates = result.update

    assert updates["review_status"] == "approved"
    assert updates["document_metadata"]["document_number"] == "108/QD-DHCNTT"
    assert updates["loop_count"] == 1


@patch("agent.graphs.indexing_graph.interrupt")
def test_parent_hitl_reject_routes_retry(mock_interrupt):
    """Rejected with loop_count=0 routes to retry."""
    mock_interrupt.return_value = {"action": "rejected", "feedback": "Wrong cohort years"}

    state: IndexingState = {
        "messages": [],
        "upload_results": [],
        "document_metadata": {"cohort_years": []},
        "temporal_extraction_complete": True,
        "loop_count": 0,
        "human_feedback": None,
        "review_status": "pending",
    }

    result = review_temporal_tags_node(state)
    updates = result.update
    assert updates["review_status"] == "rejected"
    assert updates["human_feedback"] == "Wrong cohort years"

    # Simulate state after update
    updated_state = {**state, **updates}
    assert decide_after_hitl(updated_state) == "retry"


@patch("agent.graphs.indexing_graph.interrupt")
def test_parent_hitl_reject_max_retries_routes_upload(mock_interrupt):
    """Rejected with loop_count=2 (max) routes to upload."""
    mock_interrupt.return_value = {"action": "rejected", "feedback": "Still wrong"}

    state: IndexingState = {
        "messages": [],
        "upload_results": [],
        "document_metadata": {},
        "temporal_extraction_complete": True,
        "loop_count": 2,
        "human_feedback": None,
        "review_status": "pending",
    }

    result = review_temporal_tags_node(state)
    updates = result.update
    updated_state = {**state, **updates}
    assert decide_after_hitl(updated_state) == "upload"
