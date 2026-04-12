#!/bin/bash

# LightRAG Performance Monitoring Script for M1 MacBook Pro
# This script monitors key performance metrics during document indexing
# Usage: ./monitor_lightrag_performance.sh [duration_in_seconds]

set -euo pipefail

# Configuration
MONITOR_DURATION=${1:-300}  # Default 5 minutes
SAMPLE_INTERVAL=5  # Sample every 5 seconds
LOG_FILE="/Users/jajajou1778/UIT_DOCS_AGENT/data/performance_metrics_$(date +%Y%m%d_%H%M%S).log"
# Container name patterns (may have project prefix like "uit_docs_agent-")
CONTAINER_LIGHTRAG="lightrag_uit"
CONTAINER_POSTGRES="postgres_uit"
CONTAINER_QDRANT="qdrant_uit"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Initialize log file
echo "LightRAG Performance Monitoring - Started at $(date)" > "$LOG_FILE"
echo "=================================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Function to print colored output
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if container is running
check_container() {
    local container=$1
    # Match container name with optional Docker Compose project prefix and suffix
    # Patterns: "container", "project-container-1", "container-1"
    if docker ps --format '{{.Names}}' | grep -q "${container}"; then
        return 0
    else
        return 1
    fi
}

# Helper function to get actual container name (with Docker Compose prefix/suffix)
get_container_name() {
    local base_name=$1
    # Match container with optional project prefix and suffix
    docker ps --format '{{.Names}}' | grep "${base_name}" | head -n1
}

# Function to get container CPU usage
get_cpu_usage() {
    local container=$1
    local actual_name=$(get_container_name "$container")
    if [ -n "$actual_name" ]; then
        docker stats "$actual_name" --no-stream --format "{{.CPUPerc}}" | sed 's/%//'
    else
        echo "0.0"
    fi
}

# Function to get container memory usage
get_memory_usage() {
    local container=$1
    local actual_name=$(get_container_name "$container")
    if [ -n "$actual_name" ]; then
        docker stats "$actual_name" --no-stream --format "{{.MemUsage}}"
    else
        echo "N/A"
    fi
}

# Function to count timeout errors
count_timeout_errors() {
    local actual_name=$(get_container_name "$CONTAINER_LIGHTRAG")
    if [ -n "$actual_name" ]; then
        docker logs "$actual_name" 2>&1 | grep "TimeoutError" 2>/dev/null | wc -l | tr -d ' '
    else
        echo "0"
    fi
}

# Function to get PostgreSQL connection count
get_postgres_connections() {
    local actual_name=$(get_container_name "$CONTAINER_POSTGRES")
    if [ -n "$actual_name" ]; then
        docker exec "$actual_name" psql -U uitrag -d lightrag -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ' || echo "N/A"
    else
        echo "N/A"
    fi
}

# Function to get document processing rate
get_processing_rate() {
    # Count "Successfully extracted" messages in last 60 seconds
    local actual_name=$(get_container_name "$CONTAINER_LIGHTRAG")
    if [ -n "$actual_name" ]; then
        docker logs "$actual_name" --since 60s 2>&1 | grep "Successfully extracted" 2>/dev/null | wc -l | tr -d ' '
    else
        echo "0"
    fi
}

# Function to check for worker errors
check_worker_errors() {
    local actual_name=$(get_container_name "$CONTAINER_LIGHTRAG")
    if [ -n "$actual_name" ]; then
        docker logs "$actual_name" --since 60s 2>&1 | grep -i "worker.*error" || true
    fi
}

# Startup checks
print_header "LightRAG Performance Monitor - Startup Checks"
echo ""

# Check Docker is running
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker Desktop."
    exit 1
fi
print_success "Docker is running"

# Check containers
for container in "$CONTAINER_LIGHTRAG" "$CONTAINER_POSTGRES" "$CONTAINER_QDRANT"; do
    if check_container "$container"; then
        print_success "Container $container is running"
    else
        print_error "Container $container is not running"
        exit 1
    fi
done

echo ""

# Verify configuration
print_header "Configuration Verification"
echo ""

echo "Checking LightRAG environment variables..."
LIGHTRAG_ACTUAL=$(get_container_name "$CONTAINER_LIGHTRAG")
if [ -n "$LIGHTRAG_ACTUAL" ]; then
    docker exec "$LIGHTRAG_ACTUAL" env 2>/dev/null | grep -E "WORKERS|EMBEDDING_BATCH_NUM|EMBEDDING_FUNC_MAX_ASYNC|EMBEDDING_TIMEOUT|POSTGRES_MAX_CONNECTIONS" | while IFS= read -r line; do
        echo "  $line"
    done
fi

echo ""

# System information
print_header "System Information"
echo ""

echo "M1 CPU Cores: $(sysctl -n hw.ncpu)"
echo "Physical Memory: $(sysctl -n hw.memsize | awk '{printf "%.2f GB", $1/1024/1024/1024}')"
echo "Docker Memory: $(docker system info 2>/dev/null | grep 'Total Memory' | awk '{print $3 $4}')"
echo "Docker CPUs: $(docker system info 2>/dev/null | grep 'CPUs' | awk '{print $2}')"

echo ""

# Initial metrics snapshot
print_header "Initial Metrics Snapshot"
echo ""

echo "Container Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""
echo "PostgreSQL Connections: $(get_postgres_connections) / 32 (max)"
echo "Timeout Errors (total): $(count_timeout_errors)"

echo ""
echo -e "${GREEN}Starting monitoring for $MONITOR_DURATION seconds (sampling every $SAMPLE_INTERVAL seconds)...${NC}"
echo ""

# Monitoring loop
ITERATIONS=$((MONITOR_DURATION / SAMPLE_INTERVAL))
TIMEOUT_ERRORS_START=$(count_timeout_errors)
LIGHTRAG_ACTUAL=$(get_container_name "$CONTAINER_LIGHTRAG")
if [ -n "$LIGHTRAG_ACTUAL" ]; then
    DOCS_START=$(docker logs "$LIGHTRAG_ACTUAL" 2>&1 | grep "Successfully extracted" 2>/dev/null | wc -l | tr -d ' ')
else
    DOCS_START=0
fi

echo "DEBUG: Starting loop with $ITERATIONS iterations..."
echo "DEBUG: DOCS_START=$DOCS_START, TIMEOUT_ERRORS_START=$TIMEOUT_ERRORS_START"
for i in $(seq 1 $ITERATIONS); do
    TIMESTAMP=$(date +%H:%M:%S)

    if [ "$i" -eq 1 ]; then
        echo "DEBUG: First iteration starting..."
    fi

    # Collect metrics
    CPU_LIGHTRAG=$(get_cpu_usage "$CONTAINER_LIGHTRAG")
    CPU_POSTGRES=$(get_cpu_usage "$CONTAINER_POSTGRES")
    CPU_QDRANT=$(get_cpu_usage "$CONTAINER_QDRANT")

    MEM_LIGHTRAG=$(get_memory_usage "$CONTAINER_LIGHTRAG")
    MEM_POSTGRES=$(get_memory_usage "$CONTAINER_POSTGRES")
    MEM_QDRANT=$(get_memory_usage "$CONTAINER_QDRANT")

    PG_CONNECTIONS=$(get_postgres_connections)
    TIMEOUT_ERRORS=$(count_timeout_errors)
    PROCESSING_RATE=$(get_processing_rate)

    # Calculate new timeouts since start
    NEW_TIMEOUTS=$((TIMEOUT_ERRORS - TIMEOUT_ERRORS_START))

    # Log to file
    echo "[$TIMESTAMP] LightRAG CPU: $CPU_LIGHTRAG% | Mem: $MEM_LIGHTRAG | PG Conn: $PG_CONNECTIONS | Rate: $PROCESSING_RATE docs/min | Timeouts: $NEW_TIMEOUTS" >> "$LOG_FILE"

    # Display progress
    printf "\r[%02d/%02d] %s | CPU: LR=%3s%% PG=%3s%% QD=%3s%% | PG Conn: %2s/32 | Rate: %2s docs/min | Timeouts: %3s " \
        "$i" "$ITERATIONS" "$TIMESTAMP" \
        "$CPU_LIGHTRAG" "$CPU_POSTGRES" "$CPU_QDRANT" \
        "$PG_CONNECTIONS" "$PROCESSING_RATE" "$NEW_TIMEOUTS"

    # Check for warnings
    if [ "$NEW_TIMEOUTS" -gt 0 ]; then
        echo "" # New line
        print_warning "Timeout error detected! Total: $NEW_TIMEOUTS"
        if [ -n "$LIGHTRAG_ACTUAL" ]; then
            docker logs "$LIGHTRAG_ACTUAL" --tail 10 2>&1 | grep -i "timeout" >> "$LOG_FILE"
        fi
    fi

    # Check if PostgreSQL connections are high
    if [ "$PG_CONNECTIONS" != "N/A" ] && [ "$PG_CONNECTIONS" -gt 28 ]; then
        echo "" # New line
        print_warning "PostgreSQL connections high: $PG_CONNECTIONS/32 (88%+ usage)"
    fi

    # Check worker errors
    WORKER_ERRORS=$(check_worker_errors)
    if [ -n "$WORKER_ERRORS" ]; then
        echo "" # New line
        print_error "Worker errors detected:"
        echo "$WORKER_ERRORS" | head -3
        echo "$WORKER_ERRORS" >> "$LOG_FILE"
    fi

    sleep $SAMPLE_INTERVAL
done

echo "" # New line after progress

# Final metrics
print_header "Monitoring Complete - Final Report"
echo ""

if [ -n "$LIGHTRAG_ACTUAL" ]; then
    DOCS_END=$(docker logs "$LIGHTRAG_ACTUAL" 2>&1 | grep "Successfully extracted" 2>/dev/null | wc -l | tr -d ' ')
else
    DOCS_END=0
fi
DOCS_PROCESSED=$((DOCS_END - DOCS_START))
TIMEOUT_ERRORS_END=$(count_timeout_errors)
TOTAL_NEW_TIMEOUTS=$((TIMEOUT_ERRORS_END - TIMEOUT_ERRORS_START))

echo "Duration: $MONITOR_DURATION seconds"
echo "Documents Processed: $DOCS_PROCESSED"
echo "Processing Rate: $(echo "scale=2; $DOCS_PROCESSED * 60 / $MONITOR_DURATION" | bc) docs/minute"
echo "New Timeout Errors: $TOTAL_NEW_TIMEOUTS"
echo ""

# Final resource usage
echo "Final Container Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""

# Performance assessment
print_header "Performance Assessment"
echo ""

if [ "$TOTAL_NEW_TIMEOUTS" -eq 0 ]; then
    print_success "No timeout errors detected - optimization successful!"
else
    print_error "$TOTAL_NEW_TIMEOUTS timeout errors detected - further tuning needed"
    echo ""
    echo "Recommendations:"
    echo "  1. Increase EMBEDDING_TIMEOUT further (current: 300s)"
    echo "  2. Reduce EMBEDDING_BATCH_NUM if batches are too large"
    echo "  3. Check embedding service logs for bottlenecks"
    echo "  4. Review timeout errors in LightRAG logs"
fi

echo ""

# Calculate average processing rate
AVG_RATE=$(echo "scale=2; $DOCS_PROCESSED * 60 / $MONITOR_DURATION" | bc)
if (( $(echo "$AVG_RATE >= 20" | bc -l) )); then
    print_success "Processing rate is excellent: $AVG_RATE docs/min (target: ≥20)"
elif (( $(echo "$AVG_RATE >= 10" | bc -l) )); then
    print_warning "Processing rate is moderate: $AVG_RATE docs/min (target: ≥20)"
else
    print_error "Processing rate is low: $AVG_RATE docs/min (target: ≥20)"
    echo ""
    echo "Recommendations:"
    echo "  1. Check if embedding service is the bottleneck"
    echo "  2. Increase WORKERS if CPU usage is low (<50%)"
    echo "  3. Increase EMBEDDING_FUNC_MAX_ASYNC for more concurrency"
    echo "  4. Check PostgreSQL/Qdrant performance"
fi

echo ""

# Check CPU utilization
AVG_CPU=$(awk '/LightRAG CPU:/ {sum+=$4; count++} END {if(count>0) print sum/count; else print 0}' "$LOG_FILE" | sed 's/%//')
if (( $(echo "$AVG_CPU >= 60" | bc -l) )); then
    print_success "CPU utilization is good: ${AVG_CPU}% (target: 60-80%)"
elif (( $(echo "$AVG_CPU >= 40" | bc -l) )); then
    print_warning "CPU utilization is moderate: ${AVG_CPU}% (can increase concurrency)"
else
    print_warning "CPU utilization is low: ${AVG_CPU}% (significant headroom available)"
    echo ""
    echo "Recommendations:"
    echo "  1. Increase WORKERS (current: 4, can try: 6)"
    echo "  2. Increase MAX_PARALLEL_INSERT (current: 8, can try: 10)"
    echo "  3. Check if embedding service is the bottleneck"
fi

echo ""

# Log file location
echo -e "${BLUE}Full metrics saved to:${NC} $LOG_FILE"
echo ""

# Suggest next steps
print_header "Next Steps"
echo ""
echo "1. Review full metrics log: cat $LOG_FILE"
echo "2. Check LightRAG logs for errors: docker logs ${LIGHTRAG_ACTUAL:-lightrag_uit} | grep -i error"
POSTGRES_ACTUAL=$(get_container_name "$CONTAINER_POSTGRES")
echo "3. Monitor PostgreSQL performance: docker exec ${POSTGRES_ACTUAL:-postgres_uit} psql -U uitrag -d lightrag -c \"SELECT * FROM pg_stat_activity;\""
echo "4. If performance is good, run long-term test (24 hours)"
echo "5. If issues found, consult: /Users/jajajou1778/UIT_DOCS_AGENT/PERFORMANCE_OPTIMIZATION_M1.md"
echo ""

print_success "Monitoring completed successfully!"
