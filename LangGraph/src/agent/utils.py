from __future__ import annotations

from pathlib import Path
from typing import Optional, Union, Iterable, Tuple
import re
from urllib.parse import urlparse, unquote

_MD_LINK_RE = re.compile(
    r"""
    (?:!?\[                
        (?P<text>[^\]]*)   
    \]\(
        (?P<url>[^)\s]+)   
    \))
    """,
    re.VERBOSE,
)

def _iter_md_links(text: str) -> Iterable[Tuple[str, str]]:
    """
    Yield (text, url) pairs from a Markdown blob.
    """
    for m in _MD_LINK_RE.finditer(text):
        yield (m.group("text") or "", m.group("url") or "")

def _md_unescape(s: str) -> str:
    """
    Undo common Markdown escapes  becomes '_' etc.
    """
    # Only unescape a few common escapes we see in filenames.
    return s.replace(r"\_", "_").replace(r"\-", "-").replace(r"\.", ".")

def get_url(pdf_path_input: Union[str, Path]) -> Optional[str]:
    """
    Given:  /.../website1/pdf/file.pdf
    Search in: /.../website1/markdown/*.md
    Return: direct URL to the PDF (https://.../file.pdf) if found, else None.
    """
    pdf_path: Path = Path(pdf_path_input)
    parents = list(pdf_path.parents)
    if len(parents) < 2:
        return None

    root = parents[1]                 # .../website1
    md_dir = root / "markdown"
    if not md_dir.is_dir():
        return None

    target_name = pdf_path.name.lower()

    for md_file in md_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for link_text, url in _iter_md_links(text):
            # Only consider http(s) links
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                continue

            # Only consider links that end with .pdf
            url_basename = Path(parsed.path).name
            if not url_basename.lower().endswith(".pdf"):
                continue

            # Normalize & compare
            url_name_norm = unquote(url_basename).lower()
            link_text_norm = unquote(_md_unescape(link_text)).strip().lower()

            if (
                url_name_norm == target_name
                or link_text_norm == target_name
                or target_name in url_name_norm  # permissive fallback
            ):
                # Found it — return the absolute URL as-is
                return parsed.geturl()

    return None