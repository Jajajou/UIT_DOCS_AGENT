from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[2])).resolve()
DATA_DIR = PROJECT_ROOT / "data"
MINERU_DIR = DATA_DIR / "MinerU"

MINERU_BASE_URL = os.getenv("MINERU_URL", "http://localhost:8000")  

print(f"PROJECT_ROOT is set to: {PROJECT_ROOT}")
print(f"DATA_DIR is set to: {DATA_DIR}")
print(f"MINERU_DIR is set to: {MINERU_DIR}")