"""
LightRAG Core Integration for LangGraph
Replaces API calls with direct LightRAG core library usage
"""
from __future__ import annotations
import os
import asyncio
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import setup_logger
import logging

# Load environment variables
load_dotenv("LangGraph/.env")

# Setup logger
setup_logger("lightrag", level=os.getenv("LIGHTRAG_LOG_LEVEL", "INFO"))
logger = logging.getLogger("lightrag_core")


class LightRAGCore:
    """
    LightRAG Core wrapper for LangGraph integration.
    Provides async interface for document insertion and querying.
    """
    
    def __init__(
        self,
        working_dir: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_base: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_api_base: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        kv_storage: Optional[str] = None,
        vector_storage: Optional[str] = None,
        graph_storage: Optional[str] = None,
        doc_status_storage: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize LightRAG Core with configuration from environment or parameters.
        
        Args:
            working_dir: Directory for LightRAG storage
            llm_model: LLM model name
            llm_api_base: LLM API base URL
            llm_api_key: LLM API key
            embedding_model: Embedding model name
            embedding_api_base: Embedding API base URL
            embedding_dim: Embedding dimension
            kv_storage: KV storage backend class name
            vector_storage: Vector storage backend class name
            graph_storage: Graph storage backend class name
            doc_status_storage: Doc status storage backend class name
            **kwargs: Additional LightRAG parameters
        """
        self.working_dir = working_dir or os.getenv("RAG_DIR", "./rag_storage")
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.llm_api_base = llm_api_base or os.getenv("LLM_BINDING_HOST", "https://router.huggingface.co/v1")
        self.llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
        
        self.embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.embedding_api_base = embedding_api_base or os.getenv("EMBEDDING_BINDING_HOST", "http://localhost:11434")
        self.embedding_dim = embedding_dim or int(os.getenv("EMBEDDING_DIM", "1024"))
        
        # Storage backends
        self.kv_storage = kv_storage or os.getenv("LIGHTRAG_KV_STORAGE", "JsonKVStorage")
        self.vector_storage = vector_storage or os.getenv("LIGHTRAG_VECTOR_STORAGE", "NanoVectorDBStorage")
        self.graph_storage = graph_storage or os.getenv("LIGHTRAG_GRAPH_STORAGE", "NetworkXStorage")
        self.doc_status_storage = doc_status_storage or os.getenv("LIGHTRAG_DOC_STATUS_STORAGE", "JsonDocStatusStorage")
        
        self.rag: Optional[LightRAG] = None
        self.initialized = False
        
        # Additional parameters
        self.extra_kwargs = kwargs
        
        logger.info(f"LightRAG Core initialized with working_dir={self.working_dir}")
        logger.info(f"LLM: {self.llm_model} @ {self.llm_api_base}")
        logger.info(f"Embedding: {self.embedding_model} @ {self.embedding_api_base} (dim={self.embedding_dim})")
    
    async def initialize(self) -> None:
        """
        Initialize LightRAG instance and storage backends.
        Must be called before using insert or query methods.
        """
        if self.initialized:
            logger.warning("LightRAG Core already initialized")
            return
        
        try:
            # Create working directory if not exists
            os.makedirs(self.working_dir, exist_ok=True)
            
            # Create LLM function with custom config
            async def llm_model_func(
                prompt, system_prompt=None, history_messages=[], **kwargs
            ) -> str:
                return await openai_complete_if_cache(
                    model=self.llm_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    api_key=self.llm_api_key,
                    base_url=self.llm_api_base,
                    **kwargs
                )
            
            # Create embedding function with custom config
            async def embedding_func(texts: List[str]):
                return await openai_embed(
                    texts=texts,
                    model=self.embedding_model,
                    api_key=self.llm_api_key,  # Some embedding APIs use same key
                    base_url=self.embedding_api_base,
                )
            
            # Initialize LightRAG with custom prompts
            from agent.prompt import PROMPTS
            
            self.rag = LightRAG(
                working_dir=self.working_dir,
                llm_model_func=llm_model_func,
                embedding_func=embedding_func,
                kv_storage=self.kv_storage,
                vector_storage=self.vector_storage,
                graph_storage=self.graph_storage,
                doc_status_storage=self.doc_status_storage,
                addon_params={
                    "language": os.getenv("SUMMARY_LANGUAGE", "Vietnamese"),
                    "entity_types": [
                        "organization", "person", "regulation", "procedure", 
                        "scholarship", "system", "location", "event", "document", "other"
                    ]
                },
                # Use custom prompts
                **self.extra_kwargs
            )
            
            # Override prompts with custom university-focused prompts
            self.rag.prompts = PROMPTS
            
            # Initialize storage backends
            await self.rag.initialize_storages()
            
            # Initialize pipeline status
            await initialize_pipeline_status()
            
            self.initialized = True
            logger.info("LightRAG Core successfully initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize LightRAG Core: {e}")
            raise
    
    async def insert_text(
        self, 
        text: str, 
        file_source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Insert text into LightRAG knowledge base.
        
        Args:
            text: Text content to insert
            file_source: Optional source file name
            
        Returns:
            Dict with status and message
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            await self.rag.ainsert(text)
            logger.info(f"Successfully inserted text from {file_source or 'unknown source'}")
            return {
                "status": "success",
                "message": f"Text inserted successfully",
                "source": file_source
            }
        except Exception as e:
            logger.error(f"Failed to insert text: {e}")
            return {
                "status": "error",
                "message": str(e),
                "source": file_source
            }
    
    async def insert_texts(
        self,
        texts: List[str],
        file_sources: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Insert multiple texts into LightRAG knowledge base.
        
        Args:
            texts: List of text contents to insert
            file_sources: Optional list of source file names
            
        Returns:
            Dict with status and results
        """
        if not self.initialized:
            await self.initialize()
        
        results = []
        for i, text in enumerate(texts):
            source = file_sources[i] if file_sources and i < len(file_sources) else None
            result = await self.insert_text(text, source)
            results.append(result)
        
        success_count = sum(1 for r in results if r["status"] == "success")
        
        return {
            "status": "success" if success_count == len(texts) else "partial",
            "message": f"Inserted {success_count}/{len(texts)} texts successfully",
            "results": results
        }
    
    async def query(
        self,
        query_text: str,
        mode: str = "mix",
        include_references: bool = False,
        response_type: str = "Multiple Paragraphs",
        top_k: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        max_total_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Query LightRAG knowledge base.
        
        Args:
            query_text: Query text
            mode: Query mode (local, global, hybrid, naive, mix)
            include_references: Whether to include references
            response_type: Response format type
            top_k: Number of top results to retrieve
            conversation_history: Previous conversation messages
            max_total_tokens: Maximum tokens for context
            stream: Whether to stream response (not supported in core mode)
            
        Returns:
            Dict with response and optional references
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            # Create query parameters
            param = QueryParam(
                mode=mode,
                only_need_context=False,
                response_type=response_type,
                top_k=top_k if top_k else 60,
            )
            
            # Execute query
            response = await self.rag.aquery(query_text, param=param)
            
            logger.info(f"Successfully queried: {query_text[:50]}...")
            
            return {
                "response": response,
                "mode": mode,
                "include_references": include_references,
            }
            
        except Exception as e:
            logger.error(f"Failed to query: {e}")
            return {
                "error": str(e),
                "response": "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."
            }
    
    async def finalize(self) -> None:
        """
        Finalize LightRAG instance and close storage connections.
        Should be called when shutting down.
        """
        if self.rag and self.initialized:
            try:
                await self.rag.finalize_storages()
                self.initialized = False
                logger.info("LightRAG Core finalized")
            except Exception as e:
                logger.error(f"Error finalizing LightRAG Core: {e}")


# Singleton instance for reuse across LangGraph nodes
_lightrag_core_instance: Optional[LightRAGCore] = None


def get_lightrag_core() -> LightRAGCore:
    """
    Get or create singleton LightRAG Core instance.
    
    Returns:
        LightRAGCore instance
    """
    global _lightrag_core_instance
    
    if _lightrag_core_instance is None:
        _lightrag_core_instance = LightRAGCore()
    
    return _lightrag_core_instance


async def initialize_lightrag_core() -> LightRAGCore:
    """
    Initialize and return LightRAG Core instance.
    
    Returns:
        Initialized LightRAGCore instance
    """
    core = get_lightrag_core()
    await core.initialize()
    return core
