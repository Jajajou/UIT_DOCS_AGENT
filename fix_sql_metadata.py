import os
import psycopg2

db_url = "postgresql://uitrag:admin123@localhost:5433/lightrag"

queries = [
    ("UPDATE temporal_metadata SET document_number = '671/ĐHQG-ĐT' WHERE doc_id = 'doc-bb3827f1635e67657bc975af8a489b00';", ()),
    ("UPDATE temporal_metadata SET document_number = '1681/QĐ-ĐHQG' WHERE doc_id = 'doc-75e95d97488ffe01869f552ead853ddc';", ()),
    ("UPDATE temporal_metadata SET amended_by_documents = NULL WHERE doc_id = 'doc-c0f22d558b775d87012022c820cd0e56';", ())
]

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    for q, params in queries:
        cur.execute(q, params)
        print(f"Executed: {q} | Rows affected: {cur.rowcount}")
    conn.commit()
    cur.close()
    conn.close()
    print("Success.")
except Exception as e:
    print(f"Error: {e}")
