"""
Fix Content Errors Script for Phase 2: Temporal Intelligence

This script identifies documents that failed with "only whitespace" errors,
deletes them, and re-inserts their OCR results from data/DeepSeek-OCR
as text to ensure they are fully indexed.
"""

import os
import json
import re
import sys
import asyncio
from pathlib import Path
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

# Add LangGraph/src to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "LangGraph" / "src"))

from agent.clients.lightrag_client import LightRAGAPIClient
from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from agent.config import settings

# --- Configuration ---
DEEPSEEK_OCR_DIR = ROOT / "data" / "DeepSeek-OCR"
FIRE_METADATA_PATH = ROOT / "firecrawl" / "data" / "metadata.json"
PDF_LOOKUP_PATH = ROOT / "firecrawl" / "data" / "pdf_url_lookup.json"
WORKSPACE = "uit_docs_agent"

def build_url_mapping():
    mapping = {}
    if PDF_LOOKUP_PATH.exists():
        try:
            with open(PDF_LOOKUP_PATH, 'r') as f:
                lookup = json.load(f)
                for slug, url in lookup.items():
                    mapping[slug] = url
                    mapping[f"{slug}.pdf"] = url
        except: pass
    if FIRE_METADATA_PATH.exists():
        try:
            with open(FIRE_METADATA_PATH, 'r') as f:
                metadata = json.load(f)
                for item in metadata:
                    if item.get("url", "").endswith(".pdf"):
                        url = item["url"]
                        file_path = item.get("file_path", "")
                        if file_path:
                            fname = os.path.basename(file_path)
                            mapping[fname] = url
                            slug_match = re.match(r"(.*?)-[a-f0-9]{8}\.pdf$", fname)
                            if slug_match:
                                mapping[slug_match.group(1)] = url
        except: pass
    return mapping

def find_deepseek_ocr_file(filename: str):
    base_name = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    clean_name = re.sub(r"-[a-f0-9]{8}$", "", base_name)
    folder_paths = [DEEPSEEK_OCR_DIR / base_name, DEEPSEEK_OCR_DIR / clean_name]
    for folder_path in folder_paths:
        if folder_path.exists():
            md_files = list(folder_path.glob("*.md"))
            if md_files: return md_files[0]
    matches = list(DEEPSEEK_OCR_DIR.glob(f"*{clean_name}*"))
    if matches:
        for match in matches:
            if match.is_dir():
                md_files = list(match.glob("*.md"))
                if md_files: return md_files[0]
    return None

async def fix_errors():
    print("=== Starting Content Error Fix (Delete & Re-insert) ===")
    url_mapping = build_url_mapping()
    client = LightRAGAPIClient()
    agent = TemporalExtractionAgent(None, settings)
    
    # Get current documents to check for existing processed versions
    all_docs_res = client.documents()
    processed_docs = all_docs_res.get("statuses", {}).get("processed", [])
    processed_sources = {d.get("file_path") for d in processed_docs if d.get("file_path")}
    print(f"Loaded {len(processed_sources)} processed sources from LightRAG.")
    
    # 1. Get documents with whitespace errors
    try:
        import psycopg2
        load_dotenv(ROOT / ".env.lightrag")
        conn = psycopg2.connect(
            host="localhost", port=5433,
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DATABASE", "lightrag")
        )
        with conn.cursor() as cur:
            query = "SELECT id, file_path FROM lightrag_doc_status WHERE content_summary LIKE '%%only whitespace%%' AND workspace = %s"
            cur.execute(query, (WORKSPACE,))
            error_docs = [{'id': r[0], 'file_path': r[1]} for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Error querying database: {e}")
        return

    print(f"Found {len(error_docs)} documents with whitespace errors.")
    
    for doc in error_docs:
        doc_id = doc['id']
        orig_file_path = doc['file_path']
        print(f"\nProcessing: {orig_file_path} ({doc_id})")
        
        # Determine URL
        url = url_mapping.get(orig_file_path) or url_mapping.get(re.sub(r"\.pdf$", "", orig_file_path))
        source = url or orig_file_path

        # Check if already processed as text
        if source in processed_sources:
            print(f"  ! Source already exists in 'processed' state. Deleting redundant error doc {doc_id}...")
            client.delete_document([doc_id])
            continue

        # Find OCR content
        ocr_path = find_deepseek_ocr_file(orig_file_path)
        if not ocr_path:
            print(f"  ✗ OCR not found in DeepSeek-OCR.")
            continue
            
        try:
            with open(ocr_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if not content.strip(): continue
                
            temp_meta = agent.extract_with_local_tools(content)
            
            # Metadata prep
            metadata = {
                "valid_from": temp_meta.valid_from,
                "valid_until": temp_meta.valid_until,
                "cohort_years": temp_meta.cohort_years,
                "document_number": temp_meta.document_number,
                "file_source": source,
                "fixed_from_error": True
            }

            # 1. Delete the old error document
            print(f"  → Deleting error doc {doc_id}...")
            client.delete_document([doc_id])

            # 2. Insert new text
            print(f"  → Re-inserting content...")
            result = client.insert_text(text=content, file_source=source)
            
            if result.get("status") == "success":
                new_track_id = result.get("track_id")
                print(f"  ✓ Inserted. Track ID: {new_track_id}")
                client.update_document_metadata_by_track_id(new_track_id, metadata)
            elif result.get("status") == "duplicated":
                dup_track_id = result.get("track_id")
                print(f"  ! Duplicate found: {dup_track_id}. Updating metadata...")
                client.update_document_metadata_by_track_id(dup_track_id, metadata)
            else:
                print(f"  ✗ Failed: {result}")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            
    print("\n=== Content Fix Complete ===")

if __name__ == "__main__":
    asyncio.run(fix_errors())
