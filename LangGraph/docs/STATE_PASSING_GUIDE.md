# State Passing Guide: 2-Agent RAG Pipeline

## Tổng quan

Trong LangGraph, **state passing** giữa các nodes được tự động xử lý thông qua TypedDict state schema. Mỗi node nhận state hiện tại, update các fields cần thiết, và return updated state.

## State Schema

```python
class QueryStateV2(TypedDict):
    # Required
    messages: Annotated[List[AnyMessage], add_messages]
    
    # Agent 1 outputs
    parsed_intention: NotRequired[str]
    extracted_entities: NotRequired[List[str]]
    extracted_topics: NotRequired[List[str]]
    query_confidence: NotRequired[float]
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[str]
    
    # Retrieval outputs
    retrieved_entities: NotRequired[List[Dict[str, Any]]]
    retrieved_relationships: NotRequired[List[Dict[str, Any]]]
    retrieved_chunks: NotRequired[List[Dict[str, Any]]]
    
    # Agent 2 outputs
    data_quality_score: NotRequired[float]
    data_coverage: NotRequired[str]
    should_fallback: NotRequired[bool]
    generated_response: NotRequired[str]
    references: NotRequired[List[Dict[str, Any]]]
    
    # Final
    final_answer: NotRequired[str]
    confidence_summary: NotRequired[Dict[str, Any]]
```

## Flow của State

### 1. User Input → Agent 1

**Input state:**
```python
{
    "messages": [HumanMessage(content="Sinh viên cần bao nhiêu tín chỉ?")],
    "query": "Sinh viên cần bao nhiêu tín chỉ?"
}
```

**Agent 1 updates:**
```python
state["parsed_intention"] = "Hỏi về số tín chỉ tốt nghiệp"
state["extracted_entities"] = ["tín chỉ tốt nghiệp"]
state["extracted_topics"] = ["quy chế đào tạo"]
state["query_confidence"] = 0.85
state["needs_clarification"] = False
```

### 2. Agent 1 → Retrieval

**Retrieval node đọc:**
```python
query = state.get("parsed_intention")  # From Agent 1
entities = state.get("extracted_entities")  # From Agent 1
```

**Retrieval updates:**
```python
state["retrieved_entities"] = [...]
state["retrieved_relationships"] = [...]
state["retrieved_chunks"] = [...]
```

### 3. Retrieval → Agent 2

**Agent 2 đọc:**
```python
# From Agent 1
parsed_intention = state.get("parsed_intention")
query_confidence = state.get("query_confidence")

# From Retrieval
entities = state.get("retrieved_entities")
chunks = state.get("retrieved_chunks")
```

**Agent 2 updates (Phase 1 - Assessment):**
```python
state["data_quality_score"] = 0.9
state["data_coverage"] = "complete"
state["should_fallback"] = False
```

**Agent 2 updates (Phase 2 - Generation):**
```python
state["generated_response"] = "Theo [Quy chế...](url)..."
state["response_type"] = "full_answer"
state["references"] = [{"title": "...", "url": "..."}]
state["final_answer"] = state["generated_response"]
```

## Key Points

### 1. NotRequired Fields

Tất cả fields (trừ `messages`) đều là `NotRequired`:
- Không bắt buộc phải có trong initial state
- Nodes có thể check `state.get("field")` an toàn
- Trả về `None` nếu field chưa được set

### 2. Type Safety

TypedDict cung cấp type hints:
```python
def agent1_understand_query(state: QueryStateV2) -> QueryStateV2:
    # IDE sẽ autocomplete các fields
    query = state.get("query")
    state["parsed_intention"] = "..."
    return state
```

### 3. Automatic Passing

LangGraph tự động pass state:
```python
# Không cần manually pass state giữa nodes
builder.add_edge("agent1", "retrieval")  # State tự động pass
```

### 4. State Updates

Nodes có thể update bất kỳ field nào:
```python
def my_node(state: QueryStateV2) -> QueryStateV2:
    # Read from state
    query = state.get("query")
    
    # Update state
    state["new_field"] = "value"
    
    # Return updated state
    return state
```

### 5. Messages Reducer

Field `messages` có special reducer `add_messages`:
```python
messages: Annotated[List[AnyMessage], add_messages]
```

Khi append message:
```python
messages = list(state.get("messages", []))
messages.append(AIMessage(content="..."))
state["messages"] = messages
```

LangGraph sẽ merge messages thay vì replace.

## Example: Complete State Flow

```python
# Initial state
state = {
    "messages": [HumanMessage(content="Sinh viên cần bao nhiêu tín chỉ?")]
}

# After Agent 1
state = {
    "messages": [...],
    "query": "Sinh viên cần bao nhiêu tín chỉ?",
    "parsed_intention": "Hỏi về số tín chỉ tốt nghiệp",
    "extracted_entities": ["tín chỉ tốt nghiệp"],
    "extracted_topics": ["quy chế đào tạo"],
    "query_confidence": 0.85,
    "needs_clarification": False
}

# After Retrieval
state = {
    ...,  # Previous fields preserved
    "retrieved_entities": [...],
    "retrieved_relationships": [...],
    "retrieved_chunks": [...]
}

# After Agent 2 Assessment
state = {
    ...,  # Previous fields preserved
    "data_quality_score": 0.9,
    "data_coverage": "complete",
    "should_fallback": False
}

# After Agent 2 Generation
state = {
    ...,  # Previous fields preserved
    "generated_response": "Theo [Quy chế...](url)...",
    "response_type": "full_answer",
    "references": [...],
    "final_answer": "Theo [Quy chế...](url)...",
    "messages": [..., AIMessage(content="Theo [Quy chế...](url)...")]
}

# After Format Final
state = {
    ...,  # All previous fields preserved
    "confidence_summary": {
        "query_confidence": 0.85,
        "data_quality_score": 0.9,
        "response_type": "full_answer"
    }
}
```

## Best Practices

### 1. Always use .get() for reading

```python
# Good
query = state.get("query")
confidence = state.get("query_confidence", 0.0)  # With default

# Bad
query = state["query"]  # KeyError if not set
```

### 2. Preserve existing state

```python
# Good - only update needed fields
state["new_field"] = "value"
return state

# Bad - replacing entire state
return {"new_field": "value"}  # Loses all other fields!
```

### 3. Type annotations

```python
# Good
def my_node(state: QueryStateV2) -> QueryStateV2:
    ...

# Bad
def my_node(state):  # No type checking
    ...
```

### 4. Document what each node reads/writes

```python
def agent1_understand_query(state: QueryStateV2) -> QueryStateV2:
    """
    Agent 1: Query Understanding
    
    Reads:
        - query (or messages)
    
    Writes:
        - parsed_intention
        - extracted_entities
        - extracted_topics
        - query_confidence
        - needs_clarification
        - clarification_question (if needed)
    """
    ...
```

## Debugging State

### Print state at each node

```python
def my_node(state: QueryStateV2) -> QueryStateV2:
    print("=" * 80)
    print(f"[MY_NODE] Input state keys: {list(state.keys())}")
    print(f"[MY_NODE] Query: {state.get('query')}")
    print("=" * 80)
    
    # ... process ...
    
    print(f"[MY_NODE] Updated fields: {['field1', 'field2']}")
    return state
```

### Check state in LangGraph Studio

LangGraph Studio shows state at each step:
- Before node execution
- After node execution
- Diff between states

## Common Pitfalls

### 1. Forgetting to return state

```python
# Bad
def my_node(state: QueryStateV2):
    state["field"] = "value"
    # Missing return!

# Good
def my_node(state: QueryStateV2) -> QueryStateV2:
    state["field"] = "value"
    return state
```

### 2. Mutating nested objects

```python
# Bad - mutates original list
messages = state.get("messages", [])
messages.append(...)  # Mutates!

# Good - create new list
messages = list(state.get("messages", []))
messages.append(...)
state["messages"] = messages
```

### 3. Assuming field exists

```python
# Bad - KeyError if not set
confidence = state["query_confidence"]

# Good - safe access
confidence = state.get("query_confidence", 0.0)
```

## Summary

**State passing trong LangGraph:**
- ✅ Automatic - không cần manually pass
- ✅ Type-safe - TypedDict provides hints
- ✅ Flexible - nodes chỉ update fields cần thiết
- ✅ Preserved - previous fields không bị mất
- ✅ Debuggable - có thể inspect state ở mọi step

**Key principle:** Mỗi node là một pure function nhận state và return updated state. LangGraph lo việc còn lại.
