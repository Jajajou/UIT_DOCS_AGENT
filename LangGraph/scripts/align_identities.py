import re
import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env.lightrag")

def normalize_docnum(v):
    if not v: return None
    v = v.strip().upper()
    v = re.sub(r"[\s_]", "-", v)
    v = re.sub(r"-+", "-", v)
    # Convert common filename patterns to formal ones
    # 131-QD-DHCNTT -> 131/QD-DHCNTT
    v = re.sub(r"^(\d+)-([A-Z]+)-", r"\1/\2-", v)
    # Restore diacritics
    v = v.replace("QD", "QĐ").replace("DHCNTT", "ĐHCNTT").replace("DHQG", "ĐHQG").replace("BGDDT", "BGDĐT")
    return v

def extract_from_filename(filename):
    """Extracts doc number from patterns like 131-qd-dhcntt_..."""
    stem = Path(filename).stem
    # Match starting numbers + type (QD/TB/TT)
    m = re.match(r"^(\d+[-_](?:qd|tb|tt|qd-ttg|nd-cp)[-_][a-z0-9\-]+)", stem, re.I)
    if m:
        raw = m.group(1)
        return normalize_docnum(raw)
    return None

def main():
    conn = psycopg2.connect(
        host="localhost", port=5433,
        user="uitrag", password="admin123", database="lightrag"
    )
    cur = conn.cursor()
    
    print("=== Identity Correction: Filename vs Metadata ===")
    
    cur.execute("""
        SELECT tm.id, tm.document_number, lds.file_path, tm.doc_id
        FROM temporal_metadata tm
        JOIN lightrag_doc_status lds ON tm.doc_id = lds.id
    """)
    rows = cur.fetchall()
    
    corrected = 0
    for rid, current_num, file_path, doc_id in rows:
        filename = file_path.split("/")[-1]
        file_num = extract_from_filename(filename)
        
        if file_num and current_num != file_num:
            # Check if current_num is just a hallucination (e.g. 191 vs 131)
            # If the digits differ, we trust the filename 100%
            print(f"  [FIX] id={doc_id[:8]} | DB: {current_num} | File: {file_num}")
            
            cur.execute(
                "UPDATE temporal_metadata SET document_number = %s, updated_at = NOW() WHERE id = %s",
                (file_num, rid)
            )
            corrected += 1
            
    conn.commit()
    print(f"\nDone. Corrected {corrected} document identities.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
