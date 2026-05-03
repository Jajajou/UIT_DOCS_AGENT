#!/usr/bin/env python3
"""
Rebuild pdf_url_lookup.json by scanning all markdown files in firecrawl/data.
Extracts PDF URLs from markdown and maps PDF filename stems to URLs.
"""

import json
import re
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).parent
FIRECRAWL_DATA = PROJECT_ROOT / "firecrawl" / "data"
OUTPUT_FILE = FIRECRAWL_DATA / "pdf_url_lookup.json"

PDF_URL_RE = re.compile(
    r'https?://[^\s\)\]\}\>\,"\']+?\.pdf(?=[\s\)\]\}\>\,"\']|$)',
    re.IGNORECASE,
)

def extract_pdf_links(text: str) -> list[str]:
    """Extract all PDF URLs from text."""
    seen = set()
    out = []
    for m in PDF_URL_RE.finditer(text):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out

def get_stem(url: str) -> str:
    """Extract filename stem from URL (lowercase, no .pdf extension)."""
    filename = url.rstrip("/").split("/")[-1]
    filename = unquote(filename).lower()
    if filename.endswith(".pdf"):
        filename = filename[:-4]
    return filename

def main():
    print(f"Scanning markdown files in {FIRECRAWL_DATA}...")

    lookup = {}
    markdown_files = list(FIRECRAWL_DATA.rglob("*.md"))

    print(f"Found {len(markdown_files)} markdown files")

    for md_file in markdown_files:
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            urls = extract_pdf_links(text)

            for url in urls:
                stem = get_stem(url)
                if stem:
                    # Keep first occurrence (don't overwrite)
                    if stem not in lookup:
                        lookup[stem] = url
        except Exception as e:
            print(f"Error processing {md_file}: {e}")

    print(f"\nExtracted {len(lookup)} PDF URL mappings")

    # Write to JSON
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=2, ensure_ascii=False)

    print(f"✓ Wrote {OUTPUT_FILE}")
    print(f"  Size: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    main()
