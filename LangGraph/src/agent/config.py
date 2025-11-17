from pathlib import Path
import os
from dotenv import load_dotenv

from pydantic import BaseModel
from typing import Any

load_dotenv()
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[2])).resolve()
DATA_DIR = PROJECT_ROOT / "data"
DEEPSEEK_OCR_DIR = DATA_DIR / "DeepSeek-OCR"

MODEL_NAME = "mlx-community/DeepSeek-OCR-8bit"

MODEL_CONFIGS = {
    "Gundam": {"base_size": 1024, "image_size": 640, "crop_mode": True},
    "Tiny": {"base_size": 512, "image_size": 512, "crop_mode": False},
    "Small": {"base_size": 640, "image_size": 640, "crop_mode": False},
    "Base": {"base_size": 1024, "image_size": 1024, "crop_mode": False},
    "Large": {"base_size": 1280, "image_size": 1280, "crop_mode": False}
}

TASK_PROMPTS = {
    "Markdown": {"prompt": "<|grounding|>Convert the document to markdown.", "has_grounding": True},
    "Free OCR": {"prompt": "Free OCR.", "has_grounding": False},
    "Locate": {"prompt": "Locate <|ref|>text<|/ref|> in the image.", "has_grounding": True},
    "Describe": {"prompt": "Describe this image in detail.", "has_grounding": False},
    "Custom": {"prompt": "", "has_grounding": False}
}
SKIP_REPEAT = True


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
