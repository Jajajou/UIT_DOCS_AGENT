import asyncio
import os
import argparse
import psycopg2
import json
import httpx
import sys
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from agent.config import settings
from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from agent.clients.lightrag_client import LightRAGAPIClient
from langchain.chat_models import init_chat_model

def get_pg_connection():
    # Read POSTGRES_PASSWORD from LangGraph/.env
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        password = "admin123"
        
    user = os.getenv("POSTGRES_USER", "uitrag")
    
    return psycopg2.connect(
        host='localhost',
        port=5433,
        user=user,
        password=password,
        dbname='lightrag'
    )

async def main():
    parser = argparse.ArgumentParser(description="Backfill missing temporal metadata for docs.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted, skip DB write")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N docs")
    args = parser.parse_args()

    # Load env for LLM
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    # Initialize LLM
    print(f"Initializing LLM: {os.getenv('LLM_MODEL', 'Qwen/Qwen3-4B-Instruct')}")
    llm = init_chat_model(
        model_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        model=os.getenv("LLM_MODEL", "Qwen/Qwen3-4B-Instruct"),
        streaming=False,
        temperature=0.1
    )

    agent = TemporalExtractionAgent(llm, settings)
    client = LightRAGAPIClient()

    conn = get_pg_connection()
    docs = []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lds.id AS doc_id, lds.file_path, lds.track_id, lds.metadata
                FROM lightrag_doc_status lds
                LEFT JOIN temporal_metadata tm ON tm.doc_id = lds.id
                WHERE lds.workspace = 'uit_docs_agent'
                  AND tm.doc_id IS NULL
                  AND lds.status IN ('success', 'completed', 'indexed', 'processed')
                ORDER BY lds.created_at;
            """)
            docs = cur.fetchall()
    finally:
        conn.close()

    if args.limit:
        docs = docs[:args.limit]

    print(f"Found {len(docs)} documents missing temporal metadata.")

    for doc_id, file_path, track_id, metadata_json in docs:
        print(f"\nProcessing {doc_id} ({file_path})...")
        
        # Determine filename
        filename = os.path.basename(file_path) if file_path else "unknown.pdf"
        basename = os.path.splitext(filename)[0]
        
        # Try to find content
        content = None
        
        # 1. Try DeepSeek-OCR cache (as requested in TASK-010)
        # Note: We check both data/DeepSeek-OCR and data/MinerU-OCR
        ocr_paths = [
            Path("../data/DeepSeek-OCR") / f"{basename}.txt",
            Path("../data/DeepSeek-OCR") / f"{basename}.md",
            Path("../data/MinerU-OCR") / basename / f"{basename}.md",
            Path("../data/MinerU-OCR") / basename / basename / f"{basename}.md"
        ]
        
        for p in ocr_paths:
            if p.exists():
                content = p.read_text(encoding="utf-8")
                print(f"  Using OCR cache: {p}")
                break
        
        if not content and file_path and os.path.exists(file_path):
            # Fallback: raw file (assume text/markdown or try to read as utf-8)
            try:
                with open(file_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")
                print(f"  Using raw file: {file_path}")
            except Exception as e:
                print(f"  Error reading raw file {file_path}: {e}")
        
        if not content:
            print(f"  WARNING: No content found for {doc_id}. Skipping.")
            continue

        # Extract metadata
        try:
            metadata_result = await agent.extract(content, filename, file_path)
            
            # Extract cohort info for scope computation
            cohort_years = metadata_result.get("cohort_years", [])
            cohort_scope = "unspecified"
            if cohort_years == ["*"]:
                cohort_scope = "universal"
            elif len(cohort_years) > 0:
                cohort_scope = "explicit"
            
            # Map result to expected fields for save_temporal_metadata
            meta_dict = {
                "document_number": metadata_result.get("document_number"),
                "document_type": metadata_result.get("document_type"),
                "valid_from": metadata_result.get("valid_from"),
                "valid_until": metadata_result.get("valid_until"),
                "cohort_years": cohort_years,
                "cohort_scope": cohort_scope,
                "amends_documents": metadata_result.get("amends_documents"),
                "extraction_method": metadata_result.get("temporal_extraction_method", "unknown"),
                "extraction_confidence": metadata_result.get("temporal_confidence", 0.0)
            }
            
            # Merge other fields into meta_dict (save_temporal_metadata handles additional_metadata)
            for k, v in metadata_result.items():
                if k not in meta_dict and k not in ["temporal_extraction_method", "temporal_confidence"]:
                    meta_dict[k] = v
            
            if args.dry_run:
                print(f"  [DRY-RUN] Metadata to save: {json.dumps(meta_dict, indent=2, ensure_ascii=False)}")
            else:
                res = client.save_temporal_metadata(track_id=track_id, doc_id=doc_id, metadata=meta_dict)
                if res.get("success"):
                    print(f"  Successfully saved temporal metadata for {doc_id}")
                else:
                    print(f"  ERROR saving metadata for {doc_id}: {res.get('error')}")
                    
        except Exception as e:
            print(f"  ERROR processing {doc_id}: {e}")
            import traceback
            traceback.print_exc()

    if not args.dry_run:
        print("\nBackfilling amendment links...")
        try:
            link_res = client.backfill_amendment_links()
            print(f"Link results: {json.dumps(link_res, indent=2)}")
        except Exception as e:
            print(f"ERROR backfilling amendment links: {e}")

if __name__ == "__main__":
    asyncio.run(main())
