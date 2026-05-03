"""
Metadata Backfill Script for Phase 2: Temporal Intelligence

This script scans existing MinerU-OCR results, re-extracts temporal metadata
using the new Phase 2 logic (VBHN, article-level, local tools), and updates
the PostgreSQL database (lightrag_doc_status and temporal_metadata).

It also maps local file paths back to their online URLs using firecrawl metadata.
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

from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from agent.config import settings

# --- Configuration ---
MINERU_OCR_DIR = ROOT / "data" / "MinerU-OCR"
FIRE_METADATA_PATH = ROOT / "firecrawl" / "data" / "metadata.json"
PDF_LOOKUP_PATH = ROOT / "firecrawl" / "data" / "pdf_url_lookup.json"
# The workspace discovered in the DB
WORKSPACE = os.getenv("WORKSPACE", "uit_docs_agent")

def get_pg_connection():
    """Create a PostgreSQL connection."""
    # Load env from the project's standard location
    load_dotenv(ROOT / ".env.lightrag")
    
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DATABASE", "lightrag")
    )

def build_url_mapping():
    """Build a mapping from filenames/slugs to online URLs."""
    mapping = {}
    
    # 1. Try pdf_url_lookup.json
    if PDF_LOOKUP_PATH.exists():
        try:
            with open(PDF_LOOKUP_PATH, 'r') as f:
                lookup = json.load(f)
                for slug, url in lookup.items():
                    mapping[slug] = url
                    mapping[f"{slug}.pdf"] = url
        except Exception as e:
            print(f"Error loading PDF lookup: {e}")

    # 2. Augment with metadata.json
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
                            # Also map without hash if possible
                            slug_match = re.match(r"(.*?)-[a-f0-9]{8}\.pdf$", fname)
                            if slug_match:
                                mapping[slug_match.group(1)] = url
        except Exception as e:
            print(f"Error loading metadata.json: {e}")
            
    return mapping

def find_ocr_files():
    """Find all .md files in the MinerU-OCR directory."""
    ocr_files = []
    for root, dirs, files in os.walk(MINERU_OCR_DIR):
        for file in files:
            if file.endswith(".md"):
                ocr_files.append(Path(root) / file)
    return ocr_files

async def backfill():
    print("=== Starting Metadata Backfill ===")
    print(f"Using WORKSPACE: {WORKSPACE}")
    
    url_mapping = build_url_mapping()
    print(f"Built URL mapping with {len(url_mapping)} entries.")
    
    ocr_files = find_ocr_files()
    print(f"Found {len(ocr_files)} OCR result files.")
    
    agent = TemporalExtractionAgent(None, settings)
    conn = get_pg_connection()
    
    success_count = 0
    skipped_count = 0
    
    for ocr_path in ocr_files:
        try:
            # 1. Read OCR content
            with open(ocr_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 2. Identify document info
            filename = ocr_path.stem 
            url = url_mapping.get(f"{filename}.pdf") or url_mapping.get(filename)

            # 3. Extract metadata using local tools
            temp_meta = agent.extract_with_local_tools(content)
            
            # --- IMPROVED: Document Number Hint from Filename ---
            file_num_match = re.match(r"^(\d+)[-_](qd|tb)[-_](dhcntt|dhqg)", filename, re.IGNORECASE)
            if file_num_match:
                file_doc_num = f"{file_num_match.group(1)}/{file_num_match.group(2).upper()}-{file_num_match.group(3).upper()}"
                if not temp_meta.document_number or "/20" in temp_meta.document_number or temp_meta.document_number.startswith("..."):
                    temp_meta.document_number = file_doc_num

            # --- IMPROVED: Cohort Expansion Onwards ---
            # Extract base cohorts first
            found_cohorts = [c for c in temp_meta.cohort_years if isinstance(c, int)]
            
            # Check for "từ năm" or "trở đi" patterns in content
            # e.g. "áp dụng cho các khóa tuyển sinh từ năm 2017"
            onwards_match = re.search(r"(khóa|tuyển sinh|áp dụng).*?từ năm\s*(\d{4})", content, re.IGNORECASE)
            if onwards_match:
                start_year = int(onwards_match.group(2))
                found_cohorts.append(start_year)
                current_year = datetime.now().year
                expanded = list(range(start_year, current_year + 7))
                temp_meta.cohort_years = sorted(set(expanded))
                print(f"  [COHORT] Onwards expansion detected: {start_year}+")
            elif found_cohorts:
                expanded_cohorts = []
                for cohort in found_cohorts:
                    expanded_cohorts.extend(range(cohort, cohort + 6))
                temp_meta.cohort_years = sorted(set(expanded_cohorts))
            
            # Build search terms for matching
            search_terms = [f"{filename}.pdf", filename]
            if url:
                search_terms.append(url)
            
            # Handle encoded characters
            if "%20" in filename:
                search_terms.append(filename.replace("%20", " "))
            if " " in filename:
                search_terms.append(filename.replace(" ", "%20"))

            # Find in DB
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Exact match on URL or filename
                query = """
                SELECT id, file_path, metadata 
                FROM lightrag_doc_status 
                WHERE workspace = %s 
                AND file_path = ANY(%s)
                LIMIT 1
                """
                cur.execute(query, (WORKSPACE, search_terms))
                doc = cur.fetchone()
                
                # 2. LIKE match if not found
                if not doc:
                    # Clean filename for LIKE match (remove hash if present)
                    clean_name = re.sub(r"-[a-f0-9]{8}$", "", filename)
                    cur.execute(
                        "SELECT id, file_path, metadata FROM lightrag_doc_status WHERE workspace = %s AND file_path LIKE %s LIMIT 1",
                        (WORKSPACE, f"%{clean_name}%")
                    )
                    doc = cur.fetchone()

                # 3. Match by document number if extracted
                if not doc and temp_meta.document_number:
                    cur.execute(
                        "SELECT id, file_path, metadata FROM lightrag_doc_status WHERE workspace = %s AND metadata->>'document_number' = %s LIMIT 1",
                        (WORKSPACE, temp_meta.document_number)
                    )
                    doc = cur.fetchone()

                if doc:
                    doc_id = doc['id']
                    # 4. Update Database
                    current_metadata = doc['metadata'] or {}
                    
                    updates = {
                        "valid_from": temp_meta.valid_from,
                        "valid_until": temp_meta.valid_until,
                        "academic_year": temp_meta.academic_year,
                        "cohort_years": temp_meta.cohort_years,
                        "document_type": temp_meta.document_type,
                        "document_number": temp_meta.document_number,
                        "is_vbhn": temp_meta.is_vbhn,
                        "amended_articles": temp_meta.amended_articles,
                        "amends_documents": temp_meta.amends_documents,
                        "temporal_extraction_method": "backfill_local_tools",
                        "temporal_confidence": temp_meta.confidence,
                        "temporal_reasoning": temp_meta.reasoning,
                        "updated_at": datetime.now().isoformat()
                    }
                    if url:
                        updates["file_source"] = url
                        
                    current_metadata.update(updates)
                    
                    cur.execute(
                        "UPDATE lightrag_doc_status SET metadata = %s WHERE id = %s",
                        (Json(current_metadata), doc_id)
                    )
                    
                    # Update/Insert temporal_metadata table
                    cur.execute(
                        "SELECT id FROM temporal_metadata WHERE doc_id = %s AND workspace = %s",
                        (doc_id, WORKSPACE)
                    )
                    exists = cur.fetchone()
                    
                    if exists:
                        cur.execute(
                            """
                            UPDATE temporal_metadata SET
                                valid_from = %s, valid_until = %s, academic_year = %s,
                                cohort_years = %s, document_type = %s, document_number = %s,
                                amends_documents = %s, is_archived = %s, temporal_confidence = %s,
                                extraction_method = %s, updated_at = %s,
                                additional_metadata = additional_metadata || %s::jsonb
                            WHERE doc_id = %s AND workspace = %s
                            """,
                            (
                                temp_meta.valid_from, temp_meta.valid_until, temp_meta.academic_year,
                                Json(temp_meta.cohort_years), temp_meta.document_type, temp_meta.document_number,
                                Json(temp_meta.amends_documents), False, temp_meta.confidence,
                                "backfill_local_tools", datetime.now(),
                                Json({"is_vbhn": temp_meta.is_vbhn, "amended_articles": temp_meta.amended_articles}),
                                doc_id, WORKSPACE
                            )
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO temporal_metadata (
                                doc_id, workspace, valid_from, valid_until, academic_year,
                                cohort_years, document_type, document_number, amends_documents,
                                is_archived, temporal_confidence, extraction_method, created_at, updated_at,
                                additional_metadata
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                doc_id, WORKSPACE, temp_meta.valid_from, temp_meta.valid_until, temp_meta.academic_year,
                                Json(temp_meta.cohort_years), temp_meta.document_type, temp_meta.document_number,
                                Json(temp_meta.amends_documents), False, temp_meta.confidence,
                                "backfill_local_tools", datetime.now(), datetime.now(),
                                Json({"is_vbhn": temp_meta.is_vbhn, "amended_articles": temp_meta.amended_articles})
                            )
                        )
                    
                    conn.commit()
                    success_count += 1
                    # print(f"✓ Backfilled: {filename} -> {doc_id} (Doc: {temp_meta.document_number})")
                else:
                    skipped_count += 1
                    
        except Exception as e:
            print(f"✗ Error processing {ocr_path}: {e}")
            skipped_count += 1
            conn.rollback()
            
    conn.close()
    print(f"=== Backfill Complete: {success_count} success, {skipped_count} skipped ===")

if __name__ == "__main__":
    asyncio.run(backfill())
