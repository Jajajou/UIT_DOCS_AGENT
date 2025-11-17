"""
Example usage of Query Flow V3 with Reranker

This script demonstrates how to use the new query flow with reranker.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.query_graph_v3 import graph, QueryStateV3
from langchain_core.messages import HumanMessage


def test_simple_query():
    """Test với query đơn giản."""
    print("=" * 80)
    print("TEST 1: Simple Factual Query")
    print("=" * 80)
    
    initial_state = {
        "messages": [
            HumanMessage(content="Sinh viên ngành Khoa học máy tính cần bao nhiêu tín chỉ để tốt nghiệp?")
        ]
    }
    
    try:
        result = graph.invoke(initial_state)
        
        print("\n[RESULT]")
        print(f"Final Answer: {result.get('final_answer', 'N/A')[:200]}...")
        print(f"\nConfidence Summary:")
        summary = result.get('confidence_summary', {})
        print(f"  - Query Confidence: {summary.get('query_confidence', 0):.2f}")
        print(f"  - Rerank Confidence: {summary.get('rerank_confidence', 0):.2f}")
        print(f"  - Overall Confidence: {summary.get('overall_confidence', 0):.2f}")
        print(f"  - Response Type: {summary.get('response_type', 'N/A')}")
        print(f"  - Retrieval Mode: {summary.get('retrieval_mode', 'N/A')}")
        print(f"  - Top K: {summary.get('top_k', 0)}")
        
        print("\n✅ Test 1 passed!")
        
    except Exception as e:
        print(f"\n❌ Test 1 failed: {str(e)}")
        import traceback
        traceback.print_exc()


def test_ambiguous_query():
    """Test với query mơ hồ (cần clarification)."""
    print("\n" + "=" * 80)
    print("TEST 2: Ambiguous Query (Should Ask Clarification)")
    print("=" * 80)
    
    initial_state = {
        "messages": [
            HumanMessage(content="Làm sao để xin học bổng?")
        ]
    }
    
    try:
        result = graph.invoke(initial_state)
        
        print("\n[RESULT]")
        needs_clarification = result.get('needs_clarification', False)
        clarification_q = result.get('clarification_question', 'N/A')
        
        print(f"Needs Clarification: {needs_clarification}")
        print(f"Clarification Question: {clarification_q}")
        
        if needs_clarification:
            print("\n✅ Test 2 passed! (Correctly asked for clarification)")
        else:
            print("\n⚠️  Test 2 warning: Expected clarification but didn't get one")
        
    except Exception as e:
        print(f"\n❌ Test 2 failed: {str(e)}")
        import traceback
        traceback.print_exc()


def test_complex_query():
    """Test với query phức tạp (multi-aspect)."""
    print("\n" + "=" * 80)
    print("TEST 3: Complex Multi-Aspect Query")
    print("=" * 80)
    
    initial_state = {
        "messages": [
            HumanMessage(content="Tôi muốn biết về học bổng khuyến khích học tập: điều kiện, thủ tục, deadline và số tiền?")
        ]
    }
    
    try:
        result = graph.invoke(initial_state)
        
        print("\n[RESULT]")
        print(f"Final Answer: {result.get('final_answer', 'N/A')[:200]}...")
        
        summary = result.get('confidence_summary', {})
        print(f"\nParameter Tuning:")
        print(f"  - Suggested Mode: {summary.get('retrieval_mode', 'N/A')}")
        print(f"  - Suggested Top K: {summary.get('top_k', 0)}")
        print(f"  - Tuning Reason: {summary.get('tuning_reason', 'N/A')[:100]}...")
        
        print(f"\nConfidence:")
        print(f"  - Overall: {summary.get('overall_confidence', 0):.2f}")
        print(f"  - Response Type: {summary.get('response_type', 'N/A')}")
        
        print("\n✅ Test 3 passed!")
        
    except Exception as e:
        print(f"\n❌ Test 3 failed: {str(e)}")
        import traceback
        traceback.print_exc()


def test_reranker_only():
    """Test reranker module riêng."""
    print("\n" + "=" * 80)
    print("TEST 4: Reranker Module Only")
    print("=" * 80)
    
    try:
        from agent.reranker import create_reranker
        
        print("Loading reranker model...")
        reranker = create_reranker()
        print("✓ Model loaded")
        
        query = "Số tín chỉ tốt nghiệp ngành KHMT?"
        texts = [
            "Sinh viên ngành Khoa học máy tính cần tích lũy 140 tín chỉ để tốt nghiệp",
            "Học bổng khuyến khích học tập dành cho sinh viên có GPA cao",
            "Thủ tục chuyển ngành cần nộp đơn tại phòng đào tạo"
        ]
        
        print(f"\nQuery: {query}")
        print("Texts to rank:")
        for i, text in enumerate(texts, 1):
            print(f"  {i}. {text[:60]}...")
        
        print("\nComputing scores...")
        scores = reranker.compute_scores(query, texts)
        
        print("\nScores:")
        for i, (text, score) in enumerate(zip(texts, scores), 1):
            print(f"  {i}. Score: {score:.4f} - {text[:60]}...")
        
        # Check if scores make sense
        if scores[0] > scores[1] and scores[0] > scores[2]:
            print("\n✅ Test 4 passed! (Correct ranking)")
        else:
            print("\n⚠️  Test 4 warning: Unexpected ranking")
        
    except ImportError as e:
        print(f"\n⚠️  Test 4 skipped: {str(e)}")
        print("Install FlagEmbedding to test reranker: pip install FlagEmbedding")
    except Exception as e:
        print(f"\n❌ Test 4 failed: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("QUERY FLOW V3 - TEST SUITE")
    print("=" * 80)
    
    # Test 4 first (reranker only, doesn't need LightRAG)
    test_reranker_only()
    
    # Tests 1-3 need LightRAG connection
    print("\n" + "=" * 80)
    print("NOTE: Tests 1-3 require LightRAG server running")
    print("If you see connection errors, make sure LightRAG is up")
    print("=" * 80)
    
    test_simple_query()
    test_ambiguous_query()
    test_complex_query()
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
