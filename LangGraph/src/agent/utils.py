from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional, Union, Iterable, Tuple, List, Any
import re
from urllib.parse import urlparse, unquote
import sys
import os
import pytesseract
import tempfile
from PIL import Image
from dotenv import load_dotenv
from langchain_core.messages import AnyMessage

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


_PDF_URL_LOOKUP: Optional[dict] = None

def _load_pdf_url_lookup() -> dict:
    """Load the pre-built filename->URL lookup from firecrawl metadata."""
    global _PDF_URL_LOOKUP
    if _PDF_URL_LOOKUP is not None:
        return _PDF_URL_LOOKUP
    lookup_path = Path(project_dir) / "firecrawl" / "data" / "pdf_url_lookup.json"
    if lookup_path.exists():
        import json
        with open(lookup_path, encoding="utf-8") as f:
            _PDF_URL_LOOKUP = json.load(f)
    else:
        _PDF_URL_LOOKUP = {}
    return _PDF_URL_LOOKUP

def _lookup_url_by_stem(filename: str) -> Optional[str]:
    """
    Look up the source URL for a PDF file using the pre-built lookup.
    Strips trailing dedup suffixes (_001, _002 etc) and decodes percent-encoding.
    """
    from urllib.parse import unquote
    lookup = _load_pdf_url_lookup()
    stem = unquote(filename).lower()
    if stem.endswith(".pdf"):
        stem = stem[:-4]
    # Try exact match then progressively strip trailing _NNN dedup suffixes.
    # Use a while loop so we always check the stem AFTER stripping (fixes off-by-one
    # for deeply nested duplicates like _001_001_001_001_001).
    for _ in range(20):
        if stem in lookup:
            return lookup[stem]
        new = re.sub(r"[_ ]+\d+$", "", stem)
        if new == stem:
            break
        stem = new
    # Check the fully stripped base one final time
    if stem in lookup:
        return lookup[stem]
    return None

def get_url(pdf_path_input: Union[str, Path]) -> Optional[str]:
    """
    Given:  /.../website1/pdf/file.pdf
    Search in:
      1) *.md files in the SAME FOLDER as the PDF     -> /.../website1/pdf/*.md
      2) /.../website1/markdown/**/*.md  (recursive)
      3) Pre-built pdf_url_lookup.json from firecrawl metadata (fallback)
    Return: direct URL to the PDF (https://.../file.pdf) if found, else None.
    """
    pdf_path: Path = Path(pdf_path_input)
    parents = list(pdf_path.parents)
    if len(parents) >= 2:
        root = parents[1]                   # .../website1
        md_dir = root / "markdown"
        pdf_dir = pdf_path.parent

        target_name = pdf_path.name.lower()

        # Build candidate .md sources: same-folder .md first, then markdown/**.md
        candidate_iters = []
        if pdf_dir.is_dir():
            candidate_iters.append(pdf_dir.glob("*.md"))
        if md_dir.is_dir():
            candidate_iters.append(md_dir.rglob("*.md"))

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
                result = find_urls_by_filename(urls, target_name)
                if result:
                    return result

    # Fallback: pre-built lookup from firecrawl metadata.jsonl
    return _lookup_url_by_stem(pdf_path.name)

def content_to_text(content: Any) -> str:
    """Extract text from message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                txt = (part.get("text") or "").strip()
                if txt:
                    texts.append(txt)
        return " ".join(texts) if texts else ""
    return ""


def get_last_human_message(messages: List[AnyMessage]) -> Optional[AnyMessage]:
    """Get the last human message from a list of messages."""
    for msg in reversed(messages or []):
        if msg.type == "human":
            return msg
    return None

def preprocess_image_for_ocr(image_path: str) -> str:
    """
    Pre-processes an image for OCR by detecting orientation, rotating,
    fitting to A4 size, and saving to a temporary file.

    Args:
        image_path: Path to the input image file.

    Returns:
        Path to the processed temporary image file.
    """
    temp_file_path = None
    try:
        with Image.open(image_path) as img:
            # Get orientation data
            try:
                osd_dict = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
                rotation_angle = osd_dict.get('rotate', 0)
            except pytesseract.TesseractError:
                # If OSD fails, assume no rotation is needed
                rotation_angle = 0
            
            # Rotate the image if needed
            if rotation_angle != 0:
                rotated_img = img.rotate(-1 * rotation_angle, expand=True)
            else:
                rotated_img = img

            # A4 dimensions at 300 DPI
            A4_WIDTH_PX, A4_HEIGHT_PX = 2480, 3508
            a4_page = Image.new('RGB', (A4_WIDTH_PX, A4_HEIGHT_PX), 'white')

            img_width, img_height = rotated_img.size
            width_ratio = A4_WIDTH_PX / img_width
            height_ratio = A4_HEIGHT_PX / img_height
            scaling_factor = min(width_ratio, height_ratio)

            new_width = int(img_width * scaling_factor)
            new_height = int(img_height * scaling_factor)

            resized_img = rotated_img.resize((new_width, new_height), Image.LANCZOS) #type: ignore

            paste_x = (A4_WIDTH_PX - new_width) // 2
            paste_y = (A4_HEIGHT_PX - new_height) // 2
            a4_page.paste(resized_img, (paste_x, paste_y))

            # Save the processed image to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                a4_page.save(temp_file, format="PNG")
                temp_file_path = temp_file.name
        return temp_file_path
    except Exception as e:
        print(f"Error during image preprocessing: {e}")
        return image_path # Return original path if preprocessing fails
#---