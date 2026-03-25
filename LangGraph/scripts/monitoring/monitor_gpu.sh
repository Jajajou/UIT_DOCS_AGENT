#!/bin/bash
# Monitor GPU and memory usage on M1 Mac
echo "Monitoring system resources (Press Ctrl+C to stop)..."
while true; do
    clear
    echo "=== System Monitor ==="
    date
    echo ""
    
    echo "Memory Usage:"
    vm_stat | perl -ne '/page size of (\d+)/ and $size=$1; /Pages\s+([^:]+)[^\d]+(\d+)/ and printf("%-16s % 16.2f MB\n", "$1:", $2 * $size / 1048576);'
    echo ""
    
    echo "Docker Containers:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
    
    sleep 5
done
