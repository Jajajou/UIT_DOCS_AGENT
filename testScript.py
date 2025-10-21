import psycopg2

uri = "postgresql://uit:admin%40123@postgres_docs:5433/KB_DOCS"

try:
    conn = psycopg2.connect(uri)
    print("✅ Connection successful!")
    conn.close()
except Exception as e:
    print("❌ Connection failed:", e)