"""Backfill script: inject temporal metadata into Qdrant chunk payloads.

Run this once to annotate all existing indexed documents. Safe to re-run
(idempotent — set_payload overwrites with the same values).

Usage:
    cd /Users/jajajou1778/UIT_DOCS_AGENT
    source .venv/bin/activate
    python LangGraph/scripts/inject_qdrant_payloads.py

    # Verify a specific doc after injection:
    python LangGraph/scripts/inject_qdrant_payloads.py --verify doc-29b0ec74e32e3532cb72cf5f2903cf4c
"""

from __future__ import annotations

import argparse
import logging
import sys
import os

# Allow running from project root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv("LangGraph/.env")
load_dotenv(".env.lightrag")

from agent.clients.qdrant_payload_injector import QdrantPayloadInjector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject Qdrant temporal payloads")
    parser.add_argument(
        "--verify",
        metavar="DOC_ID",
        help="After backfill, print the Qdrant payload for this doc_id",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant base URL (default: http://localhost:6336)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace filter (default: WORKSPACE env var or 'default')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be injected without writing to Qdrant",
    )
    args = parser.parse_args()

    injector = QdrantPayloadInjector(base_url=args.qdrant_url)

    if args.dry_run:
        import psycopg2

        dsn = injector._build_pg_dsn()
        workspace = args.workspace or os.getenv("WORKSPACE", "default")
        conn = psycopg2.connect(dsn)
        try:
            rows = injector._fetch_temporal_metadata(conn, workspace)
        finally:
            conn.close()

        logger.info("[DRY RUN] Would inject %d docs:", len(rows))
        for row in rows:
            payload = injector._build_qdrant_payload(row)
            logger.info("  %s -> %s", row["doc_id"], payload)
        return

    logger.info("Starting Qdrant payload backfill...")
    result = injector.backfill_from_postgres(workspace=args.workspace)

    print("\n--- Backfill Summary ---")
    print(f"  Total docs in temporal_metadata : {result['total']}")
    print(f"  Injected                        : {result['injected']}")
    print(f"  Skipped (no payload fields)     : {result['skipped']}")
    print(f"  Errors                          : {len(result['errors'])}")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  {err['doc_id']}: {err['error']}")

    if args.verify:
        print(f"\n--- Verification: {args.verify} ---")
        try:
            points = injector.get_chunk_payload(args.verify)
            if not points:
                print("  No chunks found for this doc_id.")
            else:
                print(f"  Found {len(points)} chunk(s). First chunk payload:")
                first = points[0]["payload"]
                for key in ["full_doc_id", "cohort_years", "cohort_scope",
                            "is_archived", "valid_from", "valid_until",
                            "document_number", "amends_documents"]:
                    print(f"    {key}: {first.get(key, '<not set>')}")
        except Exception as exc:
            print(f"  Verification failed: {exc}")

    sys.exit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
