import json
import sys

with open(sys.argv[1], 'r') as f:
    data = json.load(f)

for qtype, qlist in data.get('by_type', {}).items():
    for q in qlist:
        if q['id'] == int(sys.argv[2]):
            print(json.dumps(q, indent=2, ensure_ascii=False))
            break
