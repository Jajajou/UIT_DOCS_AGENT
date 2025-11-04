"""
LightRAG LangGraph package

Exports:
- build_indexing_app: compile the indexing graph
- build_query_app: compile the query graph
- LightRAGAPIClient: HTTP client supporting X-API-Key and OAuth2 password
- IndexingState, QueryState: typed state schemas
"""

from .indexing_graph import graph as build_indexing_app
from .query_graph import graph as build_query_app
from .lightrag_client import LightRAGAPIClient
from .state import IndexingState, QueryState
from .utils import get_url

__all__ = ["build_indexing_app", "build_query_app", "get_url", "predict"]

__version__ = "0.1.0"
