# mineru_ocr_client.py
import os
import io
import base64
import fitz
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from PIL import Image

from agent.config import settings

DEFAULT_TIMEOUT = 600  # 10 minutes for a full PDF

class MinerUOCRClientError(RuntimeError):
    pass

class MinerUOCRClient:
    """PDF parser using MinerU2.5-Pro with Vietnamese text normalization."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._client = None

    def _ensure_loaded(self) -> None:
        if self._client is not None:
            return
        model_name = settings.mineru_ocr.model_name
        print(f"[MinerU OCR] Loading model: {model_name}")
        from mlx_vlm.utils import get_model_path
        from mineru_vl_utils import MinerUClient
        # Use model_path= so mineru_vl_utils handles weight-tying via its own
        # mlx_compat loader — avoids missing lm_head.weight on Qwen2-VL models.
        model_path = str(get_model_path(model_name))
        self._client = MinerUClient(
            backend="mlx-engine",
            model_path=model_path,
            image_analysis=False,
        )
        print("[MinerU OCR] Model loaded successfully")

    @staticmethod
    def _normalize_vietnamese(text: str) -> str:
        """Normalize Vietnamese Unicode diacritics to reduce OCR tone-mark errors."""
        try:
            from underthesea import text_normalize
            return text_normalize(text)
        except Exception:
            return text

    @staticmethod
    def _page_to_b64(page: fitz.Page) -> str:
        pix = page.get_pixmap(matrix=fitz.Matrix(144 / 72, 144 / 72), alpha=False)
        return base64.b64encode(pix.tobytes("png")).decode()

    def _parse_pdf_remote(self, file_path: str, api_url: str) -> list[str]:
        """Send pages to remote OCR service. Returns list of per-page markdown."""
        import httpx
        doc = fitz.open(file_path)
        pages_md = []
        endpoint = api_url.rstrip("/") + "/v1/ocr"
        with httpx.Client(timeout=120) as http:
            for i, page in enumerate(doc):
                print(f"[MinerU OCR] Remote page {i + 1}/{len(doc)}")
                image_b64 = self._page_to_b64(page)
                resp = http.post(endpoint, json={"image_b64": image_b64, "lang": "vi"})
                resp.raise_for_status()
                pages_md.append(resp.json()["markdown"])
        doc.close()
        return pages_md

    def _parse_pdf_local(self, file_path: str) -> list[str]:
        """Run MinerU two_step_extract locally via MLX."""
        self._ensure_loaded()
        from mineru_vl_utils.post_process import json2md
        doc = fitz.open(file_path)
        pages_md = []
        for i, page in enumerate(doc):
            print(f"[MinerU OCR] Local page {i + 1}/{len(doc)}")
            pix = page.get_pixmap(matrix=fitz.Matrix(144 / 72, 144 / 72), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            content_list = self._client.two_step_extract(img)
            pages_md.append(json2md(content_list))
        doc.close()
        return pages_md

    def parse_pdf(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        return_md: bool = True,
    ) -> Dict[str, Any]:
        """Parse a PDF file page-by-page using MinerU2.5-Pro."""
        if not os.path.exists(file_path):
            raise MinerUOCRClientError(f"File not found: {file_path}")
        if not file_path.lower().endswith(".pdf"):
            raise MinerUOCRClientError(f"Only PDF files are supported: {file_path}")

        api_url = settings.mineru_ocr.api_url
        print(f"[MinerU OCR] Processing PDF: {file_path} ({'remote: ' + api_url if api_url else 'local MLX'})")

        if api_url:
            pages_md = self._parse_pdf_remote(file_path, api_url)
        else:
            pages_md = self._parse_pdf_local(file_path)

        raw_markdown = "\n\n".join(pages_md) if pages_md else ""
        markdown = self._normalize_vietnamese(raw_markdown)

        result: Dict[str, Any] = {
            "status": "success",
            "pages_processed": len(pages_md),
            "total_pages": len(pages_md),
            "text": markdown,
        }

        if return_md:
            result["markdown"] = markdown

        if output_dir and markdown:
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(file_path).stem
            md_path = os.path.join(output_dir, f"{base_name}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            result["markdown_path"] = md_path
            print(f"[MinerU OCR] Saved markdown to: {md_path}")

        print(f"[MinerU OCR] Completed: {len(pages_md)} pages, {len(markdown):,} chars")
        return result

    def get_markdown_from_output(self, output_dir: str) -> Optional[str]:
        """Return cached markdown from output_dir if it exists."""
        output_path = Path(output_dir)
        if not output_path.exists():
            return None
        md_files = [f for f in output_path.rglob("*.md") if f.is_file()]
        if not md_files:
            return None
        md_file = max(md_files, key=lambda f: f.stat().st_mtime)
        try:
            return md_file.read_text(encoding="utf-8")
        except Exception as e:
            raise MinerUOCRClientError(f"Failed to read cached markdown: {e}")

    def parse_and_get_markdown(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """Parse PDF and return (markdown, output_dir). Checks cache first."""
        file_stem = Path(file_path).stem
        if output_dir is None:
            output_dir = str(settings.mineru_ocr_dir / file_stem)
        else:
            output_dir = str(Path(output_dir) / file_stem)

        if settings.mineru_ocr.skip_repeat:
            cached = self.get_markdown_from_output(output_dir)
            if cached:
                print(f"[MinerU OCR] Cache hit — skipping OCR for: {file_stem}")
                return cached, output_dir

        result = self.parse_pdf(file_path, output_dir=output_dir, return_md=True, **kwargs)

        if not result.get("markdown"):
            raise MinerUOCRClientError(f"No text extracted from PDF: {file_path}")

        return result["markdown"], output_dir
