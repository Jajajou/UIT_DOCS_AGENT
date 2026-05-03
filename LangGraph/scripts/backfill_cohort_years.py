"""
Backfill cohort_years for docs with empty cohort metadata.

Uses metadata RAG subgraph to extract cohort_years from document content.

Usage:
    cd LangGraph
    python scripts/backfill_cohort_years.py [--dry-run] [--limit N]
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

from agent.clients.lightrag_client import LightRAGAPIClient
from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from agent.config import settings
from langchain.chat_models import init_chat_model


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        database=os.getenv("POSTGRES_DATABASE", "lightrag"),
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
    )


def get_target_docs(limit=None):
    """Get docs with empty cohort_years and valid file_path."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT tm.doc_id, lds.file_path
                FROM temporal_metadata tm
                LEFT JOIN lightrag_doc_status lds ON tm.track_id = lds.track_id
                WHERE tm.workspace = 'uit_docs_agent'
                  AND (tm.cohort_years IS NULL OR tm.cohort_years::text IN ('[]', 'null', ''))
                  AND lds.file_path IS NOT NULL
                  AND lds.file_path NOT IN ('', 'no-file-path', 'unknown_source')
                  AND lds.file_path LIKE '%.pdf'
                ORDER BY tm.doc_id
            """
            if limit:
                query += f" LIMIT {limit}"

            cur.execute(query)
            return cur.fetchall()
    finally:
        conn.close()


def load_ocr_content(file_path: str) -> str:
    """Load OCR content from MinerU-OCR directory."""
    ocr_dir = Path(__file__).parent.parent.parent / "data" / "MinerU-OCR"

    # Extract filename from file_path
    if file_path.startswith("http"):
        # URL - extract filename from last segment
        filename = file_path.rstrip("/").split("/")[-1]
    else:
        filename = Path(file_path).name

    # Remove .pdf extension
    base_name = filename.replace(".pdf", "")

    # MinerU creates nested structure: base_name/base_name/base_name.md
    md_file = ocr_dir / base_name / base_name / f"{base_name}.md"
    if md_file.exists():
        return md_file.read_text(encoding="utf-8")

    # Try without hash suffix
    import re
    clean_name = re.sub(r"-[a-f0-9]{8}$", "", base_name)
    md_file = ocr_dir / clean_name / clean_name / f"{clean_name}.md"
    if md_file.exists():
        return md_file.read_text(encoding="utf-8")

    return None


async def backfill_cohort(doc_id: str, file_path: str, dry_run: bool = False):
    """Extract cohort_years and update DB."""
    print(f"\n[{doc_id}] Loading OCR content for {file_path}...")

    # Load from MinerU-OCR
    content = load_ocr_content(file_path)
    if not content:
        print(f"[{doc_id}] ✗ No OCR content found")
        return False

    print(f"[{doc_id}] Extracting cohort metadata...")

    # Initialize LLM and TemporalExtractionAgent
    llm = init_chat_model(
        model_provider="openai",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.indexing_llm_model,
        streaming=False,
        temperature=0.1,
        model_kwargs={"tool_choice": "none"}
    )

    agent = TemporalExtractionAgent(llm, settings)

    # Extract metadata using TemporalExtractionAgent
    try:
        metadata = await agent.extract(
            content=content,
            filename=Path(file_path).name,
            file_source=file_path
        )
    except Exception as e:
        print(f"[{doc_id}] ✗ Extraction failed: {e}")
        return False

    cohort_years = metadata.get("cohort_years", [])
    confidence = metadata.get("temporal_confidence", 0.0)

    print(f"[{doc_id}] Extracted cohort_years: {cohort_years} (confidence: {confidence:.2f})")

    if dry_run:
        print(f"[{doc_id}] DRY RUN - would update cohort_years")
        return True

    # Update PostgreSQL
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE temporal_metadata
                SET cohort_years = %s,
                    temporal_confidence = GREATEST(temporal_confidence, %s)
                WHERE doc_id = %s
            """, (Json(cohort_years), confidence, doc_id))
            conn.commit()
            print(f"[{doc_id}] ✓ Updated PostgreSQL")
    finally:
        conn.close()

    return True


async def main():
    parser = argparse.ArgumentParser(description="Backfill cohort_years metadata")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--limit", type=int, help="Process only N docs")
    args = parser.parse_args()

    print("=== Cohort Years Backfill ===")
    print(f"Dry run: {args.dry_run}")

    docs = get_target_docs(limit=args.limit)
    print(f"Found {len(docs)} docs with empty cohort_years")

    if not docs:
        print("Nothing to backfill")
        return

    success = 0
    failed = 0

    for doc_id, file_path in docs:
        try:
            ok = await backfill_cohort(doc_id, file_path, dry_run=args.dry_run)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[{doc_id}] ✗ Error: {e}")
            failed += 1

    print(f"\n=== Summary ===")
    print(f"Success: {success}")
    print(f"Failed: {failed}")
    print(f"Total: {len(docs)}")


if __name__ == "__main__":
    asyncio.run(main())
