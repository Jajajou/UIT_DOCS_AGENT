import os
import uuid
import logging
import json
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime

# LangChain & Models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb
from chromadb.config import Settings
import numpy as np

# Internal
from ..states.metadata_rag_state import MetadataRAGState
from ..core.prompts import METADATA_PROMPTS
from langchain.chat_models import init_chat_model
from agent.config import get_attr_safe, settings
from pydantic import BaseModel, Field, validator

llm = init_chat_model(
    model_provider="openai",
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    model=settings.llm_model,
    streaming=False,
    temperature=settings.agent2_temperature,
    model_kwargs={"tool_choice": "none"}
)

# Setup Logging
logger = logging.getLogger(__name__)

# --- GLOBAL MODELS (Singleton Pattern) ---
# Load 1 lần để tránh tốn RAM mỗi khi gọi node
# Trong production có thể để lazy loading hoặc dependency injection
try:
    logger.info("Loading Embedding Model: AITeamVN/Vietnamese_Embedding_V2...")
    EMBEDDING_MODEL = SentenceTransformer("AITeamVN/Vietnamese_Embedding_V2")

    logger.info("Loading Reranker Model: namdp-ptit/ViRanker...")
    RERANKER_MODEL = CrossEncoder("namdp-ptit/ViRanker")

    # ChromaDB In-Memory Client
    CHROMA_CLIENT = chromadb.Client(Settings(
        anonymized_telemetry=False,
        allow_reset=True,
        is_persistent=False
    ))
    logger.info("Models & Vector DB Loaded Successfully.")
except Exception as e:
    logger.error(f"Error loading models: {e}")
    raise e



# --- NODES IMPLEMENTATION ---

def chunk_document_node(state: MetadataRAGState) -> MetadataRAGState:
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
        
        return {
            "chunks": chunks,
            "chunk_count": len(chunks)
        }
    except Exception as e:
        logger.error(f"Error chunking: {e}")
        return {"error": str(e), "success": False}

def index_to_vector_db_node(state: MetadataRAGState) -> MetadataRAGState:
    """Embed chunks và lưu vào ChromaDB in-memory tạm thời."""
    try:
        chunks = state["chunks"]
        if not chunks:
            return {"error": "No chunks to index", "success": False}
            
        # Tạo tên collection unique cho session này
        clean_source = ''.join(e for e in state['file_source'] if e.isalnum())[-10:]
        collection_name = f"temp_{uuid.uuid4().hex[:8]}_{clean_source}"
        
        collection = CHROMA_CLIENT.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Embedding (Batch processing)
        logger.info("Generating embeddings...")
        embeddings = EMBEDDING_MODEL.encode(chunks, show_progress_bar=False)
        
        # Add to Chroma
        ids = [f"id_{i}" for i in range(len(chunks))]
        collection.add(
            documents=chunks,
            embeddings=embeddings.tolist(),
            ids=ids
        )
        
        logger.info(f"Indexed {len(chunks)} chunks to collection '{collection_name}'")
        return {"collection_name": collection_name}
        
    except Exception as e:
        logger.error(f"Error indexing: {e}")
        return {"error": str(e), "success": False}

def _rag_retrieve_and_rerank(collection_name: str, query: str, top_k_retrieve=50, top_k_rerank=5) -> List[str]:
    """Helper function: Retrieve (Bi-encoder) -> Rerank (Cross-encoder)."""
    collection = CHROMA_CLIENT.get_collection(collection_name)
    
    # 1. Bi-encoder Retrieval
    query_vec = EMBEDDING_MODEL.encode([query])[0].tolist()
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k_retrieve
    )
    
    candidates = results['documents'][0]
    if not candidates:
        return []
        
    # 2. Cross-encoder Reranking
    # Tạo pairs (query, doc)
    pairs = [[query, doc] for doc in candidates]
    scores = RERANKER_MODEL.predict(pairs)
    
    # Sort & take top K
    # scores là numpy array, cần sort index
    sorted_indices = np.argsort(scores)[::-1][:top_k_rerank]
    top_docs = [candidates[i] for i in sorted_indices]
    
    return top_docs

def query_metadata_fields_node(state: MetadataRAGState) -> MetadataRAGState:
    """
    Node tổng hợp: Query tất cả các trường metadata.
    Gộp lại 1 node để tránh overhead chuyển state quá nhiều, 
    nhưng vẫn đảm bảo logic tách biệt.
    """
    try:
        col_name = state["collection_name"]
        # llm = get_llm_client() # Hàm này bạn đã có
        updates = {}
        
        # --- 1. Document Number ---
        q_doc = "Số hiệu văn bản, số quyết định, số thông báo"
        docs_num = _rag_retrieve_and_rerank(col_name, q_doc)
        updates["document_number_chunks"] = docs_num
        
        # LLM Extract
        context_num = "\n---\n".join(docs_num)
        prompt_num = f"{METADATA_PROMPTS['document_number']}\n\nCONTEXT:\n{context_num}"
        res_num = llm.invoke(prompt_num)
        # Extract content from response
        content = res_num.content if hasattr(res_num, 'content') else str(res_num)
        updates["document_number"] = content.strip().replace("NULL", "").strip() or None
        
        # --- 2. Valid Dates (Temporal Aware) ---
        q_date = "Ngày hiệu lực, ngày ký, ngày ban hành, ngày hết hạn"
        docs_date = _rag_retrieve_and_rerank(col_name, q_date)
        updates["valid_from_chunks"] = docs_date
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt_date = METADATA_PROMPTS['valid_dates'].format(
            current_date=current_date,
            context="\n---\n".join(docs_date)
        )
        res_date = llm.invoke(prompt_date)
        content_date = res_date.content if hasattr(res_date, 'content') else str(res_date)

        # Ensure content_date is a string
        if not isinstance(content_date, str):
            content_date = str(content_date)

        # Try to parse JSON from response
        import json
        import re
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
            updates["valid_from"] = None
            updates["valid_until"] = None
        
        # --- 3. Cohorts ---
        q_cohort = "Áp dụng cho khóa sinh viên nào? Khóa tuyển sinh năm bao nhiêu? Đối tượng áp dụng?"
        docs_cohort = _rag_retrieve_and_rerank(col_name, q_cohort)
        updates["cohort_years_chunks"] = docs_cohort

        # Use current_date for temporal awareness (already defined above)
        prompt_cohort = METADATA_PROMPTS['cohorts'].format(
            current_date=current_date,
            context="\n---\n".join(docs_cohort)
        )
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
            updates["cohort_years"] = []
            updates["cohort_scope"] = "unspecified"
        
        # --- 4. Amends ---
        q_amends = "Văn bản này sửa đổi, bổ sung, thay thế văn bản nào?"
        docs_amends = _rag_retrieve_and_rerank(col_name, q_amends)
        updates["amends_documents_chunks"] = docs_amends

        # LLM Extract for amendments
        if docs_amends:
            context_amends = "\n---\n".join(docs_amends)
            prompt_amends = f"""
Bạn là chuyên gia pháp lý. Xác định văn bản nào được sửa đổi/bổ sung bởi văn bản này.

Nội dung:
{context_amends}

Tìm số hiệu các văn bản được sửa đổi (VD: "108/QĐ-ĐHCNTT", "141/TB-KHTC").
- Nếu tìm thấy: trả về list JSON: {{"amends_documents": ["108/QĐ-ĐHCNTT", "141/TB-KHTC"]}}
- Nếu không tìm thấy: {{"amends_documents": []}}
"""
            try:
                res_amends = llm.invoke(prompt_amends)
                content_amends = res_amends.content if hasattr(res_amends, 'content') else str(res_amends)

                # Ensure content is string
                if not isinstance(content_amends, str):
                    content_amends = str(content_amends)

                # Try to find JSON in response
                json_match = re.search(r'\{.*"amends_documents".*\}', content_amends.strip(), re.DOTALL)
                if json_match:
                    amends_data = json.loads(json_match.group())
                    updates["amends_documents"] = amends_data.get("amends_documents", [])
                else:
                    # Fallback: regex search for document numbers
                    doc_numbers = re.findall(r'\d+/[A-ZĐ\-]+', context_amends)
                    updates["amends_documents"] = list(set(doc_numbers))[:5]  # Limit to 5 unique
            except Exception as e:
                logger.warning(f"Error extracting amends: {e}")
                updates["amends_documents"] = []
        else:
            updates["amends_documents"] = []

        return updates
        
    except Exception as e:
        logger.error(f"Error querying metadata: {e}")
        return {"error": str(e)}

def calculate_confidence_node(state: MetadataRAGState) -> MetadataRAGState:
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
        chunk_fields = ["document_number_chunks", "valid_from_chunks", "cohort_years_chunks", "amends_documents_chunks"]
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

        return {"extraction_confidence": round(final_confidence, 3)}

    except Exception as e:
        logger.error(f"Error calculating confidence: {e}")
        return {"extraction_confidence": 0.0}


# Pydantic model for metadata validation
class DocumentMetadata(BaseModel):
    """Validated metadata schema matching PostgreSQL table."""

    document_number: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    cohort_years: List[int | str] = Field(default_factory=list)
    cohort_scope: str = "unspecified"  # "universal", "explicit", "unspecified"
    amends_documents: List[str] = Field(default_factory=list)
    temporal_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    @validator("valid_from", "valid_until")
    def validate_date_format(cls, v):
        """Ensure dates are YYYY-MM-DD or None."""
        if v is None or v == "NULL" or v == "":
            return None
        try:
            # Try to parse the date to validate format
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except (ValueError, TypeError):
            logger.warning(f"Invalid date format: {v}, setting to None")
            return None

    @validator("cohort_years", pre=True)
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

        return normalized if normalized else []

    @validator("cohort_scope")
    def validate_cohort_scope(cls, v, values):
        """Auto-detect cohort_scope based on cohort_years."""
        cohort_years = values.get("cohort_years", [])

        if not cohort_years or len(cohort_years) == 0:
            return "unspecified"
        elif cohort_years == ["*"]:
            return "universal"
        else:
            return "explicit"


def format_metadata_node(state: MetadataRAGState) -> MetadataRAGState:
    """Validate and format metadata using Pydantic."""
    try:
        # Extract values from state
        metadata = DocumentMetadata(
            document_number=state.get("document_number"),
            valid_from=state.get("valid_from"),
            valid_until=state.get("valid_until"),
            cohort_years=state.get("cohort_years", []),
            cohort_scope=state.get("cohort_scope", "unspecified"),
            amends_documents=state.get("amends_documents", []),
            temporal_confidence=state.get("extraction_confidence", 0.0)
        )

        # Convert to dict, excluding None values
        final_metadata = metadata.dict(exclude_none=True)

        logger.info(f"Metadata validated and formatted: {final_metadata}")

        return {
            "final_metadata": final_metadata,
            "success": True
        }

    except Exception as e:
        logger.error(f"Metadata validation failed: {e}")
        return {
            "error": str(e),
            "success": False
        }


def cleanup_node(state: MetadataRAGState) -> MetadataRAGState:
    """Dọn dẹp Vector DB."""
    try:
        col_name = state.get("collection_name")
        if col_name:
            CHROMA_CLIENT.delete_collection(col_name)
            logger.info(f"Deleted temp collection {col_name}")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
    return {"success": True}