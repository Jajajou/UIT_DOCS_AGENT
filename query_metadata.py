import os
import psycopg2

db_url = "postgresql://uitrag:admin123@localhost:5433/lightrag"

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT doc_id, document_number, cohort_years, amended_by_documents FROM temporal_metadata WHERE document_number LIKE '141%';")
    rows = cur.fetchall()
    for row in rows:
        print(row)
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
