#!/usr/bin/env python3
"""Create temporal_metadata table in PostgreSQL."""

import psycopg2
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

print(f"🔌 Connecting to PostgreSQL...")
print(f"   Host: {DB_CONFIG['host']}")
print(f"   Port: {DB_CONFIG['port']}")
print(f"   Database: {DB_CONFIG['database']}")
print(f"   User: {DB_CONFIG['user']}")

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Verify connection
cursor.execute("SELECT current_database();")
current_db = cursor.fetchone()[0]
print(f"✓ Connected to database: {current_db}")

print("🗑️  Dropping existing table if exists...")
cursor.execute("DROP TABLE IF EXISTS temporal_metadata CASCADE;")

print("📊 Creating temporal_metadata table...")
cursor.execute("""
CREATE TABLE temporal_metadata (
    id SERIAL PRIMARY KEY,

    -- Link to LightRAG documents
    doc_id VARCHAR(255) UNIQUE NOT NULL,
    track_id VARCHAR(255),
    workspace VARCHAR(255) DEFAULT 'default',

    -- Document identification
    document_number VARCHAR(100),
    document_type VARCHAR(100),

    -- Temporal validity
    valid_from DATE,
    valid_until DATE,

    -- Student cohorts
    cohort_years JSONB,
    student_cohorts JSONB,

    -- Document relationships
    amends_documents JSONB,
    amended_by_documents JSONB,

    -- Extraction metadata
    extraction_method VARCHAR(50),
    extraction_confidence FLOAT,
    extraction_timestamp TIMESTAMP,

    -- Additional metadata
    additional_metadata JSONB,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

print("📇 Creating indexes...")
indexes = [
    "CREATE INDEX idx_temporal_doc_id ON temporal_metadata(doc_id);",
    "CREATE INDEX idx_temporal_track_id ON temporal_metadata(track_id);",
    "CREATE INDEX idx_temporal_document_number ON temporal_metadata(document_number);",
    "CREATE INDEX idx_temporal_workspace ON temporal_metadata(workspace);",
    "CREATE INDEX idx_temporal_valid_from ON temporal_metadata(valid_from);",
    "CREATE INDEX idx_temporal_valid_until ON temporal_metadata(valid_until);",
    "CREATE INDEX idx_temporal_cohort_years ON temporal_metadata USING GIN(cohort_years);",
    "CREATE INDEX idx_temporal_student_cohorts ON temporal_metadata USING GIN(student_cohorts);",
    "CREATE INDEX idx_temporal_amends_documents ON temporal_metadata USING GIN(amends_documents);"
]

for idx_sql in indexes:
    cursor.execute(idx_sql)

print("⚙️  Creating trigger function...")
cursor.execute("""
CREATE OR REPLACE FUNCTION update_temporal_metadata_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

print("🔔 Creating trigger...")
cursor.execute("""
CREATE TRIGGER trigger_update_temporal_metadata_timestamp
    BEFORE UPDATE ON temporal_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_temporal_metadata_timestamp();
""")

# Commit changes BEFORE attempting grant (in case grant fails)
conn.commit()
print("✓ Table and indexes committed")

# Grant permissions (skip if role doesn't exist)
try:
    print("🔑 Granting permissions...")
    cursor.execute("GRANT ALL PRIVILEGES ON temporal_metadata TO uitrag;")
    cursor.execute("GRANT USAGE, SELECT ON SEQUENCE temporal_metadata_id_seq TO uitrag;")
    conn.commit()
    print("✓ Permissions granted")
except Exception as e:
    print(f"⚠️  Could not grant permissions: {e}")
    conn.rollback()

# Show table info
print("\n" + "="*80)
print("TABLE SCHEMA:")
print("="*80)
cursor.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'temporal_metadata'
    ORDER BY ordinal_position;
""")

for col_name, data_type, nullable in cursor.fetchall():
    print(f"  {col_name:<30} {data_type:<20} nullable={nullable}")

cursor.close()
conn.close()

print("\n✓ Temporal metadata table created successfully!")
