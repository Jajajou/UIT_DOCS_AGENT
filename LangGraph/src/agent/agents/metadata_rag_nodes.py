import os
import uuid
import logging
import json
import re
from typing import List, Dict, Any, Tuple, Union, Literal
from datetime import datetime

# LangGraph
from langgraph.types import interrupt
from langgraph.graph.state import Command

# LangChain & Models
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings
import numpy as np

# Internal
from ..states.metadata_rag_state import MetadataRAGState
from ..core.prompts import METADATA_PROMPTS
from .header_extraction import extract_from_header
from langchain.chat_models import init_chat_model
from agent.config import get_attr_safe, settings
from agent.utils import strip_think_tags
from pydantic import BaseModel, Field, field_validator, ValidationInfo

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.indexing_llm_model,
    streaming=False,
    temperature=0,
    model_kwargs={
        "tool_choice": "none"
    }
)

# Setup Logging
logger = logging.getLogger(__name__)

# --- GLOBAL MODELS (Singleton Pattern) ---
# Reranker uses HTTP API; only load ChromaDB in-memory client
try:
    CHROMA_CLIENT = chromadb.Client(Settings(
        anonymized_telemetry=False,
        allow_reset=True,
        is_persistent=False
    ))
    logger.info("Vector DB Loaded Successfully.")
    print("Vector DB Loaded Successfully.")
except Exception as e:
    logger.error(f"Error loading vector DB: {e}")
    print(f"Error loading vector DB: {e}")
    raise e


# --- RERANKER HTTP CLIENT ---
def compute_rerank_scores_http(query: str, docs: List[str]) -> List[float]:
    """
    Call vLLM /v1/score endpoint to rerank documents.

    Args:
        query: Query string
        docs: List of candidate documents

    Returns:
        List of relevance scores (floats)
    """
    import requests

    url = f"{settings.reranker_base_url}/v1/score"
    payload = {
        "model": settings.reranker.default_model,
        "text_1": query,
        "text_2": docs
    }
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return [item["score"] for item in data["data"]]


# --- EMBEDDING API CLIENT ---
def get_embeddings_from_vllm(texts: List[str]) -> List[List[float]]:
    """
    Get embeddings from vLLM API.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors
    """
    import requests

    try:
        url = f"{settings.embedding_base_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
        }
        if settings.embedding_api_key and settings.embedding_api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {settings.embedding_api_key}"

        payload = {
            "input": texts,
            "model": settings.embedding_model
        }

        response = requests.post(url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()

        result = response.json()
        embeddings = [item["embedding"] for item in result["data"]]

        logger.info(f"Generated {len(embeddings)} embeddings via vLLM API")
        return embeddings

    except Exception as e:
        logger.error(f"Error calling vLLM embeddings API: {e}")
        print(f"Error calling vLLM embeddings API: {e}")
        raise e



# --- NODES IMPLEMENTATION ---

def extract_header_metadata_node(state: MetadataRAGState) -> Dict[str, Any]:
    """
    Fast extraction of document_number and amends_documents from header (first 2000 chars).
    This node runs first to provide immediate results.
    """
    try:
        doc_text = state["doc_text"]
        file_source = state["file_source"]
        
        logger.info(f"Extracting header metadata for {file_source}")
        header_result = extract_from_header(doc_text, file_source)
        
        # Simple regex for Type and Authority from the top 500 chars
        header_chunk = doc_text[:500].upper()
        doc_type = None
        if "QUYẾT ĐỊNH" in header_chunk or "QUYET DINH" in header_chunk: doc_type = "Quyết định"
        elif "THÔNG BÁO" in header_chunk or "THONG BAO" in header_chunk: doc_type = "Thông báo"
        elif "QUY ĐỊNH" in header_chunk or "QUY DINH" in header_chunk: doc_type = "Quy định"
        elif "QUY CHẾ" in header_chunk or "QUY CHE" in header_chunk: doc_type = "Quy chế"
        elif "TỜ TRÌNH" in header_chunk or "TO TRINH" in header_chunk: doc_type = "Tờ trình"
        
        authority = None
        if "HIỆU TRƯỞNG" in header_chunk or "HIEU TRUONG" in header_chunk: authority = "Hiệu trưởng"
        elif "PHÒNG ĐÀO TẠ" in header_chunk or "PHONG DAO TA" in header_chunk: authority = "Phòng Đào tạo"
        elif "HỘI ĐỒNG" in header_chunk or "HOI DONG" in header_chunk: authority = "Hội đồng"

        return {
            "document_number": header_result.get("document_number"),
            "document_type": doc_type,
            "issuing_authority": authority,
            "amends_documents": header_result.get("amends_documents", []),
            "review_status": "pending" # Initial status
        }
    except Exception as e:
        logger.error(f"Error in header extraction node: {e}")
        return {}


def chunk_document_node(state: MetadataRAGState) -> Dict[str, Any]:
    """Chia nhỏ văn bản thành chunks 1024 tokens."""
    try:
        text = state["doc_text"]

        # Sử dụng RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=200, # Tăng overlap để giữ context giữa các trang
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = splitter.split_text(text)

        logger.info(f"Document split into {len(chunks)} chunks.")
        print(f"Document split into {len(chunks)} chunks.")

        return {
            "chunks": chunks,
            "chunk_count": len(chunks)
        }
    except Exception as e:
        logger.error(f"Error chunking: {e}")
        print(f"Error chunking: {e}")
        return {"error": str(e), "success": False}

def index_to_vector_db_node(state: MetadataRAGState) -> Dict[str, Any]:
    """Embed chunks and save to ChromaDB in-memory temporarily."""
    try:
        chunks = state.get("chunks")
        if not chunks:
            return {"error": "No chunks to index", "success": False}

        # Create unique collection name for this session
        file_source = state.get('file_source') or ''
        clean_source = ''.join(e for e in file_source if e.isalnum())[-10:] or uuid.uuid4().hex[:10]
        collection_name = f"temp_{uuid.uuid4().hex[:8]}_{clean_source}"

        collection = CHROMA_CLIENT.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Embedding (Batch processing via vLLM API)
        logger.info("Generating embeddings via vLLM API...")
        print("Generating embeddings via vLLM API...")
        embeddings_list = get_embeddings_from_vllm(chunks)

        # Convert to numpy array for ChromaDB compatibility
        embeddings_array = np.array(embeddings_list, dtype=np.float32)

        # Add to Chroma
        ids = [f"id_{i}" for i in range(len(chunks))]
        collection.add(
            documents=chunks,
            embeddings=embeddings_array.tolist(),
            ids=ids
        )

        logger.info(f"Indexed {len(chunks)} chunks to collection '{collection_name}'")
        print(f"Indexed {len(chunks)} chunks to collection '{collection_name}'")
        return {"collection_name": collection_name}

    except Exception as e:
        logger.error(f"Error indexing: {e}")
        print(f"Error indexing: {e}")
        return {"error": str(e), "success": False}

def _rag_retrieve_and_rerank(collection_name: str, query: str, top_k_retrieve=50, top_k_rerank=5) -> List[str]:
    """Helper function: Retrieve (Bi-encoder) -> Rerank (Cross-encoder)."""
    collection = CHROMA_CLIENT.get_collection(collection_name)

    # 1. Bi-encoder Retrieval (using vLLM API)
    query_vec = get_embeddings_from_vllm([query])[0]
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k_retrieve
    )

    candidates_list = results.get('documents', [[]])
    if not candidates_list or not candidates_list[0]:
        return []

    candidates = candidates_list[0]

    # 2. Cross-encoder Reranking via HTTP API
    scores = compute_rerank_scores_http(query, candidates)

    # Sort & take top K
    # scores is numpy array, need to sort by index
    sorted_indices = np.argsort(scores)[::-1][:top_k_rerank]
    top_docs = [candidates[i] for i in sorted_indices]

    return top_docs

def query_metadata_fields_node(state: MetadataRAGState) -> Dict[str, Any]:
    """
    Aggregate node: Query all metadata fields.
    Combines into 1 node to avoid overhead of state transfers,
    while maintaining logical separation.
    """
    try:
        col_name = state.get("collection_name")
        if not col_name:
            return {"error": "No collection_name in state"}

        file_source = state.get("file_source", "")
        filename = os.path.basename(file_source) if file_source else "unknown"

        # HITL Feedback logic
        human_feedback = state.get("human_feedback")
        feedback_instruction = ""
        if human_feedback:
            feedback_instruction = f"\n\nCRITICAL: A human reviewer has provided the following correction. You MUST prioritize this feedback over your initial extraction:\n<feedback>\n{human_feedback}\n</feedback>"

        updates: Dict[str, Any] = {}

        # NOTE: document_number and amends_documents are extracted by
        # header_extraction.py (positional, first 2000 chars) BEFORE this
        # subgraph is invoked. RAG is kept only for cohort_years and valid_dates
        # which are legitimately scattered throughout curriculum documents.

        # --- 1. Valid Dates (Temporal Aware) ---
        q_date = "Ngày hiệu lực, ngày ký, ngày ban hành, ngày hết hạn"
        docs_date = _rag_retrieve_and_rerank(col_name, q_date)
        updates["valid_from_chunks"] = docs_date
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt_date = METADATA_PROMPTS['valid_dates'].format(
            current_date=current_date,
            filename=filename,
            context="\n---\n".join(docs_date)
        )

        if feedback_instruction:
            prompt_date += feedback_instruction

        res_date = llm.invoke(prompt_date)
        content_date = res_date.content if hasattr(res_date, 'content') else str(res_date)

        # Ensure content_date is a string
        if not isinstance(content_date, str):
            content_date = str(content_date)

        # Try to parse JSON from response
        try:
            json_match = re.search(r'\{.*?"valid_from".*?\}', content_date, re.DOTALL)
            if json_match:
                date_data = json.loads(json_match.group())
                updates["valid_from"] = date_data.get("valid_from")
                updates["valid_until"] = date_data.get("valid_until")
            else:
                updates["valid_from"] = None
                updates["valid_until"] = None
        except Exception as e:
            logger.warning(f"Error parsing date JSON: {e}")
            print(f"Error parsing date JSON: {e}")
            updates["valid_from"] = None
            updates["valid_until"] = None
        
        # --- 2. Document Type ---
        q_type = "Loại văn bản: Quyết định, Thông báo, Quy định, Quy chế, Hướng dẫn?"
        docs_type = _rag_retrieve_and_rerank(col_name, q_type)
        
        prompt_type = f"Phân tích các đoạn văn bản sau và xác định loại văn bản (document_type). Ví dụ: 'Quyết định', 'Thông báo', 'Quy định', 'Hướng dẫn'.\n\nContext:\n{chr(10).join(docs_type)}\n\nTrả về JSON: {{\"document_type\": \"...\"}}"
        if feedback_instruction:
            prompt_type += feedback_instruction
            
        res_type = llm.invoke(prompt_type)
        try:
            type_data = json.loads(strip_think_tags(res_type.content if hasattr(res_type, 'content') else str(res_type)))
            updates["document_type"] = type_data.get("document_type")
        except:
            pass

        # --- 3. Cohorts ---
        q_cohort = "Áp dụng cho khóa sinh viên nào? Khóa đào tạo, khóa tuyển sinh năm bao nhiêu? Đối tượng áp dụng? Khóa 1 khóa 2 khóa 3?"
        docs_cohort = _rag_retrieve_and_rerank(col_name, q_cohort)
        updates["cohort_years_chunks"] = docs_cohort

        # Use current_date for temporal awareness (already defined above)
        prompt_cohort = METADATA_PROMPTS['cohorts'].format(
            current_date=current_date,
            filename=filename,
            context="\n---\n".join(docs_cohort)
        )

        if feedback_instruction:
            prompt_cohort += feedback_instruction

        res_cohort = llm.invoke(prompt_cohort)
        content_cohort = res_cohort.content if hasattr(res_cohort, 'content') else str(res_cohort)

        # Ensure content is string
        if not isinstance(content_cohort, str):
            content_cohort = str(content_cohort)

        # Try to parse JSON from response
        try:
            json_match = re.search(r'\{.*?"cohort_years".*?\}', content_cohort, re.DOTALL)
            if json_match:
                cohort_data = json.loads(json_match.group())
                updates["cohort_years"] = cohort_data.get("cohort_years", [])
                updates["cohort_scope"] = cohort_data.get("cohort_scope", "unspecified")
            else:
                updates["cohort_years"] = []
                updates["cohort_scope"] = "unspecified"
        except Exception as e:
            logger.warning(f"Error parsing cohort JSON: {e}")
            print(f"Error parsing cohort JSON: {e}")
            updates["cohort_years"] = []
            updates["cohort_scope"] = "unspecified"
        
        # NOTE: amends_documents extracted by header_extraction.py (not RAG).
        # Do NOT overwrite it here — the indexing_graph merges header results
        # into the final metadata after this subgraph returns.

        # --- Fallback: Extract from Filename if RAG failed or is imprecise ---
        # Checks if document_number or valid_from is missing/imprecise
        extracted_date = updates.get("valid_from")
        is_generic_date = extracted_date and extracted_date.endswith("-01-01")
        
        if not updates.get("document_number") or not extracted_date or is_generic_date:
            if file_source:
                try:
                    logger.info(f"Attempting filename extraction for: {filename}")
                    print(f"Attempting filename extraction for: {filename}")
                    
                    # Pattern: 03-tb-dhcntt_17-1-2017.pdf
                    # Group 1: Doc Number (03-tb-dhcntt)
                    # Group 2: Date (17-1-2017)
                    match = re.search(r'([\d\w-]+)_(\d{1,2}-\d{1,2}-\d{4})', filename)
                    
                    if match:
                        # Extract Document Number
                        if not updates.get("document_number"):
                            raw_num = match.group(1)
                            # Handle two filename patterns:
                            # Pattern A: 03-tb-dhcntt    -> 03/TB-ĐHCNTT      (QD, TB from UIT)
                            # Pattern B: 02_2022-tt-bgddt -> 02/2022/TT-BGDĐT  (TT from Ministry, year encoded with _)
                            fmt_num = None
                            # Check for Ministry-style: NUM_YEAR-TYPE-ISSUER
                            ministry_match = re.match(r'^(\d+)_(\d{4})-([a-zA-Z]+)-([a-zA-Z]+)$', raw_num)
                            if ministry_match:
                                num = ministry_match.group(1)
                                year = ministry_match.group(2)
                                doc_type = ministry_match.group(3).upper()
                                issuer = ministry_match.group(4).upper()
                                issuer = issuer.replace("BGDDT", "BGDĐT")
                                fmt_num = f"{num}/{year}/{doc_type}-{issuer}"
                            else:
                                parts = raw_num.split('-')
                                if len(parts) >= 2:
                                    fmt_num = f"{parts[0]}/{parts[1].upper()}"
                                    if len(parts) > 2:
                                        suffix = "-".join(p.upper() for p in parts[2:])
                                        suffix = suffix.replace("DHCNTT", "ĐHCNTT")
                                        fmt_num = f"{fmt_num}-{suffix}"
                                else:
                                    fmt_num = raw_num

                            if fmt_num:
                                updates["document_number"] = fmt_num
                                logger.info(f"Fallback extracted doc number: {fmt_num}")
                        
                        # Extract Date - Overwrite if generic or missing
                        raw_date = match.group(2)
                        try:
                            # Parse 17-1-2017 -> 2017-01-17
                            dt = datetime.strptime(raw_date, "%d-%m-%Y")
                            fmt_date = dt.strftime("%Y-%m-%d")
                            
                            # Overwrite if LLM only guessed the year (01-01) or if missing
                            if not extracted_date or is_generic_date:
                                updates["valid_from"] = fmt_date
                                logger.info(f"Fallback extracted date: {fmt_date} (Replaced generic: {is_generic_date})")
                        except ValueError:
                            logger.warning(f"Could not parse date from filename: {raw_date}")
                except Exception as e:
                    logger.warning(f"Filename extraction failed: {e}")

        return updates
        
    except Exception as e:
        logger.error(f"Error querying metadata: {e}")
        print(f"Error querying metadata: {e}")
        return {"error": str(e)}

def calculate_confidence_node(state: MetadataRAGState) -> Dict[str, Any]:
    """
    Calculate extraction confidence based on:
    1. Field completeness (how many required fields extracted?)
    2. LLM confidence (did LLM return "NULL" or empty values?)
    3. Chunk quality (were retrieved chunks relevant?)
    """
    try:
        scores = []

        # 1. Field completeness score
        required_fields = ["document_number", "valid_from", "cohort_years"]
        filled_count = 0
        for field in required_fields:
            value = state.get(field)
            if value and value != "NULL" and value != "":
                if isinstance(value, list) and len(value) > 0:
                    filled_count += 1
                elif isinstance(value, str):
                    filled_count += 1

        completeness_score = filled_count / len(required_fields)
        scores.append(completeness_score)

        # 2. LLM confidence (inverse of NULL/empty values)
        all_extracted_fields = ["document_number", "valid_from", "valid_until", "cohort_years", "amends_documents"]
        null_count = 0
        total_fields = len(all_extracted_fields)

        for field in all_extracted_fields:
            value = state.get(field)
            if not value or value == "NULL" or value == "":
                null_count += 1
            elif isinstance(value, list) and len(value) == 0:
                null_count += 1

        llm_confidence = 1.0 - (null_count / total_fields)
        scores.append(llm_confidence)

        # 3. Chunk relevance (check if we got any chunks for each query)
        # amends_documents_chunks removed — amends now extracted by header_extraction.py
        chunk_fields = ["valid_from_chunks", "cohort_years_chunks"]
        chunks_found = 0
        for field in chunk_fields:
            chunks = state.get(field, [])
            if chunks and len(chunks) > 0:
                chunks_found += 1

        chunk_quality = chunks_found / len(chunk_fields) if len(chunk_fields) > 0 else 0.5
        scores.append(chunk_quality)

        # Final confidence: weighted average
        # 40% completeness + 40% LLM confidence + 20% chunk quality
        final_confidence = (
            0.4 * completeness_score +
            0.4 * llm_confidence +
            0.2 * chunk_quality
        )

        logger.info(f"Extraction confidence: {final_confidence:.2f} (completeness: {completeness_score:.2f}, llm: {llm_confidence:.2f}, chunks: {chunk_quality:.2f})")
        print(f"Extraction confidence: {final_confidence:.2f} (completeness: {completeness_score:.2f}, llm: {llm_confidence:.2f}, chunks: {chunk_quality:.2f})")

        return {"extraction_confidence": round(final_confidence, 3)}

    except Exception as e:
        logger.error(f"Error calculating confidence: {e}")
        print(f"Error calculating confidence: {e}")
        return {"extraction_confidence": 0.0}


# Pydantic model for metadata validation
class DocumentMetadata(BaseModel):
    """Validated metadata schema matching PostgreSQL table."""

    document_number: str | None = None
    document_type: str | None = None # "Quyết định", "Thông báo", etc.
    issuing_authority: str | None = None # "Hiệu trưởng", "Phòng Đào tạo"
    valid_from: str | None = None
    valid_until: str | None = None
    cohort_years: List[int | str] = Field(default_factory=list)
    cohort_scope: str = "unspecified"  # "universal", "explicit", "unspecified"
    amends_documents: List[str] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    @field_validator("valid_from", "valid_until")
    @classmethod
    def validate_date_format(cls, v):
        """Ensure dates are YYYY-MM-DD or None. Supports DD/MM/YYYY input."""
        if v is None or v == "NULL" or v == "":
            return None
        
        # Try multiple formats for user-friendliness
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(v, fmt)
                # Always convert to ISO format YYYY-MM-DD for the DB
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        
        logger.warning(f"Invalid date format: {v}, setting to None")
        print(f"Invalid date format: {v}, setting to None")
        return None

    @field_validator("cohort_years", mode="before")
    @classmethod
    def normalize_cohorts(cls, v):
        """Convert ["*"] to universal scope, validate year format."""
        if not v:
            return []
        if v == ["*"] or v == "*":
            return ["*"]

        # Convert strings to ints if possible
        normalized = []
        if isinstance(v, str):
            v = [v]

        for year in v:
            if year == "*":
                return ["*"]  # Universal scope
            if isinstance(year, int):
                normalized.append(year)
            elif isinstance(year, str):
                if year.isdigit():
                    normalized.append(int(year))
                else:
                    logger.warning(f"Invalid cohort year: {year}")
                    print(f"Invalid cohort year: {year}")

        return normalized if normalized else []

    @field_validator("cohort_scope")
    @classmethod
    def validate_cohort_scope(cls, v: str, info: ValidationInfo):
        """Auto-detect cohort_scope based on cohort_years."""
        cohort_years = info.data.get("cohort_years", [])

        if not cohort_years or len(cohort_years) == 0:
            return "unspecified"
        elif cohort_years == ["*"]:
            return "universal"
        else:
            return "explicit"


class MetadataReviewAction(BaseModel):
    """Payload for human review resume (from langgraph interrupt)."""

    action: Literal["approved", "rejected", "edited"] = Field(..., description="approved, rejected, or edited")
    feedback: str | None = Field(None, description="Human notes for the AI")
    
    # Field-level updates (Option B)
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    cohort_years: List[int | str] | None = None
    amends_documents: List[str] | None = None


def format_metadata_node(state: MetadataRAGState) -> Dict[str, Any]:
    """Validate and format metadata using Pydantic."""
    try:
        # Extract values from state
        metadata = DocumentMetadata(
            document_number=state.get("document_number"),
            document_type=state.get("document_type"),
            issuing_authority=state.get("issuing_authority"),
            valid_from=state.get("valid_from"),
            valid_until=state.get("valid_until"),
            cohort_years=state.get("cohort_years", []),
            cohort_scope=state.get("cohort_scope", "unspecified"),
            amends_documents=state.get("amends_documents", []),
            extraction_confidence=state.get("extraction_confidence", 0.0)
        )

        # Convert to dict, excluding None values
        final_metadata = metadata.model_dump(exclude_none=True)

        logger.info(f"Metadata validated and formatted: {final_metadata}")
        print(f"Metadata validated and formatted: {final_metadata}")

        return {
            "document_metadata": final_metadata,
            "temporal_extraction_complete": True,
            "success": True
        }

    except Exception as e:
        logger.error(f"Metadata validation failed: {e}")
        print(f"Metadata validation failed: {e}")
        return {
            "error": str(e),
            "success": False,
            "temporal_extraction_complete": False
        }


def cleanup_node(state: MetadataRAGState) -> Dict[str, Any]:
    """Dọn dẹp Vector DB."""
    try:
        col_name = state.get("collection_name")
        if col_name:
            CHROMA_CLIENT.delete_collection(col_name)
            logger.info(f"Deleted temp collection {col_name}")
            print(f"Deleted temp collection {col_name}")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
        print(f"Cleanup failed: {e}")
    return {}


def review_metadata_node(state: MetadataRAGState) -> Command:
    """Pause graph for human review of extracted metadata."""
    current_metadata = {
        "document_number": state.get("document_number"),
        "document_type": state.get("document_type"),
        "issuing_authority": state.get("issuing_authority"),
        "valid_from": state.get("valid_from"),
        "valid_until": state.get("valid_until"),
        "cohort_years": state.get("cohort_years", []),
        "amends_documents": state.get("amends_documents", [])
    }
    
    logger.info(f"Interrupting for metadata review. Current: {current_metadata}")
    
    # Trigger interrupt (Option B: Kill index, then interrupt is handled in graph wiring)
    decision_raw = interrupt({
        "action": "review_temporal_tags",
        "metadata": current_metadata,
        "human_feedback": state.get("human_feedback"),
        "loop_count": state.get("loop_count", 0)
    })
    
    # Validate decision
    try:
        if isinstance(decision_raw, dict):
            decision = MetadataReviewAction(**decision_raw)
        else:
            return Command(update={"error": "Invalid review format", "success": False})
    except Exception as e:
        logger.error(f"Review validation failed: {e}")
        return Command(update={"error": f"Validation error: {str(e)}", "success": False})

    # Prepare updates
    updates: Dict[str, Any] = {
        "review_status": decision.action,
        "human_feedback": decision.feedback,
        "loop_count": state.get("loop_count", 0) + 1
    }
    
    # Apply field-level edits (Option B)
    if decision.document_number is not None: updates["document_number"] = decision.document_number
    if decision.document_type is not None: updates["document_type"] = decision.document_type
    if decision.issuing_authority is not None: updates["issuing_authority"] = decision.issuing_authority
    if decision.valid_from is not None: updates["valid_from"] = decision.valid_from
    if decision.valid_until is not None: updates["valid_until"] = decision.valid_until
    if decision.cohort_years is not None: updates["cohort_years"] = decision.cohort_years
    if decision.amends_documents is not None: updates["amends_documents"] = decision.amends_documents

    logger.info(f"Resume from review with action: {decision.action}")
    return Command(update=updates)


def decide_after_review_node(state: MetadataRAGState) -> str:
    """Route after review: approve/edit -> finalize, reject -> retry/fail."""
    status = state.get("review_status")
    loop_count = state.get("loop_count", 0)
    
    if status == "rejected" and loop_count < 2: # Max 2 retries (loop_count 0 and 1)
        logger.info("Human rejected metadata. Looping back with feedback.")
        return "retry"
    
    # If approved or edited, or rejected twice, move to format/cleanup
    logger.info(f"Finalizing metadata extraction with status: {status}")
    return "finalize"
