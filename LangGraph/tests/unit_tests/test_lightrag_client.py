"""Unit tests for LightRAG API client authentication."""
import pytest
from unittest.mock import Mock, patch
from agent.clients.lightrag_client import LightRAGAPIClient


class TestLightRAGClientAuth:
    """Test authentication header generation."""

    def test_headers_with_api_key(self):
        """API key should use Authorization Bearer header."""
        client = LightRAGAPIClient(
            base_url="http://localhost:9622",
            api_key="test_api_key_123"
        )
        headers = client._headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_api_key_123"
        assert "X-API-Key" not in headers

    @patch.dict("os.environ", {"LIGHTRAG_API_KEY": "", "LIGHTRAG_ACCESS_TOKEN": ""}, clear=True)
    def test_headers_with_access_token(self):
        """Access token should use Authorization Bearer header."""
        client = LightRAGAPIClient(
            base_url="http://localhost:9622",
            access_token="test_token_456"
        )
        headers = client._headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_token_456"

    def test_headers_api_key_precedence(self):
        """API key takes precedence over access token."""
        client = LightRAGAPIClient(
            base_url="http://localhost:9622",
            api_key="api_key_123",
            access_token="token_456"
        )
        headers = client._headers()

        assert headers["Authorization"] == "Bearer api_key_123"

    @patch.dict("os.environ", {"LIGHTRAG_API_KEY": "", "LIGHTRAG_ACCESS_TOKEN": ""}, clear=True)
    def test_headers_without_auth(self):
        """Headers should work without authentication."""
        client = LightRAGAPIClient(base_url="http://localhost:9622")
        headers = client._headers()

        assert "Authorization" not in headers
        assert "Accept" in headers

    def test_headers_with_extra(self):
        """Extra headers should be merged."""
        client = LightRAGAPIClient(
            base_url="http://localhost:9622",
            api_key="test_key"
        )
        headers = client._headers(extra={"X-Custom": "value"})

        assert headers["Authorization"] == "Bearer test_key"
        assert headers["X-Custom"] == "value"

    @patch.dict("os.environ", {"LIGHTRAG_API_KEY": "env_api_key"})
    def test_api_key_from_env(self):
        """API key should load from environment variable."""
        client = LightRAGAPIClient(base_url="http://localhost:9622")
        headers = client._headers()

        assert headers["Authorization"] == "Bearer env_api_key"


class TestLightRAGClientInit:
    """Test client initialization."""

    def test_init_with_base_url(self):
        """Client should initialize with base URL."""
        client = LightRAGAPIClient(base_url="http://localhost:9622")
        assert client.base_url == "http://localhost:9622"

    def test_init_strips_trailing_slash(self):
        """Base URL should strip trailing slash."""
        client = LightRAGAPIClient(base_url="http://localhost:9622/")
        assert client.base_url == "http://localhost:9622"

    @patch.dict("os.environ", {"LIGHTRAG_URL": "", "LIGHTRAG_API_KEY": ""}, clear=True)
    def test_init_requires_base_url(self):
        """Client should raise error without base URL."""
        with pytest.raises(ValueError, match="Base URL is required"):
            LightRAGAPIClient()

    @patch.dict("os.environ", {"LIGHTRAG_URL": "http://env:9622"})
    def test_init_base_url_from_env(self):
        """Base URL should load from environment variable."""
        client = LightRAGAPIClient()
        assert client.base_url == "http://env:9622"
