from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional

# Load environment variables from .env file
load_dotenv()

# --- Project Paths ---
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[2])).resolve()
DATA_DIR = PROJECT_ROOT / "data"
DEEPSEEK_OCR_DIR = DATA_DIR / "DeepSeek-OCR"

# --- Load YAML Configuration ---
_config_yaml_path = Path(__file__).parent / "config.yaml"
with open(_config_yaml_path, 'r', encoding='utf-8') as f:
    _yaml_config = yaml.safe_load(f)

# --- Pydantic Config Models ---
class DeepSeekOCRConfig(BaseModel):
    model_name: str
    model_configs: Dict[str, Any]
    task_prompts: Dict[str, Any]
    skip_repeat: bool

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

class Config(BaseModel):
    """Main configuration class for the application."""
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    deepseek_ocr_dir: Path = DEEPSEEK_OCR_DIR

    # Loaded from config.yaml
    deepseek_ocr: DeepSeekOCRConfig
    query_thresholds: QueryThresholdsConfig
    retrieval: RetrievalConfig
    reranker: RerankerConfig
    temporal: TemporalConfig

    # Environment variables
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507"))
    agent1_temperature: float = Field(default_factory=lambda: float(os.getenv("AGENT1_TEMPERATURE", "0.1")))
    agent2_temperature: float = Field(default_factory=lambda: float(os.getenv("AGENT2_TEMPERATURE", "0.2")))
    agent3_temperature: float = Field(default_factory=lambda: float(os.getenv("AGENT3_TEMPERATURE", "0.3")))
    lightrag_url: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_URL"))
    lightrag_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_API_KEY"))
    lightrag_access_token: Optional[str] = Field(default_factory=lambda: os.getenv("LIGHTRAG_ACCESS_TOKEN"))
    
    class Config:
        arbitrary_types_allowed = True

# Initialize settings
settings = Config(
    deepseek_ocr=_yaml_config.get("deepseek_ocr", {}),
    query_thresholds=_yaml_config.get("query_thresholds", {}),
    retrieval=_yaml_config.get("retrieval", {}),
    reranker=_yaml_config.get("reranker", {}),
    temporal=_yaml_config.get("temporal", {})
)

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
