from pathlib import Path
import os
import yaml
from contextvars import ContextVar
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional

# Load environment variables from .env file
load_dotenv()

# --- Context-local configuration for thread-safety ---
# This allows overriding settings per-request without global mutation
_config_overrides: ContextVar[Dict[str, Any]] = ContextVar("config_overrides", default={})

# --- Project Paths ---
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[2])).resolve()
DATA_DIR = PROJECT_ROOT / "data"
MINERU_OCR_DIR = DATA_DIR / "MinerU2.5_ocr_rerun"

# --- Load YAML Configuration ---
_config_yaml_path = Path(__file__).parent / "config.yaml"
with open(_config_yaml_path, 'r', encoding='utf-8') as f:
    _yaml_config = yaml.safe_load(f)

# --- Pydantic Config Models ---
class MinerUOCRConfig(BaseModel):
    model_name: str
    skip_repeat: bool = True
    # Remote OCR service URL (e.g. https://xxx.ngrok-free.app). When set,
    # mineru_ocr_client sends pages over HTTP instead of running MLX locally.
    api_url: Optional[str] = None

class QueryThresholdsConfig(BaseModel):
    query_confidence_threshold: float
    overall_confidence_threshold: float
    fallback_confidence_threshold: float

class RetrievalConfig(BaseModel):
    default_mode: Literal["naive", "local", "global", "hybrid", "mix"]
    default_top_k: int
    default_chunk_top_k: int

class RerankerConfig(BaseModel):
    default_model: str
    top_n_for_confidence: int
    use_fp16: bool
    batch_size: int
    normalize_scores: bool
    max_length: int

class TemporalConfig(BaseModel):
    enabled: bool
    recency_weight: float
    freshness_thresholds: Dict[str, int]
    quality_penalties: Dict[str, float]
    versioning: Dict[str, Any]
    date_extraction: Dict[str, Any] = {}
    # Cohort-aware reranking weights
    cohort_weight: float = 0.25
    semantic_weight_cohort: float = 0.55
    temporal_weight_cohort: float = 0.20

class Config(BaseModel):
    """Main configuration class for the application."""
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    mineru_ocr_dir: Path = MINERU_OCR_DIR

    # Loaded from config.yaml
    mineru_ocr: MinerUOCRConfig
    query_thresholds: QueryThresholdsConfig
    retrieval: RetrievalConfig
    reranker: RerankerConfig
    temporal: TemporalConfig

    # Environment variables
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507"))
    indexing_llm_model: str = Field(default_factory=lambda: os.getenv("INDEXING_LLM_MODEL", os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")))
    agent1_temperature: float = Field(default_factory=lambda: float(os.getenv("AGENT1_TEMPERATURE", "0.1")))
    agent3_temperature: float = Field(default_factory=lambda: float(os.getenv("AGENT3_TEMPERATURE", "0.3")))
    lightrag_url: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_URL"))
    lightrag_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_API_KEY"))
    lightrag_access_token: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_ACCESS_TOKEN"))

    # Embedding configuration
    embedding_base_url: Optional[str] = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "http://localhost:8000/v1"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "AITeamVN/Vietnamese_Embedding_v2"))
    embedding_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", "EMPTY"))
    reranker_base_url: Optional[str] = Field(
        default_factory=lambda: os.getenv("RERANKER_BASE_URL")
    )
    
    # Flags with ContextVar override support
    @property
    def use_cohort_boost(self) -> bool:
        overrides = _config_overrides.get()
        if "use_cohort_boost" in overrides:
            return overrides["use_cohort_boost"]
        return os.getenv("USE_COHORT_BOOST", "true").lower() != "false"

    @property
    def use_temporal_scoring(self) -> bool:
        overrides = _config_overrides.get()
        if "use_temporal_scoring" in overrides:
            return overrides["use_temporal_scoring"]
        return os.getenv("USE_TEMPORAL_SCORING", "true").lower() != "false"

    @property
    def use_amendment_override(self) -> bool:
        overrides = _config_overrides.get()
        if "use_amendment_override" in overrides:
            return overrides["use_amendment_override"]
        return os.getenv("USE_AMENDMENT_OVERRIDE", "false").lower() == "true"

    @property
    def use_metadata_routing(self) -> bool:
        overrides = _config_overrides.get()
        if "use_metadata_routing" in overrides:
            return overrides["use_metadata_routing"]
        return os.getenv("USE_METADATA_ROUTING", "true").lower() != "false"

    class Config:
        arbitrary_types_allowed = True

# Initialize settings
settings = Config(
    mineru_ocr=_yaml_config.get("mineru_ocr", {}),
    query_thresholds=_yaml_config.get("query_thresholds", {}),
    retrieval=_yaml_config.get("retrieval", {}),
    reranker=_yaml_config.get("reranker", {}),
    temporal=_yaml_config.get("temporal", {})
)

def set_config_overrides(overrides: Dict[str, Any]) -> Any:
    """Set per-request config overrides. Returns a token for reset."""
    return _config_overrides.set(overrides)

def reset_config_overrides(token: Any) -> None:
    """Reset config overrides using a token."""
    _config_overrides.reset(token)

def get_attr_safe(obj: Any, attr: str, default: Any = None) -> Any:
    """
    Safely retrieves an attribute from a BaseModel or a dict.

    Works for:
    - Pydantic BaseModel instances
    - Dicts
    - Nested attributes using dot notation ("a.b.c")
    """
    try:
        if obj is None:
            return default

        # Support nested keys
        parts = attr.split(".")
        value = obj
        for part in parts:
            if isinstance(value, BaseModel):
                value = getattr(value, part, default)
            elif isinstance(value, dict):
                value = value.get(part, default)
            else:
                return default
        return value
    except Exception:
        return default
