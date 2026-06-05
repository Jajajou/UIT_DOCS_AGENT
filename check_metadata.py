import psycopg2
import json

def check_doc(doc_num):
    try:
        conn = psycopg2.connect(user="uitrag", password="admin123", host="localhost", port=5433, database="lightrag")
        cur = conn.cursor()
        cur.execute("SELECT document_number, indexed_at, valid_from FROM temporal_metadata WHERE document_number ILIKE %s", (f"%{doc_num}%",))
        rows = cur.fetchall()
        for row in rows:
            print(f"Doc {row[0]}: indexed_at={row[1]}, valid_from={row[2]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

docs = ["16/2024/TT-BGDĐT", "364/QĐ-ĐHCNTT", "2130/QĐ-ĐHQG", "108/QĐ-ĐHCNTT"]
for d in docs:
    check_doc(d)
