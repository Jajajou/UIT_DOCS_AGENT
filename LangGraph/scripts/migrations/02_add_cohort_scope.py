#!/usr/bin/env python3
"""Add cohort_scope column to temporal_metadata table."""

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
    'password': os.getenv('POSTGRES_PASSWORD', 'admin123').strip("'")
}

print("🔌 Connecting to PostgreSQL...")
conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Check if column already exists
cursor.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name='temporal_metadata' AND column_name='cohort_scope';
""")
exists = cursor.fetchone()

if exists:
    print("⚠️  Column 'cohort_scope' already exists, skipping...")
else:
    print("➕ Adding 'cohort_scope' column...")
    cursor.execute("""
        ALTER TABLE temporal_metadata
        ADD COLUMN cohort_scope VARCHAR(20);
    """)

    print("📝 Adding comment...")
    cursor.execute("""
        COMMENT ON COLUMN temporal_metadata.cohort_scope IS
        'Cohort scope: "universal" (applies to all students), "explicit" (specific cohorts listed), "unspecified" (unclear from document)';
    """)

    conn.commit()
    print("✓ Column 'cohort_scope' added successfully")

# Show updated schema
print("\n" + "="*80)
print("UPDATED SCHEMA:")
print("="*80)
cursor.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'temporal_metadata'
    ORDER BY ordinal_position;
""")

for col_name, data_type, nullable in cursor.fetchall():
    marker = "🆕" if col_name == "cohort_scope" else "  "
    print(f"{marker} {col_name:<30} {data_type:<20} nullable={nullable}")

cursor.close()
conn.close()

print("\n✓ Schema update complete!")
