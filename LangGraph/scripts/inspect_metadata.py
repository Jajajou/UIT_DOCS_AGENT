#!/usr/bin/env python3
"""
Inspect temporal metadata in LightRAG PostgreSQL database.

Usage:
    python inspect_metadata.py                    # Show all metadata
    python inspect_metadata.py --doc 108/2024     # Search by doc number
    python inspect_metadata.py --cohort 2020      # Search by cohort
    python inspect_metadata.py --export           # Export to CSV
"""

import psycopg2
import json
import sys
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment
load_dotenv('.env.lightrag')

# Connection config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': os.getenv('POSTGRES_DATABASE', 'lightrag'),
    'user': os.getenv('POSTGRES_USER', 'uitrag'),
    'password': os.getenv('POSTGRES_PASSWORD', 'admin123').strip("'")  # Remove quotes
}

def connect_db():
    """Connect to PostgreSQL."""
    print(f"🔌 Connecting to PostgreSQL @ {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

def print_header(title):
    """Print formatted header."""
    print("\n" + "="*100)
    print(f" {title}")
    print("="*100 + "\n")

def show_schema(cursor):
    """Show temporal_metadata table schema."""
    print_header("TEMPORAL_METADATA TABLE SCHEMA")

    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'temporal_metadata'
        ORDER BY ordinal_position;
    """)

    columns = cursor.fetchall()
    for col_name, data_type, nullable in columns:
        print(f"  {col_name:<30} {data_type:<20} nullable={nullable}")

def show_statistics(cursor):
    """Show document statistics."""
    print_header("DOCUMENT STATISTICS")

    # Total documents in temporal_metadata
    cursor.execute("SELECT COUNT(*) FROM temporal_metadata;")
    total = cursor.fetchone()[0]

    # Documents with specific fields
    cursor.execute("SELECT COUNT(*) FROM temporal_metadata WHERE document_number IS NOT NULL;")
    with_doc_number = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM temporal_metadata WHERE valid_from IS NOT NULL;")
    with_validity = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM temporal_metadata WHERE cohort_years IS NOT NULL OR student_cohorts IS NOT NULL;")
    with_cohorts = cursor.fetchone()[0]

    print(f"  Total documents:          {total:>6}")
    print(f"  With document number:     {with_doc_number:>6}  ({with_doc_number/max(total,1)*100:.1f}%)")
    print(f"  With validity dates:      {with_validity:>6}  ({with_validity/max(total,1)*100:.1f}%)")
    print(f"  With cohort info:         {with_cohorts:>6}  ({with_cohorts/max(total,1)*100:.1f}%)")

def show_all_metadata(cursor, limit=50):
    """Show all documents with metadata."""
    print_header(f"LATEST {limit} DOCUMENTS WITH METADATA")

    cursor.execute(f"""
        SELECT
            tm.id,
            tm.doc_id,
            tm.track_id,
            tm.document_number,
            tm.document_type,
            tm.valid_from,
            tm.valid_until,
            tm.cohort_years,
            tm.student_cohorts,
            tm.amends_documents,
            tm.extraction_method,
            tm.extraction_confidence,
            tm.created_at,
            lds.file_path
        FROM temporal_metadata tm
        LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id AND tm.workspace = lds.workspace
        ORDER BY tm.created_at DESC
        LIMIT {limit};
    """)

    rows = cursor.fetchall()

    if not rows:
        print("❌ No documents with metadata found!")
        return

    for i, row in enumerate(rows, 1):
        (tm_id, doc_id, track_id, doc_number, doc_type, valid_from, valid_until,
         cohort_years, student_cohorts, amends_docs, extraction_method,
         extraction_confidence, created_at, file_path) = row

        print(f"\n{i}. TM ID: {tm_id} | Doc ID: {doc_id}")
        print(f"   Track ID: {track_id}")
        if file_path:
            print(f"   File: {file_path[:80]}..." if len(file_path) > 80 else f"   File: {file_path}")
        print(f"   Created: {created_at}")

        print(f"   📄 Doc Number: {doc_number or 'N/A'}")
        print(f"   📑 Type: {doc_type or 'N/A'}")
        print(f"   📅 Valid: {valid_from or 'N/A'} → {valid_until or 'N/A'}")

        # Show cohorts (parse JSONB)
        cohorts = cohort_years or student_cohorts
        if cohorts:
            cohort_list = cohorts if isinstance(cohorts, list) else json.loads(cohorts) if cohorts else []
            cohort_str = str(cohort_list)[:50] + "..." if len(str(cohort_list)) > 50 else str(cohort_list)
            print(f"   🎓 Cohorts: {cohort_str}")

        print(f"   🔧 Method: {extraction_method or 'N/A'} (confidence: {extraction_confidence or 'N/A'})")

        # Show amends if any
        if amends_docs:
            amends_list = amends_docs if isinstance(amends_docs, list) else json.loads(amends_docs) if amends_docs else []
            print(f"   🔗 Amends: {amends_list}")

        print("   " + "-"*80)

def show_metadata_fields(cursor):
    """Show statistics by metadata field."""
    print_header("METADATA FIELD STATISTICS")

    fields = [
        ('document_number', 'document_number'),
        ('document_type', 'document_type'),
        ('valid_from', 'valid_from'),
        ('valid_until', 'valid_until'),
        ('cohort_years', 'cohort_years'),
        ('student_cohorts', 'student_cohorts'),
        ('amends_documents', 'amends_documents'),
        ('extraction_method', 'extraction_method'),
        ('extraction_confidence', 'extraction_confidence')
    ]

    for field_name, field_col in fields:
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM temporal_metadata
            WHERE {field_col} IS NOT NULL;
        """)
        count = cursor.fetchone()[0]
        print(f"  {field_name:<30} {count:>5} documents")

def show_validity_status(cursor):
    """Show documents by validity status."""
    print_header("VALIDITY STATUS DISTRIBUTION")

    cursor.execute("""
        SELECT
            CASE
                WHEN valid_from IS NULL THEN 'No validity info'
                WHEN valid_from > CURRENT_DATE THEN 'Not yet effective'
                WHEN valid_until IS NULL THEN 'Currently valid (no end date)'
                WHEN valid_until < CURRENT_DATE THEN 'Expired'
                ELSE 'Currently valid'
            END as status,
            COUNT(*) as count
        FROM temporal_metadata
        GROUP BY status
        ORDER BY count DESC;
    """)

    results = cursor.fetchall()
    for status, count in results:
        print(f"  {status:<35} {count:>5}")

def show_extraction_methods(cursor):
    """Show statistics by extraction method."""
    print_header("EXTRACTION METHOD STATISTICS")

    cursor.execute("""
        SELECT
            extraction_method as method,
            COUNT(*) as count,
            AVG(extraction_confidence) as avg_confidence
        FROM temporal_metadata
        WHERE extraction_method IS NOT NULL
        GROUP BY extraction_method
        ORDER BY count DESC;
    """)

    results = cursor.fetchall()
    for method, count, avg_conf in results:
        conf_str = f"{avg_conf:.2f}" if avg_conf is not None else "N/A"
        print(f"  {method:<20} {count:>5} documents  (avg confidence: {conf_str})")

def search_by_doc_number(cursor, doc_number):
    """Search by document number."""
    print_header(f"SEARCH: Document Number = {doc_number}")

    cursor.execute("""
        SELECT
            tm.*,
            lds.file_path
        FROM temporal_metadata tm
        LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id AND tm.workspace = lds.workspace
        WHERE tm.document_number = %s;
    """, (doc_number,))

    row = cursor.fetchone()
    if row:
        print(f"✅ Found!")
        print(f"\nTM ID: {row[0]}")
        print(f"Doc ID: {row[1]}")
        print(f"Track ID: {row[2]}")
        print(f"Workspace: {row[3]}")
        if row[-1]:  # file_path from join
            print(f"File: {row[-1]}")
        print(f"\nDocument Info:")
        print(f"  Number: {row[4]}")
        print(f"  Type: {row[5]}")
        print(f"  Valid From: {row[6]}")
        print(f"  Valid Until: {row[7]}")
        print(f"  Cohort Years: {row[8]}")
        print(f"  Student Cohorts: {row[9]}")
        print(f"  Amends: {row[10]}")
        print(f"  Extraction Method: {row[12]}")
        print(f"  Extraction Confidence: {row[13]}")
        print(f"  Created: {row[16]}")
    else:
        print(f"❌ Document '{doc_number}' not found")

def search_by_cohort(cursor, cohort_year):
    """Search documents for specific cohort."""
    print_header(f"SEARCH: Cohort Year = {cohort_year}")

    # Search in JSONB arrays using @> operator
    cursor.execute("""
        SELECT
            tm.document_number,
            tm.document_type,
            tm.cohort_years,
            tm.student_cohorts,
            tm.valid_from,
            lds.file_path
        FROM temporal_metadata tm
        LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id AND tm.workspace = lds.workspace
        WHERE tm.cohort_years @> %s::jsonb
            OR tm.student_cohorts @> %s::jsonb
        ORDER BY tm.document_number;
    """, (json.dumps([int(cohort_year)]), json.dumps([int(cohort_year)])))

    results = cursor.fetchall()

    if results:
        print(f"✅ Found {len(results)} documents:\n")
        for doc_num, doc_type, cohorts1, cohorts2, valid_from, file_path in results:
            cohorts = cohorts1 or cohorts2
            print(f"  📄 {doc_num} ({doc_type})")
            print(f"     Valid from: {valid_from}")
            print(f"     Cohorts: {cohorts}")
            if file_path:
                print(f"     File: {file_path[:70]}..." if len(file_path) > 70 else f"     File: {file_path}")
            print()
    else:
        print(f"❌ No documents found for cohort {cohort_year}")

def export_to_csv(cursor):
    """Export all metadata to CSV."""
    import csv

    filename = f"temporal_metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    cursor.execute("""
        SELECT
            tm.*,
            lds.file_path
        FROM temporal_metadata tm
        LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id AND tm.workspace = lds.workspace
        ORDER BY tm.created_at DESC;
    """)

    rows = cursor.fetchall()

    # Write CSV
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        header = [
            'id', 'doc_id', 'track_id', 'workspace',
            'document_number', 'document_type',
            'valid_from', 'valid_until',
            'cohort_years', 'student_cohorts',
            'amends_documents', 'amended_by_documents',
            'extraction_method', 'extraction_confidence', 'extraction_timestamp',
            'additional_metadata',
            'created_at', 'updated_at',
            'file_path'
        ]
        writer.writerow(header)

        # Data
        for row in rows:
            # Convert JSONB fields to JSON strings
            row_data = list(row[:-1])  # All except file_path
            for i in [8, 9, 10, 11, 15]:  # JSONB columns
                if row_data[i]:
                    row_data[i] = json.dumps(row_data[i], ensure_ascii=False)
            row_data.append(row[-1])  # Add file_path
            writer.writerow(row_data)

    print(f"✅ Exported {len(rows)} documents to: {filename}")

def main():
    """Main function."""
    # Parse arguments
    args = sys.argv[1:]

    conn = connect_db()
    cursor = conn.cursor()

    try:
        if '--export' in args:
            export_to_csv(cursor)
        elif '--doc' in args:
            idx = args.index('--doc')
            if idx + 1 < len(args):
                doc_number = args[idx + 1]
                search_by_doc_number(cursor, doc_number)
            else:
                print("❌ Error: --doc requires a document number")
        elif '--cohort' in args:
            idx = args.index('--cohort')
            if idx + 1 < len(args):
                cohort = args[idx + 1]
                search_by_cohort(cursor, cohort)
            else:
                print("❌ Error: --cohort requires a year")
        else:
            # Show everything
            show_schema(cursor)
            show_statistics(cursor)
            show_metadata_fields(cursor)
            show_extraction_methods(cursor)
            show_validity_status(cursor)
            show_all_metadata(cursor, limit=20)

            print("\n" + "="*100)
            print("💡 USAGE:")
            print("="*100)
            print("  python inspect_metadata.py                # Show all metadata (this)")
            print("  python inspect_metadata.py --doc 108/2024 # Search by doc number")
            print("  python inspect_metadata.py --cohort 2020  # Search by cohort")
            print("  python inspect_metadata.py --export       # Export to CSV")
            print()

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
