"""
Reranker Module for Vietnamese Text Ranking

This module provides reranking functionality using Vietnamese-optimized cross-encoder models.
It scores and re-ranks retrieved entities, relationships, and chunks based on relevance to the query.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re
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
            # Truncate to model's actual limit: 2048 tokens for passage, 256 for query
            # Vietnamese_Reranker max sequence = 2304 (https://huggingface.co/AITeamVN/Vietnamese_Reranker)
            # ~3 chars/token for Vietnamese → 2048 tokens ≈ 6000 chars
            _MAX_DOC_CHARS = 6000
            texts = [t[:_MAX_DOC_CHARS] if len(t) > _MAX_DOC_CHARS else t for t in texts]
            payload = {
                "model": self.config.default_model,
                "query": query,
                "documents": texts,
            }
            print(f"[RERANKER] HTTP rerank: {len(texts)} docs, query_len={len(query)}, model={self.config.default_model}")
            last_err = None
            for _attempt in range(3):
                response = requests.post(url, json=payload, timeout=60)
                if response.ok:
                    break
                last_err = f"Reranker {response.status_code}: {response.text[:300]} | docs={len(texts)} query_len={len(query)}"
                if response.status_code < 500:
                    break  # 4xx won't fix itself on retry
                print(f"[RERANKER] Attempt {_attempt+1} failed ({response.status_code}), retrying...")
            if not response.ok:
                raise RuntimeError(last_err)
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
        current_date: Optional[str] = None,
        query_is_historical: Optional[bool] = False,
        query_cohort_year: Optional[int] = None,
        query_academic_year: Optional[str] = None,
        query_date: Optional[str] = None
    ) -> float:
        """
        Calculate temporal relevance score for an item based on its metadata.

        Research shows simple recency prior achieves 1.00 accuracy on freshness tasks.

        Args:
            item: Item dict (entity, relationship, or chunk)
            current_date: ISO date string for comparison. Defaults to today.
            query_is_historical: If True, do not penalize amended/old docs.
            query_date: ISO date string for historical point-in-time penalty.

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
            return 0.0

        # NEW: Canonical Pointer Boost
        if metadata.get("is_canonical_pointer", False):
            return 1.1  # Bonus score for explicitly resolved canonical docs

        # NEW: Point-in-time penalty (Future Docs)
        # If query_date is set, penalize docs that were born AFTER that date
        future_penalty = 1.0
        if query_date:
            doc_valid_from = metadata.get("valid_from")
            if doc_valid_from:
                try:
                    # Simple string comparison works for ISO dates YYYY-MM-DD
                    if str(doc_valid_from) > query_date:
                        future_penalty = 0.2
                        print(f"[TEMPORAL] ⚠️ Penalizing future doc {metadata.get('document_number')}: valid_from={doc_valid_from} > query_date={query_date}")
                except (ValueError, TypeError):
                    pass

        # Chunk-level: specific clause confirmed superseded by amendment_resolver
        if item.get("is_superseded", False):
            # If historical query, we might want the superseded one!
            return (0.1 if not query_is_historical else 0.9) * future_penalty

        # Doc-level: whole doc has been amended (blunt signal)
        amended_by = metadata.get("amended_by", [])
        if isinstance(amended_by, list) and len(amended_by) > 0:
            # Bypass penalty if historical or if this doc specifically matches the cohort
            if query_is_historical:
                return 0.9 * future_penalty

            # Check if this document is a primary authority for the student's cohort
            # If it is, don't penalize it for being amended later.
            is_cohort_match = False
            if query_cohort_year is not None:
                cohorts = metadata.get("cohort_years", [])
                if "*" in cohorts or "*" in [str(c) for c in cohorts] or query_cohort_year in cohorts or str(query_cohort_year) in [str(c) for c in cohorts]:
                    is_cohort_match = True

            if is_cohort_match:
                return 0.85 * future_penalty # cohort-matched: no penalty even if later amended

            # Temporal exemption: if query anchors to a year and this doc was
            # valid at that time, don't penalize — the amending docs came later.
            anchor_year = None
            if query_academic_year:
                m = re.search(r"(\d{4})", str(query_academic_year))
                if m:
                    anchor_year = int(m.group(1))
            if anchor_year is not None:
                doc_valid_from = metadata.get("valid_from")
                if doc_valid_from:
                    try:
                        vf_date = datetime.fromisoformat(str(doc_valid_from))
                        if vf_date.year <= anchor_year:
                            return 0.85 * future_penalty # was active in queried year, amendments came later
                    except (ValueError, TypeError):
                        pass

            return 0.3 * future_penalty # superseded docs deprioritized

        # Check if superseded: doc has amended_by → newer version exists
        amended_by = metadata.get("amended_by", [])
        if isinstance(amended_by, list) and len(amended_by) > 0:
            return 0.3  # Superseded docs deprioritized regardless of validity dates

        # Get validity dates
        valid_from = metadata.get("valid_from")
        valid_until = metadata.get("valid_until")
        indexed_at = metadata.get("indexed_at")

        # If no temporal info, assume always valid but not prioritized
        if not valid_from and not valid_until and not indexed_at:
            return 0.5 * future_penalty # no temporal info → neutral score

        # --- TIME TRAVEL LOGIC FOR HISTORICAL QUERIES ---
        if query_is_historical:
            # Try to extract anchor year from query_academic_year or intention
            anchor_year = None
            if query_academic_year:
                m = re.search(r"(\d{4})", str(query_academic_year))
                if m: anchor_year = int(m.group(1))
            
            if anchor_year and valid_from:
                try:
                    vf_date = datetime.fromisoformat(str(valid_from))
                    # DRASTIC PENALTY for documents from the FUTURE relative to query
                    if vf_date.year > anchor_year:
                        return 0.1 * future_penalty
                    # BONUS for documents in that specific era
                    if vf_date.year == anchor_year:
                        return 1.0 * future_penalty
                    if vf_date.year == anchor_year - 1:
                        return 0.95 * future_penalty
                except: pass
            return 0.8 * future_penalty # Default good score for valid past docs

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
                        return 0.1 * future_penalty # Very old, heavily penalized
                    else:
                        # Gradual decay: 0.5 at expiry, 0.1 at 1 year
                        return max(0.1, 0.5 - (days_expired / 365) * 0.4) * future_penalty
            except (ValueError, TypeError):
                pass

        # If not valid yet
        if not is_valid:
            return 0.3 * future_penalty # Not yet valid

        # Document is currently valid - score based on recency
        # PRIORITIZE valid_from for legal recency, fallback to indexed_at
        recency_date_str = valid_from or indexed_at
        if recency_date_str:
            try:
                # Handle space in timestamp (from indexed_at)
                clean_date = str(recency_date_str).split(' ')[0]
                recency_date = datetime.fromisoformat(clean_date)
                days_old = (current - recency_date).days

                # Legal Recency: Very slow decay — UIT docs valid for years
                # 1.0 for < 30 days, 0.97 for 1 year, 0.85 for 3 years, 0.75 for 5 years, 0.6 floor
                if days_old <= 30:
                    score = 1.0
                elif days_old <= 365:
                    score = 0.98 - (days_old / 365) * 0.01  # 0.98 -> 0.97
                elif days_old <= 1095: # 3 years
                    score = 0.97 - ((days_old - 365) / 730) * 0.12 # 0.97 -> 0.85
                elif days_old <= 1825: # 5 years
                    score = 0.85 - ((days_old - 1095) / 730) * 0.10 # 0.85 -> 0.75
                else:
                    score = max(0.5, 0.75 - ((days_old - 1825) / 1825) * 0.15) # floor at 0.5

                # ADD: Confirmed Latest Boost (Grounding with system)
                # If this doc is explicitly confirmed NOT amended, give it a small boost
                # to win over older siblings in the same retrieval set.
                if not query_is_historical and amended_by == []:
                    score = min(1.0, score + 0.05)

                return score * future_penalty

            except (ValueError, TypeError):
                pass

        # Default: valid but no recency info
        return 0.8 * future_penalty

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
        # Lower than exact match (1.0) so cohort-specific docs win over universal ones
        if "*" in cohort_years or "*" in [str(y) for y in cohort_years]:
            return 0.35

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

    def _compute_academic_year_score(self, item: Dict[str, Any], query_academic_year: Optional[str]) -> float:
        """
        Compute academic year match score for an item.

        Returns:
            1.0 if item's academic_year matches query_academic_year
            0.5 (neutral) if no academic year in query or metadata, or mismatch
        """
        if not query_academic_year:
            return 0.5

        doc_academic_year = item.get("metadata", {}).get("academic_year")
        if not doc_academic_year:
            return 0.5

        # Exact match (e.g., "2024-2025" == "2024-2025")
        if str(doc_academic_year).strip() == str(query_academic_year).strip():
            return 1.0

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
        query_academic_year: Optional[str] = None,
        query_authority_scope: Optional[str] = None,
        query_is_historical: Optional[bool] = None,
        query_type: Optional[str] = None,
        query_date: Optional[str] = None
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
            query_academic_year: Optional academic year
            query_is_historical: Optional flag for historical queries
            query_date: ISO date string for point-in-time filtering

        Returns:
            List of (item, combined_score) tuples, sorted by score (highest first)
        """
        if not items:
            return []

        # Fallback historical detection: LLM may miss "trước khi/bản cũ" phrasing
        _HISTORICAL_KW = ("trước khi", "bản cũ", "lúc đó", "trước đây", "khi đó",
                          "trước năm", "thời điểm đó", "hồi đó", "trước khi có")
        if not query_is_historical and any(kw in query.lower() for kw in _HISTORICAL_KW):
            query_is_historical = True
            print(f"[RERANKER] Historical override via keyword: {query[:80]}")

        # Extract texts for semantic scoring
        texts = []
        for item in items:
            text = item.get(text_field, "")
            if not text:
                text = item.get("name", "") or item.get("description", "") or str(item)
            texts.append(str(text))

        # Compute semantic scores
        semantic_scores = self.compute_scores(query, texts)

        # 1. Compute Temporal Scores
        temporal_scores = [
            self.calculate_temporal_score(
                item, current_date=current_date, 
                query_is_historical=query_is_historical,
                query_cohort_year=query_cohort_year,
                query_academic_year=query_academic_year,
                query_date=query_date
            ) 
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
                        # F1: Protect cohort-specific authorities from being overridden by generic newer docs
                        is_cohort_protected = False
                        if query_cohort_year is not None:
                            item_cohorts = item.get("metadata", {}).get("cohort_years", [])
                            # Only protect if doc has EXPLICIT cohort matching query (not universal *)
                            if str(query_cohort_year) in [str(c) for c in item_cohorts]:
                                is_cohort_protected = True
                        
                        if not is_cohort_protected:
                            new_temporal_scores[idx] = override_score
                            overridden.append(
                                item.get("metadata", {}).get("document_number")
                                or item.get("metadata", {}).get("file_path")
                                or item.get("doc_id", "unknown")
                            )
                        else:
                            print(f"[RERANKER] 🛡️ Shielding {item.get('metadata', {}).get('document_number')} from amendment override due to cohort match ({query_cohort_year})")
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

        if use_cohort and (query_cohort_year is not None or query_authority_scope is not None or query_academic_year is not None):
            s_w = getattr(temporal_config, 'semantic_weight_cohort', 0.55)
            t_w = getattr(temporal_config, 'temporal_weight_cohort', 0.20)
            boost_w = getattr(temporal_config, 'cohort_weight', 0.25)
            
            # Compute raw boost scores
            raw_cohort_scores = [self._compute_cohort_score(item, query_cohort_year) for item in items]
            raw_authority_scores = [self._compute_authority_score(item, query_authority_scope) for item in items]
            raw_academic_scores = [self._compute_academic_year_score(item, query_academic_year) for item in items]
            
            # Combine cohort, authority, and academic year into final c_w component
            cohort_scores = []
            for c, a, ac in zip(raw_cohort_scores, raw_authority_scores, raw_academic_scores):
                components = []
                weights = []
                
                if query_cohort_year is not None:
                    components.append(c)
                    weights.append(0.5)
                if query_authority_scope is not None:
                    components.append(a)
                    weights.append(0.3)
                if query_academic_year is not None:
                    components.append(ac)
                    weights.append(0.2)
                
                if not components:
                    cohort_scores.append(0.5)
                else:
                    # Normalize weights
                    total_w = sum(weights)
                    weighted_score = sum(comp * (w / total_w) for comp, w in zip(components, weights))
                    cohort_scores.append(weighted_score)
            
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
            
            # Cohort Scope Boost (+0.15) - prioritize docs EXPLICITLY for this cohort
            # Only if c == 1.0 (exact match) and scope is explicit
            if c >= 1.0:
                metadata = items[i].get("metadata", {})
                if metadata.get("cohort_scope") == "explicit":
                    score += 0.15
                    # print(f"[RERANKER] 🚀 Explicit cohort boost for {metadata.get('document_number')}")

            # VBHN Boost (+0.1) - prioritize consolidated documents
            if items[i].get("metadata", {}).get("is_vbhn", False):
                score += 0.1
                
            # Article Priority Boost (+0.15) - matches specific articles mentioned in query
            if items[i].get("metadata", {}).get("article_priority_boost", False):
                score += 0.15
            
            # Procedure Boost (+0.1) - prioritize procedures for procedural queries
            if query_type == "PROCEDURE":
                if items[i].get("metadata", {}).get("document_type") == "procedure":
                    score += 0.1
            
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
        query_academic_year: Optional[str] = None,
        query_authority_scope: Optional[str] = None,
        query_is_historical: Optional[bool] = None,
        query_type: Optional[str] = None,
        query_date: Optional[str] = None
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
            query_academic_year: Optional academic year
            query_is_historical: Optional flag for historical queries
            query_date: ISO date string for point-in-time filtering

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
            if query_date:
                print(f"[RERANKER] 🕒 Point-in-time: {query_date}")
        print("=" * 80)

        # Choose reranking method based on temporal boost setting
        if use_temporal_boost:
            def rerank_func(q, items, text_field, top_k):
                return self.reranker.rerank_with_temporal_boost(
                    q, items, text_field=text_field, top_k=top_k,
                    query_cohort_year=query_cohort_year,
                    query_academic_year=query_academic_year,
                    query_authority_scope=query_authority_scope,
                    query_is_historical=query_is_historical,
                    query_type=query_type,
                    query_date=query_date
                )
        else:
            rerank_func = self.reranker.rerank_items  # type: ignore

        # Rerank entities, relationships, chunks in parallel
        _tasks = {
            "entities": (entities, "entity_name", top_k_entities),
            "relationships": (relationships, "description", top_k_relationships),
            "chunks": (chunks, "content", top_k_chunks),
        }
        _results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(rerank_func, query, items, text_field, top_k): key
                for key, (items, text_field, top_k) in _tasks.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                _results[key] = future.result()

        reranked_entities = _results["entities"]
        reranked_relationships = _results["relationships"]
        reranked_chunks = _results["chunks"]

        entity_scores = [score for _, score in reranked_entities]
        relationship_scores = [score for _, score in reranked_relationships]
        chunk_scores = [score for _, score in reranked_chunks]

        print(f"[RERANKER] Reranked {len(reranked_entities)} entities, {len(reranked_relationships)} rels, {len(reranked_chunks)} chunks (parallel)")
        if entity_scores:
            print(f"[RERANKER]   Top entity score: {max(entity_scores):.4f}")
        if relationship_scores:
            print(f"[RERANKER]   Top relationship score: {max(relationship_scores):.4f}")
        if chunk_scores:
            print(f"[RERANKER]   Top chunk score: {max(chunk_scores):.4f}")

        # Calculate overall confidence
        all_scores = entity_scores + relationship_scores + chunk_scores
        overall_confidence = self.reranker.calculate_aggregate_confidence(all_scores)

        print(f"[RERANKER] ✓ Overall confidence: {overall_confidence:.4f}")
        print("=" * 80)
        
        # --- Canonical Conflict Resolution (Option B) ---
        reranked_chunks = self.resolve_canonical_conflicts(reranked_chunks)
        
        return {
            "reranked_entities": reranked_entities,
            "reranked_relationships": reranked_relationships,
            "reranked_chunks": reranked_chunks,
            "entity_scores": entity_scores,
            "relationship_scores": relationship_scores,
            "chunk_scores": [s for _, s in reranked_chunks],
            "overall_confidence": overall_confidence,
            "metadata": {
                "total_items_reranked": len(all_scores),
                "entity_count": len(reranked_entities),
                "relationship_count": len(reranked_relationships),
                "chunk_count": len(reranked_chunks),
                "model_name": self.reranker.config.default_model
            }
        }

    def resolve_canonical_conflicts(self, reranked_chunks: List[Tuple[Dict[str, Any], float]]) -> List[Tuple[Dict[str, Any], float]]:
        """
        Prioritize documents with higher authority_level when multiple documents
        talk about the same concept_id.
        """
        if not reranked_chunks:
            return []

        # 1. Group by concept_id
        concept_groups: Dict[str, List[int]] = {}
        for i, (item, _) in enumerate(reranked_chunks):
            concept_id = item.get("metadata", {}).get("concept_id")
            if concept_id:
                if concept_id not in concept_groups:
                    concept_groups[concept_id] = []
                concept_groups[concept_id].append(i)

        if not concept_groups:
            return reranked_chunks

        # 2. For each concept, find the max authority_level
        new_reranked = list(reranked_chunks)
        for cid, indices in concept_groups.items():
            if len(indices) <= 1:
                continue
            
            # Get max authority in this group
            max_auth = max([reranked_chunks[idx][0].get("metadata", {}).get("authority_level", 1) for idx in indices])
            
            # Apply penalty to those with lower authority
            for idx in indices:
                item, score = reranked_chunks[idx]
                auth = item.get("metadata", {}).get("authority_level", 1)
                
                if auth < max_auth:
                    # Confidence Guard: If the lower authority item is significantly more 
                    # relevant semantically, do not penalize it.
                    # Also, if it's a LOCAL doc vs a SYSTEM doc, local implementations 
                    # are often more relevant for the user.
                    
                    doc_num = str(item.get("metadata", {}).get("document_number", "")).upper()
                    is_local = any(k in doc_num for k in ["ĐHCNTT", "UIT"])
                    
                    # If this is a local doc and the max_auth is from a system doc (5), 
                    # skip the penalty.
                    if is_local and max_auth == 5:
                        print(f"[RERANKER] ℹ️ Local implementation preserved: {doc_num} vs System Auth {max_auth}")
                        continue

                    # Otherwise apply penalty but only if semantic score isn't dominant
                    # (score here is the already combined score from rerank_with_temporal_boost)
                    penalty = 0.5 
                    new_score = score * penalty
                    new_reranked[idx] = (item, new_score)
                    print(f"[RERANKER] ⚠️ Canonical Conflict: Concept '{cid}' found in multiple docs. "
                          f"Penalized {item.get('metadata', {}).get('document_number')} "
                          f"(Auth {auth} < Max {max_auth})")
        
        # Sort again by the new scores
        new_reranked.sort(key=lambda x: x[1], reverse=True)
        return new_reranked


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "Reranker",
    "MultiSourceReranker",
]
