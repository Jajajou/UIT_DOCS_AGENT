import os
import json
from langchain_core.messages import HumanMessage, SystemMessage
from agent.agents.agent1_query_understanding import agent1_understand_query
from agent.states.query_state import QueryState

def test_agent1_concept_extraction():
    # Test 1: Graduation Requirements in 2022
    state1: QueryState = {
        "messages": [HumanMessage(content="Điều kiện tốt nghiệp năm 2022 như thế nào?")],
        "logs": []
    }
    print("\n--- TEST 1: Graduation Requirements 2022 ---")
    res1 = agent1_understand_query(state1)
    print(f"Concept: {res1.get('concept_id')}")
    print(f"Target Time: {res1.get('target_time')}")
    print(f"Query Type: {res1.get('query_type')}")

    # Test 2: Scholarship criteria
    state2: QueryState = {
        "messages": [HumanMessage(content="Làm sao để nhận học bổng KKHT?")],
        "logs": []
    }
    print("\n--- TEST 2: Scholarship Criteria ---")
    res2 = agent1_understand_query(state2)
    print(f"Concept: {res2.get('concept_id')}")
    print(f"Query Type: {res2.get('query_type')}")

if __name__ == "__main__":
    test_agent1_concept_extraction()
