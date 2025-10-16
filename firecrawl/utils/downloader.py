import os
import hashlib
from urllib.parse import urlparse

import requests
from .ratelimit import sleep_for_bandwidth

CHUNK = 1024 * 64

EXT_DIR_MAP = {
    "pdf": "pdf",
    "doc": "docs",
    "docx": "docs",
    "xls": "docs",
    "xlsx": "docs",
    "txt": "docs",
}

def url_to_safe_path(url: str, suffix: str = "") -> str:
    parsed = urlparse(url)
    base = (parsed.path or "/").rstrip("/")
    if not base:
        base = "index"
    name = base.replace("/", "_")
    if not name:
        name = "index"
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{name}{suffix}{'-' + h if h else ''}"

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def infer_ext(url: str) -> str:
    for ext in EXT_DIR_MAP.keys():
        if url.lower().split("?")[0].endswith(f".{ext}"):
            return ext
    return ""

def download_file(url: str, pdf_dir: str, docs_dir: str) -> str:
    ext = infer_ext(url)
    if not ext:
        raise ValueError("Unsupported file type")

    out_dir = pdf_dir if ext == "pdf" else docs_dir
    ensure_dir(out_dir)
    safe = url_to_safe_path(url)
    dest = os.path.join(out_dir, f"{safe}.{ext}")

    headers = {"User-Agent": os.environ.get("CRAWL_USER_AGENT", "firecrawl-uit-bot/1.0")}
    with requests.get(url, headers=headers, stream=True, timeout=60, verify=False) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                # throttle per chunk
                sleep_for_bandwidth(len(chunk))

    return dest
