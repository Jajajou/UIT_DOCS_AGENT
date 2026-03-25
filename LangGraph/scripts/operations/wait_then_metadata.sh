#!/bin/bash
# wait_then_metadata.sh
# Waits for LightRAG background processing to finish, then runs metadata extraction.

set -e
cd /Users/jajajou1778/UIT_DOCS_AGENT
source .venv/bin/activate

LOG=/tmp/overnight.log

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== PHASE 2: Waiting for LightRAG to finish background processing ==="

# Poll until pending + processing = 0
while true; do
    COUNTS=$(python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute(\"SELECT status, COUNT(*) FROM lightrag_doc_status GROUP BY status\")
rows = dict(cur.fetchall())
pending = rows.get('pending', 0)
processing = rows.get('processing', 0)
processed = rows.get('processed', 0)
failed = rows.get('failed', 0)
print(f'{pending} {processing} {processed} {failed}')
conn.close()
")
    PENDING=$(echo $COUNTS | awk '{print $1}')
    PROCESSING=$(echo $COUNTS | awk '{print $2}')
    PROCESSED=$(echo $COUNTS | awk '{print $3}')
    FAILED=$(echo $COUNTS | awk '{print $4}')

    log "LightRAG: pending=$PENDING processing=$PROCESSING processed=$PROCESSED failed=$FAILED"

    if [ "$PENDING" -eq 0 ] && [ "$PROCESSING" -eq 0 ]; then
        log "LightRAG finished. Starting metadata extraction..."
        break
    fi

    # Wait 2 minutes before checking again
    sleep 120
done

# Brief pause to let embedding server cool down
log "Waiting 60s for embedding server to settle..."
sleep 60

# Clear previous 0-confidence records
log "Clearing zero-confidence temporal_metadata rows..."
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute('DELETE FROM temporal_metadata WHERE extraction_confidence = 0.0')
deleted = cur.rowcount
conn.commit()
conn.close()
print(f'Cleared {deleted} zero-confidence rows')
"

# Run standalone metadata extraction
log "Running extract_metadata_standalone.py --force..."
python3 extract_metadata_standalone.py --force

log "=== ALL DONE ==="
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='lightrag', user='uitrag', password='admin123')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM lightrag_doc_full')
print(f'  lightrag_doc_full: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM temporal_metadata')
print(f'  temporal_metadata: {cur.fetchone()[0]}')
cur.execute('SELECT ROUND(AVG(extraction_confidence)::numeric, 3), ROUND(MAX(extraction_confidence)::numeric, 3), COUNT(*) FILTER (WHERE extraction_confidence > 0.3) FROM temporal_metadata')
avg, mx, good = cur.fetchone()
print(f'  avg confidence: {avg}, max: {mx}, docs with confidence>0.3: {good}')
conn.close()
"
