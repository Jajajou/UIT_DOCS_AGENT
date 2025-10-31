# mineru_client.py
import os
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Literal
from dotenv import load_dotenv

load_dotenv("../../.env")
base_url = os.getenv("MINERU_URL")

DEFAULT_TIMEOUT = 300  # 5 minutes for 1 PDF parsing


class MinerUClientError(RuntimeError):
    pass


class MinerUClient:
    """Client for MinerU PDF parsing API."""
    
    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        load_dotenv("LangGraph/.env")
        self.base_url = base_url or os.getenv("MINERU_URL")
        self.timeout = timeout
        self._session = session or requests.Session()
    
    def _headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "accept": "application/json",
        }
    
    def parse_pdf(
        self,
        file_path: str,
        output_dir: str | None = None,
        parse_method: Literal["auto", "txt", "ocr"] = "auto",
        lang_list: str = "latin",
        start_page_id: int = 0,
        end_page_id: int = 99999,
        return_md: bool = True,
        return_images: bool = False,
        table_enable: bool = True,
        formula_enable: bool = True,
        backend: Literal["pipeline", "layout"] = "pipeline",
    ) -> Dict[str, Any]:
        """
        Parse a PDF file using MinerU.
        
        Args:
            file_path: Path to the PDF file
            output_dir: Output directory (defaults to ./output/<filename>)
            parse_method: Parsing method (auto, txt, ocr)
            lang_list: Language list for OCR (e.g., "ch", "en", "ch,en")
            start_page_id: Starting page ID (0-indexed)
            end_page_id: Ending page ID
            return_md: Return markdown content
            return_images: Return extracted images
            table_enable: Enable table parsing
            formula_enable: Enable formula parsing
            backend: Backend to use (pipeline or layout)
        
        Returns:
            API response with parsed content
        """
        if not os.path.exists(file_path):
            raise MinerUClientError(f"File not found: {file_path}")
        
        if not file_path.lower().endswith('.pdf'):
            raise MinerUClientError(f"Only PDF files are supported: {file_path}")
        
        # Create output directory based on file name if not provided
        if output_dir is None:
            file_stem = Path(file_path).stem
            output_dir = f"./output/{file_stem}"
        
        # Prepare form data
        files = {
            'files': (os.path.basename(file_path), open(file_path, 'rb'), 'application/pdf')
        }
        
        data = {
            'return_middle_json': 'false',
            'return_model_output': 'false',
            'return_md': str(return_md).lower(),
            'return_images': str(return_images).lower(),
            'end_page_id': str(end_page_id),
            'parse_method': parse_method,
            'start_page_id': str(start_page_id),
            'lang_list': lang_list,
            'output_dir': output_dir,
            'server_url': 'string',
            'return_content_list': 'false',
            'backend': backend,
            'table_enable': str(table_enable).lower(),
            'response_format_zip': 'false',
            'formula_enable': str(formula_enable).lower(),
        }
        
        try:
            url = f"{self.base_url}/file_parse"
            response = self._session.post(
                url,
                headers=self._headers(),
                files=files,
                data=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise MinerUClientError(f"MinerU API request failed: {str(e)}")
        finally:
            # Close the file
            files['files'][1].close()
    
    def get_markdown_from_output(self, output_dir: str) -> Optional[str]:
        """
        Extract the markdown content from MinerU output directory.
        
        Args:
            output_dir: The output directory path
        
        Returns:
            Markdown content as string, or None if not found
        """
        output_path = Path(output_dir)
        
        if not output_path.exists():
            return None
        
        # Look for .md files in the output directory
        md_files = list(output_path.glob("*.md"))
        
        if not md_files:
            return None
        
        # Return the first markdown file content
        md_file = md_files[0]
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise MinerUClientError(f"Failed to read markdown file: {str(e)}")
    
    def parse_and_get_markdown(
        self,
        file_path: str,
        output_dir: str | None = None,
        **kwargs
    ) -> tuple[str, str]:
        """
        Parse PDF and return markdown content.
        
        Args:
            file_path: Path to PDF file
            output_dir: Output directory (optional)
            **kwargs: Additional arguments for parse_pdf
        
        Returns:
            Tuple of (markdown_content, output_dir_path)
        """
        # Set default output directory
        if output_dir is None:
            file_stem = Path(file_path).stem
            output_dir = f"./output/{file_stem}"
        
        print(f"[MinerU] Parsing PDF: {file_path}")
        print(f"[MinerU] Output directory: {output_dir}")
        
        # Parse the PDF
        result = self.parse_pdf(file_path, output_dir=output_dir, **kwargs)
        
        print(f"[MinerU] Parse result: {result}")
        
        # Get markdown content
        md_content = self.get_markdown_from_output(output_dir)
        
        if md_content is None:
            raise MinerUClientError(f"No markdown file found in output directory: {output_dir}")
        
        print(f"[MinerU] ✓ Extracted markdown ({len(md_content)} chars)")
        
        return md_content, output_dir

