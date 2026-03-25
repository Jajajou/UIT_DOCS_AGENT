#!/bin/bash
# overnight.sh - Full reindex + metadata extraction using Ollama
# Run with: bash overnight.sh > /tmp/overnight.log 2>&1 &

set -e
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate

LOG=/tmp/overnight.log
LANGGRAPH_URL=http://localhost:2024

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ---- 1. Wait for LangGraph to be ready ----
log "Waiting for LangGraph server at $LANGGRAPH_URL..."
for i in $(seq 1 60); do
    if curl -sf "$LANGGRAPH_URL/ok" > /dev/null 2>&1; then
        log "LangGraph is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        log "ERROR: LangGraph not ready after 60s. Aborting."
        exit 1
    fi
    sleep 5
done

# ---- 2. Run full reindex (checkpoint skips already-done files) ----
log "Starting reindex: src/script.py (57 already done, ~117 remaining)..."
python3 src/script.py --root_dir firecrawl/data/daa
REINDEX_EXIT=$?

if [ "$REINDEX_EXIT" -ne 0 ]; then
    log "WARNING: script.py exited with code $REINDEX_EXIT (some files may have failed)"
else
    log "Reindex complete."
fi

# ---- 3. Report LightRAG doc count ----
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM lightrag_doc_full')
total = cur.fetchone()[0]
cur.execute(\"SELECT COUNT(*) FROM lightrag_doc_full WHERE workspace='uit_docs_agent'\")
ws = cur.fetchone()[0]
print(f'[DB] lightrag_doc_full: {total} total, {ws} in workspace')
conn.close()
"

# ---- 4. Clear low-confidence temporal_metadata (will be re-extracted) ----
log "Clearing low-confidence temporal_metadata records (confidence=0.0)..."
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute('DELETE FROM temporal_metadata WHERE extraction_confidence = 0.0')
deleted = cur.rowcount
conn.commit()
cur.close()
conn.close()
print(f'Cleared {deleted} zero-confidence rows')
"

# ---- 5. Run metadata extraction with Ollama ----
log "Running metadata extraction (Ollama qwen2.5:7b)..."
python3 extract_metadata_standalone.py --force

log "ALL DONE."
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM lightrag_doc_full')
print(f'  lightrag_doc_full: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM temporal_metadata')
print(f'  temporal_metadata: {cur.fetchone()[0]}')
cur.execute('SELECT AVG(extraction_confidence), MAX(extraction_confidence) FROM temporal_metadata')
avg, mx = cur.fetchone()
print(f'  avg confidence: {avg:.3f}, max: {mx:.3f}')
conn.close()
"
