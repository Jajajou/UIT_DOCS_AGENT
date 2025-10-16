import re
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text as pdf_extract_text
from docx import Document

# Detect download links via <a href> and onclick handlers
FILE_EXTS = ("pdf", "doc", "docx", "xls", "xlsx", "txt")
FILE_REGEX = re.compile(r"https?://[^\s'\"]+\.(?:" + "|".join(FILE_EXTS) + ")", re.IGNORECASE)

def find_download_links(html: str):
    soup = BeautifulSoup(html, "lxml")
    links = set()

    # hrefs
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if any(href.lower().endswith(f".{ext}") for ext in FILE_EXTS):
            links.add(href)

    # onclick=window.open('...') / location.href='...'
    for tag in soup.find_all(attrs={"onclick": True}):
        onclick = tag.get("onclick", "")
        for m in FILE_REGEX.findall(onclick):
            links.add(m)

    # data attributes
    for attr in ("data-href", "data-url"):
        for tag in soup.find_all(attrs={attr: True}):
            val = tag.get(attr, "")
            if any(val.lower().endswith(f".{ext}") for ext in FILE_EXTS):
                links.add(val)

    return list(links)

def clean_html_to_text(soup: BeautifulSoup) -> str:
    for bad in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        bad.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def extract_text_from_pdf(path: str) -> str:
    return pdf_extract_text(path) or ""

def extract_text_from_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)
