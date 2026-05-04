"""
Temporal Maintenance Toolkit - Unified CLI for managing document metadata and links.
Consolidates scattered maintenance scripts into a single tool.

Usage:
    python manage_temporal.py <command> [options]

Commands:
    links          Backfill amendment links (bidirectional)
    metadata       Backfill missing temporal metadata rows
    fix-amends     Re-extract document numbers and amendments from headers
    fix-confidence Re-process documents with 0 extraction confidence
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent.clients.lightrag_client import LightRAGAPIClient

async def cmd_links(args):
    """Handle amendment linking backfill."""
    print(">>> Command: Backfilling Amendment Links")
    client = LightRAGAPIClient()
    result = client.backfill_amendment_links()
    print(f"Total: {result.get('total_amending_docs', 0)} | Linked: {result.get('linked', 0)} | Not Found: {result.get('not_found', 0)} | Errors: {result.get('errors', 0)}")

async def cmd_metadata(args):
    """Handle missing metadata backfill."""
    print(f">>> Command: Backfilling Missing Metadata (Limit: {args.limit})")
    # Logic from scripts/backfill_temporal_metadata.py
    # For now, we call the existing script logic or re-implement cleanly here
    # To avoid bloat in THIS file, we can import the core function if we refactor them
    # But for a quick cleanup, we can move the logic here.
    print("Note: This command will run the full OCR + RAG pipeline for missing docs.")
    from scripts.archive.backfill_temporal_metadata import main as backfill_main
    # Mocking sys.argv for the imported script
    sys.argv = ["manage_temporal.py", "--limit", str(args.limit)] if args.limit else ["manage_temporal.py"]
    if args.dry_run: sys.argv.append("--dry-run")
    await backfill_main()

async def cmd_fix_amends(args):
    """Handle amends extraction fix."""
    print(f">>> Command: Fixing Amends Extraction (Limit: {args.limit})")
    from scripts.archive.fix_amends_extraction import main as fix_main
    sys.argv = ["manage_temporal.py", "--limit", str(args.limit)] if args.limit else ["manage_temporal.py"]
    if args.dry_run: sys.argv.append("--dry-run")
    if args.only_missing: sys.argv.append("--only-missing-doc-num")
    await fix_main()

def main():
    parser = argparse.ArgumentParser(description="Temporal Maintenance Toolkit")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Links command
    subparsers.add_parser("links", help="Backfill amendment links")

    # Metadata command
    meta_parser = subparsers.add_parser("metadata", help="Backfill missing temporal metadata")
    meta_parser.add_argument("--limit", type=int, default=None)
    meta_parser.add_argument("--dry-run", action="store_true")

    # Fix amends command
    fix_parser = subparsers.add_parser("fix-amends", help="Re-extract doc numbers and amendments")
    fix_parser.add_argument("--limit", type=int, default=None)
    fix_parser.add_argument("--dry-run", action="store_true")
    fix_parser.add_argument("--only-missing", action="store_true", help="Also target docs with null doc numbers")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    loop = asyncio.get_event_loop()
    if args.command == "links":
        loop.run_until_complete(cmd_links(args))
    elif args.command == "metadata":
        loop.run_until_complete(cmd_metadata(args))
    elif args.command == "fix-amends":
        loop.run_until_complete(cmd_fix_amends(args))
    else:
        print(f"Unknown command: {args.command}")

if __name__ == "__main__":
    main()
