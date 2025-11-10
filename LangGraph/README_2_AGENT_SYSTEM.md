# 2-Agent RAG Pipeline với Confidence Scoring

## Tổng quan

Hệ thống RAG nâng cao với 2 agents độc lập, mỗi agent có nhiệm vụ riêng và confidence scoring:

- **Agent 1**: Query Understanding - Phân tích và đánh giá độ hiểu câu hỏi
- **Agent 2**: Data Quality Assessment & Response Generation - Đánh giá chất lượng data và tạo câu trả lời

## Kiến trúc

```
User Query 
    ↓
┌─────────────────────────────────────────┐
│ Agent 1: Query Understanding            │
│ - Parse intention                       │
│ - Extract entities/topics               │
│ - Calculate query confidence (0-1)      │
│ - Decide: clarify or proceed?           │
└─────────────────────────────────────────┘
    ↓
    ├─ [Low Confidence] → Ask Clarification → END
    │
    └─ [High Confidence] → Continue
            ↓
┌─────────────────────────────────────────┐
│ Data Retrieval (LightRAG)               │
│ - Use /query/data endpoint              │
│ - Get entities, relationships, chunks   │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Agent 2: Assessment & Generation        │
│ - Evaluate data quality (0-1)           │
│ - Decide: full/partial/fallback?        │
│ - Generate response with hyperlinks     │
└─────────────────────────────────────────┘
    ↓
Final Answer
```

## Files

```
LangGraph/src/agent/
├── state_v2.py                      # Extended state schema
├── agent1_query_understanding.py    # Agent 1 implementation
├── agent2_response_generation.py    # Agent 2 implementation
└── query_graph_v2.py                # Graph orchestration
```

## State Schema

### Các trường quan trọng được pass giữa agents:

| Field | Source | Used By | Purpose |
|-------|--------|---------|---------|
| `query` | User | Agent 1 | Original query |
| `parsed_intention` | Agent 1 | Retrieval, Agent 2 | Clarified query |
| `extracted_entities` | Agent 1 | Retrieval | Enhance search |
| `extracted_topics` | Agent 1 | Agent 2 | Context for generation |
| `query_confidence` | Agent 1 | Decision, Agent 2 | Quality indicator |
| `needs_clarification` | Agent 1 | Decision | Flow control |
| `retrieved_entities` | Retrieval | Agent 2 | Data for assessment |
| `retrieved_chunks` | Retrieval | Agent 2 | Data for generation |
| `data_quality_score` | Agent 2 | Final | Quality indicator |
| `should_fallback` | Agent 2 | Generation | Response type decision |
| `references` | Agent 2 | Final | Citations with hyperlinks |

## Agent 1: Query Understanding

### Nhiệm vụ

1. Phân tích câu hỏi của user
2. Trích xuất entities và topics
3. Tính confidence score (0.0 - 1.0)
4. Quyết định có cần hỏi lại user không

### Confidence Scoring

**High Confidence (0.8 - 1.0):**
- Query rõ ràng, cụ thể
- Có đủ context
- Entities được xác định rõ

Ví dụ: *"Sinh viên ngành KHMT cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?"*

**Medium Confidence (0.5 - 0.8):**
- Query hơi chung chung nhưng có thể infer
- Thiếu vài chi tiết nhưng không critical

Ví dụ: *"Làm sao để chuyển ngành?"* (thiếu: từ ngành nào sang ngành nào)

**Low Confidence (0.0 - 0.5):**
- Query quá mơ hồ
- Thiếu context quan trọng
- Cần clarification

Ví dụ: *"Làm sao để xin học bổng?"* (không rõ loại học bổng)

### Structured Output

```python
class QueryUnderstanding(BaseModel):
    parsed_intention: str
    extracted_entities: List[str]
    extracted_topics: List[str]
    confidence: float  # 0.0 - 1.0
    confidence_reason: str
    needs_clarification: bool
    clarification_question: Optional[str]
```

### Configuration

```bash
# .env
QUERY_CONFIDENCE_THRESHOLD=0.5  # Below this → ask clarification
AGENT1_TEMPERATURE=0.1          # Low temp for consistent analysis
```

## Data Retrieval

### Endpoint

Sử dụng LightRAG `/query/data` endpoint (KHÔNG phải `/query`):

```python
result = api_client.query_data(
    query_text=parsed_intention,  # From Agent 1
    mode="mix",
    top_k=60
)
```

### Output

```python
{
    "entities": [...],        # Entity data
    "relationships": [...],   # Relationship data
    "chunks": [...]          # Text chunks with file_source
}
```

## Agent 2: Data Quality Assessment & Response Generation

### Phase 1: Data Quality Assessment

**Đánh giá dựa trên:**

1. **Relevance**: Data có liên quan đến query không?
2. **Completeness**: Data có đủ để trả lời không?
3. **Consistency**: Các chunks có mâu thuẫn không?
4. **Recency**: Data có lỗi thời không?
5. **Source Quality**: Nguồn có đáng tin cậy không?

**Quality Scoring:**

- **High (0.7 - 1.0)**: Data đầy đủ, đáng tin cậy → Full answer
- **Medium (0.4 - 0.7)**: Data thiếu một số chi tiết → Partial answer + suggest advisor
- **Low (0.0 - 0.4)**: Data không đủ → Fallback to advisor

**Structured Output:**

```python
class DataQualityAssessment(BaseModel):
    quality_score: float  # 0.0 - 1.0
    quality_reason: str
    coverage: Literal["complete", "partial", "insufficient"]
    should_fallback: bool
    fallback_reason: Optional[str]
```

### Phase 2: Response Generation

**Nếu `should_fallback == True`:**

```
Cảm ơn bạn đã đặt câu hỏi về {topic}.

Dựa trên thông tin hiện có trong hệ thống, tôi chưa thể cung cấp 
câu trả lời đầy đủ và chính xác cho câu hỏi này.

Đề xuất: Vui lòng liên hệ cố vấn học tập hoặc phòng ban liên quan.

Lý do: {fallback_reason}
```

**Nếu `should_fallback == False`:**

Tạo response với:
- Nội dung trả lời dựa trên retrieved data
- Hyperlinks đến tài liệu gốc: `[Tên tài liệu](URL)`
- References list với relevance scores

**Structured Output:**

```python
class ResponseGeneration(BaseModel):
    response_text: str  # With markdown & hyperlinks
    response_type: Literal["full_answer", "partial_answer"]
    references: List[Reference]

class Reference(BaseModel):
    title: str
    url: Optional[str]
    relevance: float
    excerpt: Optional[str]
```

### Configuration

```bash
# .env
DATA_QUALITY_THRESHOLD_HIGH=0.7   # Above → full answer
DATA_QUALITY_THRESHOLD_LOW=0.4    # Below → fallback
AGENT2_ASSESSMENT_TEMP=0.1        # Low temp for assessment
AGENT2_GENERATION_TEMP=0.3        # Higher temp for creative response
```

## Hyperlinks trong Response

Agent 2 tự động thêm hyperlinks vào response:

**Input (từ LightRAG):**
```json
{
  "chunks": [
    {
      "content": "Sinh viên cần tích lũy 140 tín chỉ...",
      "file_source": "https://daa.uit.edu.vn/quy-che-2024.pdf",
      "score": 0.95
    }
  ]
}
```

**Output (response text):**
```markdown
Theo [Quy chế đào tạo 2024](https://daa.uit.edu.vn/quy-che-2024.pdf), 
sinh viên ngành Khoa học Máy tính cần tích lũy tối thiểu **140 tín chỉ** 
để đủ điều kiện tốt nghiệp.
```

## Installation

### 1. Install dependencies

```bash
cd LangGraph
pip install -e .
```

Hoặc:

```bash
pip install openai pydantic langchain-core langgraph
```

### 2. Configure environment

```bash
cp .env.example .env
```

Chỉnh sửa `.env`:

```bash
# LLM Configuration (OpenAI-compatible)
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# LightRAG API
LIGHTRAG_URL=http://localhost:8020
LIGHTRAG_API_KEY=your_lightrag_key

# Agent 1 Configuration
QUERY_CONFIDENCE_THRESHOLD=0.5
AGENT1_TEMPERATURE=0.1

# Agent 2 Configuration
DATA_QUALITY_THRESHOLD_HIGH=0.7
DATA_QUALITY_THRESHOLD_LOW=0.4
AGENT2_ASSESSMENT_TEMP=0.1
AGENT2_GENERATION_TEMP=0.3

# Retrieval Configuration
DEFAULT_RETRIEVAL_MODE=mix
DEFAULT_TOP_K=60
```

## Usage

### 1. Update langgraph.json

Chỉnh sửa `LangGraph/langgraph.json`:

```json
{
  "dependencies": ["."],
  "graphs": {
    "agent": "./src/agent/query_graph_v2.py:graph"
  },
  "env": ".env"
}
```

### 2. Run LangGraph Server

```bash
cd LangGraph
langgraph dev
```

### 3. Test via Chat UI

Truy cập: http://localhost:2024

**Test Case 1: High Confidence Query**

```
User: Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp ngành Khoa học máy tính?
```

Expected flow:
1. Agent 1: High confidence (0.9+) → Proceed
2. Retrieve data from LightRAG
3. Agent 2: High quality (0.8+) → Full answer with hyperlinks

**Test Case 2: Low Confidence Query**

```
User: Làm sao để xin học bổng?
```

Expected flow:
1. Agent 1: Low confidence (0.3) → Ask clarification
2. System: "Bạn muốn hỏi về loại học bổng nào? Ví dụ: học bổng khuyến khích học tập, học bổng tài trợ doanh nghiệp, hay học bổng chính phủ?"

**Test Case 3: Low Data Quality**

```
User: Thủ tục chuyển ngành mới nhất là gì?
```

Expected flow (if only old data available):
1. Agent 1: High confidence → Proceed
2. Retrieve data (old documents from 2020)
3. Agent 2: Low quality (0.3) → Fallback response
4. System: "Vui lòng liên hệ Phòng Đào tạo. Lý do: Thông tin trong hệ thống có thể đã lỗi thời"

### 4. Test via Graph Tab

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?"
    }
  ]
}
```

Hoặc với parameters:

```json
{
  "query": "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?",
  "retrieval_mode": "mix",
  "top_k": 60
}
```

### 5. Test via API

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2024")

# Create thread
thread = await client.threads.create()

# Run graph
run = await client.runs.create(
    thread_id=thread["thread_id"],
    assistant_id="agent",
    input={
        "messages": [
            {
                "role": "user",
                "content": "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?"
            }
        ]
    }
)

# Wait for completion
await client.runs.join(thread_id=thread["thread_id"], run_id=run["run_id"])

# Get state
state = await client.threads.get_state(thread_id=thread["thread_id"])

print(state["values"]["final_answer"])
print(state["values"]["confidence_summary"])
```

## Monitoring & Debugging

### Confidence Summary

Mỗi response đều có `confidence_summary`:

```python
{
  "query_confidence": 0.85,
  "query_confidence_reason": "Query rõ ràng, có đủ context",
  "data_quality_score": 0.9,
  "data_quality_reason": "Data đầy đủ từ quy chế chính thức",
  "data_coverage": "complete",
  "response_type": "full_answer"
}
```

### Logs

Xem logs trong terminal:

```
================================================================================
[AGENT 1] Analyzing query: Sinh viên cần tích lũy bao nhiêu tín chỉ...
================================================================================
[AGENT 1] Parsed Intention: Hỏi về số tín chỉ tối thiểu để tốt nghiệp...
[AGENT 1] Entities: ['Khoa học máy tính', 'tín chỉ tốt nghiệp']
[AGENT 1] Topics: ['quy chế đào tạo', 'điều kiện tốt nghiệp']
[AGENT 1] Confidence: 0.95
[AGENT 1] Reason: Query rất rõ ràng, cụ thể về ngành học...
[AGENT 1] Needs Clarification: False
================================================================================
[DECISION] Confidence: 0.95, Threshold: 0.50
[DECISION] Needs Clarification: False
[DECISION] → retrieve_data
================================================================================
[RETRIEVE] Query: Hỏi về số tín chỉ tối thiểu để tốt nghiệp...
[RETRIEVE] Mode: mix, Top-K: 60
[RETRIEVE] ✓ Retrieved 15 entities, 25 relationships, 8 chunks
================================================================================
[AGENT 2 - ASSESSMENT] Evaluating data quality
[AGENT 2 - ASSESSMENT] Entities: 15, Relationships: 25, Chunks: 8
[AGENT 2 - ASSESSMENT] Quality Score: 0.90
[AGENT 2 - ASSESSMENT] Coverage: complete
[AGENT 2 - ASSESSMENT] Reason: Data đầy đủ từ quy chế chính thức
[AGENT 2 - ASSESSMENT] Should Fallback: False
================================================================================
[AGENT 2 - GENERATION] Generating response (Fallback: False)
[AGENT 2 - GENERATION] Response generated (full_answer)
[AGENT 2 - GENERATION] References: 2
================================================================================
[FINAL] Response Type: full_answer
[FINAL] Query Confidence: 0.95
[FINAL] Data Quality: 0.90
================================================================================
```

## Tuning Thresholds

### Query Confidence Threshold

```bash
QUERY_CONFIDENCE_THRESHOLD=0.5  # Default
```

- **Tăng (0.6-0.7)**: Hệ thống sẽ hỏi lại nhiều hơn → An toàn hơn nhưng có thể phiền user
- **Giảm (0.3-0.4)**: Hệ thống ít hỏi lại → Nhanh hơn nhưng có thể hiểu sai

### Data Quality Thresholds

```bash
DATA_QUALITY_THRESHOLD_HIGH=0.7  # Above → full answer
DATA_QUALITY_THRESHOLD_LOW=0.4   # Below → fallback
```

- **Tăng HIGH (0.8-0.9)**: Chỉ trả lời khi rất chắc chắn → Ít sai nhưng nhiều fallback
- **Giảm LOW (0.2-0.3)**: Chấp nhận data kém hơn → Nhiều câu trả lời nhưng có thể kém chất lượng

## Troubleshooting

### 1. Agent 1 luôn hỏi lại

**Nguyên nhân:** Threshold quá cao hoặc prompt quá strict

**Giải pháp:**
```bash
QUERY_CONFIDENCE_THRESHOLD=0.4  # Giảm threshold
```

### 2. Agent 2 luôn fallback

**Nguyên nhân:** Data quality threshold quá cao hoặc data trong LightRAG kém

**Giải pháp:**
```bash
DATA_QUALITY_THRESHOLD_LOW=0.3  # Giảm threshold
```

Hoặc cải thiện data trong LightRAG (upload thêm tài liệu chính thức)

### 3. Không có hyperlinks trong response

**Nguyên nhân:** Chunks không có `file_source` URL

**Giải pháp:**
- Kiểm tra script upload đã truyền `file_source` chưa
- Xem `indexing_graph.py` dòng 417-428:
  ```python
  url = get_url(file_path)
  result = api_client.insert_text(
      text=parsed_content,
      file_source=url  # ← Phải có URL
  )
  ```

### 4. LLM errors

**Nguyên nhân:** API key sai hoặc model không hỗ trợ structured output

**Giải pháp:**
```bash
# Kiểm tra API key
echo $OPENAI_API_KEY

# Dùng model hỗ trợ structured output
LLM_MODEL=gpt-4o-mini  # hoặc gpt-4o, gpt-4-turbo
```

## Migration từ query_graph.py cũ

### Option 1: Thay thế hoàn toàn

```json
// langgraph.json
{
  "graphs": {
    "agent": "./src/agent/query_graph_v2.py:graph"  // ← Đổi từ query_graph.py
  }
}
```

### Option 2: Chạy song song

```json
// langgraph.json
{
  "graphs": {
    "agent": "./src/agent/query_graph.py:graph",      // Old
    "agent_v2": "./src/agent/query_graph_v2.py:graph" // New
  }
}
```

Test cả 2 versions, sau đó chọn version tốt hơn.

## Next Steps

- [ ] Thêm conversation memory (lưu lịch sử chat)
- [ ] A/B testing giữa query_graph.py và query_graph_v2.py
- [ ] Fine-tune thresholds dựa trên feedback thực tế
- [ ] Thêm logging vào database để phân tích confidence scores
- [ ] Implement reranking cho references
- [ ] Thêm citation inline (footnotes) thay vì chỉ hyperlinks

## Support

Nếu gặp vấn đề:
1. Check logs trong terminal
2. Kiểm tra `confidence_summary` trong state
3. Xem LightRAG có trả về data không
4. Test với các query đơn giản trước

## License

MIT
