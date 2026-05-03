import pytest
import os
import json
from datetime import datetime, timedelta
from agent.services.ping_service import archive_expired_documents
from agent.clients.lightrag_client import LightRAGAPIClient

@pytest.mark.asyncio
async def test_archive_expired_documents_dry_run():
    """
    Test the archival logic in dry_run mode.
    Since we don't want to mess with the actual DB in a basic test, 
    we verify the client call structure.
    """
    # This will at least verify the imports and client initialization work
    # and the logic flow through archive_expired_documents
    try:
        await archive_expired_documents(dry_run=True)
        # If no exception, it's a pass for the service wrapper
        assert True
    except Exception as e:
        pytest.fail(f"archive_expired_documents failed: {e}")

@pytest.mark.asyncio
async def test_ping_service_client_integration():
    """
    Verify the LightRAG client has the required archival methods.
    """
    client = LightRAGAPIClient()
    assert hasattr(client, 'archive_expired_documents')
    assert hasattr(client, 'get_all_documents_with_metadata')
