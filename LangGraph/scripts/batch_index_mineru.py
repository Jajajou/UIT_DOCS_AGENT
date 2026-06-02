#!/usr/bin/env python3
"""
Batch indexer: reads MinerU2.5_ocr_rerun MDs, builds URLs, runs full
temporal extraction + LightRAG upload for each doc.

Usage (from LangGraph/):
    python scripts/batch_index_mineru.py [--dry-run] [--limit N] [--skip N]
    python scripts/batch_index_mineru.py --reextract [--conf-threshold 0.3]
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

OCR_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/data/MinerU2.5_final_cleaned")
PDF_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa")

# Government-level decree patterns that UIT docs never amend (only cite as legal basis)
_EXTERNAL_DOC_PATTERNS = ("NĐ-CP", "ND-CP", "QĐ-TTg", "QD-TTg", "CT-TTg", "NQ-CP", "NQ-UBTVQH")

def _filter_external_amends(amends: list) -> tuple[list, list]:
    """Split amends into linkable (in-corpus) vs external (govt decrees cited as legal basis)."""
    linkable = [d for d in amends if not any(p in d for p in _EXTERNAL_DOC_PATTERNS)]
    external = [d for d in amends if any(p in d for p in _EXTERNAL_DOC_PATTERNS)]
    return linkable, external


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


def _build_url(stem: str, pdf_path) -> str:
    url = get_url(str(pdf_path)) if pdf_path else None
    if not url:
        base = stem[:-9] if (len(stem) > 9 and stem[-9] == "-") else stem
        url = f"https://daa.uit.edu.vn/sites/daa/files/{base}.pdf"
    return url


async def upload_one(stem: str, client: LightRAGClient) -> dict:
    """Phase 1: upload to LightRAG only, return track_id immediately."""
    md_path = find_md(stem)
    if not md_path:
        return {"stem": stem, "status": "no_md"}
    pdf_path = find_pdf(stem)
    url = _build_url(stem, pdf_path)
    md_content = md_path.read_text(encoding="utf-8", errors="ignore")
    try:
        result = client.insert_text(text=md_content, file_source=url)
        track_id = result.get("track_id", "")
        print(f"  [UPLOAD] {stem[:55]} track={track_id}")
        return {"stem": stem, "status": "uploaded", "track_id": track_id, "url": url, "md_content": md_content}
    except Exception as e:
        print(f"  [FAIL] {stem[:55]} upload: {e}")
        return {"stem": stem, "status": "upload_fail", "error": str(e)}


async def extract_meta_one(upload: dict, client: LightRAGClient) -> dict:
    """Phase 2: run metadata RAG + save; called after LightRAG queue has the doc."""
    stem = upload["stem"]
    track_id = upload.get("track_id", "")
    url = upload.get("url", "")
    md_content = upload.get("md_content", "")

    if not track_id or not md_content:
        return {**upload, "status": "ok"}

    try:
        from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph
        from agent.states.metadata_rag_state import MetadataRAGState

        state: MetadataRAGState = {"doc_text": md_content, "file_source": url, "doc_id": ""}
        meta_result = await metadata_rag_subgraph.ainvoke(state)
        document_metadata = meta_result.get("document_metadata", {})
        print(f"  [META] {stem[:45]} doc_num={document_metadata.get('document_number')!r} conf={document_metadata.get('extraction_confidence', 0):.2f}")
    except Exception as e:
        print(f"  [WARN] {stem[:45]} meta extract: {e}")
        return {**upload, "status": "ok"}

    # Resolve doc_id from track_id
    doc_id = None
    for _ in range(15):
        try:
            conn = client._get_pg_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM lightrag_doc_status WHERE track_id = %s", (track_id,))
                    row = cur.fetchone()
                    if row:
                        doc_id = row[0]
            finally:
                conn.close()
        except Exception:
            pass
        if doc_id:
            break
        await asyncio.sleep(2)

    if not doc_id:
        print(f"  [WARN] {stem[:45]} doc_id not found for track_id={track_id}")
        return {**upload, "status": "ok"}

    if document_metadata:
        try:
            save_result = client.save_temporal_metadata(track_id=track_id, doc_id=doc_id, metadata=document_metadata)
            if save_result.get("success"):
                print(f"  [META] saved (doc_id={doc_id})")
                amends = document_metadata.get("amends_documents") or []
                if amends:
                    linkable, external = _filter_external_amends(amends)
                    if external:
                        print(f"  [META] skip {len(external)} external: {external}")
                    if linkable:
                        link_result = client.link_amended_documents(doc_id, linkable)
                        print(f"  [META] linked {len(link_result.get('linked_docs', []))}/{len(linkable)} amended")
        except Exception as e:
            print(f"  [WARN] {stem[:45]} meta save: {e}")

    return {**upload, "status": "ok", "doc_id": doc_id}


def find_ocr_stem(base_stem: str) -> str | None:
    """Find OCR dir name matching a file_path basename (handles hash suffixes)."""
    exact = OCR_DIR / base_stem
    if exact.exists():
        return base_stem
    for d in OCR_DIR.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        stripped = name[:-9] if (len(name) > 9 and name[-9] == "-") else name
        if stripped == base_stem or name == base_stem:
            return name
    return None


def _fetch_low_conf_docs(client: LightRAGClient, threshold: float) -> list[dict]:
    """Query PG for docs with extraction_confidence < threshold."""
    conn = client._get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lds.id, lds.track_id, lds.file_path, tm.extraction_confidence
                FROM temporal_metadata tm
                JOIN lightrag_doc_status lds ON lds.id = tm.doc_id
                WHERE tm.extraction_confidence < %s AND lds.file_path IS NOT NULL
                ORDER BY tm.extraction_confidence ASC
                """,
                (threshold,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"doc_id": r[0], "track_id": r[1] or "", "file_path": r[2], "conf": r[3]} for r in rows]


async def reextract_one(row: dict, client: LightRAGClient) -> dict:
    """Re-run metadata extraction for an already-indexed doc using known doc_id."""
    doc_id = row["doc_id"]
    track_id = row["track_id"]
    file_path = row["file_path"]
    base_stem = Path(file_path).stem

    stem = find_ocr_stem(base_stem)
    if not stem:
        print(f"  [SKIP] {base_stem[:50]} no OCR dir found")
        return {**row, "status": "no_ocr"}

    md_path = find_md(stem)
    if not md_path:
        print(f"  [SKIP] {stem[:50]} no .md in OCR dir")
        return {**row, "status": "no_md"}

    pdf_path = find_pdf(stem)
    url = _build_url(stem, pdf_path)
    md_content = md_path.read_text(encoding="utf-8", errors="ignore")

    try:
        from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph
        from agent.states.metadata_rag_state import MetadataRAGState

        state: MetadataRAGState = {"doc_text": md_content, "file_source": url, "doc_id": doc_id}
        meta_result = await metadata_rag_subgraph.ainvoke(state)
        document_metadata = meta_result.get("document_metadata", {})
        new_conf = document_metadata.get("extraction_confidence", 0)
        print(f"  [META] {stem[:45]} doc_num={document_metadata.get('document_number')!r} conf={row['conf']:.2f}->{new_conf:.2f}")
    except Exception as e:
        print(f"  [WARN] {stem[:45]} meta extract: {e}")
        return {**row, "status": "extract_fail"}

    if document_metadata:
        try:
            save_result = client.save_temporal_metadata(track_id=track_id, doc_id=doc_id, metadata=document_metadata)
            if save_result.get("success"):
                print(f"  [SAVE] {stem[:45]} saved (doc_id={doc_id})")
                amends = document_metadata.get("amends_documents") or []
                if amends:
                    linkable, external = _filter_external_amends(amends)
                    if external:
                        print(f"  [META] skip {len(external)} external: {external}")
                    if linkable:
                        link_result = client.link_amended_documents(doc_id, linkable)
                        print(f"  [META] linked {len(link_result.get('linked_docs', []))}/{len(linkable)} amended")
        except Exception as e:
            print(f"  [WARN] {stem[:45]} meta save: {e}")

    return {**row, "status": "ok"}


async def process_one(stem: str, client: LightRAGClient, dry_run: bool = False) -> dict:
    """Legacy single-pass (used when --two-phase not set)."""
    md_path = find_md(stem)
    if not md_path:
        return {"stem": stem, "status": "no_md"}
    pdf_path = find_pdf(stem)
    url = _build_url(stem, pdf_path)
    md_content = md_path.read_text(encoding="utf-8", errors="ignore")
    if dry_run:
        print(f"  [DRY] {stem[:60]} -> url={url} ({len(md_content):,} chars)")
        return {"stem": stem, "status": "dry_run"}
    up = await upload_one(stem, client)
    if up["status"] != "uploaded":
        return up
    return await extract_meta_one(up, client)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--stems", nargs="+")
    parser.add_argument("--workers", type=int, default=1, help="Meta workers (default 1)")
    parser.add_argument("--upload-workers", type=int, default=8, help="Upload workers phase1 (default 8)")
    parser.add_argument("--reextract", action="store_true", help="Re-run metadata extraction for already-indexed low-conf docs (skip Phase 1)")
    parser.add_argument("--conf-threshold", type=float, default=0.3, help="Confidence threshold for --reextract (default 0.3)")
    args = parser.parse_args()

    client = LightRAGClient()
    t0 = time.time()

    # --reextract: Phase 2 only on already-indexed low-conf docs
    if args.reextract:
        rows = _fetch_low_conf_docs(client, args.conf_threshold)
        if args.limit:
            rows = rows[:args.limit]
        total = len(rows)
        print(f"Found {total} docs with conf < {args.conf_threshold} in temporal_metadata")
        if not rows:
            print("Nothing to reextract.")
            return

        sem = asyncio.Semaphore(args.workers)
        done = [0]

        async def do_reextract(row: dict) -> dict:
            async with sem:
                r = await reextract_one(row, client)
                done[0] += 1
                elapsed = time.time() - t0
                rate = done[0] / elapsed * 60
                eta = (total - done[0]) / max(done[0] / elapsed, 0.001)
                print(f"  [{done[0]}/{total}] conf={row['conf']:.2f} | {rate:.1f}/min | ETA {eta/60:.1f}min")
                return r

        results = await asyncio.gather(*[do_reextract(r) for r in rows])
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"\nReextract done: {ok}/{total} ok in {(time.time()-t0)/60:.1f}min")
        return

    stems = sorted(d.name for d in OCR_DIR.iterdir() if d.is_dir())
    print(f"Found {len(stems)} stems in MinerU2.5_ocr_rerun")
    if args.stems:
        stems = [s for s in stems if s in args.stems]
    if args.skip:
        stems = stems[args.skip:]
        print(f"Skipping first {args.skip} -> {len(stems)} remaining")
    if args.limit:
        stems = stems[:args.limit]

    total = len(stems)

    # Phase 1: upload all docs to LightRAG concurrently (insert_text is fast)
    print(f"\n=== Phase 1: uploading {total} docs to LightRAG (workers={args.upload_workers}) ===")
    up_sem = asyncio.Semaphore(args.upload_workers)
    up_done = [0]

    async def do_upload(stem: str) -> dict:
        async with up_sem:
            r = await upload_one(stem, client)
            up_done[0] += 1
            print(f"  [P1 {up_done[0]}/{total}] {stem[:55]} -> {r['status']}")
            return r

    uploads = await asyncio.gather(*[do_upload(s) for s in stems])
    ok_uploads = [u for u in uploads if u["status"] == "uploaded"]
    print(f"Phase 1 done: {len(ok_uploads)}/{total} uploaded in {(time.time()-t0)/60:.1f}min")

    # Phase 2: metadata extraction sequentially (embed server bottleneck)
    print(f"\n=== Phase 2: metadata extraction (workers={args.workers}) ===")
    meta_sem = asyncio.Semaphore(args.workers)
    meta_done = [0]

    async def do_meta(upload: dict) -> dict:
        async with meta_sem:
            r = await extract_meta_one(upload, client)
            meta_done[0] += 1
            elapsed = time.time() - t0
            rate = meta_done[0] / elapsed * 60
            eta = (len(ok_uploads) - meta_done[0]) / max(meta_done[0] / elapsed, 0.001)
            print(f"  [P2 {meta_done[0]}/{len(ok_uploads)}] {upload['stem'][:45]} | {rate:.1f}/min | ETA {eta/60:.1f}min")
            return r

    await asyncio.gather(*[do_meta(u) for u in ok_uploads])
    print(f"\nDone in {(time.time()-t0)/60:.1f}min total")


if __name__ == "__main__":
    asyncio.run(main())
