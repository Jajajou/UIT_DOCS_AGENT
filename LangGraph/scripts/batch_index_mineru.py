#!/usr/bin/env python3
"""
Batch indexer: reads MinerU2.5_ocr_rerun MDs, builds URLs, runs full
temporal extraction + LightRAG upload for each doc.

Usage (from LangGraph/):
    python scripts/batch_index_mineru.py [--dry-run] [--limit N] [--skip N]
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from agent.config import settings
from agent.clients.lightrag_client import LightRAGAPIClient as LightRAGClient
from agent.utils import get_url

OCR_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/data/MinerU2.5_ocr_rerun")
PDF_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa")


def find_pdf(stem: str) -> Path | None:
    """Find PDF by stem (exact or with hash suffix)."""
    # Exact match first
    exact = PDF_DIR.rglob(f"{stem}.pdf")
    for p in exact:
        return p
    # Hash-stripped match: stem may have -xxxxxxxx suffix stripped
    for p in PDF_DIR.rglob("*.pdf"):
        candidate = p.stem
        # strip 8-char hex suffix
        stripped = candidate
        if len(candidate) > 9 and candidate[-9] == "-":
            stripped = candidate[:-9]
        if stripped == stem or candidate == stem:
            return p
    return None


def find_md(stem: str) -> Path | None:
    """Find .md in MinerU2.5_ocr_rerun/<stem>/**/*.md"""
    stem_dir = OCR_DIR / stem
    if not stem_dir.exists():
        return None
    mds = list(stem_dir.rglob("*.md"))
    if not mds:
        return None
    return max(mds, key=lambda f: f.stat().st_mtime)


async def process_one(
    stem: str,
    client: LightRAGClient,
    dry_run: bool = False,
) -> dict:
    md_path = find_md(stem)
    if not md_path:
        return {"stem": stem, "status": "no_md"}

    pdf_path = find_pdf(stem)
    url = get_url(str(pdf_path)) if pdf_path else None

    if not url:
        # Fallback: construct from stem pattern
        # strip hash suffix for URL
        base = stem
        if len(stem) > 9 and stem[-9] == "-":
            base = stem[:-9]
        url = f"https://daa.uit.edu.vn/sites/daa/files/{base}.pdf"

    md_content = md_path.read_text(encoding="utf-8", errors="ignore")

    if dry_run:
        print(f"  [DRY] {stem[:60]} -> url={url} ({len(md_content):,} chars)")
        return {"stem": stem, "status": "dry_run", "url": url, "chars": len(md_content)}

    # Upload to LightRAG
    try:
        result = client.insert_text(text=md_content, file_source=url)
        track_id = result.get("track_id", "")
        print(f"  [OK] {stem[:55]} track={track_id}")
    except Exception as e:
        print(f"  [FAIL] {stem[:55]} upload: {e}")
        return {"stem": stem, "status": "upload_fail", "error": str(e)}

    # Temporal metadata extraction (runs independently, uses track_id)
    if not track_id:
        return {"stem": stem, "status": "no_track_id", "url": url}

    try:
        from agent.graphs.indexing_graph import extract_temporal_metadata_rag
        from agent.states.indexing_state import IndexingState

        state: IndexingState = {
            "parsed_content": md_content,
            "file_source": url,
            "current_file_path": str(pdf_path) if pdf_path else str(md_path),
            "track_id": track_id,
            "doc_id": "",
            "messages": [],
        }
        await extract_temporal_metadata_rag(state)
        print(f"  [META] temporal extraction done: {stem[:50]}")
    except Exception as e:
        print(f"  [WARN] temporal extraction failed: {e}")

    return {"stem": stem, "status": "ok", "track_id": track_id, "url": url}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max docs to process (0=all)")
    parser.add_argument("--skip", type=int, default=0, help="Skip first N docs")
    args = parser.parse_args()

    stems = sorted(d.name for d in OCR_DIR.iterdir() if d.is_dir())
    print(f"Found {len(stems)} stems in MinerU2.5_ocr_rerun")

    if args.skip:
        stems = stems[args.skip:]
        print(f"Skipping first {args.skip} -> {len(stems)} remaining")
    if args.limit:
        stems = stems[:args.limit]
        print(f"Limiting to {args.limit} docs")

    client = LightRAGClient()

    ok = fail = skip = 0
    t0 = time.time()

    for i, stem in enumerate(stems, 1):
        print(f"\n[{i}/{len(stems)}] {stem}")
        result = await process_one(stem, client, dry_run=args.dry_run)
        status = result.get("status", "")
        if status in ("ok", "dry_run"):
            ok += 1
        elif status == "no_md":
            skip += 1
        else:
            fail += 1

        elapsed = time.time() - t0
        rate = i / elapsed * 60
        eta = (len(stems) - i) / (i / elapsed) if i > 0 else 0
        print(f"  Progress: {ok} ok / {fail} fail / {skip} skip | {rate:.1f}/min | ETA {eta/60:.1f}min")

    print(f"\nDone: {ok} ok, {fail} fail, {skip} no_md — {(time.time()-t0)/60:.1f}min total")


if __name__ == "__main__":
    asyncio.run(main())
