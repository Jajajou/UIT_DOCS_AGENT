
import os
import psycopg2
import json

def patch_amendment_links():
    pg_url = "postgresql://uitrag:admin123@localhost:5433/lightrag"
    conn = psycopg2.connect(pg_url)
    
    try:
        with conn.cursor() as cur:
            # 1. Find discrepancies where a new doc says it amends an old doc, 
            # but the old doc's amended_by_documents is missing the new doc.
            cur.execute("""
                WITH discrepancies AS (
                    SELECT 
                        jsonb_array_elements_text(amends_documents) AS old_doc_num,
                        document_number AS new_doc_num
                    FROM temporal_metadata
                    WHERE amends_documents IS NOT NULL AND jsonb_array_length(amends_documents) > 0
                )
                SELECT 
                    d.old_doc_num,
                    d.new_doc_num
                FROM discrepancies d
                LEFT JOIN temporal_metadata tm ON d.old_doc_num = tm.document_number
                WHERE tm.document_number IS NOT NULL -- only if old doc exists in metadata
                  AND (tm.amended_by_documents IS NULL 
                       OR NOT (tm.amended_by_documents @> jsonb_build_array(d.new_doc_num)));
            """)
            discrepancies = cur.fetchall()
            
            print(f"Found {len(discrepancies)} discrepancies to patch.")
            
            for old_num, new_num in discrepancies:
                print(f"Patching: {old_num} -> amended_by += {new_num}")
                cur.execute("""
                    UPDATE temporal_metadata
                    SET amended_by_documents = CASE
                        WHEN amended_by_documents IS NULL THEN jsonb_build_array(%s)
                        ELSE amended_by_documents || jsonb_build_array(%s)
                    END,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE document_number = %s;
                """, (new_num, new_num, old_num))
            
            # 2. Ensure all docs have at least [] instead of NULL for amended_by_documents
            # This makes the logic more robust.
            cur.execute("""
                UPDATE temporal_metadata
                SET amended_by_documents = '[]'::jsonb
                WHERE amended_by_documents IS NULL;
            """)
            
            conn.commit()
            print("Successfully patched amendment links and normalized NULLs to [].")
            
    except Exception as e:
        print(f"Error during patch: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    patch_amendment_links()
