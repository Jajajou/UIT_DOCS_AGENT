# deepseek_ocr_client.py
import os
import fitz
import io
import re
import numpy as np
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Dict, Any, Tuple, List, Literal
from PIL import Image
from mlx_vlm import load, apply_chat_template, generate
# from mlx_vlm.utils import load_image
from agent.config import MODEL_NAME, MODEL_CONFIGS, TASK_PROMPTS, SKIP_REPEAT, DEEPSEEK_OCR_DIR

DEFAULT_TIMEOUT = 300  # 5 minutes for 1 PDF parsing

class DeepSeekOCRClientError(RuntimeError):
    pass

class DeepSeekOCRClient:
    """Client for DeepSeek OCR PDF parsing."""
    
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.timeout = timeout
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.config = None
        # self._load_model()

    def _ensure_loaded(self):
        if self.model is None or self.processor is None:
            self._load_model()
    
    def _load_model(self):
        """Load the DeepSeek OCR model."""
        if self.model is not None and self.processor is not None:
            return
        print(f"[DeepSeek OCR] Loading model: {self.model_name}")
        self.model, self.processor = load(self.model_name)
        self.config = self.model.config
        print("[DeepSeek OCR] Model loaded successfully")

    def _draw_bounding_boxes(
        self,
        image: Image.Image,
        refs: List[Any],
        extract_images: bool = False
    ) -> Tuple[Image.Image, List[Image.Image]]:

        img_w, img_h = image.size
        img_draw = image.copy()
        draw = ImageDraw.Draw(img_draw)

        overlay = Image.new('RGBA', img_draw.size, (0, 0, 0, 0))
        draw2 = ImageDraw.Draw(overlay)
        crops = []

        font = ImageFont.load_default()
        np.random.seed(42)


        color_map = {}
        
        for ref in refs:
            label = ref[1]
            if label not in color_map:
                color_map[label] = (np.random.randint(50, 255), np.random.randint(50, 255), np.random.randint(50, 255))

            color = color_map[label]
            coords = eval(ref[2])
            color_a = color + (60,)
            
            for box in coords:
                x1, y1, x2, y2 = int(box[0]/999*img_w), int(box[1]/999*img_h), int(box[2]/999*img_w), int(box[3]/999*img_h)
                
                if extract_images and label == 'image':
                    crops.append(image.crop((x1, y1, x2, y2)))
                
                width = 5 if label == 'title' else 3
                draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
                draw2.rectangle([x1, y1, x2, y2], fill=color_a)
                
                text_bbox = draw.textbbox((0, 0), label, font=font)
                tw, th = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
                ty = max(0, y1 - 20)
                draw.rectangle([x1, ty, x1 + tw + 4, ty + th + 4], fill=color)
                draw.text((x1 + 2, ty + 2), label, font=font, fill=(255, 255, 255))
        
        img_draw.paste(overlay, (0, 0), overlay)
        return img_draw, crops
    
    def _extract_grounding_references(self, text: str) -> List[Any]: 
        pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
        return re.findall(pattern, text, re.DOTALL)
    
    def _embed_images(self, markdown: str, crops: List[Image.Image]) -> str:
        if not crops:
            return markdown
        for i, img in enumerate(crops):
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            markdown = markdown.replace(f'**[Figure {i + 1}]**', f'\n\n![Figure {i + 1}](data:image/png;base64,{b64})\n\n', 1)
        return markdown

    
    def _clean_output(self, text: str, include_images: bool = False, remove_labels: bool = False) -> str:
        """Clean the OCR output by removing grounding tags."""
        if not text:
            return ""
        
        pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
        matches = re.findall(pattern, text, re.DOTALL)
        img_num = 0
        
        for match in matches:
            ref_type = match[1]
            
            if ref_type == 'image':
                if include_images:
                    text = text.replace(match[0], f'\n\n**[Figure {img_num + 1}]**\n\n', 1)
                    img_num += 1
                else:
                    text = text.replace(match[0], '', 1)
            elif ref_type == 'title':
                # Keep title tags for markdown formatting
                if not remove_labels:
                    text = text.replace(match[0], '', 1)  # Remove the tags but keep the content
                else:
                    text = text.replace(match[0], '', 1)
            elif ref_type == 'table':
                # Tables are already in markdown format, just remove the tags
                text = text.replace(match[0], '', 1)
            else:
                # For text and other types
                if remove_labels:
                    text = text.replace(match[0], '', 1)
                else:
                    text = text.replace(match[0], '', 1)  # Remove tags, keep content
    
        return text
    
    def _ocr_page(self, image: Image.Image) -> Tuple[str, str, str, Optional[Image.Image], List[Image.Image]]:
        """
        OCR a single page image.
        
        Returns:
            Tuple of (clean_text, markdown, raw_output)
        """
        self._ensure_loaded()

        try:
            prompt = TASK_PROMPTS["Markdown"]["prompt"]
            has_grounding = TASK_PROMPTS["Markdown"]["has_grounding"]

            messages = [
                {"role": "user", "content": f"{prompt}"}
            ]
            
            formatted = apply_chat_template(
                self.processor,
                self.config,
                messages,
                num_images=1
            )
            
            output = generate(
                model=self.model, # type: ignore
                processor=self.processor, # type: ignore
                prompt=formatted, # type: ignore
                image=[image.resize((1024, 1024))], # type: ignore
                temperature=0.0,
                max_tokens=2048,
                verbose=False
            )
            
            # Extract text from GenerationResult
            if hasattr(output, 'text'):
                raw_text = output.text
            else:
                raw_text = str(output)
                if 'GenerationResult(text=' in raw_text:
                    match = re.search(r"text='(.*?)',\s*token=", raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(1)
                        raw_text = raw_text.replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")
            
            if not output:
                return "No text", "", "", None, []
            
            raw_text = '\n'.join([l for l in str(raw_text).split('\n') 
                        if not any(s in l for s in ['image:', 'other:', 'PATCHES', '====', 'BASE:', '%|', 'torch.Size'])]).strip()


            # Clean the output
            clean_text = self._clean_output(raw_text, include_images=True, remove_labels=True)
            markdown = self._clean_output(raw_text, include_images=False, remove_labels=False)
            
            crops = []
            img_out = None
            if has_grounding and "<|ref|>" in raw_text:
                refs = self._extract_grounding_references(raw_text)
                if refs:
                    img_out, crops = self._draw_bounding_boxes(image, refs, True)
            
            # markdown = self._embed_images(markdown, crops)

            return clean_text, markdown, raw_text, img_out, crops
            
        finally:
            # Clean up temp file
            print("")
    
    def parse_pdf(
        self,
        file_path: str,
        output_dir: str | None = None,
        return_md: bool = True,
        return_raw: bool = False,
        start_page: int = 0,
        end_page: int = 99999,
    ) -> Dict[str, Any]:
        """
        Parse a PDF file using DeepSeek OCR.
        
        Args:
            file_path: Path to the PDF file
            output_dir: Output directory for saving results
            return_md: Return markdown content
            return_raw: Return raw OCR output with grounding tags
            start_page: Starting page (0-indexed)
            end_page: Ending page
        
        Returns:
            Dictionary with parsed content
        """
        self._ensure_loaded()

        if not os.path.exists(file_path):
            raise DeepSeekOCRClientError(f"File not found: {file_path}")
        
        if not file_path.lower().endswith('.pdf'):
            raise DeepSeekOCRClientError(f"Only PDF files are supported: {file_path}")
        
        print(f"[DeepSeek OCR] Processing PDF: {file_path}")
        
        # Open PDF
        doc = fitz.open(file_path)
        image_format="PNG"
        texts, markdowns, raws, all_crops = [], [], [], []

        
        # Process pages
        # total_pages = min(len(doc), end_page + 1)
        for i in range(len(doc)):
            print(f"[DeepSeek OCR] Processing page {i + 1}/{len(doc)}")
            if(i>=len(doc)):
                break
            # Get page as image
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(144/72, 144/72), alpha=False)
            img_data = pix.tobytes("png")
            Image.MAX_IMAGE_PIXELS = None

            if image_format.upper() == "PNG":
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
            else:
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
            
            # OCR the page
            clean_text, markdown, raw, _, crops = self._ocr_page(img)
            
            if clean_text and clean_text != "No text":
                texts.append(f"{clean_text}")
                markdowns.append(markdown)
                raws.append(f"{raw}")
                all_crops.extend(crops)
        
        
        # Combine results
        result = {
            "status": "success",
            "pages_processed": len(texts),
            "total_pages": len(doc)
        }
        
        if return_md:
            result["markdown"] = "".join(markdowns) if markdowns else "No text detected in PDF"
        
        if return_raw:
            result["raw"] = "".join(raws) if raws else ""
        
        result["text"] = "".join(texts) if texts else "No text detected in PDF"
        
        # Save to output directory if specified
        if output_dir and texts:
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(file_path).stem
            
            # Save markdown
            if return_md and result.get("markdown"):
                md_path = os.path.join(output_dir, f"{base_name}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(result["markdown"])
                result["markdown_path"] = md_path
                print(f"[DeepSeek OCR] Saved markdown to: {md_path}")
            
            # Save raw output
            if return_raw and result.get("raw"):
                raw_path = os.path.join(output_dir, f"{base_name}_raw.txt")
                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(result["raw"])
                result["raw_path"] = raw_path
        
        doc.close()
        print(f"[DeepSeek OCR] ✓ Completed processing {len(texts)} pages")
        return result
    
    def get_markdown_from_output(self, output_dir: str) -> Optional[str]:
        """
        Extract the markdown content from output directory.
        
        Args:
            output_dir: The output directory path
        
        Returns:
            Markdown content as string, or None if not found
        """
        output_path = Path(output_dir)
        
        if not output_path.exists():
            return None
        
        # Find all .md files
        md_files = [f for f in output_path.rglob("*.md") if f.is_file()]
        if not md_files:
            return None
        
        # Pick the most recently modified .md
        md_file = max(md_files, key=lambda f: f.stat().st_mtime)
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise DeepSeekOCRClientError(f"Failed to read markdown file: {str(e)}")
    
    def parse_and_get_markdown(
        self,
        file_path: str,
        output_dir: str | None = None,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Parse PDF and return markdown content.
        
        Args:
            file_path: Path to PDF file
            output_dir: Output directory (optional)
            **kwargs: Additional arguments for parse_pdf
        
        Returns:
            Tuple of (markdown_content, output_dir_path)
        """
        self._ensure_loaded()

        # Set default output directory
        file_stem = Path(file_path).stem
        if output_dir is None:
            output_dir = str(Path("./output") / file_stem)
        else:
            output_dir = str(DEEPSEEK_OCR_DIR / file_stem)
        
        # Parse the PDF
        result = self.parse_pdf(file_path, output_dir=output_dir, return_md=True, **kwargs)
        
        if "markdown" not in result or not result["markdown"]:
            raise DeepSeekOCRClientError(f"No text extracted from PDF: {file_path}")
        
        return result["markdown"], output_dir