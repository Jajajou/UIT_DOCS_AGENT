# State Passing Guide: 2-Agent RAG Pipeline (v0.2.0)

## v0.2.0 State Field Changes

These fields were removed in v0.2.0 when Agent 2 was eliminated:
- `data_quality_score` removed (confidence now derived from reranking scores)
- `should_fallback` removed (Agent 3 decides directly based on retrieved data)
- `overall_confidence` removed (no separate assessment pass)
- `needs_clarification` removed (all queries proceed to retrieval)
- `clarification_question` removed (no clarification branch)
- `data_coverage` removed (Agent 3 infers coverage from reranked results)

## Pipeline Overview

Linear 7-node graph:
```
prepare_input -> agent1_understand_query -> retrieve_data ->
enrich_with_temporal_metadata -> rerank_data ->
agent3_generate_response -> format_final_answer
```

## Tong quan

Trong LangGraph, **state passing** giua cac nodes duoc tu dong xu ly thong qua TypedDict state schema. Moi node nhan state hien tai, update cac fields can thiet, va return updated state.

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

    # Retrieval outputs
    retrieved_entities: NotRequired[List[Dict[str, Any]]]
    retrieved_relationships: NotRequired[List[Dict[str, Any]]]
    retrieved_chunks: NotRequired[List[Dict[str, Any]]]

    # Agent 3 outputs
    generated_response: NotRequired[str]
    response_type: NotRequired[str]
    references: NotRequired[List[Dict[str, Any]]]

    # Final
    final_answer: NotRequired[str]
    confidence_summary: NotRequired[Dict[str, Any]]
```

## Flow cua State

### 1. prepare_input

**Input state:**
```python
{
    "messages": [HumanMessage(content="Sinh vien can bao nhieu tin chi?")],
    "query": "Sinh vien can bao nhieu tin chi?"
}
```

### 2. agent1_understand_query

**Agent 1 updates:**
```python
state["parsed_intention"] = "Hoi ve so tin chi tot nghiep"
state["extracted_entities"] = ["tin chi tot nghiep"]
state["extracted_topics"] = ["quy che dao tao"]
state["query_confidence"] = 0.85
```

All queries proceed to retrieval -- there is no clarification branch.

### 3. retrieve_data

**Retrieval node reads:**
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

### 4. enrich_with_temporal_metadata

**Enrichment node reads:**
```python
entities = state.get("retrieved_entities")
chunks = state.get("retrieved_chunks")
```

**Enrichment updates:** Attaches temporal metadata (valid_from, valid_until, cohort_years, amends_documents) to each retrieved item in-place.

### 5. rerank_data

**Reranker reads:**
```python
parsed_intention = state.get("parsed_intention")  # From Agent 1
entities = state.get("retrieved_entities")  # Enriched
chunks = state.get("retrieved_chunks")  # Enriched
```

**Reranker updates:** Re-sorts retrieved items by combined score (semantic + temporal). Items are scored and filtered in-place within the existing state lists.

### 6. agent3_generate_response

**Agent 3 reads:**
```python
# From Agent 1
parsed_intention = state.get("parsed_intention")
query_confidence = state.get("query_confidence")

# From Retrieval + Enrichment + Reranking
entities = state.get("retrieved_entities")
chunks = state.get("retrieved_chunks")
```

**Agent 3 updates:**
```python
state["generated_response"] = "Theo [Quy che...](url)..."
state["response_type"] = "full_answer"
state["references"] = [{"title": "...", "url": "..."}]
```

Agent 3 decides response type directly based on retrieved data quality -- no separate confidence assessment node.

### 7. format_final_answer

**Format node reads:**
```python
generated_response = state.get("generated_response")
response_type = state.get("response_type")
references = state.get("references")
```

**Format node updates:**
```python
state["final_answer"] = formatted_markdown_with_warnings
state["confidence_summary"] = {
    "query_confidence": state.get("query_confidence"),
    "response_type": state.get("response_type")
}
```

## Key Points

### 1. NotRequired Fields

Tat ca fields (tru `messages`) deu la `NotRequired`:
- Khong bat buoc phai co trong initial state
- Nodes co the check `state.get("field")` an toan
- Tra ve `None` neu field chua duoc set

### 2. Type Safety

TypedDict cung cap type hints:
```python
def agent1_understand_query(state: QueryStateV2) -> QueryStateV2:
    # IDE se autocomplete cac fields
    query = state.get("query")
    state["parsed_intention"] = "..."
    return state
```

### 3. Automatic Passing

LangGraph tu dong pass state:
```python
# Khong can manually pass state giua nodes
builder.add_edge("agent1", "retrieval")  # State tu dong pass
```

### 4. State Updates

Nodes co the update bat ky field nao:
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

Field `messages` co special reducer `add_messages`:
```python
messages: Annotated[List[AnyMessage], add_messages]
```

Khi append message:
```python
messages = list(state.get("messages", []))
messages.append(AIMessage(content="..."))
state["messages"] = messages
```

LangGraph se merge messages thay vi replace.

## Example: Complete State Flow

```python
# Initial state
state = {
    "messages": [HumanMessage(content="Sinh vien can bao nhieu tin chi?")]
}

# After prepare_input
state = {
    "messages": [...],
    "query": "Sinh vien can bao nhieu tin chi?"
}

# After agent1_understand_query
state = {
    ...,
    "parsed_intention": "Hoi ve so tin chi tot nghiep",
    "extracted_entities": ["tin chi tot nghiep"],
    "extracted_topics": ["quy che dao tao"],
    "query_confidence": 0.85
}

# After retrieve_data
state = {
    ...,  # Previous fields preserved
    "retrieved_entities": [...],
    "retrieved_relationships": [...],
    "retrieved_chunks": [...]
}

# After enrich_with_temporal_metadata
# (temporal metadata attached to retrieved items in-place)

# After rerank_data
# (retrieved items re-sorted by combined semantic + temporal score)

# After agent3_generate_response
state = {
    ...,  # Previous fields preserved
    "generated_response": "Theo [Quy che...](url)...",
    "response_type": "full_answer",
    "references": [...],
    "messages": [..., AIMessage(content="Theo [Quy che...](url)...")]
}

# After format_final_answer
state = {
    ...,  # All previous fields preserved
    "final_answer": "Theo [Quy che...](url)...",
    "confidence_summary": {
        "query_confidence": 0.85,
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

**State passing trong LangGraph (v0.2.0):**
- Automatic - khong can manually pass
- Type-safe - TypedDict provides hints
- Flexible - nodes chi update fields can thiet
- Preserved - previous fields khong bi mat
- Debuggable - co the inspect state o moi step
- Linear - 7 nodes, no branching, no clarification loops

**Key principle:** Moi node la mot pure function nhan state va return updated state. LangGraph lo viec con lai.
