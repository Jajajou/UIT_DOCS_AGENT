#!/usr/bin/env python3
"""Check PostgreSQL schema for LightRAG."""

import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env.lightrag")

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    database=os.getenv("POSTGRES_DATABASE", "lightrag")
)

cursor = conn.cursor()

# List all tables
print("=== Available Tables ===")
cursor.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
""")
tables = cursor.fetchall()
for table in tables:
    print(f"  - {table[0]}")

# Show structure of each table
print("\n=== Table Structures ===")
for table in tables:
    table_name = table[0]
    print(f"\nTable: {table_name}")
    cursor.execute(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = '{table_name}'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"  - {col[0]}: {col[1]}")

# Check current workspace and sample data
workspace = os.getenv("WORKSPACE", "default")
print(f"\n=== Current Workspace: {workspace} ===")

# Try to query documents from each table
for table in tables:
    table_name = table[0]
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"\n{table_name}: {count} rows")

        # If it has data, show sample
        if count > 0:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1;")
            sample = cursor.fetchone()
            print(f"  Sample columns: {len(sample)}")
            print(f"  First 3 values: {sample[:min(3, len(sample))]}")
    except Exception as e:
        print(f"\n{table_name}: Error - {str(e)[:100]}")

conn.close()
print("\n✓ Done")
