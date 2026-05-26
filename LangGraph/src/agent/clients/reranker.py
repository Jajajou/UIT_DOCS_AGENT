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
            url = f"{settings.reranker_base_url}/v2/rerank"
            payload = {
                "model": self.config.default_model,
                "query": query,
                "documents": texts,
            }
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            # Cohere /v2/rerank returns results sorted by relevance_score with original index
            scored = sorted(data["results"], key=lambda x: x["index"])
            return [item["relevance_score"] for item in scored]

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
            1.0 if item's cohort_years contains query_cohort_year OR is universal ("*")
            0.5 (neutral) if no cohort in query, no metadata, empty cohort_years, or mismatch
        """
        if query_cohort_year is None:
            return 0.5  # neutral — no cohort specified in query
        
        cohort_years = item.get("metadata", {}).get("cohort_years", None)
        if not cohort_years:
            return 0.5  # neutral — no cohort metadata or empty list

        # 1. Check for Universal marker ("*") - partial boost, not exact match
        if "*" in cohort_years or "*" in [str(y) for y in cohort_years]:
            return 0.75

        # 2. Check for explicit year match
        try:
            normalized_query_year = int(query_cohort_year)
        except (ValueError, TypeError):
            return 0.5

        for y in cohort_years:
            try:
                if int(y) == normalized_query_year:
                    return 1.0
            except (ValueError, TypeError):
                continue

        # Return neutral (0.5) on mismatch so cohort boost only rewards matches,
        # never penalizes.
        return 0.5

    def _compute_authority_score(self, item: Dict[str, Any], query_authority_scope: Optional[str]) -> float:
        """
        Compute authority match score (system vs local).
        Returns:
            1.0 if authority matches query scope
            0.5 (neutral) if no scope in query
            0.3 if authority mismatches query scope (gentle penalty)
        """
        if query_authority_scope is None:
            return 0.5
            
        doc_num = str(item.get("metadata", {}).get("document_number", "")).upper()
        # Fallback to file_path/source if doc_num is empty
        if not doc_num:
            doc_num = str(item.get("metadata", {}).get("file_path", "")).upper()
        if not doc_num:
            doc_num = str(item.get("metadata", {}).get("file_source", "")).upper()
            
        is_system = any(k in doc_num for k in ["ĐHQG", "BGDĐT", "BGDDT", "DHQG", "BỘ"])
        is_local = any(k in doc_num for k in ["ĐHCNTT", "UIT"])
        
        if query_authority_scope == "system":
            return 1.0 if is_system else 0.3
        if query_authority_scope == "local":
            return 1.0 if is_local else 0.3
            
        return 0.5

    def rerank_with_temporal_boost(
        self,
        query: str,
        items: List[Dict[str, Any]],
        text_field: str = "content",
        top_k: Optional[int] = None,
        temporal_weight: Optional[float] = None,
        current_date: Optional[str] = None,
        query_cohort_year: Optional[int] = None,
        query_authority_scope: Optional[str] = None,
        query_is_historical: Optional[bool] = None,
        query_type: Optional[str] = None
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
            query_cohort_year: Optional cohort year
            query_is_historical: Optional flag for historical queries

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

        # Amendment override: demote doc X only when BOTH conditions hold:
        # 1. The amending doc Y is present in the candidate set.
        # 2. Y has semantic_score >= X's semantic_score (confidence guard).
        # Without (2), the override fires even when X is the correct answer for
        # the query and Y is a partial/tangential amendment — causing regression
        # on TDCE cases where the amended doc is the right retrieval target.
        if getattr(settings, 'use_amendment_override', False) and not query_is_historical:
            raw_override = settings.temporal.quality_penalties.get("amendment_override_score", 0.3)
            override_score = max(0.0, min(1.0, float(raw_override)))
            # Build doc_id → item index map for O(1) lookup + score comparison
            candidate_doc_id_to_idx: dict = {}
            for idx, item in enumerate(items):
                doc_id = (item.get("doc_id") or
                          item.get("id") or
                          item.get("metadata", {}).get("doc_id"))
                if doc_id:
                    candidate_doc_id_to_idx[str(doc_id)] = idx
            overridden = []
            new_temporal_scores = list(temporal_scores)
            for idx, item in enumerate(items):
                amended_by = item.get("metadata", {}).get("amended_by")
                if not (isinstance(amended_by, list) and len(amended_by) > 0):
                    continue
                
                # F1: Identify current doc_id to prevent self-demotion
                item_doc_id = str(item.get("doc_id") or item.get("id") or item.get("metadata", {}).get("doc_id", ""))
                
                amending_ids = [str(aid) for aid in amended_by]
                for aid in amending_ids:
                    # F1: Skip self-references and error-prefixed garbage IDs
                    if aid == item_doc_id or aid.startswith('error-'):
                        continue
                        
                    if aid not in candidate_doc_id_to_idx:
                        continue
                    amender_idx = candidate_doc_id_to_idx[aid]
                    # Confidence guard: only override if amender is semantically
                    # at least as relevant. If amender has lower semantic score,
                    # the query targets the original doc — skip override.
                    if semantic_scores[amender_idx] >= semantic_scores[idx]:
                        new_temporal_scores[idx] = override_score
                        overridden.append(item.get("metadata", {}).get("file_path", "unknown"))
                        break
            if overridden:
                print(f"[RERANKER] Amendment override applied to {len(overridden)} item(s): {overridden[:3]}")
            temporal_scores = new_temporal_scores

        # Combined scoring logic: 3-weight formula (55/20/25)
        # Use cohort/authority formula if metadata present, otherwise 70/30 formula
        use_cohort = getattr(settings, 'use_cohort_boost', True)
        temporal_config = getattr(settings, 'temporal', None)
        
        # Default weights
        s_w = 0.7
        t_w = 0.3
        c_w = 0.0
        
        # --- Clause-level Temporal Scoring Modification ---
        # Before applying whole-doc penalties, check for clause-level amendments
        if not query_is_historical:
            for idx, item in enumerate(items):
                metadata = item.get("metadata", {})
                amended_clauses = metadata.get("amended_clauses")
                if amended_clauses and isinstance(amended_clauses, dict):
                    # item might be a chunk, check its clause_number
                    chunk_clause_num = item.get("clause_number") or metadata.get("clause_number")
                    doc_num = metadata.get("document_number")
                    
                    # If this is a chunk and we know its clause number and doc number
                    if chunk_clause_num is not None and doc_num:
                        is_clause_amended = False
                        
                        # amended_clauses is {target_doc_num: [clause_nums]}
                        # Check if THIS document is amended
                        if doc_num in amended_clauses:
                            amended_list = amended_clauses[doc_num]
                            if isinstance(amended_list, list) and int(chunk_clause_num) in [int(c) for c in amended_list]:
                                is_clause_amended = True
                        
                        if is_clause_amended:
                            temporal_scores[idx] = 0.3
                        else:
                            temporal_scores[idx] = 1.0
                    else:
                        # Chunk has no clause_number or we don't know the doc num, apply mild penalty
                        temporal_scores[idx] = 0.7
        # --- End of Modification ---

        if use_cohort and (query_cohort_year is not None or query_authority_scope is not None):
            s_w = getattr(temporal_config, 'semantic_weight_cohort', 0.55)
            t_w = getattr(temporal_config, 'temporal_weight_cohort', 0.20)
            boost_w = getattr(temporal_config, 'cohort_weight', 0.25)
            
            # Compute raw boost scores
            raw_cohort_scores = [self._compute_cohort_score(item, query_cohort_year) for item in items]
            raw_authority_scores = [self._compute_authority_score(item, query_authority_scope) for item in items]
            
            # Combine cohort and authority into final c_w component
            cohort_scores = []
            for c, a in zip(raw_cohort_scores, raw_authority_scores):
                if query_cohort_year is not None and query_authority_scope is not None:
                    # Both present: weighted average (60/40)
                    cohort_scores.append(0.6 * c + 0.4 * a)
                elif query_cohort_year is not None:
                    cohort_scores.append(c)
                else:
                    cohort_scores.append(a)
            
            c_w = boost_w
        else:
            if temporal_weight is not None:
                t_w = temporal_weight
            else:
                t_w = getattr(temporal_config, 'recency_weight', 0.3)
            s_w = 1.0 - t_w
            cohort_scores = [0.0] * len(items)

        # Calculate final combined scores
        combined_scores = []
        for i, (s, t, c) in enumerate(zip(semantic_scores, temporal_scores, cohort_scores)):
            score = s_w * s + t_w * t + c_w * c
            
            # VBHN Boost (+0.1) - prioritize consolidated documents
            if items[i].get("metadata", {}).get("is_vbhn", False):
                score += 0.1
                
            # Article Priority Boost (+0.15) - matches specific articles mentioned in query
            if items[i].get("metadata", {}).get("article_priority_boost", False):
                score += 0.15
            
            # Clamp to 1.0
            score = min(1.0, max(0.0, score))
            combined_scores.append(score)

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
        query_cohort_year: Optional[int] = None,
        query_authority_scope: Optional[str] = None,
        query_is_historical: Optional[bool] = None,
        query_type: Optional[str] = None
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
            query_cohort_year: Optional cohort year
            query_is_historical: Optional flag for historical queries

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
            if query_is_historical:
                print(f"[RERANKER] ⏳ Historical query mode: ON (suppressing amendment override)")
        print("=" * 80)

        # Choose reranking method based on temporal boost setting
        if use_temporal_boost:
            def rerank_func(q, items, text_field, top_k):
                return self.reranker.rerank_with_temporal_boost(
                    q, items, text_field=text_field, top_k=top_k,
                    query_cohort_year=query_cohort_year,
                    query_authority_scope=query_authority_scope,
                    query_is_historical=query_is_historical,
                    query_type=query_type
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
