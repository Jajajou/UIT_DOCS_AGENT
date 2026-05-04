import pytest
from datetime import datetime, timedelta
from agent.clients.reranker import Reranker

@pytest.fixture
def reranker():
    return Reranker()

def test_calculate_temporal_score_current(reranker):
    """Test scoring for a current valid document."""
    today = datetime.now().strftime("%Y-%m-%d")
    item = {
        "metadata": {
            "valid_from": "2020-01-01",
            "valid_until": "2030-12-31",
            "indexed_at": today
        }
    }
    score = reranker.calculate_temporal_score(item)
    assert score >= 0.9

def test_calculate_temporal_score_expired(reranker):
    """Test scoring for an expired document."""
    item = {
        "metadata": {
            "valid_until": "2020-01-01"
        }
    }
    # Should be heavily penalized (0.1)
    score = reranker.calculate_temporal_score(item)
    assert score <= 0.5

def test_calculate_temporal_score_archived(reranker):
    """Test scoring for an archived document."""
    item = {
        "metadata": {
            "is_archived": True
        }
    }
    score = reranker.calculate_temporal_score(item)
    assert score == 0.0

def test_cohort_match_score(reranker):
    """Test cohort match logic."""
    # Match explicit year
    item = {"metadata": {"cohort_years": [2024, 2025]}}
    assert reranker._compute_cohort_score(item, 2024) == 1.0
    
    # Match universal
    item_universal = {"metadata": {"cohort_years": ["*"]}}
    assert reranker._compute_cohort_score(item_universal, 2024) == 1.0
    
    # Neutral on mismatch
    assert reranker._compute_cohort_score(item, 2023) == 0.5

@pytest.mark.asyncio
async def test_vbhn_and_article_extraction():
    """Test VBHN and article-level extraction logic."""
    from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
    from agent.config import settings
    
    agent = TemporalExtractionAgent(None, settings)
    content = "Văn bản hợp nhất: Quy định về học vụ. Sửa đổi Điều 5 và Điều 12 của Quyết định số 123/QĐ-ĐHCNTT."
    
    metadata = agent.extract_with_local_tools(content)
    
    assert metadata.is_vbhn is True
    assert "Điều 5" in metadata.amended_articles
    assert "Điều 12" in metadata.amended_articles
    assert "123/QĐ-ĐHCNTT" in metadata.amends_documents
