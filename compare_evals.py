import json
import sys

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def extract_questions(data):
    questions = {}
    for qtype, qlist in data.get('by_type', {}).items():
        for q in qlist:
            q['qtype'] = qtype
            questions[q['id']] = q
    return questions

def compare(path1, path2):
    d1 = load_json(path1)
    d2 = load_json(path2)
    
    q1 = extract_questions(d1)
    q2 = extract_questions(d2)
    
    degraded = []
    improved = []
    
    for qid, q_after in q2.items():
        if qid in q1:
            q_before = q1[qid]
            acc_before = q_before.get('accuracy@1', 0)
            acc_after = q_after.get('accuracy@1', 0)
            
            if acc_after < acc_before:
                degraded.append((q_before, q_after))
            elif acc_after > acc_before:
                improved.append((q_before, q_after))
                
    print(f"Total questions: {len(q2)}")
    print(f"Degraded (Acc 1 -> 0): {len(degraded)}")
    print(f"Improved (Acc 0 -> 1): {len(improved)}")
    print("\n" + "="*80)
    print("DEGRADED CASES (run4 was correct, run5 was wrong)")
    print("="*80)
    for q1_data, q2_data in degraded:
        print(f"ID: {q1_data['id']} | Type: {q1_data['qtype']}")
        print(f"Query: {q1_data['query']}")
        print(f"Expected Docs: {q1_data.get('expected_doc_numbers')}")
        print(f"Run4 Retrieved: {q1_data.get('retrieved_doc_numbers')}")
        print(f"Run5 Retrieved: {q2_data.get('retrieved_doc_numbers')}")
        print(f"Run4 Response Excerpt:\n{q1_data.get('response_excerpt', '')}")
        print(f"Run5 Response Excerpt:\n{q2_data.get('response_excerpt', '')}")
        print("-" * 80)

if __name__ == "__main__":
    compare(sys.argv[1], sys.argv[2])
