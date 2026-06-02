import importlib.util
import sys
from pathlib import Path

# agent/utils.py is shadowed by this package; load it explicitly
_utils_path = Path(__file__).parent.parent / "utils.py"
_spec = importlib.util.spec_from_file_location("agent._utils_flat", _utils_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

find_urls_by_filename = _mod.find_urls_by_filename
extract_pdf_links = _mod.extract_pdf_links
read_text_from = _mod.read_text_from
get_url = _mod.get_url
normalize_docnum = _mod.normalize_docnum
strip_think_tags = _mod.strip_think_tags
content_to_text = _mod.content_to_text
get_last_human_message = _mod.get_last_human_message
preprocess_image_for_ocr = _mod.preprocess_image_for_ocr
