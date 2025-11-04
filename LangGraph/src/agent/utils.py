from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional, Union, Iterable, Tuple, List
import re
from urllib.parse import urlparse, unquote
import sys
import os
from dotenv import load_dotenv

load_dotenv()
project_dir = str(os.environ.get("PROJECT_ROOT"))

def find_urls_by_filename(
    links: Iterable[str],
    filename: str,
    *,
    case_insensitive: bool = True,
    decode_percent_escapes: bool = False,
):
    """
    Return every URL in `links` whose basename equals `filename`.
    Matching ignores query strings and fragments (they're not part of the basename).
    """
    key = filename.casefold() if case_insensitive else filename
    out: List[str] = []

    for url in links:
        p = urlparse(url)
        base = PurePosixPath(p.path).name  # last path component of the URL
        if decode_percent_escapes:
            base = unquote(base)           # handle "my%20file.pdf" -> "my file.pdf"
        cand = base.casefold() if case_insensitive else base
        if cand == key:
            return url              # return the original URL, untouched

PDF_URL_RE = re.compile(
    r'https?://[^\s\)\]\}\>\,"\']+?\.pdf(?=[\s\)\]\}\>\,"\']|$)',
    re.IGNORECASE,
)

def extract_pdf_links(text: str) -> List[str]:
    """Return a de-duplicated, order-preserving list of PDF links."""
    seen = set()
    out: List[str] = []
    for m in PDF_URL_RE.finditer(text):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out

def read_text_from(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def get_url(pdf_path_input: Union[str, Path]) -> Optional[str]:
    """
    Given:  /.../website1/pdf/file.pdf
    Search in:
      1) *.md files in the SAME FOLDER as the PDF     -> /.../website1/pdf/*.md
      2) /.../website1/markdown/**/*.md  (recursive)
    Return: direct URL to the PDF (https://.../file.pdf) if found, else None.
    """
    pdf_path: Path = Path(pdf_path_input)
    parents = list(pdf_path.parents)
    if len(parents) < 2:
        return None

    root = parents[1]                   # .../website1
    md_dir = root / "markdown"
    pdf_dir = pdf_path.parent

    target_name = pdf_path.name.lower()

    # Build candidate .md sources: same-folder .md first (non-recursive), then markdown/**.md
    candidate_iters = []
    if pdf_dir.is_dir():
        candidate_iters.append(pdf_dir.glob("*.md"))           # shallow search next to the PDF
    if md_dir.is_dir():
        candidate_iters.append(md_dir.rglob("*.md"))           # existing recursive search

    seen: set[Path] = set()
    for it in candidate_iters:
        for md_file in it:
            if md_file in seen:
                continue
            seen.add(md_file)

            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            urls = extract_pdf_links(text)

            return find_urls_by_filename(urls, target_name)
        
    return None

#---