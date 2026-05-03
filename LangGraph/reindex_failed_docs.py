#!/usr/bin/env python3
"""
Reindex 17 failed documents using existing MinerU OCR output.
"""
import asyncio
from pathlib import Path
from src.agent.graphs.indexing_graph import graph
from langchain_core.messages import HumanMessage

# Failed docs from LightRAG UI
FAILED_DOCS = [
    "de_an.pdf",
    "de_an-ad2c831c.pdf",
    "828_qd-dhcntt_04-10-2022_quy_dinh_dao_tao_ngoai_ngu_doi_voi_he_chinh_qui_khoa_2022_0_0.pdf",
    "560-qd-dhcntt_5-6-2024_sua_doi_quy_dinh_dao_tao_ngoai_ngu_doi_voi_he_dai_hoc_chinh_quy.pdf",
    "53_qd_dhcntt_19_2_2019scan-8b45fc45.pdf",
    "501-qd-dhcntt_7-7-2022_qd_mo_nganh_tri_tue_nhan_tao.pdf",
    "491-qd-dhcntt_21-04-2025_mo_dao_tao_nganh_truyen_thong_da_phuong_tien.pdf",
    "491-qd-dhcntt_21-04-2025_mo_dao_tao_nganh_truyen_thong_da_phuong_tien-f6c586b0.pdf",
    "435-qd-dhcntt_07-07-2021_quy_dinh_dao_tao_chuong_trinh_chat_luong_cao.pdf",
    "364-qd-dhcntt_22-04-2024_sua_doi_quy_dinh_dao_tao_ngoai_ngu.pdf",
    "35-tb-dhcntt_21-5-2019_cong_nhan_chung_chi_tieng_nhat_nat-test_cho_chuan_qua_trinh_0_0.pdf",
    "28_dhcntt_dtdh_22_04_2015.pdf",
    "153-tb-dhcntt13-12-2022_ngung_su_dung_ket_qua_bai_thi_nn_qt_ielts_indicator_va_toefl_ibt_home_edition_0.pdf",
    "1376_qd-dhcntt_28-12-2023_cap_nhat_quy_dinh_to_chuc_thi.pdf",
    "119-tb-dhcntt_19-9-2022_thong_bao_ngung_su_dung_chung_chi_vpet_toeic_bach_khoa_va_phoi_van_bang_moi_0_0.pdf",
    "1141-qd-dhcntt_7-11-2023_quy_dinh_to_chuc_danh_gia_ket_qua_hoc_tap_theo_hinh_thuc_truc_tuyen.pdf",
    "1021-qd-dhcntt4-10-2023_quyet_dinh_mo_nganh.pdf",
]

FIRECRAWL_DATA = Path("/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa")

async def main():
    print(f"Reindexing {len(FAILED_DOCS)} failed documents...")

    for i, filename in enumerate(FAILED_DOCS, 1):
        # Find file in firecrawl data
        matches = list(FIRECRAWL_DATA.rglob(filename))

        if not matches:
            print(f"[{i}/{len(FAILED_DOCS)}] SKIP: {filename} (not found)")
            continue

        file_path = str(matches[0])
        print(f"\n[{i}/{len(FAILED_DOCS)}] Processing: {filename}")
        print(f"  Path: {file_path}")

        # Invoke indexing graph
        try:
            result = await graph.ainvoke({
                "messages": [HumanMessage(content=f"upload {file_path}")]
            })

            upload_results = result.get("upload_results", [])
            if upload_results:
                status = upload_results[0].get("status", "unknown")
                track_id = upload_results[0].get("track_id", "N/A")
                print(f"  Status: {status}, Track ID: {track_id}")
            else:
                print(f"  Status: No upload results")

        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\nDone! Reindexed {len(FAILED_DOCS)} documents.")

if __name__ == "__main__":
    asyncio.run(main())
