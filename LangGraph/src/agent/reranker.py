"""
Reranker Module for Vietnamese Text Ranking

This module provides reranking functionality using Vietnamese-optimized cross-encoder models.
It scores and re-ranks retrieved entities, relationships, and chunks based on relevance to the query.
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from dataclasses import dataclass


@dataclass
class RerankConfig:
    """Configuration for reranker."""
    model_name: str = "namdp-ptit/ViRanker"
    use_fp16: bool = True
    batch_size: int = 32
    normalize_scores: bool = True
    max_length: int = 512


class Reranker:
    """
    Vietnamese text reranker using cross-encoder models.
    
    Supports:
    - namdp-ptit/ViRanker (default, best performance)
    - thanhtantran/Vietnamese_Reranker (for longer documents)
    """
    
    def __init__(self, config: Optional[RerankConfig] = None):
        """
        Initialize reranker with configuration.
        
        Args:
            config: RerankConfig object. If None, uses default config from env vars.
        """
        if config is None:
            config = RerankConfig(
                model_name=os.getenv("RERANKER_MODEL", "namdp-ptit/ViRanker"),
                use_fp16=os.getenv("RERANKER_USE_FP16", "True").lower() == "true",
                batch_size=int(os.getenv("RERANKER_BATCH_SIZE", "32")),
                normalize_scores=True,
                max_length=512
            )
        
        self.config = config
        self._model = None
        self._load_model()
    
    def _load_model(self):
        """Load reranker model using FlagEmbedding."""
        try:
            from FlagEmbedding import FlagReranker
            
            print(f"[RERANKER] Loading model: {self.config.model_name}")
            self._model = FlagReranker(
                self.config.model_name,
                use_fp16=self.config.use_fp16
            )
            print(f"[RERANKER] ✓ Model loaded successfully")
            
        except ImportError:
            raise ImportError(
                "FlagEmbedding is required for reranker. "
                "Install it with: pip install FlagEmbedding"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load reranker model: {str(e)}")
    
    def compute_scores(
        self,
        query: str,
        texts: List[str],
        batch_size: Optional[int] = None
    ) -> List[float]:
        """
        Compute relevance scores for a list of texts given a query.
        
        Args:
            query: The query text
            texts: List of texts to score
            batch_size: Batch size for processing. If None, uses config.batch_size
            
        Returns:
            List of scores (0.0-1.0 if normalized, raw scores otherwise)
        """
        if not texts:
            return []
        
        if self._model is None:
            raise RuntimeError("Reranker model not loaded")
        
        # Prepare pairs
        pairs = [[query, text] for text in texts]
        
        # Compute scores
        batch_size = batch_size or self.config.batch_size
        scores = self._model.compute_score(
            pairs,
            batch_size=batch_size,
            normalize=self.config.normalize_scores
        )
        
        # Ensure scores is a list
        if isinstance(scores, (int, float)):
            scores = [scores]
        elif hasattr(scores, 'tolist'):
            scores = scores.tolist()
        
        return scores
    
    def rerank_items(
        self,
        query: str,
        items: List[Dict[str, Any]],
        text_field: str = "content",
        top_k: Optional[int] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Rerank a list of items (entities, relationships, or chunks).
        
        Args:
            query: The query text
            items: List of items to rerank (each item is a dict)
            text_field: Field name containing the text to score
            top_k: Return only top K items. If None, returns all items.
            
        Returns:
            List of (item, score) tuples, sorted by score (highest first)
        """
        if not items:
            return []
        
        # Extract texts
        texts = []
        for item in items:
            text = item.get(text_field, "")
            if not text:
                # Try alternative fields
                text = item.get("name", "") or item.get("description", "") or str(item)
            texts.append(str(text))
        
        # Compute scores
        scores = self.compute_scores(query, texts)
        
        # Zip items with scores
        items_with_scores = list(zip(items, scores))
        
        # Sort by score (descending)
        items_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top K if specified
        if top_k is not None:
            items_with_scores = items_with_scores[:top_k]
        
        return items_with_scores
    
    def calculate_aggregate_confidence(
        self,
        scores: List[float],
        top_n: int = 5
    ) -> float:
        """
        Calculate aggregate confidence score from a list of scores.
        
        Formula:
        - 60% weight on max score (best match)
        - 30% weight on mean of top-N scores (overall quality)
        - 10% weight on consistency (1 - std of top-N)
        
        Args:
            scores: List of relevance scores
            top_n: Number of top scores to consider
            
        Returns:
            Aggregate confidence score (0.0-1.0)
        """
        if not scores:
            return 0.0
        
        # Get top N scores
        top_scores = sorted(scores, reverse=True)[:min(top_n, len(scores))]
        
        if not top_scores:
            return 0.0
        
        # Calculate components
        max_score = max(top_scores)
        mean_score = np.mean(top_scores)
        
        # Calculate consistency (lower std = higher consistency)
        if len(top_scores) > 1:
            std_score = np.std(top_scores)
            # Normalize std to [0,1] range (assume max std is 0.5)
            consistency = max(0.0, 1.0 - (std_score / 0.5))
        else:
            consistency = 1.0  # Perfect consistency for single score
        
        # Weighted combination
        aggregate = (
            0.6 * max_score +
            0.3 * mean_score +
            0.1 * consistency
        )
        
        # Ensure in [0,1] range
        return max(0.0, min(1.0, aggregate))


class MultiSourceReranker:
    """
    Reranker for multiple sources (entities, relationships, chunks).
    
    This class handles reranking of all retrieved data sources and
    calculates an overall confidence score.
    """
    
    def __init__(self, reranker: Optional[Reranker] = None):
        """
        Initialize multi-source reranker.
        
        Args:
            reranker: Reranker instance. If None, creates a new one.
        """
        self.reranker = reranker or Reranker()
    
    def rerank_all(
        self,
        query: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
        top_k_entities: Optional[int] = None,
        top_k_relationships: Optional[int] = None,
        top_k_chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Rerank all sources and calculate overall confidence.
        
        Args:
            query: The query text
            entities: List of entity dicts
            relationships: List of relationship dicts
            chunks: List of chunk dicts
            top_k_entities: Keep top K entities
            top_k_relationships: Keep top K relationships
            top_k_chunks: Keep top K chunks
            
        Returns:
            Dict containing:
            - reranked_entities: List of (entity, score) tuples
            - reranked_relationships: List of (relationship, score) tuples
            - reranked_chunks: List of (chunk, score) tuples
            - entity_scores: List of entity scores
            - relationship_scores: List of relationship scores
            - chunk_scores: List of chunk scores
            - overall_confidence: Aggregate confidence score
            - metadata: Reranking metadata
        """
        print("=" * 80)
        print(f"[RERANKER] Reranking all sources for query: {query[:100]}...")
        print("=" * 80)
        
        # Rerank entities
        reranked_entities = self.reranker.rerank_items(
            query, entities, text_field="name", top_k=top_k_entities
        )
        entity_scores = [score for _, score in reranked_entities]
        
        print(f"[RERANKER] ✓ Reranked {len(reranked_entities)} entities")
        if entity_scores:
            print(f"[RERANKER]   Top entity score: {max(entity_scores):.4f}")
        
        # Rerank relationships
        reranked_relationships = self.reranker.rerank_items(
            query, relationships, text_field="description", top_k=top_k_relationships
        )
        relationship_scores = [score for _, score in reranked_relationships]
        
        print(f"[RERANKER] ✓ Reranked {len(reranked_relationships)} relationships")
        if relationship_scores:
            print(f"[RERANKER]   Top relationship score: {max(relationship_scores):.4f}")
        
        # Rerank chunks
        reranked_chunks = self.reranker.rerank_items(
            query, chunks, text_field="content", top_k=top_k_chunks
        )
        chunk_scores = [score for _, score in reranked_chunks]
        
        print(f"[RERANKER] ✓ Reranked {len(reranked_chunks)} chunks")
        if chunk_scores:
            print(f"[RERANKER]   Top chunk score: {max(chunk_scores):.4f}")
        
        # Calculate overall confidence
        all_scores = entity_scores + relationship_scores + chunk_scores
        overall_confidence = self.reranker.calculate_aggregate_confidence(all_scores)
        
        print(f"[RERANKER] ✓ Overall confidence: {overall_confidence:.4f}")
        print("=" * 80)
        
        return {
            "reranked_entities": reranked_entities,
            "reranked_relationships": reranked_relationships,
            "reranked_chunks": reranked_chunks,
            "entity_scores": entity_scores,
            "relationship_scores": relationship_scores,
            "chunk_scores": chunk_scores,
            "overall_confidence": overall_confidence,
            "metadata": {
                "total_items_reranked": len(all_scores),
                "entity_count": len(reranked_entities),
                "relationship_count": len(reranked_relationships),
                "chunk_count": len(reranked_chunks),
                "model_name": self.reranker.config.model_name
            }
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def create_reranker(model_name: Optional[str] = None) -> Reranker:
    """
    Create a reranker instance with optional model name.
    
    Args:
        model_name: Model name to use. If None, uses env var or default.
        
    Returns:
        Reranker instance
    """
    config = RerankConfig()
    if model_name:
        config.model_name = model_name
    return Reranker(config)


def create_multi_source_reranker(model_name: Optional[str] = None) -> MultiSourceReranker:
    """
    Create a multi-source reranker instance.
    
    Args:
        model_name: Model name to use. If None, uses env var or default.
        
    Returns:
        MultiSourceReranker instance
    """
    reranker = create_reranker(model_name)
    return MultiSourceReranker(reranker)


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "Reranker",
    "MultiSourceReranker",
    "RerankConfig",
    "create_reranker",
    "create_multi_source_reranker"
]
