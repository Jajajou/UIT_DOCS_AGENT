#!/bin/bash

echo "Running System config (No Routing)..."
USE_METADATA_ROUTING=false langgraph dev --port 2024 > /dev/null 2>&1 &
SERVER_PID=$!
sleep 5
python tests/eval/run_evaluation.py --config System --out tests/eval/res_sys.json
kill $SERVER_PID
sleep 2

echo "Running Full config (With Routing)..."
USE_METADATA_ROUTING=true langgraph dev --port 2024 > /dev/null 2>&1 &
SERVER_PID=$!
sleep 5
python tests/eval/run_evaluation.py --config v0.3.0_Full --out tests/eval/res_v3f.json
kill $SERVER_PID

echo "Combining results..."
python -c '
import json
res = {}
with open("tests/eval/res_sys.json") as f: res.update(json.load(f))
with open("tests/eval/res_v3f.json") as f: res.update(json.load(f))
with open("tests/eval/ablation_results_v033.json", "w") as f: json.dump(res, f, indent=2)
'
echo "Done. Results in ablation_results_v033.json"
