import json

with open('tests/eval/temporal_test_pairs.json') as f:
    pairs = json.load(f)["pairs"]

# Let's just look at the logs or behavior of v0.3.0_Full
# Wait, we don't have the logs, only the eval results.
# But we can test the exact match logic manually in DB.
