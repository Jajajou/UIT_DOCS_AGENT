import os
import glob
import hashlib

def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def cleanup_markdown_files(directory):
    print(f"--- Cleaning up Markdown files in: {directory} ---")
    md_files = glob.glob(os.path.join(directory, "**/*.md"), recursive=True)
    deleted_count = 0
    seen_hashes = set()
    
    error_patterns = ["Too Many Requests", "429", "Page not found"]
    
    for file_path in md_files:
        should_delete = False
        reason = ""
        
        # 1. Check filename for pagination or special characters
        filename = os.path.basename(file_path).lower()
        pagination_patterns = ["page=", "page-", "page=", "?page="]
        if any(p in filename for p in pagination_patterns):
            should_delete = True
            reason = "Pagination file (list page)"
            
        # 2. Check file size
        if not should_delete:
            try:
                size = os.path.getsize(file_path)
                if size < 500:
                    should_delete = True
                    reason = f"File too small ({size} bytes)"
            except OSError:
                continue

        # 3. Check content for errors
        if not should_delete:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1000) # Only read the beginning
                    for pattern in error_patterns:
                        if pattern in content:
                            should_delete = True
                            reason = f"Error pattern found: {pattern}"
                            break
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

        # 4. Deduplicate based on content hash
        if not should_delete:
            try:
                file_hash = get_file_hash(file_path)
                if file_hash in seen_hashes:
                    should_delete = True
                    reason = "Duplicate content (same hash)"
                else:
                    seen_hashes.add(file_hash)
            except Exception as e:
                print(f"Error hashing {file_path}: {e}")

        if should_delete:
            # print(f"Deleting: {file_path} (Reason: {reason})")
            os.remove(file_path)
            deleted_count += 1

    print(f"Total Markdown files deleted: {deleted_count}")

def cleanup_root_junk():
    print("--- Cleaning up junk files in Root ---")
    junk_patterns = [
        ".upload_checkpoint_rebuild.jsonl",
        ".upload_checkpoint_rebuild.jsonl.bak*",
        ".upload_checkpoint_v2.jsonl",
        ".upload_checkpoint.jsonl",
        "clipboard-*.png" # In case there are more clipboard images in root
    ]
    
    deleted_count = 0
    for pattern in junk_patterns:
        for file_path in glob.glob(pattern):
            if os.path.isfile(file_path):
                # print(f"Deleting root junk: {file_path}")
                os.remove(file_path)
                deleted_count += 1
    
    print(f"Total Root junk files deleted: {deleted_count}")

if __name__ == "__main__":
    target_dir = "firecrawl/data/daa"
    if os.path.exists(target_dir):
        cleanup_markdown_files(target_dir)
    else:
        print(f"Directory {target_dir} not found.")
        
    cleanup_root_junk()
    print("Cleanup completed.")
