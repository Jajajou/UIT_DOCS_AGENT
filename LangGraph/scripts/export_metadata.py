import json
import os
import psycopg2
from pathlib import Path

def main():
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5433'),
            database=os.getenv('POSTGRES_DB', 'lightrag'),
            user=os.getenv('POSTGRES_USER', 'lightrag'),
            password=os.getenv('POSTGRES_PASSWORD', 'lightrag123'),
            connect_timeout=5
        )
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    cur = conn.cursor()

    try:
        query = """
            SELECT document_number, doc_id, amends_documents, amended_by_documents, 
                   cohort_years, valid_from, valid_until, document_type
            FROM temporal_metadata
            WHERE document_number IS NOT NULL
        """
        
        cur.execute(query)

        metadata = {}
        for row in cur.fetchall():
            doc_num, doc_id, amends, amended_by, cohorts, v_from, v_until, doc_type = row
            
            # Basic parsing of cohort_years to a list of ints if it's not already
            cohort_list = []
            if cohorts:
                if isinstance(cohorts, list):
                    cohort_list = cohorts
                else:
                    try:
                        cohort_list = json.loads(cohorts)
                    except:
                        cohort_list = [cohorts]
            
            metadata[doc_num] = {
                'doc_id': doc_id,
                'amends_documents': amends if amends else [],
                'amended_by': amended_by if amended_by else [],
                'cohort_years': cohort_list,
                'valid_from': str(v_from) if v_from else None,
                'valid_until': str(v_until) if v_until else None,
                'document_type': doc_type,
                # Simple heuristic for authority level
                'authority_level': 'uit' if ('UIT' in doc_num or 'CNTT' in doc_num) else ('dhqg' if 'ĐHQG' in doc_num else 'bo')
            }

        out_path = Path(__file__).parent.parent / 'tests' / 'eval' / 'eval_metadata_cache.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        print(f"Successfully exported metadata for {len(metadata)} documents to {out_path}")

    except Exception as e:
        print(f"Query failed: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
