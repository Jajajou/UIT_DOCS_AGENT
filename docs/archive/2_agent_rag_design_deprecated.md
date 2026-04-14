<!-- Archived at v0.2.0. Replaced by 2-agent pipeline. See CHANGELOG for rationale. -->

# Thiết kế 3-Agent RAG Pipeline với Confidence Scoring

**Last Updated:** 2026-01-04
**Current Phase:** Phase 1.5 COMPLETE (Metadata RAG Subgraph), Phase 2 pending

## Tổng quan kiến trúc

### Flow tổng thể

```
User Query
    ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENT 1: Query Understanding & Tuning                       │
│ - Parse user intention                                      │
│ - Extract key entities/topics                               │
│ - Calculate confidence score (0-1)                          │
│ - Tune retrieval parameters (mode, top_k)                   │
│ - Decision: confident enough to proceed?                    │
└─────────────────────────────────────────────────────────────┘
    ↓
    ├─── [Low Confidence] ──→ Ask Clarification ──→ Loop back
    │
    └─── [High Confidence] ──→ Continue
                ↓
┌─────────────────────────────────────────────────────────────┐
│ Data Retrieval (LightRAG /query/data endpoint)             │
│ - Query với parsed intention                                │
│ - Lấy raw data (entities, relationships, chunks)            │
│ - Fetch temporal metadata from PostgreSQL                   │
│ - KHÔNG generate response                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ ViRanker Reranking + Temporal Scoring                       │
│ - Vietnamese cross-encoder reranking                        │
│ - Temporal scoring: 70% semantic + 30% temporal             │
│ - Penalties for expired/amended documents                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENT 2: Confidence Assessment                              │
│ - Evaluate retrieved data quality                           │
│ - Calculate data confidence score (0-1)                     │
│ - Apply freshness penalties for expired documents           │
│ - Decision: data sufficient to answer?                      │
└─────────────────────────────────────────────────────────────┘
    ↓
    ├─── [Low Data Quality] ──→ Continue with fallback marker
    │
    └─── [High Data Quality] ──→ Continue
                ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENT 3: Response Generation                                │
│ - Generate answer based on confidence level                 │
│ - Full answer (quality >= 0.7)                              │
│ - Partial answer (quality 0.4-0.7)                          │
│ - Fallback (quality < 0.4)                                  │
│ - Add expiration warnings for documents                     │
│ - Format references with hyperlinks                         │
└─────────────────────────────────────────────────────────────┘
    ↓
Final Answer with References
```

### Metadata RAG Subgraph (Indexing Pipeline)

**Mục đích:** Extract temporal metadata từ documents (dates, cohorts, amendments) với độ chính xác cao

**6-Node Workflow:**

```
PDF Document
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. Chunk Document                                            │
│    - Split text: 1024 tokens, 200 overlap                   │
│    - Large chunks for metadata context                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Index to ChromaDB (In-Memory)                            │
│    - Temporary vector database                              │
│    - Vietnamese_Embedding_V2 (1024-dim)                     │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Query Metadata Fields                                     │
│    - Query 4 fields: document_number, dates, cohorts,       │
│      amendments                                             │
│    - Bi-encoder retrieval (top-50)                          │
│    - Cross-encoder reranking (ViRanker, top-5)              │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Calculate Confidence                                      │
│    - 40% Completeness (fields extracted)                    │
│    - 40% LLM confidence (extraction quality)                │
│    - 20% Chunk quality (relevance scores)                   │
│    - Rating: 0.9+ Excellent, 0.7-0.9 Good, <0.5 Low         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Format & Validate Metadata                               │
│    - Pydantic DocumentMetadata model                        │
│    - Date format validation (YYYY-MM-DD)                    │
│    - Cohort year expansion (2024-2028 → [2024,2025,...])    │
│    - Temporal awareness with current_date                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Cleanup                                                   │
│    - Delete temporary ChromaDB collection                   │
└─────────────────────────────────────────────────────────────┘
    ↓
Save to PostgreSQL (lightrag_doc_status)
```

**Performance:** 0.92 confidence trên test documents (Vietnamese university regulations)

**Metadata Fields:**
- `document_number`: Official ID (e.g., "108/QĐ-ĐHCNTT")
- `valid_from`, `valid_until`: Validity period (YYYY-MM-DD)
- `academic_year`: Academic year (e.g., "2024-2025")
- `cohort_years`: Student cohorts [2024, 2025, 2026, 2027, 2028]
- `cohort_scope`: "explicit" | "universal" | "unspecified"
- `amends_documents`: Documents this amends (e.g., ["141/QĐ-ĐHCNTT"])
- `temporal_confidence`: Extraction confidence (0-1)

## State Schema - Passing data giữa các Agent

### QueryState (Extended)

```python
from typing import TypedDict, NotRequired, Literal, List, Dict, Any
from langchain_core.messages import AnyMessage

class QueryState(TypedDict):
    """Extended state schema for 2-agent RAG pipeline."""
    
    # ============ Input ============
    messages: NotRequired[List[AnyMessage]]
    query: NotRequired[str]  # Original user query
    
    # ============ Agent 1: Query Understanding ============
    # Output từ Agent 1
    parsed_intention: NotRequired[str]  # Câu query đã được clarify/rephrase
    extracted_entities: NotRequired[List[str]]  # Entities quan trọng
    extracted_topics: NotRequired[List[str]]  # Topics chính
    query_confidence: NotRequired[float]  # 0.0 - 1.0
    query_confidence_reason: NotRequired[str]  # Lý do confidence score
    
    # Decision từ Agent 1
    needs_clarification: NotRequired[bool]  # True nếu cần hỏi lại user
    clarification_question: NotRequired[str]  # Câu hỏi để clarify
    
    # ============ Data Retrieval ============
    # Parameters cho LightRAG query
    retrieval_mode: NotRequired[Literal["naive", "local", "global", "hybrid", "mix"]]
    top_k: NotRequired[int]
    
    # Raw data từ LightRAG /query/data
    retrieved_entities: NotRequired[List[Dict[str, Any]]]  # Entity data
    retrieved_relationships: NotRequired[List[Dict[str, Any]]]  # Relationship data
    retrieved_chunks: NotRequired[List[Dict[str, Any]]]  # Text chunks
    retrieval_metadata: NotRequired[Dict[str, Any]]  # Metadata (scores, etc.)
    
    # ============ Agent 2: Data Quality & Response ============
    # Assessment từ Agent 2
    data_quality_score: NotRequired[float]  # 0.0 - 1.0
    data_quality_reason: NotRequired[str]  # Lý do score
    data_coverage: NotRequired[str]  # "complete" | "partial" | "insufficient"
    
    # Decision từ Agent 2
    should_fallback: NotRequired[bool]  # True nếu cần fallback
    fallback_reason: NotRequired[str]  # Lý do fallback
    
    # Response generation
    generated_response: NotRequired[str]  # Final response text
    response_type: NotRequired[Literal["full_answer", "partial_answer", "fallback"]]
    
    # References với hyperlinks
    references: NotRequired[List[Dict[str, Any]]]  # [{"title": "...", "url": "...", "relevance": 0.9}]
    
    # ============ Final Output ============
    final_answer: NotRequired[str]  # Formatted final answer
    confidence_summary: NotRequired[Dict[str, Any]]  # Summary of all confidence scores
    
    # ============ Error Handling ============
    error: NotRequired[str]
    status_message: NotRequired[str]
```

## Chi tiết từng Agent

### Agent 1: Query Understanding

**Input:**
- `query` hoặc `messages`

**Processing:**
- Sử dụng LLM để phân tích query
- Structured output với Pydantic model:

```python
class QueryUnderstanding(BaseModel):
    parsed_intention: str = Field(description="Ý định rõ ràng của user")
    extracted_entities: List[str] = Field(description="Các thực thể quan trọng")
    extracted_topics: List[str] = Field(description="Chủ đề chính")
    confidence: float = Field(ge=0.0, le=1.0, description="Độ tự tin hiểu query")
    confidence_reason: str = Field(description="Lý do confidence score")
    needs_clarification: bool = Field(description="Có cần hỏi lại không")
    clarification_question: Optional[str] = Field(description="Câu hỏi clarify nếu cần")
```

**Confidence Scoring Logic:**
- **High (0.8-1.0)**: Query rõ ràng, có đủ context, entities được identify
- **Medium (0.5-0.8)**: Query hơi mơ hồ nhưng có thể infer được
- **Low (0.0-0.5)**: Query không rõ, thiếu context, cần clarification

**Output State Fields:**
- `parsed_intention`
- `extracted_entities`
- `extracted_topics`
- `query_confidence`
- `query_confidence_reason`
- `needs_clarification`
- `clarification_question`

**Conditional Edge:**
```python
if state["query_confidence"] < 0.5 or state["needs_clarification"]:
    return "ask_clarification"
else:
    return "retrieve_data"
```

### Data Retrieval Node

**Input:**
- `parsed_intention` (từ Agent 1)
- `extracted_entities`, `extracted_topics` (để enhance query)

**Processing:**
- Call LightRAG `/query/data` endpoint (KHÔNG phải `/query`)
- Parameters:
  ```python
  payload = {
      "query": state["parsed_intention"],
      "mode": state.get("retrieval_mode", "mix"),
      "top_k": state.get("top_k", 60),
      # Không có response_type vì chỉ lấy data
  }
  ```

**Output State Fields:**
- `retrieved_entities`
- `retrieved_relationships`
- `retrieved_chunks`
- `retrieval_metadata`

### Agent 2: Data Quality Assessment & Response Generation

**Input:**
- `parsed_intention` (từ Agent 1)
- `retrieved_entities`, `retrieved_relationships`, `retrieved_chunks` (từ retrieval)
- `query_confidence` (từ Agent 1, để tham khảo)

**Processing Phase 1: Data Quality Assessment**

Structured output:
```python
class DataQualityAssessment(BaseModel):
    quality_score: float = Field(ge=0.0, le=1.0, description="Chất lượng data")
    quality_reason: str = Field(description="Lý do score")
    coverage: Literal["complete", "partial", "insufficient"] = Field(
        description="Mức độ đầy đủ của data"
    )
    should_fallback: bool = Field(description="Có nên fallback không")
    fallback_reason: Optional[str] = Field(description="Lý do fallback nếu có")
```

**Quality Scoring Factors:**
1. **Relevance**: Retrieved data có liên quan đến query không?
2. **Completeness**: Data có đủ để trả lời đầy đủ không?
3. **Consistency**: Các chunks/entities có mâu thuẫn không?
4. **Recency**: Data có cập nhật không? (nếu có timestamp)
5. **Source Quality**: file_source có tin cậy không?

**Thresholds:**
- `quality_score >= 0.7` → Generate full answer
- `0.4 <= quality_score < 0.7` → Generate partial answer + suggest contact advisor
- `quality_score < 0.4` → Fallback to advisor contact

**Processing Phase 2: Response Generation**

Nếu `should_fallback == False`:

```python
class ResponseGeneration(BaseModel):
    response_text: str = Field(description="Câu trả lời chi tiết")
    response_type: Literal["full_answer", "partial_answer"] = Field(
        description="Loại response"
    )
    references: List[Reference] = Field(description="Tài liệu tham khảo")
    
class Reference(BaseModel):
    title: str = Field(description="Tên document")
    url: Optional[str] = Field(description="URL nếu có")
    relevance: float = Field(ge=0.0, le=1.0, description="Độ liên quan")
    excerpt: Optional[str] = Field(description="Trích dẫn ngắn")
```

**Prompt Template cho Response Generation:**

```python
RESPONSE_GENERATION_PROMPT = """
Bạn là trợ lý tư vấn học tập cho sinh viên UIT.

<user_query>
{parsed_intention}
</user_query>

<retrieved_data>
Entities: {entities}
Relationships: {relationships}
Text Chunks: {chunks}
</retrieved_data>

<data_quality_assessment>
Quality Score: {quality_score}
Coverage: {coverage}
Reason: {quality_reason}
</data_quality_assessment>

<instructions>
1. Dựa vào retrieved data, trả lời câu hỏi của sinh viên một cách chính xác và đầy đủ
2. Trích dẫn nguồn tài liệu bằng cách sử dụng hyperlink markdown: [Tên tài liệu](URL)
3. Nếu data chỉ đủ trả lời một phần (coverage = "partial"), hãy:
   - Trả lời phần có thể trả lời được
   - Ghi chú rõ phần nào chưa đủ thông tin
   - Đề xuất sinh viên liên hệ cố vấn học tập để được hỗ trợ thêm
4. Sử dụng ngôn ngữ chuyên nghiệp, thân thiện
5. Format response rõ ràng, dễ đọc
</instructions>

<output_format>
Trả về JSON với schema ResponseGeneration
</output_format>
"""
```

**Fallback Response Template:**

```python
FALLBACK_RESPONSE = """
Cảm ơn bạn đã đặt câu hỏi về {topic}.

Dựa trên thông tin hiện có trong hệ thống, tôi chưa thể cung cấp câu trả lời đầy đủ và chính xác cho câu hỏi này.

**Đề xuất:**
Để được tư vấn chi tiết và chính xác nhất, bạn vui lòng liên hệ:
- **Cố vấn học tập** của lớp/khoa
- **Phòng Đào tạo** (nếu liên quan đến quy chế, quy trình đào tạo)
- **Phòng Công tác Sinh viên** (nếu liên quan đến học bổng, hoạt động sinh viên)

Lý do: {fallback_reason}
"""
```

**Output State Fields:**
- `data_quality_score`
- `data_quality_reason`
- `data_coverage`
- `should_fallback`
- `fallback_reason`
- `generated_response`
- `response_type`
- `references`

## Graph Structure

```python
from langgraph.graph import StateGraph, END

builder = StateGraph(state_schema=QueryState)

# Nodes
builder.add_node("prepare_input", prepare_input_node)
builder.add_node("agent1_understand_query", agent1_understand_query_node)
builder.add_node("ask_clarification", ask_clarification_node)
builder.add_node("retrieve_data", retrieve_data_node)
builder.add_node("agent2_assess_and_generate", agent2_assess_and_generate_node)
builder.add_node("format_final_answer", format_final_answer_node)

# Edges
builder.set_entry_point("prepare_input")
builder.add_edge("prepare_input", "agent1_understand_query")

# Conditional edge từ Agent 1
builder.add_conditional_edges(
    "agent1_understand_query",
    decide_after_agent1,  # Function returns "ask_clarification" or "retrieve_data"
    {
        "ask_clarification": "ask_clarification",
        "retrieve_data": "retrieve_data"
    }
)

builder.add_edge("ask_clarification", END)  # Wait for user response
builder.add_edge("retrieve_data", "agent2_assess_and_generate")
builder.add_edge("agent2_assess_and_generate", "format_final_answer")
builder.add_edge("format_final_answer", END)

graph = builder.compile()
```

## Conditional Logic Functions

```python
def decide_after_agent1(state: QueryState) -> str:
    """Decide next step after Agent 1."""
    confidence = state.get("query_confidence", 0.0)
    needs_clarification = state.get("needs_clarification", False)
    
    # Threshold có thể config
    CONFIDENCE_THRESHOLD = 0.5
    
    if confidence < CONFIDENCE_THRESHOLD or needs_clarification:
        return "ask_clarification"
    else:
        return "retrieve_data"
```

## Configuration

Các threshold có thể config qua environment variables:

```python
# config.py
QUERY_CONFIDENCE_THRESHOLD = float(os.getenv("QUERY_CONFIDENCE_THRESHOLD", "0.5"))
DATA_QUALITY_THRESHOLD_HIGH = float(os.getenv("DATA_QUALITY_THRESHOLD_HIGH", "0.7"))
DATA_QUALITY_THRESHOLD_LOW = float(os.getenv("DATA_QUALITY_THRESHOLD_LOW", "0.4"))
```

## Example Flow

### Scenario 1: High Confidence Query

**User:** "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp ngành Khoa học máy tính?"

**Agent 1 Output:**
```json
{
  "parsed_intention": "Hỏi về số tín chỉ tốt nghiệp của ngành Khoa học máy tính",
  "extracted_entities": ["Khoa học máy tính", "tín chỉ tốt nghiệp"],
  "extracted_topics": ["quy chế đào tạo", "điều kiện tốt nghiệp"],
  "query_confidence": 0.95,
  "confidence_reason": "Query rõ ràng, có đủ entities và context",
  "needs_clarification": false
}
```

**Retrieved Data:** (từ LightRAG)
- Entities: "Ngành Khoa học máy tính", "Tín chỉ", "Quy chế đào tạo"
- Chunks: Văn bản quy chế về điều kiện tốt nghiệp

**Agent 2 Output:**
```json
{
  "quality_score": 0.9,
  "quality_reason": "Data đầy đủ, rõ ràng từ quy chế chính thức",
  "coverage": "complete",
  "should_fallback": false,
  "response_type": "full_answer",
  "response_text": "Theo [Quy chế đào tạo 2024](https://example.com/quy-che.pdf), sinh viên ngành Khoa học máy tính cần tích lũy tối thiểu 140 tín chỉ để đủ điều kiện tốt nghiệp...",
  "references": [
    {
      "title": "Quy chế đào tạo 2024",
      "url": "https://example.com/quy-che.pdf",
      "relevance": 0.95
    }
  ]
}
```

### Scenario 2: Low Confidence Query

**User:** "Làm sao để xin học bổng?"

**Agent 1 Output:**
```json
{
  "parsed_intention": "Hỏi về quy trình xin học bổng",
  "extracted_entities": ["học bổng"],
  "extracted_topics": ["học bổng"],
  "query_confidence": 0.3,
  "confidence_reason": "Query quá chung chung, không rõ loại học bổng nào (khuyến khích, tài trợ, chính phủ...)",
  "needs_clarification": true,
  "clarification_question": "Bạn muốn hỏi về loại học bổng nào? Ví dụ: học bổng khuyến khích học tập, học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?"
}
```

**Flow:** → Ask clarification → END (wait for user)

### Scenario 3: Low Data Quality

**User:** "Thủ tục chuyển ngành mới nhất là gì?"

**Agent 1:** High confidence (0.85)

**Retrieved Data:** Chỉ có văn bản cũ từ 2020, không có quy trình mới

**Agent 2 Output:**
```json
{
  "quality_score": 0.35,
  "quality_reason": "Chỉ tìm thấy quy trình cũ từ 2020, có thể đã thay đổi",
  "coverage": "insufficient",
  "should_fallback": true,
  "fallback_reason": "Thông tin trong hệ thống có thể đã lỗi thời",
  "response_type": "fallback"
}
```

**Final Response:**
```
Cảm ơn bạn đã đặt câu hỏi về thủ tục chuyển ngành.

Dựa trên thông tin hiện có trong hệ thống, tôi chưa thể cung cấp câu trả lời đầy đủ và chính xác cho câu hỏi này.

**Đề xuất:**
Để được tư vấn chi tiết và chính xác nhất, bạn vui lòng liên hệ:
- Cố vấn học tập của lớp/khoa
- Phòng Đào tạo

Lý do: Thông tin trong hệ thống có thể đã lỗi thời
```

## Summary: State Passing giữa các Agent

| State Field | Source | Used By | Purpose |
|-------------|--------|---------|---------|
| `query` | User input | Agent 1 | Original query |
| `parsed_intention` | Agent 1 → | Retrieval, Agent 2 | Clarified query |
| `extracted_entities` | Agent 1 → | Retrieval | Enhance search |
| `query_confidence` | Agent 1 → | Conditional edge, Agent 2 | Decision making |
| `needs_clarification` | Agent 1 → | Conditional edge | Flow control |
| `retrieved_entities` | Retrieval → | Agent 2 | Data for assessment |
| `retrieved_chunks` | Retrieval → | Agent 2 | Data for generation |
| `data_quality_score` | Agent 2 → | Final formatting | Quality indicator |
| `should_fallback` | Agent 2 → | Final formatting | Response type decision |
| `references` | Agent 2 → | Final formatting | Citations with hyperlinks |

**Key Point:** Mỗi agent output structured data vào state, agent tiếp theo consume data đó để xử lý. LangGraph state management tự động handle việc passing này.
