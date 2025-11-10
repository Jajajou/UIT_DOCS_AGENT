import argparse
import glob
import hashlib
import json
import os
import signal
import sys
import time
from typing import Dict, Any

from langgraph_sdk import get_sync_client
from tqdm import tqdm


def sha1_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_checkpoint(index_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load checkpoint JSONL into a dict keyed by file path.
    If duplicates exist for the same path, keep the latest entry.
    """
    state: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(index_path):
        return state
    with open(index_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                p = rec.get("path")
                ts = rec.get("ts", 0)
                prev = state.get(p)
                if p and (prev is None or ts >= prev.get("ts", 0)):
                    state[p] = rec
            except json.JSONDecodeError:
                # skip corrupted line
                continue
    return state


def append_checkpoint(index_path: str, record: Dict[str, Any]) -> None:
    tmp = index_path + ".tmp"
    with open(tmp, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # Append is already atomic enough on POSIX, but make sure file exists
    # and then append by renaming chunk -> we’ll just append directly:
    # To keep it simple and fast, we just append to the main file.
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # Clean temp if created
    try:
        os.remove(tmp)
    except FileNotFoundError:
        pass


def should_skip(path: str, sig: str, state: Dict[str, Dict[str, Any]]) -> bool:
    rec = state.get(path)
    if not rec:
        return False
    # Skip if previously succeeded with the same content signature
    return rec.get("status") == "success" and rec.get("sha1") == sig


def main():
    parser = argparse.ArgumentParser(description="Checkpointed uploader for PDFs.")
    parser.add_argument("--root_dir", default="firecrawl/data/daa", help="Root directory to scan for PDFs.")
    parser.add_argument("--checkpoint", default=".upload_checkpoint.jsonl", help="Path to checkpoint JSONL file.")
    parser.add_argument("--url", default="http://localhost:2024", help="LangGraph SDK endpoint URL.")
    parser.add_argument("--dry_run", action="store_true", help="List what would be uploaded and exit.")
    parser.add_argument("--glob", default="**/*.pdf", help="Glob pattern (relative to root_dir).")
    args = parser.parse_args()

    root_dir = args.root_dir
    checkpoint_path = args.checkpoint

    # Discover PDFs
    pdf_paths = sorted(
        os.path.abspath(p)
        for p in glob.glob(os.path.join(root_dir, args.glob), recursive=True)
    )

    # Load prior state
    state = load_checkpoint(checkpoint_path)

    # Pre-compute signatures and split into todo / skipped
    to_upload = []
    skipped = 0
    print("Hashing files (SHA1) to determine what’s already done...")
    for p in tqdm(pdf_paths, desc="Hashing", unit="file"):
        try:
            sig = sha1_file(p)
        except Exception as e:
            # Record a hash error so we don’t get stuck on the same file repeatedly
            rec = {
                "path": p,
                "sha1": None,
                "status": "hash_error",
                "error": repr(e),
                "ts": time.time(),
            }
            append_checkpoint(checkpoint_path, rec)
            state[p] = rec
            continue
        if should_skip(p, sig, state):
            skipped += 1
            continue
        to_upload.append((p, sig))

    if args.dry_run:
        print(f"[DRY RUN] Total PDFs found: {len(pdf_paths)}")
        print(f"[DRY RUN] Already done (skipped): {skipped}")
        print(f"[DRY RUN] To upload: {len(to_upload)}")
        for p, _ in to_upload[:25]:
            print("  -", p)
        if len(to_upload) > 25:
            print(f"  ... and {len(to_upload) - 25} more")
        return

    client = get_sync_client(url=args.url)

    # Graceful stop support: on SIGINT/SIGTERM, just exit the loop after finishing current file.
    stop_flag = {"stop": False}

    def _handle_signal(signum, frame):
        stop_flag["stop"] = True
        print("\nReceived stop signal; will finish current file and exit gracefully...")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    pbar = tqdm(total=len(to_upload), desc="Uploading", unit="file")
    try:
        for path, sig in to_upload:
            if stop_flag["stop"]:
                break
            start_ts = time.time()
            rec_base = {"path": path, "sha1": sig, "ts": start_ts}
            try:
                # Stream the indexing/upload
                for _chunk in client.runs.stream(
                    None,
                    "index",
                    input={
                        "messages": [
                            {
                                "role": "human",
                                "content": f"upload {path}",
                            }
                        ]
                    },
                    stream_mode="updates",
                ):
                    # No-op: consume stream to completion
                    pass

                # Mark success
                rec = {**rec_base, "status": "success", "duration_s": time.time() - start_ts}
                append_checkpoint(checkpoint_path, rec)
                state[path] = rec

            except Exception as e:
                rec = {**rec_base, "status": "error", "error": repr(e), "duration_s": time.time() - start_ts}
                append_checkpoint(checkpoint_path, rec)
                state[path] = rec
            finally:
                pbar.update(1)
    finally:
        pbar.close()

    # Summary
    succeeded = sum(1 for r in state.values() if r.get("status") == "success")
    errors = [p for p, r in state.items() if r.get("status") == "error"]
    print(f"Done. Total known successes: {succeeded}")
    if errors:
        print(f"{len(errors)} error(s). Example:\n  - {errors[0]}")
        if len(errors) > 1:
            print(f"  ... and {len(errors) - 1} more")


if __name__ == "__main__":
    # If running inside an interactive session without CLI, provide sensible defaults.
    if hasattr(sys, "ps1") and len(sys.argv) == 1:
        sys.argv.extend(["--root_dir", "firecrawl/data/daa"])
    main()