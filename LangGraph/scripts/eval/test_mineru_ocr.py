"""Quick evaluation of MinerU2.5-Pro on a known-broken DeepSeek-OCR file."""
import asyncio
from pathlib import Path

INPUT_PDF = Path("/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa/quydinh_huongdan/quyche-bogddt/pdf/tt16_bgddt_20-11-2024_sua_doi_bo_sung_tt02_ve_mo_nganh_dao_tao.pdf")
OUTPUT_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/data/MinerU-test/tt16_bgddt")

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Try the high-level pipeline API first (handles PDF rendering internally)
    try:
        from mineru.cli import api_client as _api_client
        import httpx

        form_data = _api_client.build_parse_request_form_data(
            lang_list=["vi"],
            backend="vlm-mlx-engine",
            parse_method="auto",
            formula_enable=False,
            table_enable=True,
            server_url=None,
            start_page_id=0,
            end_page_id=None,
            return_md=True,
            return_images=False,
            response_format_zip=True,
            return_middle_json=False,
            return_model_output=False,
            return_content_list=False,
            return_original_file=False,
        )

        upload_assets = [_api_client.UploadAsset(path=INPUT_PDF, upload_name=INPUT_PDF.name)]

        async with httpx.AsyncClient(timeout=_api_client.build_http_timeout()) as http_client:
            local_server = _api_client.LocalAPIServer()
            base_url = local_server.start()
            await _api_client.wait_for_local_api_ready(http_client, local_server)

            submit = await _api_client.submit_parse_task(
                base_url=base_url,
                upload_assets=upload_assets,
                form_data=form_data,
            )
            await _api_client.wait_for_task_result(http_client, submit, INPUT_PDF.stem)
            result_zip = await _api_client.download_result_zip(http_client, submit, INPUT_PDF.stem)
            _api_client.safe_extract_zip(result_zip, OUTPUT_DIR)
            local_server.stop()

        print(f"Done. Output in {OUTPUT_DIR}")
        for f in sorted(OUTPUT_DIR.rglob("*.md")):
            print(f"  {f}")

    except Exception as e:
        print(f"Pipeline API failed: {e}")
        print("Falling back to page-by-page MLX approach...")
        _fallback_page_by_page()

def _fallback_page_by_page():
    """Fallback: render pages with fitz, run MinerUClient per page."""
    import fitz
    from PIL import Image
    import io
    from mlx_vlm import load as mlx_load
    from mineru_vl_utils import MinerUClient
    from mineru_vl_utils.post_process import json2md

    model, processor = mlx_load("opendatalab/MinerU2.5-Pro-2604-1.2B")
    client = MinerUClient(backend="mlx-engine", model=model, processor=processor, image_analysis=False)

    doc = fitz.open(str(INPUT_PDF))
    pages_md = []
    for i, page in enumerate(doc):
        print(f"Processing page {i+1}/{len(doc)}...")
        pix = page.get_pixmap(dpi=150)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        content_list = client.two_step_extract(img)
        md = json2md(content_list)
        pages_md.append(f"\n\n<!-- Page {i+1} -->\n\n{md}")

    output_md = OUTPUT_DIR / f"{INPUT_PDF.stem}_mineru.md"
    output_md.write_text("\n".join(pages_md), encoding="utf-8")
    print(f"Saved: {output_md}")

if __name__ == "__main__":
    asyncio.run(main())
