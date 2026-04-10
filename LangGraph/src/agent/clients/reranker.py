"""
Reranker Module for Vietnamese Text Ranking

This module provides reranking functionality using Vietnamese-optimized cross-encoder models.
It scores and re-ranks retrieved entities, relationships, and chunks based on relevance to the query.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from agent.config import settings


class Reranker:
    """
    Vietnamese text reranker using cross-encoder models.
    
    Supports:
    - namdp-ptit/ViRanker (default, best performance)
    - thanhtantran/Vietnamese_Reranker (for longer documents)
    """
    
    def __init__(self):
        """
        Initialize reranker with configuration from settings.
        """
        self.config = settings.reranker
        self._model = None
        self._load_model()
    
    def _load_model(self):
        """Load reranker model. If reranker_base_url is configured, skip local model load."""
        if settings.reranker_base_url:
            print(f"[RERANKER] HTTP mode: using {settings.reranker_base_url}")
            return
        try:
            from FlagEmbedding import FlagReranker

            print(f"[RERANKER] Loading model: {self.config.default_model}")
            self._model = FlagReranker(
                self.config.default_model,
                use_fp16=self.config.use_fp16
            )
            print(f"[RERANKER] Model loaded successfully")

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
    ) -> List[float]: #type: ignore
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
            raise RuntimeError("Texts empty")

        if settings.reranker_base_url:
            import requests
            url = f"{settings.reranker_base_url}/v1/score"
            payload = {
                "model": self.config.default_model,
                "text_1": query,
                "text_2": texts
            }
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return [item["score"] for item in data["data"]]

        if self._model is None:
            raise RuntimeError("Reranker model not loaded")

        # Prepare pairs
        pairs = [(query, text) for text in texts]

        # Compute scores
        batch_size = batch_size or self.config.batch_size
        scores = self._model.compute_score(
            pairs,
            batch_size=batch_size,
            normalize=self.config.normalize_scores
        )

        return scores #type: ignore
    
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

        print(texts)
        
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
        top_n: int = settings.reranker.top_n_for_confidence
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
        return max(0.0, min(1.0, aggregate)) #type: ignore

    def calculate_temporal_score(
        self,
        item: Dict[str, Any],
        current_date: Optional[str] = None
    ) -> float:
        """
        Calculate temporal relevance score for an item based on its metadata.

        Research shows simple recency prior achieves 1.00 accuracy on freshness tasks.

        Args:
            item: Item dict (entity, relationship, or chunk)
            current_date: ISO date string for comparison. Defaults to today.

        Returns:
            Temporal score (0.0-1.0)
            - 1.0: Current and valid
            - 0.5-1.0: Valid but older
            - 0.0-0.5: Expired or very old
        """
        if current_date is None:
            current = datetime.now()
        else:
            current = datetime.fromisoformat(current_date)

        # Extract temporal metadata
        metadata = item.get("metadata", {})

        # Check if archived
        if metadata.get("is_archived", False):
            return 0.0  # Archived documents get zero temporal score

        # Get validity dates
        valid_from = metadata.get("valid_from")
        valid_until = metadata.get("valid_until")
        indexed_at = metadata.get("indexed_at")

        # If no temporal info, assume always valid but not prioritized
        if not valid_from and not valid_until and not indexed_at:
            return 0.5  # Neutral score

        # Check if currently valid
        is_valid = True
        if valid_from:
            try:
                from_date = datetime.fromisoformat(valid_from)
                if current < from_date:
                    is_valid = False  # Not yet valid
            except (ValueError, TypeError):
                pass

        if valid_until:
            try:
                until_date = datetime.fromisoformat(valid_until)
                if current > until_date:
                    # Expired document
                    days_expired = (current - until_date).days
                    if days_expired > 365:
                        return 0.1  # Very old, heavily penalized
                    else:
                        # Gradual decay: 0.5 at expiry, 0.1 at 1 year
                        return max(0.1, 0.5 - (days_expired / 365) * 0.4)
            except (ValueError, TypeError):
                pass

        # If not valid yet
        if not is_valid:
            return 0.3  # Not yet valid

        # Document is currently valid - score based on recency
        if indexed_at:
            try:
                index_date = datetime.fromisoformat(indexed_at)
                days_old = (current - index_date).days

                # Recency scoring with diminishing returns
                # 1.0 for today, 0.9 for 30 days, 0.7 for 365 days, 0.5 for 2+ years
                if days_old <= 30:
                    return 1.0
                elif days_old <= 365:
                    return 0.9 - (days_old - 30) / 365 * 0.2  # Linear decay to 0.7
                elif days_old <= 730:
                    return 0.7 - (days_old - 365) / 365 * 0.2  # Decay to 0.5
                else:
                    return max(0.5, 0.7 - (days_old - 365) / 365 * 0.2)  # Floor at 0.5

            except (ValueError, TypeError):
                pass

        # Default: valid but no recency info
        return 0.8

    def _compute_cohort_score(self, item: Dict[str, Any], query_cohort_year: Optional[int]) -> float:
        """
        Compute cohort match score for an item.

        Returns:
            1.0 if item's cohort_years contains query_cohort_year
            0.0 if item has cohort_years and query_cohort_year is not in it
            0.5 (neutral) if no cohort in query, no metadata, or empty cohort_years list
        """
        if query_cohort_year is None:
            return 0.5  # neutral — no cohort specified in query
        cohort_years = item.get("metadata", {}).get("cohort_years", None)
        if not cohort_years:
            return 0.5  # neutral — no cohort metadata or empty list
        return 1.0 if query_cohort_year in cohort_years else 0.0

    def rerank_with_temporal_boost(
        self,
        query: str,
        items: List[Dict[str, Any]],
        text_field: str = "content",
        top_k: Optional[int] = None,
        temporal_weight: Optional[float] = None,
        current_date: Optional[str] = None,
        query_cohort_year: Optional[int] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Rerank items with temporal boosting.

        Combines semantic relevance with temporal relevance using weighted scoring.

        Args:
            query: The query text
            items: List of items to rerank
            text_field: Field containing text to score
            top_k: Return only top K items
            temporal_weight: Weight for temporal score (0.0-1.0).
                           If None, uses config.temporal.recency_weight
            current_date: ISO date for temporal comparison. Defaults to today.

        Returns:
            List of (item, combined_score) tuples, sorted by score (highest first)
        """
        if not items:
            return []

        # Extract texts for semantic scoring
        texts = []
        for item in items:
            text = item.get(text_field, "")
            if not text:
                text = item.get("name", "") or item.get("description", "") or str(item)
            texts.append(str(text))

        # Compute semantic scores
        semantic_scores = self.compute_scores(query, texts)

        # Compute temporal scores
        temporal_scores = [
            self.calculate_temporal_score(item, current_date)
            for item in items
        ]

        # Combine scores: 3-weight formula when cohort active, 2-weight otherwise
        use_cohort = getattr(settings, 'use_cohort_boost', True)
        if use_cohort and query_cohort_year is not None:
            temporal_config = getattr(settings, 'temporal', None)
            s_w = getattr(temporal_config, 'semantic_weight_cohort', 0.55)
            t_w = getattr(temporal_config, 'temporal_weight_cohort', 0.20)
            c_w = getattr(temporal_config, 'cohort_weight', 0.25)
            cohort_scores = [self._compute_cohort_score(item, query_cohort_year) for item in items]
            combined_scores = [
                s_w * s + t_w * t + c_w * c
                for s, t, c in zip(semantic_scores, temporal_scores, cohort_scores)
            ]
        else:
            # Original 2-weight formula
            if temporal_weight is None:
                temporal_config = getattr(settings, 'temporal', None)
                if temporal_config:
                    temporal_weight = getattr(temporal_config, 'recency_weight', 0.3)
                else:
                    temporal_weight = 0.3
            semantic_weight = 1.0 - temporal_weight
            combined_scores = [
                semantic_weight * sem + temporal_weight * temp
                for sem, temp in zip(semantic_scores, temporal_scores)
            ]

        # Zip items with combined scores
        items_with_scores = list(zip(items, combined_scores))

        # Sort by score (descending)
        items_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Return top K if specified
        if top_k is not None:
            items_with_scores = items_with_scores[:top_k]

        return items_with_scores


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
        top_k_chunks: Optional[int] = None,
        use_temporal_boost: bool = True,
        query_cohort_year: Optional[int] = None
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
            use_temporal_boost: If True, apply temporal boosting (default: True)

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
        if use_temporal_boost:
            print(f"[RERANKER] 📅 Temporal boosting: ENABLED")
        print("=" * 80)

        # Choose reranking method based on temporal boost setting
        if use_temporal_boost:
            def rerank_func(q, items, text_field, top_k):
                return self.reranker.rerank_with_temporal_boost(
                    q, items, text_field=text_field, top_k=top_k,
                    query_cohort_year=query_cohort_year
                )
        else:
            rerank_func = self.reranker.rerank_items  # type: ignore

        # Rerank entities
        reranked_entities = rerank_func(
            query, entities, text_field="entity_name", top_k=top_k_entities
        )
        entity_scores = [score for _, score in reranked_entities]

        print(f"[RERANKER] Reranked {len(reranked_entities)} entities")
        if entity_scores:
            print(f"[RERANKER]   Top entity score: {max(entity_scores):.4f}")

        # Rerank relationships
        reranked_relationships = rerank_func(
            query, relationships, text_field="description", top_k=top_k_relationships
        )
        relationship_scores = [score for _, score in reranked_relationships]

        print(f"[RERANKER] Reranked {len(reranked_relationships)} relationships")
        if relationship_scores:
            print(f"[RERANKER]   Top relationship score: {max(relationship_scores):.4f}")

        # Rerank chunks
        reranked_chunks = rerank_func(
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
                "model_name": self.reranker.config.default_model
            }
        }


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "Reranker",
    "MultiSourceReranker",
]
